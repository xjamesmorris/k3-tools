# SPDX-License-Identifier: Apache-2.0
# SpacemiT K3 X100, hart 0, M-mode entry from the vendor SPL (USB download).
#
# The image is staged in RAM by k3val/k3-mmode-run.py; there is no
# simulator target. MEM_BASE is the start of DRAM, where OpenSBI normally
# runs: below the SPL heap (0x1_0400_0000) and staged-FIT buffer
# (0x1_4000_0000), which are idle once the image is entered.

CROSS_COMPILER ?= riscv64-linux-gnu-

MEM_BASE ?= 0x100000000
