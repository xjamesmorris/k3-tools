/* SPDX-License-Identifier: GPL-2.0-only */
OUTPUT_ARCH("riscv")
ENTRY(_start)

SECTIONS
{
	. = 0x100000000;
	.text : { *(.text.init) *(.text .text.*) }
	.rodata : { *(.rodata .rodata.* .srodata .srodata.*) }
	.data : { *(.data .data.* .sdata .sdata.*) }
	.bss (NOLOAD) : {
		. = ALIGN(16);
		__bss_start = .;
		*(.bss .bss.* .sbss .sbss.* COMMON)
		. = ALIGN(16);
		__bss_end = .;
	}
	/DISCARD/ : { *(.comment) *(.note*) *(.riscv.attributes) *(.eh_frame*) }
}
