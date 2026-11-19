#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Run RAM-only M-mode payloads on the K3 X100 through the boot ROM's USB mode.

Each payload is entered by the vendor SPL, staged over USB, in M-mode:

  k3ctl recovery  ->  boot ROM USB download mode
  fastboot stage FSBL.bin; fastboot continue  ->  vendor SPL, DDR training
  fastboot stage PAYLOAD.itb; fastboot continue  ->  payload in M-mode

Nothing is written to NOR, UFS, NVMe or the U-Boot environment: the vendor
U-Boot proper, which saves DDR training data to NOR, never runs on this
path. Only the fastboot commands getvar, stage and continue are sent. The
operator's picocom keeps the serial port; this tool only reads its log.

Subcommands:
  preflight   read-only checks of tools, dongle, serial log and Fedora
  shutdown    clean Fedora reboot, stopping once Linux has finished
  run         one recovery cycle per payload, serial transcript per payload
  restore     plain reset to the saved NOR boot, then verify Fedora over SSH

Board settings come from options or environment variables; there are no
built-in workstation defaults:

  --k3ctl       K3VAL_K3CTL       k3ctl client; default ../k3ctl/k3ctl, then PATH
  --fsbl        K3VAL_FSBL        factory/FSBL.bin of Bianbu K3 v4.0.1 (SHA-256 checked)
  --serial-log  K3VAL_SERIAL_LOG  the log file the operator's picocom writes
  --ssh-target  K3VAL_SSH_TARGET  user@host of the board's Linux; its host key must
                                  already be known (strict host-key checking)

run refuses the DAMO suites listed in X100_NEVER_RUN before touching the board.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Board settings, set in main() from options or K3VAL_* environment variables.
K3CTL = FSBL = SERIAL_LOG = SSH_TARGET = None
# factory/FSBL.bin of the Bianbu K3 v4.0.1 releases: the vendor SPL this path
# was verified with. Other releases' FSBLs differ and are untested here.
FSBL_SHA256 = "7991c200a80e05dde2918ab9b2194505df81df109ed99bb4703f2d0f8feab85d"
# DAMO privileged suites that hard-code a translation mode the X100 lacks
# (Sv48, Sv57 and their x4 forms) and do not skip it. On the X100 they run
# with translation off, so their deliberately invalid addresses become
# physical accesses. Never run them.
X100_NEVER_RUN = frozenset(
    {
        "Sv48",
        "Sv48x4",
        "Sv48x4_Sv39",
        "Sv48x4_Sv48",
        "Sv48x4_Sv57",
        "Sv57",
        "Sv57x4",
        "Sv57x4_Sv39",
        "Sv57x4_Sv48",
        "Sv57x4_Sv57",
    }
)
SSH_OPTS = [
    "-o",
    "BatchMode=yes",
    "-o",
    "StrictHostKeyChecking=yes",
    "-o",
    "UpdateHostKeys=no",
    "-o",
    "ConnectTimeout=5",
]
USB_ID = ("361c", "1001")
ROM_USB = re.compile(r"ROM: usb download handler")
SPL_BANNER = re.compile(r"U-Boot SPL 2022\.10")
DDR_DONE = re.compile(r"DDR (training|quick boot) consume \d+ms")
UBOOT_PROPER = re.compile(r"U-Boot 2022\.10 \(")
LINUX_RESTART = re.compile(r"reboot: Restarting system")
REDACT = [
    (
        re.compile(r"(?i)(serial#?|serial number|chip ?id|sn)\s*[=:]\s*\S+"),
        r"\1=[redacted]",
    ),
    (re.compile(r"\b([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b"), "[mac]"),
]
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07\x1b]*(\x07|\x1b\\)")


class Stop(Exception):
    pass


def utc():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class Record:
    def __init__(self, path):
        self.path = path

    def __call__(self, event, **fields):
        fields = {"utc": utc(), "event": event, **fields}
        line = json.dumps(fields, sort_keys=False)
        print(line, flush=True)
        if self.path:
            with self.path.open("a") as f:
                f.write(line + "\n")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def log_size():
    return SERIAL_LOG.stat().st_size


def log_text(start, end=None):
    with SERIAL_LOG.open("rb") as f:
        f.seek(start)
        data = f.read() if end is None else f.read(end - start)
    return ANSI.sub("", data.decode("latin-1")).replace("\r", "")


def redact(text):
    for pattern, repl in REDACT:
        text = pattern.sub(repl, text)
    return text


def wait_log(start, pattern, timeout, abort=None):
    """Wait for pattern in the serial log after start; abort pattern stops early."""
    deadline = time.monotonic() + timeout
    while True:
        text = log_text(start)
        if abort is not None and abort.search(text):
            return "abort", text
        if pattern.search(text):
            return "match", text
        if time.monotonic() > deadline:
            return "timeout", text
        time.sleep(0.2)


def wait_quiet(seconds, timeout):
    """Wait until the serial log has not grown for `seconds`."""
    deadline = time.monotonic() + timeout
    last, since = log_size(), time.monotonic()
    while time.monotonic() < deadline:
        time.sleep(0.2)
        now = log_size()
        if now != last:
            last, since = now, time.monotonic()
        elif time.monotonic() - since >= seconds:
            return True
    return False


def picocom_owns_log():
    """PID of a picocom that names SERIAL_LOG in its arguments or has it open."""
    try:
        log = SERIAL_LOG.stat()
    except OSError:
        return None
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            argv = (proc / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if not (argv and argv[0].endswith(b"picocom")):
            continue
        if str(SERIAL_LOG).encode() in argv:
            return int(proc.name)
        try:
            fds = list((proc / "fd").iterdir())
        except OSError:
            continue
        for fd in fds:
            try:
                st = fd.stat()
            except OSError:
                continue
            if (st.st_dev, st.st_ino) == (log.st_dev, log.st_ino):
                return int(proc.name)
    return None


def k3ctl(rec, *args, expect):
    cmd = [str(K3CTL), *args]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    out = (p.stdout + p.stderr).strip()
    rec("k3ctl", argv=args, rc=p.returncode, out=out)
    if p.returncode or not out.startswith(expect):
        raise Stop(f"k3ctl {' '.join(args)}: rc={p.returncode} {out!r}")
    return out


def k3ctl_idle(rec):
    out = k3ctl(rec, "status", expect="OK status")
    if not all(f in out.split() for f in ("rst=0", "fcrec=0", "pwr=0")):
        raise Stop(f"dongle lines not released: {out}")


ALLOWED_FASTBOOT = {("getvar", "version-brom"), ("getvar", "version"), ("continue",)}


def fastboot(rec, *args, timeout=30):
    if not (args in ALLOWED_FASTBOOT or (len(args) == 2 and args[0] == "stage")):
        raise Stop(f"fastboot {args} is not allowed")
    try:
        p = subprocess.run(
            ["fastboot", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        rc, out = p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        rc, out = -1, f"timeout after {timeout}s"
    rec("fastboot", argv=args, rc=rc, out=out[-400:])
    return rc, out


def usb_device():
    for dev in Path("/sys/bus/usb/devices").iterdir():
        try:
            ids = (
                (dev / "idVendor").read_text().strip(),
                (dev / "idProduct").read_text().strip(),
            )
        except OSError:
            continue
        if ids == USB_ID:
            bus = int((dev / "busnum").read_text())
            num = int((dev / "devnum").read_text())
            return Path(f"/dev/bus/usb/{bus:03d}/{num:03d}")
    return None


def wait_usb(rec, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        node = usb_device()
        # udev applies the group/mode shortly after the node appears.
        if node and node.exists() and os.access(node, os.R_OK | os.W_OK):
            return node
        time.sleep(0.2)
    node = usb_device()
    rec("usb", present=bool(node), node=str(node))
    if node:
        raise Stop(f"{node} not accessible; install the 361c:1001 udev rule")
    raise Stop("boot ROM / SPL USB device 361c:1001 did not appear (USB-C cable?)")


def wait_spl_fastboot(rec, rom_node, timeout):
    """Wait for the SPL's gadget: same IDs as the ROM's, but re-enumerated."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        node = usb_device()
        if (
            node
            and node != rom_node
            and node.exists()
            and os.access(node, os.R_OK | os.W_OK)
        ):
            _, out = fastboot(rec, "getvar", "version", timeout=5)
            if "version:" in out or "FAILED (remote" in out:
                return node
        time.sleep(0.5)
    raise Stop("SPL fastboot did not answer")


def ssh(rec, command, timeout=30):
    p = subprocess.run(
        ["ssh", *SSH_OPTS, SSH_TARGET, command],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    rec(
        "ssh",
        command=command,
        rc=p.returncode,
        out=(p.stdout + p.stderr).strip()[-600:],
    )
    return p.returncode, p.stdout


def cmd_preflight(opts, rec):
    for tool in ("fastboot", "ssh", "dtc"):
        if subprocess.run(
            ["sh", "-c", f"command -v {tool}"], capture_output=True, check=False
        ).returncode:
            raise Stop(f"missing {tool}")
    pid = picocom_owns_log()
    if not pid:
        raise Stop(f"no picocom writing {SERIAL_LOG}")
    if sha256(FSBL) != FSBL_SHA256:
        raise Stop("FSBL.bin does not match the published vendor image")
    rec(
        "preflight",
        picocom_pid=pid,
        fsbl_sha256=FSBL_SHA256,
        k3ctl_sha256=sha256(K3CTL),
        fwupd=subprocess.run(
            ["systemctl", "is-active", "fwupd.service"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip(),
        usb_present=bool(usb_device()),
    )
    k3ctl_idle(rec)
    rc, out = ssh(
        rec,
        "uname -r; cat /sys/devices/system/cpu/online; "
        "cat /proc/sys/kernel/tainted; sudo -n true && echo sudo-ok",
    )
    if rc or "sudo-ok" not in out:
        raise Stop("Fedora not reachable with non-interactive sudo")


def cmd_shutdown(opts, rec):
    k3ctl_idle(rec)
    start = log_size()
    rc, _ = ssh(rec, "sudo -n systemctl reboot", timeout=30)
    rec("reboot-requested", rc=rc, log_offset=start)
    state, _ = wait_log(start, LINUX_RESTART, 180)
    if state != "match":
        raise Stop(
            "Linux did not reach 'reboot: Restarting system'; nothing sent to the board"
        )
    # This board usually halts here; a real reboot shows the SPL banner instead.
    state, _ = wait_log(start, SPL_BANNER, 6)
    rec("linux-stopped", rebooting=state == "match", log_offset=log_size())


def run_one(opts, rec, payload, outdir):
    name = payload.name.removesuffix(".itb")
    k3ctl_idle(rec)
    off0 = log_size()
    k3ctl(rec, "recovery", expect="OK recovery")
    state, _ = wait_log(off0, ROM_USB, 15, abort=SPL_BANNER)
    if state != "match":
        raise Stop(f"boot ROM USB mode not entered ({state}); FC_REC line attached?")
    rom_node = wait_usb(rec, 20)
    _, out = fastboot(rec, "getvar", "version-brom", timeout=10)
    if "version-brom:" not in out:
        raise Stop("boot ROM did not answer getvar version-brom")
    off1 = log_size()
    if (
        fastboot(rec, "stage", str(FSBL), timeout=60)[0]
        or fastboot(rec, "continue", timeout=10)[0]
    ):
        raise Stop("staging FSBL failed")
    state, _ = wait_log(off1, DDR_DONE, 30)
    if state != "match":
        raise Stop("SPL banner/DDR init not seen after FSBL continue")
    spl_node = wait_spl_fastboot(rec, rom_node, 30)
    rec("usb", rom=str(rom_node), spl=str(spl_node))
    off2 = log_size()
    t0 = time.monotonic()
    if (
        fastboot(rec, "stage", str(payload), timeout=60)[0]
        or fastboot(rec, "continue", timeout=10)[0]
    ):
        raise Stop(f"staging {name} failed")
    state, _ = wait_log(off2, opts.end, opts.timeout, abort=UBOOT_PROPER)
    if state == "match":
        wait_quiet(1.0, 10)
    elapsed = round(time.monotonic() - t0, 2)
    end = log_size()
    (outdir / f"{name}.log").write_text(redact(log_text(off0, end)))
    if state == "abort":
        raise Stop("vendor U-Boot proper started; stopping before anything else runs")
    rec(
        "payload",
        name=name,
        state=state,
        seconds=elapsed,
        log_from=off2,
        log_to=end,
        sha256=sha256(payload),
    )
    return state


def cmd_run(opts, rec):
    refused = sorted(
        {p.name.removesuffix(".itb") for p in opts.payloads} & X100_NEVER_RUN
    )
    if refused:
        raise Stop(f"never run on the X100: {', '.join(refused)}")
    outdir = opts.out
    outdir.mkdir(parents=True, exist_ok=True)
    if sha256(FSBL) != FSBL_SHA256:
        raise Stop("FSBL.bin does not match the published vendor image")
    for payload in opts.payloads:
        if payload.suffix != ".itb" or not payload.is_file():
            raise Stop(f"not a payload: {payload}")
    if (
        subprocess.run(
            ["systemctl", "is-active", "--quiet", "fwupd.service"], check=False
        ).returncode
        == 0
    ):
        raise Stop("fwupd is active; its fastboot plugin would also query the device")
    if opts.from_fedora:
        # Recovery follows at once: Linux has finished, and a real reboot is
        # still in the SPL or U-Boot's countdown, never in Linux.
        cmd_shutdown(opts, rec)
    for payload in opts.payloads:
        run_one(opts, rec, payload, outdir)


def cmd_restore(opts, rec):
    k3ctl_idle(rec)
    start = log_size()
    k3ctl(rec, "reset", expect="OK reset")
    state, _ = wait_log(start, SPL_BANNER, 15, abort=ROM_USB)
    if state != "match":
        raise Stop(f"no NOR boot after reset ({state})")
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        rc, out = ssh(
            rec,
            "uname -r; cat /sys/devices/system/cpu/online; "
            "cat /proc/sys/kernel/tainted",
            timeout=10,
        )
        if rc == 0:
            rec("fedora", lines=out.split())
            return
        time.sleep(5)
    raise Stop("Fedora did not answer SSH after reset")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--record", type=Path, help="append JSON events to this file")
    def env(name):
        return os.environ.get(name) or None

    parser.add_argument(
        "--k3ctl",
        type=Path,
        default=env("K3VAL_K3CTL"),
        help="k3ctl client (default: ../k3ctl/k3ctl beside this tool, then PATH)",
    )
    parser.add_argument(
        "--fsbl",
        type=Path,
        default=env("K3VAL_FSBL"),
        help="factory/FSBL.bin from a Bianbu K3 v4.0.1 release",
    )
    parser.add_argument(
        "--serial-log",
        type=Path,
        default=env("K3VAL_SERIAL_LOG"),
        help="log file written by the operator's picocom (--logfile)",
    )
    parser.add_argument(
        "--ssh-target",
        default=env("K3VAL_SSH_TARGET"),
        help="user@host of the board's Linux, with a known host key",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight")
    sub.add_parser("shutdown")
    run = sub.add_parser("run")
    run.add_argument("--out", type=Path, required=True, help="transcript directory")
    run.add_argument(
        "--end",
        type=re.compile,
        required=True,
        help="regex marking payload completion in the serial log",
    )
    run.add_argument("--timeout", type=float, default=120)
    run.add_argument(
        "--from-fedora",
        action="store_true",
        help="first reboot Fedora over SSH, then go straight to recovery",
    )
    run.add_argument("payloads", nargs="+", type=Path)
    sub.add_parser("restore")
    opts = parser.parse_args()
    needs = {
        "preflight": ("fsbl", "serial_log", "ssh_target"),
        "shutdown": ("serial_log", "ssh_target"),
        "run": ("fsbl", "serial_log")
        + (("ssh_target",) if getattr(opts, "from_fedora", False) else ()),
        "restore": ("serial_log", "ssh_target"),
    }[opts.cmd]
    for name in needs:
        flag = "--" + name.replace("_", "-")
        value = getattr(opts, name)
        if value is None:
            parser.error(f"{opts.cmd} needs {flag} or K3VAL_{name.upper()}")
        if name != "ssh_target" and not value.is_file():
            parser.error(f"{flag}: {value} is not a file")
    if opts.k3ctl is None:
        bundled = Path(__file__).resolve().parent.parent / "k3ctl" / "k3ctl"
        found = shutil.which("k3ctl")
        opts.k3ctl = (
            bundled if bundled.is_file() else Path(found) if found else None
        )
        if opts.k3ctl is None:
            parser.error("k3ctl not found; use --k3ctl or K3VAL_K3CTL")
    if not opts.k3ctl.is_file():
        parser.error(f"--k3ctl: {opts.k3ctl} is not a file")
    global K3CTL, FSBL, SERIAL_LOG, SSH_TARGET
    K3CTL, FSBL = opts.k3ctl.absolute(), opts.fsbl
    SERIAL_LOG, SSH_TARGET = opts.serial_log, opts.ssh_target
    rec = Record(opts.record)
    try:
        {
            "preflight": cmd_preflight,
            "shutdown": cmd_shutdown,
            "run": cmd_run,
            "restore": cmd_restore,
        }[opts.cmd](opts, rec)
    except (Stop, subprocess.TimeoutExpired) as err:
        rec("stop", reason=str(err))
        return 1
    rec("done", cmd=opts.cmd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
