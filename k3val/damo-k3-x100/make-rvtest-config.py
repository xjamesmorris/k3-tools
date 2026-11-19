#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Derive the K3 X100 rvtest_config.h from the pinned QEMU rv64 max profile.

Every change is backed by the M-mode probes of 2026-11-19 or by the board
device tree; see README.md. Undeclared extensions make the corresponding
cases skip rather than fail.

Usage: make-rvtest-config.py QEMU_RV64_MAX_RVTEST_CONFIG_H OUTPUT
"""

import re
import sys
from pathlib import Path

# Absent on X100: trapping CSR, unwritable enable bit, illegal encoding,
# or neither in the vendor nor the Linux device tree.
DROP = {
    "Q",
    "SMCDELEG",
    "SMCSRIND",
    "SMCTR",
    "SMDBLTRP",
    "SMMPM",
    "SSCCFG",
    "SSCSRIND",
    "SSCTR",
    "SSDBLTRP",
    "SSPM",
    "SSQOSID",
    "SSSTRICT",
    "SUPM",
    "SV48",
    "SV57",
    "SVADU",
    "SVRSW60T59B",
    "SVVPTC",
    "ZA128RS",
    "ZABHA",
    "ZACAS",
    "ZALASR",
    "ZAMA16B",
    "ZBKB",
    "ZBKC",
    "ZBKX",
    "ZICCAMOC",
    "ZICFILP",
    "ZICFISS",
    "ZK",
    "ZKN",
    "ZKND",
    "ZKNE",
    "ZKNH",
    "ZKR",
    "ZKS",
    "ZKSED",
    "ZKSH",
}
DROP_UDB = re.compile(
    r"UDB_(IGNORE_INVALID_VSATP_MODE_WRITES_WHEN_V_EQ_ZERO"
    r"|SV(48|57)(X4|_VSMODE)_TRANSLATION|MCTRCTL_[A-Z]+_IMPLEMENTED)$"
)
VALUES = {
    "ARCH_ID_VALUE": 0x8000000058000002,  # marchid
    "IMP_ID_VALUE": 0x33D8A600,  # mimpid
    "VENDOR_ID_BANK": 0x710 >> 7,  # mvendorid 0x710
    "VENDOR_ID_OFFSET": 0x710 & 0x7F,
    "NUM_EXTERNAL_GUEST_INTERRUPTS": 7,  # hgeie writable 0xfe
    "PHYS_ADDR_WIDTH": 40,  # pmpaddr writable 0x3ffffffc00
    "PMP_GRANULARITY": 13,  # 8 KiB: pmpaddr[9:0] read zero with A=OFF
    "VLEN": 256,  # vlenb 0x20
}
LAST_COUNTER = 18  # mcounteren/hcounteren/scounteren writable 0x7ffff
COUNTER = re.compile(
    r"UDB_(HPM_COUNTER|MCOUNTENABLE|SCOUNTENABLE|HCOUNTENABLE|COUNTINHIBIT)_EN_(\d+)$"
)


def keep(name):
    if name.endswith("_SUPPORTED"):
        stem = name.removesuffix("_SUPPORTED")
        # Names can end in digits (SV48 + 1P0P0), so try every version split.
        bases = {stem} | {
            stem[:i]
            for i in range(1, len(stem))
            if re.fullmatch(r"\d+P\d+(P\d+)?", stem[i:])
        }
        if bases & DROP:
            return False
    if DROP_UDB.match(name):
        return False
    m = COUNTER.match(name)
    return not (m and int(m.group(2)) > LAST_COUNTER)


def main():
    src, dst = map(Path, sys.argv[1:3])
    out = []
    for line in src.read_text().splitlines():
        m = re.match(r"#define (\w+)(?:\s+(\S+))?\s*$", line)
        if not m:
            out.append(line.replace("QEMU_RV64_MAX", "K3_X100"))
            continue
        name, value = m.groups()
        name = name.replace("QEMU_RV64_MAX", "K3_X100")
        key = name[4:] if name.startswith("UDB_") else None
        if not keep(name):
            continue
        if key in VALUES and value is not None:
            out.append(f"#define {name} {VALUES[key]}")
            continue
        base = next((k for k in VALUES if key and key.startswith(k + "_")), None)
        if base and value is None:
            out.append(f"#define UDB_{base}_{VALUES[base]}")
            continue
        out.append(f"#define {name}" + (f" {value}" if value is not None else ""))
    guard_end = max(i for i, line in enumerate(out) if line.startswith("#endif"))
    out[guard_end:guard_end] = ["#define ZVL256B_SUPPORTED  /* vlenb 0x20 */", ""]
    dst.write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
