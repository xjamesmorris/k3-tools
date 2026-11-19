#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build and run the pinned RV64 DAMO suites, keeping one verdict and log per image."""

import argparse
import csv
import hashlib
import os
import platform
import re
import resource
import shlex
import shutil
import subprocess
import sys
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PINS = {
    "priv": ("damo-rv-priv-ats", "824dbb02ce20a6ceabb3ea0665496f0b19bcce19"),
    "unpriv": ("damo-rv-ats", "71067d59cf513d9b0c9efff3656e740308d34c76"),
}
SEED, ITERATIONS = 20261118, 1000
FIELDS = (
    "case",
    "verdict",
    "build_rc",
    "run_rc",
    "passed",
    "failed",
    "skipped",
    "iterations_reported",
    "elf_sha256",
)


def output(*args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def checkout(src, name, pin):
    if not src.exists():
        src.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", src], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                src,
                "fetch",
                "-q",
                "--depth=1",
                f"https://github.com/XUANTIE-RV/{name}.git",
                pin,
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", src, "checkout", "-q", "--detach", pin], check=True
        )
    if output("git", "-C", src, "rev-parse", "HEAD") != pin:
        sys.exit(f"Wrong source revision in {src}; use a fresh scratch directory")
    if output("git", "-C", src, "status", "--porcelain", "--untracked-files=no"):
        sys.exit(f"Tracked source changes in {src}; refusing a non-baseline run")


def tool(name):
    path = shutil.which(name)
    if not path:
        sys.exit(f"Missing executable: {name}")
    return os.path.abspath(path)  # Keep the compiler driver's invocation symlink.


def command(args, cwd, seconds):
    cmd = ["timeout", "--kill-after=3s", str(seconds), *args]
    p = subprocess.run(
        cmd,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return p.returncode, "$ " + shlex.join(cmd) + "\n" + p.stdout.decode(
        errors="replace"
    )


def priv_verdict(rc, log, row):
    counts = re.findall(
        r"^\s*Total:\s*(\d+)\s+Passed:\s*(\d+)\s+"
        r"Failed:\s*(\d+)\s+Skipped:\s*(\d+)\s*$",
        log,
        re.MULTILINE,
    )
    if len(counts) == 1:
        total, passed, failed, skipped = map(int, counts[0])
        row.update(passed=passed, failed=failed, skipped=skipped)
    if rc in (124, 137):
        return "TIMEOUT"
    if re.search(
        r"unable to find CPU|can't apply global|Property .* not found",
        log,
        re.IGNORECASE,
    ):
        return "EMU_UNAVAILABLE"
    if len(counts) != 1 or total == 0 or total != passed + failed + skipped:
        return "INCOMPLETE"
    if failed:
        return "FAIL"
    if rc or not re.search(
        r"^\s*RESULT: ALL PASSED(?: \(\d+ tests skipped\))?\s*$", log, re.MULTILINE
    ):
        return "INCOMPLETE"
    if not passed:
        return "ALL_SKIPPED"
    return "PASS_WITH_SKIPS" if skipped else "PASS"


def vector_verdict(rc, log, row):
    end = re.findall(
        r"^Finalizing program \(expect illegal: [0-9a-f]+, "
        r"iterations: ([0-9a-f]+)\) \.\.\.\s*$",
        log,
        re.MULTILINE | re.IGNORECASE,
    )
    if len(end) == 1:
        row["iterations_reported"] = end[0]
    if rc in (124, 137):
        return "TIMEOUT"
    if "[ERROR]" in log:
        return "FAIL"
    if rc:
        return "RUN_ERROR"
    # Some cases leave the cout stream in hex. Neither an early break nor
    # exit(0) after a mismatch is a passing run.
    start = "Starting testcase: " + row["case"].split("/")[-1] + ".cpp"
    if start not in log.splitlines() or end not in (
        [str(ITERATIONS)],
        [f"{ITERATIONS:x}"],
    ):
        return "INCOMPLETE"
    return "PASS"


def x100_isa():
    dt = Path("/proc/device-tree")
    if (
        os.geteuid() == 0
        or platform.machine() != "riscv64"
        or not dt.is_dir()
        or b"spacemit,k3-com260-ifx"
        not in (dt / "compatible").read_bytes().split(b"\0")
        or Path("/sys/devices/system/cpu/online").read_text().strip() != "0-7"
    ):
        sys.exit(
            "Native mode requires a non-root user on the K3 CoM260 IFX with only the eight X100 harts online"
        )
    os.sched_setaffinity(0, {0})
    props = (dt / "cpus/cpu@0/riscv,isa-extensions").read_bytes()
    isa = set(props.decode().strip("\0").split("\0"))
    if "v" not in isa:
        sys.exit("X100 vector extension not advertised; no native run")
    return isa


def native_manifest(src, pin):
    env = (src / "environment.txt").read_text().splitlines()
    if "mode=unpriv" not in env or f"revision={pin}" not in env:
        sys.exit("Native input must be the pinned workstation vector build")
    with (src / "results.tsv").open() as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    if len(rows) != 671 or len({r["case"] for r in rows}) != len(rows):
        sys.exit("Incomplete or duplicated native input manifest")
    for r in rows:
        if not re.fullmatch(r"[a-z0-9_]+/[a-zA-Z0-9_.-]+", r["case"]):
            sys.exit(f"Invalid manifest case: {r['case']}")
        if r["build_rc"] == "0" and not re.fullmatch(r"[0-9a-f]{64}", r["elf_sha256"]):
            sys.exit(f"Missing ELF hash: {r['case']}")
    return {r["case"]: r["elf_sha256"] for r in rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=["priv", "unpriv", "x100"],
        help="system QEMU, user QEMU, or native unprivileged Linux",
    )
    parser.add_argument(
        "source",
        type=Path,
        help="dedicated scratch checkout, or unpacked binary bundle for x100",
    )
    parser.add_argument(
        "out", type=Path, help="new evidence directory (never overwritten)"
    )
    parser.add_argument(
        "--jobs", type=int, default=4, help="parallel builds; native runs use one CPU"
    )
    opts = parser.parse_args()
    if opts.jobs < 1:
        parser.error("--jobs must be positive")
    src, out = opts.source.resolve(), opts.out.resolve()
    if src == out or src in out.parents or out in src.parents:
        parser.error("keep evidence separate from the source checkout")
    priv, native = opts.mode == "priv", opts.mode == "x100"
    isa = x100_isa() if native else set()
    name, pin = PINS["priv" if priv else "unpriv"]
    cross = os.environ.get("CROSS_COMPILE", "riscv64-linux-gnu-")
    cc = (
        None
        if native
        else tool(
            cross + "gcc" if priv else os.environ.get("CXX", "riscv64-linux-gnu-g++")
        )
    )
    qemu = (
        None
        if native
        else tool(
            os.environ.get(
                "QEMU", "qemu-system-riscv64" if priv else "qemu-riscv64-static"
            )
        )
    )
    if native:
        binaries = native_manifest(src, pin)
    else:
        checkout(src, name, pin)
    os.environ["LC_ALL"] = "C"
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    out.mkdir(parents=True, exist_ok=False)
    files = [] if native else output("git", "-C", src, "ls-files").splitlines()
    if priv:
        cases = sorted(
            p.split("/")[0] for p in files if re.fullmatch(r"[^/]+/Makefile", p)
        )
        rule = "inventory:\n\t@echo $(EXTENSIONS)\n"
        declared = output(
            "make", "-s", "-f", "Makefile", "-f", "-", "inventory", cwd=src, input=rule
        )
        missing = sorted(set(declared.split()) - set(cases))
        (out / "unpublished.txt").write_text("".join(f"{case}\n" for case in missing))
    elif native:
        cases = sorted(binaries)
    else:
        cases = sorted(p[:-4] for p in files if re.fullmatch(r"[^/]+/[^/]+\.cpp", p))
    if len(cases) != (75 if priv else 671):
        sys.exit(f"Unexpected suite inventory at {pin}: {len(cases)}")
    meta = [
        f"mode={opts.mode}",
        f"repo=XUANTIE-RV/{name}",
        f"revision={pin}",
        f"machine={platform.machine()}",
        f"kernel={platform.release()}",
        f"cases={len(cases)}",
        f"jobs={opts.jobs}",
    ]
    if cc:
        meta.extend(
            [
                f"cc={cc}",
                output(cc, "--version").splitlines()[0],
                "build_timeout_seconds=300",
            ]
        )
    if qemu:
        meta.extend([f"qemu={qemu}", output(qemu, "--version").splitlines()[0]])
    if priv:
        meta.extend(["config=qemu-rv64-max", "run_timeout_seconds=30"])
    else:
        meta.extend(
            [
                f"seed={SEED}",
                f"iterations={ITERATIONS}",
                "early_stop=true",
                "run_timeout_seconds=60",
                "cpu=" + ("X100 hart 0" if native else "max,vlen=256"),
            ]
        )
    if native:
        meta.append("dt_isa=" + "_".join(sorted(isa)))
        meta.append(
            "source_manifest_sha256="
            + hashlib.sha256((src / "results.tsv").read_bytes()).hexdigest()
        )
    (out / "environment.txt").write_text("\n".join(meta) + "\n")

    def run(case):
        row = {"case": case}
        if priv:
            cwd = src / case
            flags = [f"CROSS_COMPILER={cross}", "CONFIG=qemu-rv64-max"]
            build = [
                "make",
                "--no-print-directory",
                "-sB",
                f"-j{opts.jobs}",
                *flags,
                "all",
            ]
            launch = [
                "make",
                "--no-print-directory",
                *flags,
                f"QEMU={qemu} -accel tcg -nic none -monitor none",
                "qemu",
            ]
        else:
            cwd, stem = (src / case).parent, Path(case).name
            group = cwd.name
            required = {"zvknh": {"zvknhb"}, "zvfbfwma": {"zvfbfmin", "zvfbfwma"}}.get(
                group, {group} if group.startswith("z") else {"v"}
            )
            if native and not required <= isa:
                row["verdict"] = "NOT_ADVERTISED"
                return (
                    row,
                    f"CPU 0 DT does not advertise {', '.join(sorted(required - isa))}\n",
                )
            build = ["make", "--no-print-directory", "-sB", f"CXX={cc}", f"{stem}.elf"]
            launch = ([] if native else [qemu, "-cpu", "max,vlen=256"]) + [
                f"./{stem}.elf",
                "--seed",
                str(SEED),
                "--runtime",
                str(ITERATIONS),
                "--early-stop",
            ]
        if native:
            if not binaries[case]:
                row["verdict"] = "NOT_BUILT"
                return row, "No cross-built ELF in the source manifest\n"
            transcript = "Using workstation-built static ELF; no native compilation\n"
        else:
            rc, transcript = command(build, cwd, 300)
            row["build_rc"] = rc
            if rc:
                row["verdict"] = "BUILD_TIMEOUT" if rc in (124, 137) else "BUILD_ERROR"
                return row, transcript
        images = list(cwd.glob("*.elf")) if priv else [cwd / f"{stem}.elf"]
        if len(images) != 1 or not images[0].is_file():
            row["verdict"] = "BUILD_ERROR"
            return row, transcript + "\nExpected exactly one built test image\n"
        row["elf_sha256"] = hashlib.sha256(images[0].read_bytes()).hexdigest()
        if native and row["elf_sha256"] != binaries[case]:
            row["verdict"] = "IMAGE_MISMATCH"
            return (
                row,
                transcript
                + "ELF differs from the workstation manifest; not executed\n",
            )
        rc, log = command(launch, cwd, 30 if priv else 60)
        row.update(
            run_rc=rc, verdict=(priv_verdict if priv else vector_verdict)(rc, log, row)
        )
        return row, transcript + "\n" + log

    counts = Counter()
    # Privileged Makefiles share common/*.o and a single flags file.
    workers = 1 if priv or native else opts.jobs
    with (
        (out / "results.tsv").open("x", buffering=1) as table,
        zipfile.ZipFile(out / "logs.zip", "x", zipfile.ZIP_DEFLATED) as logs,
        ThreadPoolExecutor(max_workers=workers) as pool,
    ):
        writer = csv.DictWriter(table, FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row, transcript in pool.map(run, cases):
            logs.writestr(row["case"] + ".log", transcript)
            writer.writerow(row)
            counts[row["verdict"]] += 1
    summary = "\n".join(f"{v}\t{n}" for v, n in sorted(counts.items())) + "\n"
    (out / "counts.tsv").write_text(summary)
    print(summary, end="")
    return int(
        bool(
            counts.keys() - {"PASS", "PASS_WITH_SKIPS", "ALL_SKIPPED", "NOT_ADVERTISED"}
        )
        or not (counts["PASS"] + counts["PASS_WITH_SKIPS"])
    )


if __name__ == "__main__":
    sys.exit(main())
