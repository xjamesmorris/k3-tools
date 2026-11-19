#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Build every published DAMO privileged suite for the K3 X100 RAM path
# and wrap each image in a FIT for k3-mmode-run.py.
set -euo pipefail
set -x

PIN=824dbb02ce20a6ceabb3ea0665496f0b19bcce19
LOAD=0x100000000
MAX_BIN=$((8 * 1024 * 1024))

if (($# != 2)); then
	echo "Usage: $0 DEDICATED_SOURCE_CHECKOUT NEW_OUTPUT_DIR" >&2
	exit 2
fi

here=$(realpath -e -- "$(dirname -- "$0")")
port=$here/damo-k3-x100
src=$(realpath -m -- "$1")
out=$(realpath -m -- "$2")
cross=${CROSS_COMPILE:-riscv64-linux-gnu-}

[[ ! -e $out ]] || {
	echo "$out exists; use a new output directory" >&2
	exit 1
}
if [[ ! -d $src ]]; then
	git clone --quiet --no-checkout https://github.com/XUANTIE-RV/damo-rv-priv-ats.git "$src"
	git -C "$src" checkout --quiet --detach "$PIN"
fi
[[ $(git -C "$src" rev-parse HEAD) == "$PIN" ]]

# The tracked tree may differ from the pin only by the two port patches.
patches=("$port/uart-ier-init.patch" "$port/build-portability.patch")
if ! git -C "$src" apply --reverse --check "${patches[@]}" 2>/dev/null; then
	[[ -z $(git -C "$src" status --porcelain --untracked-files=no) ]]
	git -C "$src" apply "${patches[@]}"
fi
git -C "$src" diff --quiet -- . ':!common/uart.c' ':!common/test_framework.c' \
	':!common/test_framework.h'

# The committed capability header must be what the generator produces.
generated=$(mktemp)
trap 'rm -f -- "$generated"' EXIT
"$port/make-rvtest-config.py" "$src/config/qemu-rv64-max/rvtest_config.h" "$generated"
cmp -- "$generated" "$port/config/k3-x100/rvtest_config.h"
rm -rf -- "$src/config/k3-x100"
cp -a -- "$port/config/k3-x100" "$src/config/k3-x100"

mkdir -p -- "$out/build" "$out/itb"
{
	echo "source_revision=$PIN"
	for patch in "${patches[@]}"; do
		echo "patch=${patch##*/} sha256=$(sha256sum <"$patch" | cut -d' ' -f1)"
	done
	echo "config_sha256=$(cat "$port"/config/k3-x100/* | sha256sum | cut -d' ' -f1)"
	echo "cc=$("${cross}gcc" --version | head -1)"
	echo "load=$LOAD"
} >"$out/environment.txt"
printf 'suite\tbuild_rc\telf_sha256\tbin_bytes\titb_sha256\n' >"$out/manifest.tsv"

mapfile -t suites < <(git -C "$src" ls-files '*/Makefile' | cut -d/ -f1 | sort -u)
((${#suites[@]} == 75))
for suite in "${suites[@]}"; do
	dir=$src/$suite
	rc=0
	make -C "$dir" --no-print-directory -sB -j4 CROSS_COMPILER="$cross" \
		CONFIG=k3-x100 all >"$out/build/$suite.log" 2>&1 || rc=$?
	elf_hash=- bin_bytes=- itb_hash=-
	if ((rc == 0)); then
		mapfile -t elfs < <(find "$dir" -maxdepth 1 -name '*.elf')
		((${#elfs[@]} == 1))
		elf=${elfs[0]}
		bin=${elf%.elf}.bin
		entry=$("${cross}readelf" -h "$elf" | awk '/Entry point/ {print $4}')
		[[ $((entry)) == $((LOAD)) ]]
		bin_bytes=$(stat -c %s "$bin")
		((bin_bytes > 0 && bin_bytes <= MAX_BIN))
		# Nothing may be linked below the load address or use semihosting.
		lowest=$("${cross}readelf" -lW "$elf" | awk '$1 == "LOAD" {print $3}' | sort | head -1)
		[[ $((lowest)) == $((LOAD)) ]]
		if "${cross}objdump" -d "$elf" | grep -A1 -E 'slli\s+zero,zero,0x1f' | grep -q ebreak; then
			echo "$suite: semihosting sequence present" >&2
			exit 1
		fi
		"$here/k3-mmode-fit.py" "$bin" "$out/itb/$suite.itb" --name "$suite"
		elf_hash=$(sha256sum <"$elf" | cut -d' ' -f1)
		itb_hash=$(sha256sum <"$out/itb/$suite.itb" | cut -d' ' -f1)
	fi
	printf '%s\t%s\t%s\t%s\t%s\n' "$suite" "$rc" "$elf_hash" "$bin_bytes" "$itb_hash" >>"$out/manifest.tsv"
done
awk -F '\t' 'NR > 1 && $2 != 0 {bad++} END {print "build failures:", bad + 0; exit bad > 0}' "$out/manifest.tsv"
