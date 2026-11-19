#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Classify K3 X100 serial transcripts of the DAMO privileged suite.

Uses the same verdict rules as the QEMU run (run-damo-ats.py): a
suite passes only with exactly one consistent summary, no failures and
the framework's ALL PASSED line. The K3 halt marker stands in for the
simulator exit status; no marker means the image hung or timed out.
"""

import argparse
import csv
import hashlib
import importlib.util
import zipfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("run_damo_ats", HERE / "run-damo-ats.py")
damo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(damo)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "transcripts", type=Path, help="k3-mmode-run.py --out directory"
    )
    parser.add_argument(
        "build", type=Path, help="build-damo-k3-priv.sh output directory"
    )
    parser.add_argument("out", type=Path, help="new evidence directory")
    opts = parser.parse_args()
    with (opts.build / "manifest.tsv").open() as f:
        built = list(csv.DictReader(f, delimiter="\t"))
    if len(built) != 75:
        raise SystemExit("expected 75 manifest rows")
    opts.out.mkdir(parents=True, exist_ok=False)
    counts = Counter()
    with (
        (opts.out / "results.tsv").open("x") as table,
        zipfile.ZipFile(opts.out / "logs.zip", "x", zipfile.ZIP_DEFLATED) as logs,
    ):
        writer = csv.DictWriter(table, damo.FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for b in built:
            suite = b["suite"]
            row = {
                "case": suite,
                "build_rc": b["build_rc"],
                "elf_sha256": b["elf_sha256"],
            }
            path = opts.transcripts / f"{suite}.log"
            if b["build_rc"] != "0":
                row["verdict"] = "BUILD_ERROR"
            elif not path.is_file():
                row["verdict"] = "NOT_RUN"
            else:
                log = path.read_text(errors="replace")
                logs.writestr(f"{suite}.log", log)
                if "K3-DAMO-HALT: PASS" in log:
                    rc = 0
                elif "K3-DAMO-HALT: FAIL" in log:
                    rc = 1
                else:
                    rc = 124
                row["run_rc"] = rc
                row["verdict"] = damo.priv_verdict(rc, log, row)
            writer.writerow(row)
            counts[row["verdict"]] += 1
    (opts.out / "counts.tsv").write_text(
        "".join(f"{v}\t{n}\n" for v, n in sorted(counts.items()))
    )
    env = (opts.build / "environment.txt").read_text()
    manifest_hash = hashlib.sha256(
        (opts.build / "manifest.tsv").read_bytes()
    ).hexdigest()
    (opts.out / "environment.txt").write_text(
        env + f"build_manifest_sha256={manifest_hash}\ntarget=K3 X100 hart 0, M-mode\n"
    )
    print("".join(f"{v}\t{n}\n" for v, n in sorted(counts.items())), end="")


if __name__ == "__main__":
    main()
