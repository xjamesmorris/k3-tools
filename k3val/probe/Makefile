# SPDX-License-Identifier: GPL-2.0-only
CROSS_COMPILE ?= riscv64-linux-gnu-
CC := $(CROSS_COMPILE)gcc
OBJCOPY := $(CROSS_COMPILE)objcopy
OBJDUMP := $(CROSS_COMPILE)objdump
OUT ?= build
FIT := ../k3-mmode-fit.py

# No RVC: the trap handler skips a fixed 4-byte faulting instruction.
CFLAGS := -march=rv64ima_zicsr_zifencei -mabi=lp64 -mcmodel=medany -O2 \
	-ffreestanding -fno-builtin -fno-pic -fno-stack-protector -nostdlib \
	-Wall -Wextra -Werror -Wno-unused-parameter
LDFLAGS := -nostdlib -static -no-pie -Wl,--no-relax -Wl,-T,probe.ld \
	-Wl,--build-id=none -Wl,--no-warn-rwx-segments

all: $(OUT)/k3-probe.itb

$(OUT)/k3-probe.elf: probe.S probe.c probe.ld | $(OUT)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ probe.S probe.c
	! $(OBJDUMP) -d $@ | grep -E '^ +[0-9a-f]+:\s+[0-9a-f]{4}\s+'

$(OUT)/k3-probe.bin: $(OUT)/k3-probe.elf
	$(OBJCOPY) -O binary $< $@

$(OUT)/k3-probe.itb: $(OUT)/k3-probe.bin
	rm -f $@
	$(FIT) $< $@ --name k3-probe

$(OUT):
	mkdir -p $@

clean:
	rm -rf $(OUT)

.PHONY: all clean
