/*
 * Copyright (c) 2026 Alibaba Group.
 * SPDX-License-Identifier: Apache-2.0
 */

// rvmodel_macros.h
// DUT-specific macro definitions for Qemu
// Jordan Carlin jcarlin@hmc.edu Feb 2026
// SPDX-License-Identifier: BSD-3-Clause

/*
 * Changed in k3-tools for the SpacemiT K3 X100, from config/qemu-rv64-max in
 * XUANTIE-RV/damo-rv-priv-ats at 824dbb02ce20a6ceabb3ea0665496f0b19bcce19.
 */

/*
 * SpacemiT K3 X100 model macros for the DAMO privileged suite.
 *
 * Runs on hart 0 in M-mode after the vendor SPL. There is no simulator:
 * a halt prints a marker on the console UART and parks the hart; the
 * board runner then resets the board.
 */

#ifndef _RVMODEL_MACROS_H
#define _RVMODEL_MACROS_H

#define STANDARD_SM_SUPPORTED

#define K3_UART_THR 0xd4017000
#define K3_UART_LSR 0xd4017014

#define RVMODEL_DATA_SECTION \
        .pushsection .rodata,"a",@progbits;                            \
        .global _k3_halt_pass_msg;                                      \
        _k3_halt_pass_msg: .asciz "\r\nK3-DAMO-HALT: PASS\r\n";         \
        .global _k3_halt_fail_msg;                                      \
        _k3_halt_fail_msg: .asciz "\r\nK3-DAMO-HALT: FAIL\r\n";         \
        .popsection

/*
 * The X100 per-hart settings the vendor OpenSBI (k3-br-v1.0.1,
 * firmware/fw_base.S and spacemit_k3.c) makes before Linux runs:
 * misa.H (reset value 0 on X100), the L1 cache/prefetch enables in
 * MSETUP (0x7c0) and the L2 instruction/TLB prefetch bits in ML2SETUP
 * (0x7f0). The SPL has already enabled the caches and snoop.
 */
#define RVMODEL_BOOT                    \
    li      t0, (1 << 7)               ;\
    csrs    misa, t0                   ;\
    li      t0, 0x10073                ;\
    csrs    0x7c0, t0                  ;\
    li      t0, (1 << 16) | (1 << 18)  ;\
    csrs    0x7f0, t0                  ;\
    fence   iorw, iorw                 ;\
    fence.i

#define K3_PUTS(_R1, _R2, _R3, _STR_PTR) \
1:                                ;\
    lbu     _R1, 0(_STR_PTR)      ;\
    beqz    _R1, 3f               ;\
    li      _R2, K3_UART_LSR      ;\
2:                                ;\
    lw      _R3, 0(_R2)           ;\
    andi    _R3, _R3, 0x20        ;\
    beqz    _R3, 2b               ;\
    li      _R2, K3_UART_THR      ;\
    sw      _R1, 0(_R2)           ;\
    addi    _STR_PTR, _STR_PTR, 1 ;\
    j       1b                    ;\
3:

#define RVMODEL_IO_WRITE_STR(_R1, _R2, _R3, _STR_PTR) \
    K3_PUTS(_R1, _R2, _R3, _STR_PTR)

#define RVMODEL_HALT_PASS                 \
    la      a1, _k3_halt_pass_msg        ;\
    K3_PUTS(t0, t1, t2, a1)              ;\
4:  wfi                                  ;\
    j       4b

#define RVMODEL_HALT_FAIL                 \
    la      a1, _k3_halt_fail_msg        ;\
    K3_PUTS(t0, t1, t2, a1)              ;\
5:  wfi                                  ;\
    j       5b

// ===== Machine timer (clint@f1810000, 32-bit accesses only) =====

#define RVMODEL_MTIME_ADDRESS     0xf181bff8
#define RVMODEL_MTIMECMP_ADDRESS  0xf1814000
#define CLINT_BASE_ADDRESS        0xf1810000
#define RVMODEL_MSIP_ADDRESS      (CLINT_BASE_ADDRESS + 0x0)

#define RVMODEL_INTERRUPT_LATENCY 10
#define RVMODEL_TIMER_INT_SOON_DELAY 100
/* 24 MHz timebase; the X100 runs at about 2 GHz or less. */
#define RVMODEL_MAX_CYCLES_PER_TIMER_TICK 200

#define RVMODEL_SET_MSW_INT(_R1, _R2) \
  li _R1, 1; \
  li _R2, RVMODEL_MSIP_ADDRESS; \
  sw _R1, 0(_R2);

#define RVMODEL_CLR_MSW_INT(_R1, _R2) \
  li _R2, RVMODEL_MSIP_ADDRESS; \
  sw zero, 0(_R2);

#define RVMODEL_SET_SSW_INT(_R1, _R2)

#define RVMODEL_CLR_SSW_INT(_R1, _R2)

#endif // _RVMODEL_MACROS_H
