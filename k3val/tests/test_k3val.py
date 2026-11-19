#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Hardware-free tests for k3val.

They cover the verdict rules, the board runner's guards (refused suites,
required settings and the fastboot allowlist), FIT creation, payload
selection and transcript classification. No board, QEMU, cross compiler
or network is used; the FIT test needs dtc and is skipped without it.

Run:  python3 -B k3val/tests/test_k3val.py
"""

import csv
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

K3VAL = Path(__file__).resolve().parent.parent


def load(script):
    name = script.removesuffix(".py").replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, K3VAL / script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


damo = load("run-damo-ats.py")
runner = load("k3-mmode-run.py")


def run(script, *args, env=None):
    clean = {k: v for k, v in os.environ.items() if not k.startswith("K3VAL_")}
    clean.update(env or {})
    return subprocess.run(
        [sys.executable, "-I", "-B", str(K3VAL / script), *map(str, args)],
        capture_output=True,
        text=True,
        env=clean,
        timeout=60,
        check=False,
    )


def summary(total, passed, failed, skipped):
    return f"  Total: {total} Passed: {passed} Failed: {failed} Skipped: {skipped}\n"


class PrivilegedVerdicts(unittest.TestCase):
    def verdict(self, rc, log):
        row = {"case": "Sstc"}
        return damo.priv_verdict(rc, log, row), row

    def test_pass_and_counts(self):
        verdict, row = self.verdict(0, summary(5, 5, 0, 0) + "RESULT: ALL PASSED\n")
        self.assertEqual(verdict, "PASS")
        self.assertEqual((row["passed"], row["failed"], row["skipped"]), (5, 0, 0))

    def test_skips(self):
        done = "RESULT: ALL PASSED (2 tests skipped)\n"
        self.assertEqual(self.verdict(0, summary(5, 3, 0, 2) + done)[0], "PASS_WITH_SKIPS")
        self.assertEqual(self.verdict(0, summary(2, 0, 0, 2) + done)[0], "ALL_SKIPPED")

    def test_failure_wins_over_exit_status(self):
        self.assertEqual(self.verdict(0, summary(5, 4, 1, 0))[0], "FAIL")

    def test_incomplete_runs(self):
        passed = "RESULT: ALL PASSED\n"
        self.assertEqual(self.verdict(0, "booting\n")[0], "INCOMPLETE")
        self.assertEqual(self.verdict(0, summary(5, 3, 0, 1) + passed)[0], "INCOMPLETE")
        self.assertEqual(self.verdict(1, summary(5, 5, 0, 0) + passed)[0], "INCOMPLETE")
        self.assertEqual(self.verdict(0, summary(5, 5, 0, 0))[0], "INCOMPLETE")

    def test_timeout_and_emulator(self):
        self.assertEqual(self.verdict(124, summary(5, 5, 0, 0))[0], "TIMEOUT")
        log = "qemu-system-riscv64: unable to find CPU model 'x'\n"
        self.assertEqual(self.verdict(1, log)[0], "EMU_UNAVAILABLE")


class VectorVerdicts(unittest.TestCase):
    def verdict(self, rc, log):
        row = {"case": "vx/vadd.vv"}
        return damo.vector_verdict(rc, log, row), row

    @staticmethod
    def log(iterations, extra=""):
        return (
            "Starting testcase: vadd.vv.cpp\n"
            + extra
            + f"Finalizing program (expect illegal: 0, iterations: {iterations}) ...\n"
        )

    def test_pass_needs_every_iteration(self):
        verdict, row = self.verdict(0, self.log("3e8"))
        self.assertEqual((verdict, row["iterations_reported"]), ("PASS", "3e8"))
        self.assertEqual(self.verdict(0, self.log("1000"))[0], "PASS")
        self.assertEqual(self.verdict(0, self.log("5"))[0], "INCOMPLETE")

    def test_error_line_fails_despite_exit_zero(self):
        log = self.log("3e8", "[ERROR] vd mismatch\n")
        self.assertEqual(self.verdict(0, log)[0], "FAIL")

    def test_exit_status_and_timeout(self):
        self.assertEqual(self.verdict(1, self.log("3e8"))[0], "RUN_ERROR")
        self.assertEqual(self.verdict(124, self.log("3e8"))[0], "TIMEOUT")


class BoardRunnerGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        for name in ("fsbl.bin", "boot.log"):
            (self.tmp / name).write_bytes(b"")

    def test_refuses_never_run_suites_before_any_board_action(self):
        payloads = []
        for name in ("framework_test", "Sv48", "Sv57x4_Sv39"):
            payloads.append(self.tmp / f"{name}.itb")
            payloads[-1].write_bytes(b"x")
        record, out = self.tmp / "events.jsonl", self.tmp / "transcripts"
        p = run(
            "k3-mmode-run.py",
            "--k3ctl", "/bin/false",
            "--fsbl", self.tmp / "fsbl.bin",
            "--serial-log", self.tmp / "boot.log",
            "--record", record,
            "run", "--out", out, "--end", "HALT",
            *payloads,
        )
        self.assertEqual(p.returncode, 1, p.stderr)
        events = [json.loads(line) for line in record.read_text().splitlines()]
        self.assertEqual([e["event"] for e in events], ["stop"])
        self.assertEqual(events[0]["reason"], "never run on the X100: Sv48, Sv57x4_Sv39")
        self.assertFalse(out.exists())

    def test_board_settings_are_required(self):
        p = run("k3-mmode-run.py", "preflight")
        self.assertEqual(p.returncode, 2)
        self.assertIn("preflight needs --fsbl or K3VAL_FSBL", p.stderr)
        env = {
            "K3VAL_FSBL": str(self.tmp / "fsbl.bin"),
            "K3VAL_SERIAL_LOG": str(self.tmp / "boot.log"),
        }
        p = run(
            "k3-mmode-run.py", "run", "--from-fedora", "--out", self.tmp / "o",
            "--end", "HALT", self.tmp / "a.itb", env=env,
        )
        self.assertEqual(p.returncode, 2)
        self.assertIn("run needs --ssh-target or K3VAL_SSH_TARGET", p.stderr)

    def test_fastboot_allowlist(self):
        calls = []

        def fake_run(argv, **_kwargs):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, "version-brom: 1.0", "")

        def rec(*_args, **_kwargs):
            pass

        saved, runner.subprocess.run = runner.subprocess.run, fake_run
        self.addCleanup(setattr, runner.subprocess, "run", saved)
        for args in (
            ("flash", "fsbl", "x"),
            ("erase", "env"),
            ("oem", "x"),
            ("getvar", "all"),
            ("reboot",),
            ("stage",),
        ):
            with self.assertRaises(runner.Stop):
                runner.fastboot(rec, *args)
        self.assertEqual(calls, [])
        for args in (("getvar", "version-brom"), ("stage", "a.itb"), ("continue",)):
            runner.fastboot(rec, *args)
        self.assertEqual(
            [c[1:] for c in calls],
            [["getvar", "version-brom"], ["stage", "a.itb"], ["continue"]],
        )


@unittest.skipUnless(shutil.which("dtc"), "dtc not installed")
class Fit(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.data = bytes(range(256)) * 4
        (self.tmp / "image.bin").write_bytes(self.data)

    def test_single_firmware_image_at_dram_base(self):
        itb = self.tmp / "image.itb"
        p = run("k3-mmode-fit.py", self.tmp / "image.bin", itb, "--name", "framework_test")
        self.assertEqual(p.returncode, 0, p.stderr)
        dts = subprocess.run(
            ["dtc", "-q", "-I", "dtb", "-O", "dts", str(itb)],
            capture_output=True, text=True, check=True,
        ).stdout
        for prop in ("load", "entry"):
            self.assertRegex(dts, rf"{prop} = <0x0*1 0x0+>;")
        self.assertIn('type = "firmware";', dts)
        self.assertIn('os = "u-boot";', dts)
        self.assertRegex(dts, rf"value = <{zlib.crc32(self.data):#x}>;")
        nodes = re.findall(r"^\t\t(\S+) \{", dts, re.MULTILINE)
        self.assertEqual(nodes, ["payload", "conf-1"])

    def test_refuses_existing_output_and_unsafe_names(self):
        (self.tmp / "taken.itb").write_bytes(b"keep")
        p = run("k3-mmode-fit.py", self.tmp / "image.bin", self.tmp / "taken.itb",
                "--name", "x")
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual((self.tmp / "taken.itb").read_bytes(), b"keep")
        p = run("k3-mmode-fit.py", self.tmp / "image.bin", self.tmp / "new.itb",
                "--name", 'x";')
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse((self.tmp / "new.itb").exists())


class PayloadSelection(unittest.TestCase):
    def setUp(self):
        self.build = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.build)
        (self.build / "itb").mkdir()
        rows = []
        for suite, rc in (("framework_test", 0), ("Ssdbltrp", 2), ("Sv57", 0), ("Svnapot", 0)):
            digest = "-"
            if rc == 0:
                itb = self.build / "itb" / f"{suite}.itb"
                itb.write_bytes(suite.encode())
                digest = hashlib.sha256(itb.read_bytes()).hexdigest()
            rows.append(f"{suite}\t{rc}\t-\t-\t{digest}\n")
        (self.build / "manifest.tsv").write_text(
            "suite\tbuild_rc\telf_sha256\tbin_bytes\titb_sha256\n" + "".join(rows)
        )

    def test_runs_built_suites_except_never_run(self):
        p = run("k3val", "x100-priv", "--dry-run", self.build, "out")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(
            "run --out out --end 'K3-DAMO-HALT: (PASS|FAIL)' --timeout 120 ", p.stdout
        )
        self.assertEqual(re.findall(r"itb/(\w+)\.itb", p.stdout), ["framework_test", "Svnapot"])

    def test_named_suites_are_checked(self):
        p = run("k3val", "x100-priv", "--dry-run", "--suite", "Sv57", self.build, "out")
        self.assertEqual(p.returncode, 2)
        self.assertIn("Sv57 must never run on the X100", p.stderr)
        p = run("k3val", "x100-priv", "--dry-run", "--suite", "Ssdbltrp", self.build, "out")
        self.assertEqual(p.returncode, 2)
        self.assertIn("was not built", p.stderr)

    def test_changed_payload_is_rejected(self):
        (self.build / "itb" / "Svnapot.itb").write_bytes(b"changed")
        p = run("k3val", "x100-priv", "--dry-run", self.build, "out")
        self.assertEqual(p.returncode, 2)
        self.assertIn("does not match", p.stderr)


class Classification(unittest.TestCase):
    def test_markers_become_verdicts(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        build, transcripts = tmp / "build", tmp / "transcripts"
        build.mkdir()
        transcripts.mkdir()
        rows = "".join(
            f"suite{i:02d}\t{2 if i == 3 else 0}\t{'0' * 64}\t1\t-\n" for i in range(75)
        )
        (build / "manifest.tsv").write_text(
            "suite\tbuild_rc\telf_sha256\tbin_bytes\titb_sha256\n" + rows
        )
        (build / "environment.txt").write_text("source_revision=x\n")
        (transcripts / "suite00.log").write_text(
            summary(3, 3, 0, 0) + "RESULT: ALL PASSED\nK3-DAMO-HALT: PASS\n"
        )
        (transcripts / "suite01.log").write_text(summary(3, 2, 1, 0) + "K3-DAMO-HALT: FAIL\n")
        (transcripts / "suite02.log").write_text("TEST 4 of 9\n")
        p = run("classify-damo-k3-priv.py", transcripts, build, tmp / "out")
        self.assertEqual(p.returncode, 0, p.stderr)
        with (tmp / "out" / "results.tsv").open() as f:
            verdicts = {r["case"]: r["verdict"] for r in csv.DictReader(f, delimiter="\t")}
        self.assertEqual(
            [verdicts[f"suite{i:02d}"] for i in range(5)],
            ["PASS", "FAIL", "TIMEOUT", "BUILD_ERROR", "NOT_RUN"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=1)
