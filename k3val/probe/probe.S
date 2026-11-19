/* SPDX-License-Identifier: GPL-2.0-only */
/* K3 X100 M-mode probe: entry, trap skip handler and park loop. */

	.section .text.init, "ax"
	.globl _start
_start:
	/* SPL enters with a0 = hartid, a1 = its DTB copy; only hart 0 runs. */
	csrr	t0, mhartid
	bnez	t0, park
	csrci	mstatus, 0x8
	csrw	mie, zero
	/* Clear BSS first: entry_a0/a1 and the trap state live there. */
	la	t0, __bss_start
	la	t1, __bss_end
1:	bgeu	t0, t1, 2f
	sd	zero, 0(t0)
	addi	t0, t0, 8
	j	1b
2:	la	t0, entry_a0
	sd	a0, 0(t0)
	la	t0, entry_a1
	sd	a1, 0(t0)
	la	sp, stack_top
	la	t0, trap_save
	csrw	mscratch, t0
	la	t0, trap_entry
	csrw	mtvec, t0
	call	probe_main
park:
	wfi
	j	park

	/* Built without RVC: every faulting instruction is 4 bytes long. */
	.align	4
	.globl trap_entry
trap_entry:
	csrrw	t0, mscratch, t0
	sd	t1, 0(t0)
	sd	t2, 8(t0)
	csrr	t1, mcause
	la	t2, trap_cause
	sd	t1, 0(t2)
	csrr	t1, mtval
	la	t2, trap_tval
	sd	t1, 0(t2)
	la	t2, trap_count
	ld	t1, 0(t2)
	addi	t1, t1, 1
	sd	t1, 0(t2)
	csrr	t1, mcause
	bltz	t1, 3f
	csrr	t1, mepc
	addi	t1, t1, 4
	csrw	mepc, t1
3:	ld	t1, 0(t0)
	ld	t2, 8(t0)
	csrrw	t0, mscratch, t0
	mret

	.section .bss
	.align	4
trap_save:
	.space	16
	.align	4
	.space	16384
stack_top:
