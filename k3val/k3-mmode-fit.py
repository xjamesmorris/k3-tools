#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Wrap a raw M-mode binary in a FIT that the K3 vendor SPL enters directly.

In USB download mode the vendor SPL loads the staged FIT with
spl_load_simple_fit(). A single "firmware" image with os = "u-boot" is
copied to its load address and entered by jump_to_image_no_args() in
M-mode on the boot hart (a0 = hartid, a1 = SPL DTB copy). The FIT has no
fdt, rcpu firmware, OpenSBI, or U-Boot image, and is never written to
storage.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

# DRAM starts at 0x1_0000_0000; the SPL heap is at 0x1_0400_0000 and the
# staged FIT buffer at 0x1_4000_0000.
DEFAULT_LOAD = 0x100000000
MAX_SIZE = 0x01F00000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path, help="raw image linked at --load")
    parser.add_argument("output", type=Path, help="new .itb path (not overwritten)")
    parser.add_argument("--name", required=True, help="image description")
    parser.add_argument("--load", type=lambda s: int(s, 0), default=DEFAULT_LOAD)
    opts = parser.parse_args()

    data = opts.binary.read_bytes()
    if not data or len(data) > MAX_SIZE:
        sys.exit(f"{opts.binary}: size {len(data)} outside 1..{MAX_SIZE}")
    if opts.load % 0x1000 or not 0x100000000 <= opts.load < 0x101000000:
        sys.exit(f"load address {opts.load:#x} outside the checked window")
    if opts.output.exists():
        sys.exit(f"{opts.output} exists")
    if not all(c.isalnum() or c in "._-" for c in opts.name):
        sys.exit(f"unsafe image name: {opts.name}")
    dtc = shutil.which("dtc")
    if not dtc:
        sys.exit("dtc not found")

    hi, lo = opts.load >> 32, opts.load & 0xFFFFFFFF
    with tempfile.TemporaryDirectory() as tmp:
        payload = Path(tmp) / "payload.bin"
        payload.write_bytes(data)
        its = Path(tmp) / "image.its"
        its.write_text(f"""/dts-v1/;
/ {{
\tdescription = "K3 X100 M-mode RAM payload {opts.name}";
\t#address-cells = <2>;
\timages {{
\t\tpayload {{
\t\t\tdescription = "{opts.name}";
\t\t\ttype = "firmware";
\t\t\tos = "u-boot";
\t\t\tarch = "riscv";
\t\t\tcompression = "none";
\t\t\tload = <{hi:#x} {lo:#x}>;
\t\t\tentry = <{hi:#x} {lo:#x}>;
\t\t\tdata = /incbin/("payload.bin");
\t\t\thash-1 {{
\t\t\t\talgo = "crc32";
\t\t\t\tvalue = <{zlib.crc32(data):#010x}>;
\t\t\t}};
\t\t}};
\t}};
\tconfigurations {{
\t\tdefault = "conf-1";
\t\tconf-1 {{
\t\t\tdescription = "k3-mmode-payload";
\t\t\tfirmware = "payload";
\t\t}};
\t}};
}};
""")
        tmp_out = Path(tmp) / "out.itb"
        subprocess.run(
            [dtc, "-q", "-I", "dts", "-O", "dtb", "-o", tmp_out, its],
            cwd=tmp,
            check=True,
        )
        fd = os.open(opts.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "wb") as f:
            f.write(tmp_out.read_bytes())
    print(f"{opts.output}: {len(data)} payload bytes at {opts.load:#x}")


if __name__ == "__main__":
    main()
