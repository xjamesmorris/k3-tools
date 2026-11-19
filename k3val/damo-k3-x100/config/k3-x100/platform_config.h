/*
 * Copyright (c) 2026 Alibaba Group.
 * SPDX-License-Identifier: Apache-2.0
 */

/*
 * Changed in k3-tools for the SpacemiT K3 X100, from config/qemu-rv64-max in
 * XUANTIE-RV/damo-rv-priv-ats at 824dbb02ce20a6ceabb3ea0665496f0b19bcce19.
 */

/*
 * SpacemiT K3 CoM260 IFX, X100 hart 0 in M-mode (RAM payload via the
 * vendor SPL). Addresses are from the vendor SPL device tree (U-Boot
 * 2022.10 build 395, k3_com260_ifx.dtb) and were confirmed by an M-mode
 * probe on the board.
 *
 * This header is included via CFLAGS -include for C code only.
 */

#ifndef PLATFORM_K3_X100_H
#define PLATFORM_K3_X100_H

/* uart0: ns16550 (XScale-derived), reg-shift 2, reg-io-width 4,
 * 14.7456 MHz; the SPL leaves it at 115200 8N1 (divisor 8). IER bit 6
 * is the XScale unit enable that the vendor U-Boot keeps set. */
#define PLATFORM_UART0_BASE     0xd4017000UL
#define PLATFORM_UART_REG_SHIFT 2
#define PLATFORM_UART_IO_WIDTH  4
#define PLATFORM_UART_IER_INIT  0x40
#define UART_DLL_VALUE          0x08
#define UART_DLM_VALUE          0x00

/* DRAM is 0x1_0000_0000..0x3_0000_0000. The tests use 256 MiB from the
 * start; nothing else runs once the SPL has jumped. */
#ifndef PLATFORM_MEM_BASE
#define PLATFORM_MEM_BASE       0x100000000UL
#endif

#define PLATFORM_MEM_SIZE       0x10000000UL    /* 256 MB */

#define CONFIG_NAME           "SpacemiT K3 X100 (M-mode RAM payload)"

/* No SSCOFPMF_COUNT_EVENT: no mhpmevent selector has been measured to
 * count on X100, so counting-dependent cases skip. */

/* clint@f1810000, "riscv,clint0", clint,has-no-64bit-mmio: 32-bit
 * accesses only (the framework writes MTIMECMP as two words). MTIME
 * tracks the time CSR (24 MHz timebase). */
#define PLATFORM_CLINT_BASE       0xf1810000UL
#define CLINT_SUPPORTED
#define MSWI_SUPPORTED
#define PLATFORM_MSIP_ADDR        PLATFORM_CLINT_BASE
#define PLATFORM_MTIMECMP_ADDR    (PLATFORM_CLINT_BASE + 0x4000UL)
#define PLATFORM_MTIME_ADDR       (PLATFORM_CLINT_BASE + 0xBFF8UL)

#endif /* PLATFORM_K3_X100_H */
