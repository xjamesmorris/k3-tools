#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Pack only the checksum-bound Linux test images, manifest, and native runner.
set -euo pipefail
set -x

if (($# != 3)); then
	echo "Usage: $0 VECTOR_CHECKOUT QEMU_VECTOR_EVIDENCE NEW_BUNDLE.tar.zst" >&2
	exit 2
fi

src=$(realpath -e -- "$1")
evidence=$(realpath -e -- "$2")
out=$(realpath -m -- "$3")
here=$(dirname -- "$(realpath -e -- "$0")")
[[ -f $evidence/counts.tsv && ! -e $out ]] || {
	echo 'Need a completed QEMU run and a new archive path' >&2
	exit 1
}
grep -Fxq 'mode=unpriv' "$evidence/environment.txt"
pin=$(git -C "$src" rev-parse HEAD)
grep -Fxq "revision=$pin" "$evidence/environment.txt"
manifest=$(mktemp)
partial=$(mktemp --tmpdir="$(dirname -- "$out")" .damo-pack.XXXXXXXX)
trap 'rm -f -- "$manifest" "$partial"' EXIT

awk -F '\t' '
	NR == 1 { if ($1 != "case" || $3 != "build_rc" || $9 != "elf_sha256") exit 1; next }
	$1 !~ /^[[:alnum:]_]+\/[[:alnum:]_.-]+$/ || seen[$1]++ { exit 1 }
	$3 == "0" {
		if ($9 !~ /^[0-9a-f]{64}$/) exit 1
		print $9 "  " $1 ".elf"
	}
	END { if (NR != 672) exit 1 }
' "$evidence/results.tsv" > "$manifest"
(cd "$src" && sha256sum --strict --quiet -c "$manifest")
tar -I 'zstd -q -T2 -3 --long=27' -cf "$partial" \
	-C "$evidence" environment.txt results.tsv \
	-C "$here" run-damo-ats.py \
	-C "$src" --verbatim-files-from -T <(cut -c67- "$manifest")
ln -- "$partial" "$out"
sha256sum -- "$out"
