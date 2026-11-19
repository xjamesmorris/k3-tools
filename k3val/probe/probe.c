// SPDX-License-Identifier: GPL-2.0-only
/*
 * K3 X100 M-mode probe.
 *
 * Reports, over the console UART left configured by the vendor SPL, the
 * entry state and the implementation parameters that the DAMO privileged
 * suite declares per platform. Every CSR access is guarded by the trap
 * handler in probe.S. Writes are limited to WARL probes of registers
 * that do not affect M-mode execution, each restored immediately, plus
 * setting misa.H as the vendor firmware does for X100 harts. It never
 * writes mstatus.MPRV or MBE, a PMP lock bit, or the sticky mseccfg
 * MML/MMWP bits; mtvec and mseccfg.RLB are restored at once.
 */

typedef unsigned long u64;
typedef unsigned int u32;

u64 entry_a0, entry_a1;
volatile u64 trap_count, trap_cause, trap_tval;

#ifdef PROBE_QEMU_VIRT
/* Emulator logic check only: QEMU virt UART and CLINT, byte-stride 16550. */
#define UART_BASE 0x10000000UL
#define UART_THR (UART_BASE + 0x0)
#define UART_LSR (UART_BASE + 0x5)
#define CLINT_BASE 0x02000000UL
#else
#define UART_BASE 0xd4017000UL
#define UART_THR (UART_BASE + 0x00)
#define UART_LSR (UART_BASE + 0x14)
#define CLINT_BASE 0xf1810000UL
#endif

static inline u32 mmio_r32(u64 addr)
{
	u32 v = 0;
	asm volatile(".option push\n.option norvc\nlw %0, 0(%1)\n.option pop"
		     : "+r"(v) : "r"(addr) : "memory");
	return v;
}

#ifdef PROBE_QEMU_VIRT
static void putc_raw(char c)
{
	volatile unsigned char *lsr = (volatile unsigned char *)UART_LSR;
	while (!(*lsr & 0x20))
		;
	*(volatile unsigned char *)UART_THR = (unsigned char)c;
}
#endif

static inline void mmio_w32(u64 addr, u32 v)
{
	asm volatile(".option push\n.option norvc\nsw %0, 0(%1)\n.option pop"
		     :: "r"(v), "r"(addr) : "memory");
}

#ifndef PROBE_QEMU_VIRT
static void putc_raw(char c)
{
	while (!(mmio_r32(UART_LSR) & 0x20))
		;
	mmio_w32(UART_THR, (u32)(unsigned char)c);
}
#endif

static void puts_(const char *s)
{
	for (; *s; s++) {
		if (*s == '\n')
			putc_raw('\r');
		putc_raw(*s);
	}
}

static void puthex(u64 v)
{
	static const char d[] = "0123456789abcdef";
	char b[19];
	b[0] = '0';
	b[1] = 'x';
	for (int i = 0; i < 16; i++)
		b[2 + i] = d[(v >> (60 - 4 * i)) & 0xf];
	b[18] = 0;
	puts_(b);
}

static void line(const char *kind, const char *name, int ok, u64 a, int two, u64 b)
{
	puts_("K3P ");
	puts_(kind);
	puts_(" ");
	puts_(name);
	puts_(ok ? " ok " : " trap ");
	puthex(a);
	if (two) {
		puts_(" ");
		puthex(b);
	}
	if (!ok) {
		puts_(" cause=");
		puthex(trap_cause);
	}
	puts_("\n");
}

#define READ(csr, name)                                                      \
	do {                                                                 \
		u64 v_ = 0, t_ = trap_count;                                 \
		asm volatile("csrr %0, " #csr : "+r"(v_)::"memory");         \
		line("csr", name, trap_count == t_, v_, 0, 0);               \
	} while (0)

/* Read, write a probe value, read back, then restore the original. */
#define WARL(csr, name, w)                                                   \
	do {                                                                 \
		u64 o_ = 0, r_ = 0, w_ = (w), t_ = trap_count;               \
		asm volatile("csrr %0, " #csr "\n\tcsrw " #csr ", %2\n\t"     \
			     "csrr %1, " #csr "\n\tcsrw " #csr ", %0"         \
			     : "+r"(o_), "+r"(r_) : "r"(w_) : "memory");     \
		line("warl", name, trap_count == t_, o_, 1, r_);             \
	} while (0)

#define CASE_R(n)                                                            \
	case n:                                                              \
		asm volatile("csrr %0, " #n : "+r"(v)::"memory");            \
		break;
#define CASE_W(n)                                                            \
	case n:                                                              \
		asm volatile("csrw " #n ", %0" ::"r"(v) : "memory");         \
		break;
#define PMPADDR_CASES(X)                                                     \
	X(0x3b0) X(0x3b1) X(0x3b2) X(0x3b3) X(0x3b4) X(0x3b5) X(0x3b6)       \
	X(0x3b7) X(0x3b8) X(0x3b9) X(0x3ba) X(0x3bb) X(0x3bc) X(0x3bd)       \
	X(0x3be) X(0x3bf) X(0x3c0) X(0x3c1) X(0x3c2) X(0x3c3) X(0x3c4)       \
	X(0x3c5) X(0x3c6) X(0x3c7) X(0x3c8) X(0x3c9) X(0x3ca) X(0x3cb)       \
	X(0x3cc) X(0x3cd) X(0x3ce) X(0x3cf) X(0x3d0) X(0x3d1) X(0x3d2)       \
	X(0x3d3) X(0x3d4) X(0x3d5) X(0x3d6) X(0x3d7) X(0x3d8) X(0x3d9)       \
	X(0x3da) X(0x3db) X(0x3dc) X(0x3dd) X(0x3de) X(0x3df) X(0x3e0)       \
	X(0x3e1) X(0x3e2) X(0x3e3) X(0x3e4) X(0x3e5) X(0x3e6) X(0x3e7)       \
	X(0x3e8) X(0x3e9) X(0x3ea) X(0x3eb) X(0x3ec) X(0x3ed) X(0x3ee)       \
	X(0x3ef)
#define PMPCFG_CASES(X)                                                      \
	X(0x3a0) X(0x3a2) X(0x3a4) X(0x3a6) X(0x3a8) X(0x3aa) X(0x3ac)       \
	X(0x3ae)

static u64 csr_read(int n, int *ok)
{
	u64 v = 0, t = trap_count;
	switch (n) {
	PMPADDR_CASES(CASE_R)
	PMPCFG_CASES(CASE_R)
	default:
		*ok = 0;
		return 0;
	}
	*ok = trap_count == t;
	return v;
}

static int csr_write(int n, u64 v)
{
	u64 t = trap_count;
	switch (n) {
	PMPADDR_CASES(CASE_W)
	default:
		return 0;
	}
	return trap_count == t;
}

static void probe_pmp(void)
{
	u64 cfg[8];
	int ok, implemented = 0;

	for (int i = 0; i < 8; i++) {
		cfg[i] = csr_read(0x3a0 + 2 * i, &ok);
		line("csr", "pmpcfg", ok, cfg[i], 1, (u64)(2 * i));
	}
	for (int e = 0; e < 64; e++) {
		u64 c = (cfg[e / 8] >> (8 * (e % 8))) & 0xff;
		u64 orig = csr_read(0x3b0 + e, &ok), rb = 0;
		int w = 0;

		if (ok && !(c & 0x80)) {
			w = csr_write(0x3b0 + e, ~0UL);
			rb = csr_read(0x3b0 + e, &ok);
			csr_write(0x3b0 + e, orig);
		}
		if (rb)
			implemented = e + 1;
		puts_("K3P pmp ");
		puthex((u64)e);
		puts_(" cfg=");
		puthex(c);
		puts_(" addr=");
		puthex(orig);
		puts_(w ? " rb=" : " rb(not-written)=");
		puthex(rb);
		puts_("\n");
	}
	puts_("K3P pmp-entries ");
	puthex((u64)implemented);
	puts_("\n");
}

static void probe_paging(void)
{
	static const u64 modes[] = { 8, 9, 10 };
	for (int i = 0; i < 3; i++) {
		u64 w = (modes[i] << 60) | (0xffffUL << 44);
		WARL(0x180, "satp-mode", w);
		WARL(0x680, "hgatp-mode", w);
		WARL(0x280, "vsatp-mode", w);
	}
}

static void probe_aia(void)
{
	static const u64 sels[] = { 0x30, 0x70, 0x72, 0x80, 0xc0 };
	u64 orig = 0, t = trap_count;
	asm volatile("csrr %0, 0x350" : "+r"(orig)::"memory");
	if (trap_count != t) {
		line("csr", "miselect", 0, 0, 0, 0);
		return;
	}
	for (int i = 0; i < 5; i++) {
		u64 v = 0;
		t = trap_count;
		asm volatile("csrw 0x350, %1\n\tcsrr %0, 0x351"
			     : "+r"(v) : "r"(sels[i]) : "memory");
		line("mireg", "sel", trap_count == t, sels[i], 1, v);
	}
	asm volatile("csrw 0x350, %0" ::"r"(orig) : "memory");
}

static void probe_vector_fp(void)
{
	u64 ms = 0;
	asm volatile("csrr %0, mstatus" : "=r"(ms));
	asm volatile("csrs mstatus, %0" ::"r"((1UL << 9) | (1UL << 13)) : "memory");
	READ(0xc22, "vlenb");
	READ(0xc20, "vl");
	READ(0xc21, "vtype");
	READ(0x008, "vstart");
	READ(0x00f, "vcsr");
	READ(0x003, "fcsr");
	asm volatile("csrw mstatus, %0" ::"r"(ms) : "memory");
}

static void probe_clint(void)
{
	u64 t0 = 0, t1 = 0;
	asm volatile("csrr %0, 0xc01" : "+r"(t0)::"memory");
	u32 lo = mmio_r32(CLINT_BASE + 0xbff8), hi = mmio_r32(CLINT_BASE + 0xbffc);
	asm volatile("csrr %0, 0xc01" : "+r"(t1)::"memory");
	puts_("K3P clint mtime ");
	puthex(((u64)hi << 32) | lo);
	puts_(" time-before ");
	puthex(t0);
	puts_(" time-after ");
	puthex(t1);
	puts_("\nK3P clint mtimecmp0 ");
	puthex(((u64)mmio_r32(CLINT_BASE + 0x4004) << 32) | mmio_r32(CLINT_BASE + 0x4000));
	puts_(" msip0 ");
	puthex(mmio_r32(CLINT_BASE));
	puts_(" traps ");
	puthex(trap_count);
	puts_("\n");
}

static void probe_ram(void)
{
	static const u64 addrs[] = { 0x100800000UL, 0x10fff0000UL };
	for (int i = 0; i < 2; i++) {
		volatile u64 *p = (volatile u64 *)addrs[i];
		u64 pat = 0x5a5a00000000a5a5UL ^ addrs[i];
		*p = pat;
		puts_("K3P ram ");
		puthex(addrs[i]);
		puts_(*p == pat ? " ok\n" : " MISMATCH\n");
	}
}

static void probe_vendor(void)
{
	READ(0x7c0, "msetup");
	READ(0x7c1, "mhcr");
	READ(0x7c5, "mhint");
	READ(0x7f0, "ml2setup");
	READ(0x7f7, "ml2hint");
	READ(0x7d0, "perf_ctrl");
	READ(0x7d1, "prefetch_ctrl");
	READ(0x5db, "tcmcfg");
	READ(0x7de, "pmacfg0");
	READ(0x7df, "pmacfg2");
	READ(0x7e0, "pmaaddr0");
	READ(0x7e1, "pmaaddr1");
	READ(0x7e2, "pmaaddr2");
	READ(0x7e3, "pmaaddr3");
	READ(0x7e4, "pmaaddr4");
	READ(0x7e5, "pmaaddr5");
	READ(0x7e6, "pmaaddr6");
	READ(0x7e7, "pmaaddr7");
	READ(0x7e8, "pmaaddr8");
	READ(0x7e9, "pmaaddr9");
	READ(0x7ea, "pmaaddr10");
	READ(0x7eb, "pmaaddr11");
	READ(0x7ec, "pmaaddr12");
	READ(0x7ed, "pmaaddr13");
	READ(0x7ee, "pmaaddr14");
	READ(0x7ef, "pmaaddr15");
}

static void probe_atomics(void)
{
	static volatile u64 word __attribute__((aligned(64)));
	u64 old = 0, sc = 1, t = trap_count, v;
	word = 40;
	asm volatile(".option push\n.option norvc\namoadd.d %0, %2, (%1)\n.option pop"
		     : "+r"(old) : "r"(&word), "r"(2UL) : "memory");
	v = word;
	puts_("K3P amoadd.d old=");
	puthex(old);
	puts_(" new=");
	puthex(v);
	for (int i = 0; i < 16 && sc; i++) {
		u64 cur = 0;
		asm volatile(".option push\n.option norvc\nlr.d %0, (%2)\nsc.d %1, %3, (%2)\n.option pop"
			     : "+r"(cur), "+r"(sc) : "r"(&word), "r"(7UL) : "memory");
	}
	puts_(" sc.d=");
	puthex(sc);
	puts_(" final=");
	puthex(word);
	puts_(" traps=");
	puthex(trap_count - t);
	puts_("\n");
}

static void probe_hypervisor(void)
{
	READ(0x301, "misa-before-h");
	asm volatile("csrs misa, %0" ::"r"(1UL << 7) : "memory");
	READ(0x301, "misa-after-h");
	READ(0x600, "hstatus");
	READ(0xe12, "hgeip");
	READ(0x605, "htimedelta");
	READ(0x646, "hviprio1");
	READ(0x647, "hviprio2");
	READ(0x24d, "vstimecmp");
	READ(0x25c, "vstopei");
	READ(0xeb0, "vstopi");
	READ(0x250, "vsiselect");
	READ(0x200, "vsstatus");
	READ(0x34a, "mtinst");
	READ(0x34b, "mtval2");
	WARL(0x602, "hedeleg", ~0UL);
	WARL(0x603, "hideleg", ~0UL);
	WARL(0x606, "hcounteren", ~0UL);
	WARL(0x607, "hgeie", ~0UL);
	WARL(0x60a, "henvcfg", ~0UL);
	WARL(0x60c, "hstateen0", ~0UL);
	WARL(0x609, "hvictl", ~0UL);
	WARL(0x608, "hvien", ~0UL);
	WARL(0x302, "medeleg-h", ~0UL);
	WARL(0x303, "mideleg-h", ~0UL);
	WARL(0x304, "mie-h", ~0UL);
	WARL(0x30a, "menvcfg-h", ~0UL);
	WARL(0x30c, "mstateen0-h", ~0UL);
	static const u64 modes[] = { 8, 9, 10 };
	for (int i = 0; i < 3; i++) {
		u64 w = (modes[i] << 60) | (0xffffUL << 44);
		WARL(0x680, "hgatp-mode", w);
		WARL(0x280, "vsatp-mode", w);
	}
}

static void report_trap(const char *name, u64 t, u64 value)
{
	line("exec", name, trap_count == t, value, 0, 0);
}

static void probe_v3(void)
{
	static volatile u64 buf[4] __attribute__((aligned(64)));
	u64 o = 0, r = 0, r2 = 0, t = trap_count;

	/* Smepmp: RLB is settable while no PMP entry is locked; cleared again. */
	asm volatile("csrr %0, 0x747\n\tcsrs 0x747, %3\n\tcsrr %1, 0x747\n\t"
		     "csrc 0x747, %3\n\tcsrr %2, 0x747"
		     : "+r"(o), "+r"(r), "+r"(r2) : "r"(4UL) : "memory");
	puts_("K3P mseccfg-rlb orig=");
	puthex(o);
	puts_(" set=");
	puthex(r);
	puts_(" cleared=");
	puthex(r2);
	puts_(trap_count == t ? " ok\n" : " trap\n");

	WARL(0x321, "mcyclecfg", 0xf8UL << 56);
	WARL(0x322, "minstretcfg", 0xf8UL << 56);

	/* S/U endianness only; never MBE, which would change these accesses. */
	{
		u64 ms0 = 0, ms1 = 0;
		t = trap_count;
		asm volatile("csrr %0, mstatus\n\tcsrs mstatus, %2\n\tcsrr %1, mstatus\n\t"
			     "csrc mstatus, %2"
			     : "+r"(ms0), "+r"(ms1) : "r"((1UL << 36) | (1UL << 6)) : "memory");
		line("warl", "mstatus-sbe-ube", trap_count == t, ms0, 1, ms1);
	}

	/* mtvec vectored mode, restored immediately; no trap can occur between. */
	{
		u64 mt = 0, rb = 0;
		asm volatile("csrr %0, mtvec\n\tori t0, %0, 1\n\tcsrw mtvec, t0\n\t"
			     "csrr %1, mtvec\n\tcsrw mtvec, %0"
			     : "+r"(mt), "+r"(rb) :: "t0", "memory");
		line("warl", "mtvec-vectored", 1, mt, 1, rb);
	}
	WARL(0x105, "stvec-vectored", 0x100000001UL);

	buf[0] = 0x0807060504030201UL;
	buf[1] = 0x100f0e0d0c0b0a09UL;
	t = trap_count;
	r = 0;
	asm volatile(".option push\n.option norvc\nld %0, 0(%1)\n.option pop"
		     : "+r"(r) : "r"((u64)buf + 1) : "memory");
	report_trap("misaligned-ld", t, r);
	t = trap_count;
	asm volatile(".option push\n.option norvc\nsd %0, 0(%1)\n.option pop"
		     :: "r"(0x1111111111111111UL), "r"((u64)buf + 3) : "memory");
	report_trap("misaligned-sd", t, buf[0]);
	t = trap_count;
	r = 0;
	asm volatile(".option push\n.option norvc\nlr.d %0, (%1)\n.option pop"
		     : "+r"(r) : "r"((u64)buf + 4) : "memory");
	report_trap("misaligned-lr.d", t, trap_cause);

	buf[2] = 5;
	t = trap_count;
	r = 5;
	asm volatile(".option push\n.option norvc\n"
		     ".insn r 0x2f, 0x2, 0x14, %0, %1, %2\n.option pop"
		     : "+r"(r) : "r"(&buf[2]), "r"(9UL) : "memory");
	report_trap("amocas.w", t, buf[2]);
	buf[3] = 0x10;
	t = trap_count;
	r = 0;
	asm volatile(".option push\n.option norvc\n"
		     ".insn r 0x2f, 0x0, 0x00, %0, %1, %2\n.option pop"
		     : "+r"(r) : "r"(&buf[3]), "r"(1UL) : "memory");
	report_trap("amoadd.b", t, buf[3]);
}

void probe_main(void)
{
	u64 start = 0, end = 0;
	asm volatile("csrr %0, 0xc01" : "+r"(start)::"memory");
	puts_("\nK3P BEGIN k3-x100-mmode-probe v3\n");
	puts_("K3P entry a0=");
	puthex(entry_a0);
	puts_(" a1=");
	puthex(entry_a1);
	if (entry_a1 >= 0x100000000UL && entry_a1 < 0x300000000UL) {
		u32 m = *(volatile u32 *)entry_a1, sz = *(volatile u32 *)(entry_a1 + 4);
		puts_(" fdt-magic-le=");
		puthex(m);
		puts_(" fdt-size-le=");
		puthex(sz);
	}
	puts_("\n");

	READ(0xf11, "mvendorid");
	READ(0xf12, "marchid");
	READ(0xf13, "mimpid");
	READ(0xf14, "mhartid");
	READ(0xf15, "mconfigptr");
	READ(0x301, "misa");
	READ(0x300, "mstatus");
	READ(0x305, "mtvec");
	READ(0x304, "mie");
	READ(0x344, "mip");
	READ(0x747, "mseccfg");
	READ(0x740, "mnscratch");
	READ(0x321, "mcyclecfg");
	READ(0x34e, "mctrctl");
	READ(0x352, "mireg2");
	READ(0x35c, "mtopei");
	READ(0xfb0, "mtopi");
	READ(0x308, "mvien");
	READ(0x309, "mvip");
	READ(0x7a0, "tselect");
	READ(0x7a1, "tdata1");
	READ(0x7a4, "tinfo");
	READ(0x323, "mhpmevent3");
	READ(0xb00, "mcycle");
	READ(0xb02, "minstret");
	READ(0xc00, "cycle");
	READ(0xc02, "instret");
	READ(0x600, "hstatus");
	READ(0xe12, "hgeip");
	READ(0x605, "htimedelta");
	READ(0x646, "hviprio1");
	READ(0x14d, "stimecmp");
	READ(0x24d, "vstimecmp");
	READ(0x150, "siselect");
	READ(0x15c, "stopei");
	READ(0xdb0, "stopi");
	READ(0xda0, "scountovf");
	READ(0x152, "sireg2");
	READ(0x120, "scountinhibit");
	READ(0x14e, "sctrctl");
	READ(0x181, "srmcfg");
	READ(0x011, "ssp");
	READ(0x017, "jvt");
	READ(0x25c, "vstopei");
	READ(0xeb0, "vstopi");
	{
		u64 v = 0, t = trap_count;
		asm volatile("csrrw %0, 0x015, x0" : "+r"(v)::"memory");
		line("csr", "seed", trap_count == t, v, 0, 0);
	}

	WARL(0x302, "medeleg", ~0UL);
	WARL(0x303, "mideleg", ~0UL);
	WARL(0x304, "mie", ~0UL);
	WARL(0x306, "mcounteren", ~0UL);
	WARL(0x320, "mcountinhibit", ~0UL);
	WARL(0x30a, "menvcfg", ~0UL);
	WARL(0x30c, "mstateen0", ~0UL);
	WARL(0x30d, "mstateen1", ~0UL);
	WARL(0x106, "scounteren", ~0UL);
	WARL(0x10a, "senvcfg", ~0UL);
	WARL(0x10c, "sstateen0", ~0UL);
	WARL(0x602, "hedeleg", ~0UL);
	WARL(0x603, "hideleg", ~0UL);
	WARL(0x606, "hcounteren", ~0UL);
	WARL(0x607, "hgeie", ~0UL);
	WARL(0x60a, "henvcfg", ~0UL);
	WARL(0x60c, "hstateen0", ~0UL);
	WARL(0x609, "hvictl", ~0UL);
	WARL(0x608, "hvien", ~0UL);
	WARL(0x350, "miselect", ~0UL);

	probe_paging();
	probe_vendor();
	probe_atomics();
	probe_hypervisor();
	probe_v3();
	probe_aia();
	probe_vector_fp();
	probe_pmp();
	probe_clint();
	probe_ram();

	asm volatile("csrr %0, 0xc01" : "+r"(end)::"memory");
	puts_("K3P elapsed-ticks ");
	puthex(end - start);
	puts_(" traps ");
	puthex(trap_count);
	puts_("\nK3P DONE\n");
}
