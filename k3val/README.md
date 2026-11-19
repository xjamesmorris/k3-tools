<!-- SPDX-License-Identifier: GPL-2.0-only -->

# k3val - architecture test runs for the K3

k3val builds and runs architecture test suites on workstation QEMU and on
the X100 cores of a SpacemiT K3, keeping one verdict and one log per test
image. It starts with XUANTIE-RV's DAMO RV64 suites, at pinned revisions:

| Suite | Pinned revision | Where it runs |
| --- | --- | --- |
| [damo-rv-priv-ats](https://github.com/XUANTIE-RV/damo-rv-priv-ats) (privileged) | `824dbb02ce20a6ceabb3ea0665496f0b19bcce19` | QEMU `virt`; X100 hart 0 as M-mode RAM payloads |
| [damo-rv-ats](https://github.com/XUANTIE-RV/damo-rv-ats) (unprivileged) | `71067d59cf513d9b0c9efff3656e740308d34c76` | QEMU user mode; natively under Linux on X100 hart 0 |

The runners fetch the suites at these revisions; this repository does not
copy them. At these revisions the privileged suite publishes 74 of the
extension targets its top-level Makefile declares, plus `framework_test`
(75 images); the unprivileged suite has 671 instruction programs.

The board procedures were developed with a K3-CoM260 on a Firefly carrier,
with Bianbu K3 v4.0.1 firmware in its NOR flash, Fedora 45 on NVMe and a
[k3ctl](../k3ctl/README.md) dongle. Other boards, carriers and firmware have
not been tried. This page records no test results. Keep QEMU results and K3
results apart: a QEMU run describes the test, compiler and emulator, not the
hardware.

## Safety

**Run board commands only when someone is at the board**, its serial
console is attended and its power can be removed by hand.

- The privileged path resets the K3 into its boot ROM's USB download mode
  for every test image, and `k3val board restore` resets it again. Resets
  are abrupt; save anything that matters on the board first.
- The board runner sends only the fastboot commands `getvar`, `stage` and
  `continue`, never `flash`, `erase` or `oem`. It stops if vendor U-Boot
  proper starts, because U-Boot proper writes DDR training data to NOR.
  [Why this path writes nothing](#why-this-path-writes-nothing) gives the
  basis and its limits.
- It never types on the serial console. It reads the log file of the
  operator's picocom, which keeps the port.
- It accepts only the FSBL from the Bianbu K3 v4.0.1 releases, checked by
  SHA-256. Other releases' FSBLs differ and have not been used on this path.
- It refuses ten privileged suites that hard-code a translation mode the
  X100 lacks (`Sv48`, `Sv48x4`, `Sv48x4_Sv39`, `Sv48x4_Sv48`, `Sv48x4_Sv57`,
  `Sv57`, `Sv57x4`, `Sv57x4_Sv39`, `Sv57x4_Sv48`, `Sv57x4_Sv57`). They do
  not skip, so on the X100 they run with translation off and their
  deliberately invalid addresses become physical accesses. Suites that
  check for a mode before using it, such as `Sv39x4_Sv48`, are not refused.

## Commands

`k3val COMMAND --help` shows each command's own options. Each command runs
one script in this directory, which can also be run directly.

| Command | Script | Purpose |
| --- | --- | --- |
| `k3val suites` | | Show the pinned suites and the refused suites |
| `k3val qemu priv\|unpriv SOURCE OUT` | `run-damo-ats.py` | Build and run a suite on workstation QEMU |
| `k3val pack SOURCE QEMU_OUT BUNDLE` | `pack-damo-x100.sh` | Pack the unprivileged ELFs for a native K3 run |
| `k3val native SOURCE OUT` | `run-damo-ats.py x100` | Run packed ELFs under Linux on the K3 |
| `k3val build-x100 SOURCE OUT` | `build-damo-k3-priv.sh` | Build the privileged suite as X100 M-mode payloads |
| `k3val board ...` | `k3-mmode-run.py` | Board runner: `preflight`, `shutdown`, `run`, `restore` |
| `k3val x100-priv BUILD OUT` | `k3-mmode-run.py run` | Run every built payload except the refused suites |
| `k3val classify TRANSCRIPTS BUILD OUT` | `classify-damo-k3-priv.py` | Turn board transcripts into verdicts |

`k3-mmode-fit.py` wraps a raw M-mode binary in the FIT the vendor SPL loads;
the build calls it for each image.

## Requirements

On the workstation: Linux, Python 3.10 or later, Git, GNU make and
coreutils `timeout`. The development runs used Fedora 44 x86_64 with QEMU
10.2.2 and Fedora's `riscv64-linux-gnu-gcc` 16.2.1.

- **Privileged images:** a RISC-V GCC cross compiler; set `CROSS_COMPILE`
  (default `riscv64-linux-gnu-`). QEMU runs use `qemu-system-riscv64`, or
  `QEMU` if set.
- **Unprivileged images:** a RISC-V Linux C++ driver with static target
  libraries, set as `CXX`. Fedora's cross GCC has no C++ driver. The
  development runs used Bootlin's
  [`riscv64-lp64d--glibc--bleeding-edge-2025.08-1`](https://toolchains.bootlin.com/downloads/releases/toolchains/riscv64-lp64d/tarballs/riscv64-lp64d--glibc--bleeding-edge-2025.08-1.tar.xz)
  toolchain (SHA-256
  `4040cd45c13ff03e8daac0ef69caf4322ed10e9843914d628b315c5dc27bf9c9`).
  QEMU runs use `qemu-riscv64-static`, or `QEMU` if set. Packing needs
  `zstd`.
- **X100 M-mode runs:** `dtc`, `fastboot`, `ssh`, a k3ctl dongle with its
  FC_REC line attached (header pin 10 on the Firefly carrier), the board's
  USB-C port cabled to the workstation, and picocom on the board's serial
  console, writing a `--logfile`. See [Board settings](#board-settings).

## Run the suites on QEMU

Use a dedicated scratch checkout and a **new** output directory each time;
`scratch/` in this repository is ignored by Git. The runner clones the
pinned revision when the source directory does not exist, and refuses a
checkout at another revision or with tracked changes.

```sh
k3val/k3val qemu priv scratch/damo-rv-priv-ats scratch/priv-qemu --jobs 4
CXX=/path/to/riscv64-lp64d--glibc--bleeding-edge-2025.08-1/bin/riscv64-linux-g++ \
  k3val/k3val qemu unpriv scratch/damo-rv-ats scratch/unpriv-qemu --jobs 12
```

Privileged suites build one at a time because they share objects. Each runs
with its upstream QEMU machine and CPU settings under TCG, with no network
or disk. The unprivileged programs run in QEMU user mode with
`-cpu max,vlen=256`, which is not an X100 CPU model. A nonzero exit after
`counts.tsv` is written means the run completed with non-passing results;
read the individual rows.

### Verdicts

A privileged suite passes only with exactly one consistent summary line, no
failed case and the framework's `RESULT: ALL PASSED` line. The verdicts are
`PASS`, `PASS_WITH_SKIPS`, `ALL_SKIPPED`, `FAIL`, `INCOMPLETE`, `TIMEOUT`,
`EMU_UNAVAILABLE` (QEMU lacks the requested CPU or feature), `BUILD_ERROR`
and `BUILD_TIMEOUT`. Declared targets without published source are listed in
`unpublished.txt` and not counted as runs.

An unprivileged program passes only if it starts, prints no `[ERROR]`,
reports all 1,000 iterations and exits with status 0. A program that logs
an error and still exits 0 is a `FAIL`. Every program uses the same nonzero
seed (`20261118`) and `--early-stop`, so this is a fixed-seed baseline, not
exhaustive coverage. The other verdicts are `RUN_ERROR`, `INCOMPLETE`,
`TIMEOUT`, `BUILD_ERROR` and `BUILD_TIMEOUT`; native runs add
`NOT_ADVERTISED` (the device tree does not advertise the extension),
`NOT_BUILT` and `IMAGE_MISMATCH`.

## Run the unprivileged suite on the X100

The native run uses the ELFs the workstation built and checked, not a
compiler on the board. `pack` takes a completed unprivileged QEMU run,
checks each ELF against its manifest and packs those ELFs, the manifest and
`run-damo-ats.py`:

```sh
k3val/k3val pack scratch/damo-rv-ats scratch/unpriv-qemu scratch/x100-input.tar.zst
```

`pack` prints the archive's SHA-256. Copy the archive to a new directory
owned by an ordinary user on the board, over SSH with a verified host key,
and check the SHA-256 there. Then, in that directory:

```sh
mkdir input && tar -I zstd -xf x100-input.tar.zst -C input
input/run-damo-ats.py x100 input evidence --jobs 1
```

Native mode runs as an ordinary user (it refuses root) and needs no
compiler, virtual machine or firmware access. It requires the
`spacemit,k3-com260-ifx` device tree with exactly CPUs 0-7 (the X100 cores)
online, pins itself to CPU 0, checks each ELF against the manifest and skips
extension families that CPU 0's device-tree node does not advertise. Copy
`evidence/` back and keep it apart from the QEMU runs.

## Run the privileged suite on the X100

Each image runs alone on hart 0 in M-mode, entered by the vendor SPL in
the boot ROM's USB download mode:

1. `k3ctl recovery` holds FC_REC through a reset, so the boot ROM enters
   USB download mode (USB ID `361c:1001`).
2. Over fastboot, `stage` and `continue` send the FSBL. The vendor SPL
   trains DDR and presents its own fastboot gadget.
3. `stage` and `continue` send the test image as a FIT whose only image is
   the test (`type = "firmware"`, `os = "u-boot"`, load and entry address
   `0x1_0000_0000`). The SPL copies it and enters it in M-mode.
4. The test prints over the console UART, then prints a halt marker and
   parks the hart. The next `recovery` starts the next image; `restore`
   resets the board back to its saved NOR boot.

### Why this path writes nothing

The basis is the vendor U-Boot source, branch `k3-br-v1.0.y` at commit
`0dcf0d83dd`, the last commit before the build date of the Bianbu K3 v4.0.1
firmware (May 21, 2026):

- In USB mode the SPL skips loading the U-Boot environment and loads the
  staged FIT after `continue` (`board/spacemit/k3/spl.c`,
  `common/spl/spl_fastboot.c`).
- The SPL keeps DDR training data in SRAM. Only U-Boot proper's
  `save_ddr_training_info()` (`board/spacemit/k3/k3.c`) writes it to NOR,
  and this path never starts U-Boot proper; the runner stops if its banner
  appears.
- `CONFIG_SPL_SMP` is off, so only hart 0 enters the image, and the SPL
  starts no watchdog.

This is source analysis for that firmware, not a guarantee for other
releases. The runner's checks for the boot ROM and SPL banners also match
that firmware's messages.

### Board settings

The board runner has no built-in workstation defaults. Give each setting as
an option or environment variable:

| Option | Variable | Value |
| --- | --- | --- |
| `--k3ctl` | `K3VAL_K3CTL` | k3ctl client; default `../k3ctl/k3ctl` beside k3val, then `PATH` |
| `--fsbl` | `K3VAL_FSBL` | `factory/FSBL.bin` from a Bianbu K3 v4.0.1 release |
| `--serial-log` | `K3VAL_SERIAL_LOG` | the file the operator's picocom writes with `--logfile` |
| `--ssh-target` | `K3VAL_SSH_TARGET` | `user@host` of the board's Linux, for `preflight`, `shutdown`, `restore` and `run --from-fedora` |

Get the FSBL from a Bianbu K3 v4.0.1 release tarball, from the
[vendor archive](https://archive.spacemit.com/image/k3/version/bianbu/).
Both `Bianbu-Minimal-K3-v4.0.1-20260521183730.tar.gz` and
`Bianbu-LXQt-K3-v4.0.1-20260521185240.tar.gz` contain it; check the tarball
against the pins in
[`k3-image-manifest.txt`](../k3-flash-bianbu/k3-image-manifest.txt), then
extract the one file:

```sh
tar -xzf Bianbu-Minimal-K3-v4.0.1-20260521183730.tar.gz ./factory/FSBL.bin
sha256sum factory/FSBL.bin
# 7991c200a80e05dde2918ab9b2194505df81df109ed99bb4703f2d0f8feab85d
```

This repository does not include the FSBL; its redistribution terms have
not been checked. SSH uses strict host-key checking, so the board's host key
must already be in `known_hosts`. `--from-fedora` and `shutdown` reboot the
board's Linux with `sudo -n systemctl reboot`, which must not need a
password.

### Commands

Build all 75 images into a new directory. The build applies the port to a
dedicated checkout at the pinned revision; it fails if the committed
`rvtest_config.h` differs from its generator's output, if an image is not
linked at the load address, is larger than 8 MiB or contains QEMU's
semihosting sequence.

```sh
k3val/k3val build-x100 scratch/damo-rv-priv-ats-k3 scratch/x100-build
```

Allow the workstation user to open the boot ROM's USB device, and stop
fwupd for the session, since its fastboot plugin queries any fastboot
device:

```sh
sudo install -m 0644 k3val/99-k3-usb-download.rules /etc/udev/rules.d/
sudo udevadm control --reload
sudo systemctl mask --runtime --now fwupd.service
```

The rule gives group `dialout` access to `361c:1001`. Then, with the board
running its Linux and the settings above exported:

```sh
k3val/k3val board preflight
k3val/k3val x100-priv --from-fedora --record scratch/events.jsonl \
  scratch/x100-build scratch/x100-transcripts
k3val/k3val board restore
k3val/k3val classify scratch/x100-transcripts scratch/x100-build scratch/x100-results
```

`preflight` is read-only: it checks the tools, the FSBL hash, that picocom
is writing the serial log, that the dongle's lines are released, and that
the board's Linux answers SSH with working `sudo -n`. `x100-priv` checks
each image against the build manifest and runs them in build order, each
with a 120-second limit (`--timeout`); `--suite NAME` runs only the named
suites. Without `--from-fedora` it starts from a board already parked in a
test image or in the SPL. `classify` applies the QEMU verdict rules, with
the halt marker in place of the simulator's exit status: no marker means
`TIMEOUT`, and an image without a transcript is `NOT_RUN`.

Afterwards, undo the workstation changes:

```sh
sudo rm /etc/udev/rules.d/99-k3-usb-download.rules
sudo udevadm control --reload
sudo systemctl unmask --runtime fwupd.service
sudo systemctl start fwupd.service
```

## The K3 X100 port

[`damo-k3-x100/`](damo-k3-x100/README.md) adapts the privileged suite to
X100 hart 0 in M-mode:

- `config/k3-x100/`: `MEM_BASE` `0x1_0000_0000` with 256 MiB of test
  memory; UART `0xd4017000` (register shift 2, 32-bit access, divisor 8,
  `IER` bit 6 kept set); CLINT `0xf1810000` with 32-bit accesses only; halt
  markers `K3-DAMO-HALT: PASS` and `K3-DAMO-HALT: FAIL`. `RVMODEL_BOOT`
  makes the X100 settings the vendor OpenSBI (`k3-br-v1.0.1`) makes before
  Linux: it sets `misa.H`, which resets to 0, `MSETUP |= 0x10073` and the
  `ML2SETUP` instruction and TLB prefetch bits.
- `rvtest_config.h`, generated from the upstream QEMU profile by
  `make-rvtest-config.py`, which drops extensions the X100 lacks and sets
  measured implementation values. A case for an extension declared absent
  skips. `SSCOFPMF_COUNT_EVENT` is not declared, so counting-dependent cases
  skip. Behavior flags that were not measured keep the QEMU profile's
  values, so a failure that depends on one is a profile question before a
  hardware one.
- `uart-ier-init.patch` gives `uart_init()` a platform `IER` value; writing
  0 disables an XScale-style UART.
- `build-portability.patch` fixes two guards without which
  `Hypervisor_Smmpm`, `Hypervisor_Smnpm`, `Hypervisor_Ssnpm` and `Ssdbltrp`
  do not compile for a platform that lacks those extensions.

## Profile probe

[`probe/`](probe/) builds `k3-probe.itb`, an M-mode program that reports
the hart's entry state and the implementation parameters the privileged
suite declares per platform, such as PMP, paging and hypervisor CSR
properties. Every CSR access is guarded by its trap handler; its few writes
are probes of fields that do not affect M-mode execution, restored at once,
plus setting `misa.H` as the vendor firmware does.

```sh
make -C k3val/probe OUT="$PWD/scratch/probe"
k3val/k3val board run --out scratch/probe-transcript --end 'K3P DONE' \
  --timeout 60 scratch/probe/k3-probe.itb
```

## Outputs and sharing

| Command | Writes |
| --- | --- |
| `qemu`, `native`, `classify` | `environment.txt`, `results.tsv` (one row per image), `counts.tsv`, `logs.zip` (one transcript per row) |
| `build-x100` | `environment.txt`, `manifest.tsv` (image hashes), `build/` logs, `itb/` payloads |
| `board run`, `x100-priv` | one serial transcript per image, and JSON events with `--record` |

Transcripts redact serial numbers and MAC addresses, but logs keep command
lines with local paths, and SSH output can include network addresses.
Review them before sharing.

## Tests

```sh
python3 -B k3val/tests/test_k3val.py
```

The tests cover the verdict rules, the refused suites, required board
settings, the fastboot allowlist, FIT creation, payload selection and
classification, without a board, QEMU or a cross compiler. They are not
hardware results.

## Licensing

The k3val tools, the probe and the udev rule are GPL-2.0-only; see
[LICENSE](../LICENSE). The port in `damo-k3-x100/` is Apache-2.0, with
upstream notices kept; see [its README](damo-k3-x100/README.md). The
runners call [k3ctl](../k3ctl/README.md) as a separate program.
