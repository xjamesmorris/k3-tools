/*
 * SPDX-License-Identifier: Apache-2.0
 * Changed in k3-tools for the SpacemiT K3 X100 (base address MEM_BASE),
 * from config/qemu-rv64-max/link.ld in XUANTIE-RV/damo-rv-priv-ats at
 * 824dbb02ce20a6ceabb3ea0665496f0b19bcce19.
 */

OUTPUT_ARCH( "riscv" )
ENTRY(rvtest_entry_point)

SECTIONS
{
  . = MEM_BASE;
  .text.init    : { *(.text.init) }
  .text.rvtest  : { *(.text.rvtest) *(.text.rvtest.*) }
  . = ALIGN(0x1000);
  .text.rvmodel : { *(.text.rvmodel) *(.text.rvmodel.*) *(.text) *(.text.*) }
  . = ALIGN(0x1000);
  . = ALIGN(0x10000);
  .data         : { *(.data) *(.sdata .sdata.*) *(.got .got.*) }
  _end = .;
}
