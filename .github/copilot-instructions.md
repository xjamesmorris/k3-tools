# Agent-assisted contribution policy

Read [AGENTS.md](../AGENTS.md) and the [LLM policy](../LLM-POLICY.md) before
working on contributions. They provide the tool-independent requirements for
human authorship, review, attribution, sign-off, and publication.

# Repository purpose

This repository is a public collection of tools for developing, testing and
recovering **SpacemiT K3** boards, tested with a K3-CoM260 on a Firefly
carrier. The root `README.md` introduces each tool and links to its own
README, which carries usage, safety limits and recorded hardware results.
Board notes, hardware findings and the Fedora developer wiki live in
`xjamesmorris/k3-com260-info`; these tools moved here from its `tools/`
directory, with their history, on 2026-11-19. Keep facts that appear in both
repositories consistent.

Keep module-level facts separate from carrier-specific details: the existing
recovery-header pin assignments and procedures describe the Firefly carrier.
Do not generalize results to other K3 modules or carriers without evidence.
Hardware findings should identify the relevant carrier and firmware/image
version and distinguish observed results, vendor guidance, and untested ideas.
Public instructions must not depend on unpublished notes or files elsewhere
on the maintainer's machine.

Pushes, releases and repository settings are separate human-authorized
actions. A local commit or a passing check authorizes neither publication nor
a new hardware result.

# k3ctl

`k3ctl/` holds the ESP32-C3 dongle firmware, a standard-library Python client,
a udev rule, logo tooling and hardware-free tests. `k3ctl/README.md` is the
authority for wiring, recorded results and limits.

```sh
# Hardware-free client tests against a fake dongle on a pseudo-terminal
python3 -B k3ctl/tests/test_k3ctl.py

# Firmware builds (arduino-esp32 core 3.x; U8g2 for the default OLED build)
FQBN=esp32:esp32:esp32c3:CDCOnBoot=cdc,FlashSize=4M
arduino-cli compile --fqbn "$FQBN" k3ctl/firmware/k3ctl
arduino-cli compile --fqbn "$FQBN" --build-property "build.defines=-DK3CTL_OLED=0" k3ctl/firmware/k3ctl
```

Never send a board-control command (`reset`, `recovery`, `power`, `press`,
`hold`) or upload firmware as an automated check. Host tests and builds are
not hardware results; an `OK` reply acknowledges a dongle command, not a K3
state change. New hardware results need an attended test recording the
module/carrier, K3 firmware/OS, exact ESP32 source/build and dependency
versions, date, commands, observed outcome and failures.

# k3val

`k3val/` runs architecture test suites, starting with XUANTIE-RV's DAMO
suites at pinned revisions, on QEMU and on the K3 X100. `k3val/README.md`
is the authority for its procedures and safety basis. Keep these invariants:

- The board runner (`k3-mmode-run.py`) sends only fastboot `getvar`,
  `stage` and `continue`, stops if vendor U-Boot proper's banner appears,
  never types on the serial console (it reads the picocom log), keeps the
  FSBL SHA-256 pin and strict SSH host-key checking, and refuses every suite
  in `X100_NEVER_RUN` before touching the board. Do not add workstation
  defaults for its board settings.
- Builders clone the upstream suites at pinned revisions; do not copy the
  suites into this repository, and do not commit vendor firmware such as
  `FSBL.bin`.
- `damo-k3-x100/` keeps upstream notices. The build requires
  `config/k3-x100/rvtest_config.h` to equal `make-rvtest-config.py`'s output
  and records SHA-256 values of the patches and config files, so changing
  them changes recorded build identities.
- Keep QEMU results apart from K3 results, and keep host tests and builds
  apart from hardware results. Publishing test results is a separate human
  decision.

```sh
# Hardware-free tests
python3 -B k3val/tests/test_k3val.py

# Shell and Python checks
bash -n k3val/pack-damo-x100.sh k3val/build-damo-k3-priv.sh
shellcheck k3val/pack-damo-x100.sh k3val/build-damo-k3-priv.sh
```

A QEMU run (`k3val/k3val qemu priv SOURCE NEW_OUT`) builds and runs all 75
privileged images without hardware. Never run `board`, `x100-priv` or
`native` commands as automated checks.

# Existing flashing tool architecture

`k3-flash-bianbu/k3-flash-bianbu.sh` is a standalone Bash factory-flashing
tool, tested on the K3-CoM260 with a Firefly carrier. It replaces the
TitanFlasher GUI with stock `fastboot`.

- `k3-flash-bianbu/README.md` documents usage, prerequisites, troubleshooting,
  hardware results, and contribution requirements.
  `k3-flash-bianbu/k3-flash-bianbu-HANDOFF.md` records measured protocol
  behavior, design rationale, and unimplemented ideas.
- The release tarball's `fastboot.yaml` is the authority for the flash recipe.
  The script translates it manually; it does not parse YAML. Partition selection
  currently uses the CoM260-specific `partition_4M.json` and
  `partition_universal.json`, rather than the vendor's dynamic size probes.
- Input handling converges from HTTPS URL to local archive to extracted image
  directory. Registration exits before extraction; `--check` exits after
  preflight and before device traffic. Flashing then performs RAM bootstrap,
  EC firmware update, partition-table writes, and NOR/UFS payload writes.
- `k3-flash-bianbu/k3-image-manifest.txt` supplies release pins independently
  of the script. Add releases through the manifest rather than hardcoding them
  in Bash.

# Flashing tool commands

Run these from the repository root:

```sh
# Bash syntax check
bash -n k3-flash-bianbu/k3-flash-bianbu.sh

# Lint (the contribution docs require ShellCheck-clean changes)
shellcheck k3-flash-bianbu/k3-flash-bianbu.sh

# Single-image preflight: use an existing extracted release
bash k3-flash-bianbu/k3-flash-bianbu.sh --check /absolute/path/to/release-directory

# Single-archive preflight: includes verification, extraction, and content checks
bash k3-flash-bianbu/k3-flash-bianbu.sh --check /absolute/path/to/release.tar.gz

# Register a release: validates the archive and modifies the adjacent manifest
bash k3-flash-bianbu/k3-flash-bianbu.sh --register-image /absolute/path/to/release.tar.gz
```

`--check` works without a board or `fastboot` installed, but may download and
extract multi-GB images; it is not a side-effect-free command preview. Archive
extraction requires free space of at least five times the compressed file size.
The script uses Bash and GNU/Linux utilities, including GNU `stat`/`df`,
`sha256sum`, `tar`, and `timeout`; URL input additionally requires `curl`.

Normal invocation **erases NOR firmware and all UFS contents**, including the
environment; NVMe is untouched. Never use a real flash as an automated check.
Changes to the flash sequence require a hardware result recorded in the PR,
including the image used and observed outcome. Keep manifest-pinned status
separate from successfully flashed/booted status in the documentation.

# Flashing tool conventions and invariants

- Resolve resource paths from `BASH_SOURCE[0]`, not the caller's working
  directory: the script later changes into the image directory. The manifest
  and extraction area are adjacent to the script
  (`k3-flash-bianbu/images/<release>/`); default downloads are in
  `downloads/` at the repository root. Both generated directories are
  gitignored.
- Preserve `set -euo pipefail`, fatal diagnostics through `die()`, and progress
  through `step()`. Expected failures must be handled explicitly.
- `REQUIRED` is shared by archive registration and extracted-content preflight.
  Keep it aligned with every flash payload. Registration checks member names;
  extracted-content checks require each file to be non-empty before any
  fastboot traffic.
- Manifest records are `sha256 size-bytes archive-filename`, with blank lines
  and `#` comments allowed. The basename is the key. Validate the entire
  manifest, rejecting malformed records and duplicate names. Known archives
  must match size first, then SHA-256; unknown names warn and receive a member
  path scan before continuing. Re-registering a known name verifies rather
  than duplicates or overwrites its pin.
- Downloads require HTTPS across redirects. Downloads and extractions use
  hidden `.partial` paths, EXIT cleanup traps, and rename-on-success.
  Reusing an extraction requires a matching archive hash in
  `.k3-extracted-from`, followed by content checks. Preserve failed-flash
  extractions for retry; `--rm` removes only script-created extractions after
  successful flashing, never the source archive or a user-supplied directory.
- Detect BootROM with a timeout-bounded `getvar version-brom` probe. Bootstrap
  stages FSBL, then U-Boot, with `continue` and a readiness probe after each.
  USB readiness requires a real `getvar` response, including remote `FAILED`;
  fixed sleeps or `fastboot devices` alone are unreliable. A remote failure
  of the initial BootROM probe means loaders are already staged.
- EC stage/flash refusals are deliberately non-fatal, matching vendor
  `skip_fail`; do not extend that exception to partition or payload writes.
  NOR uses `factory/bootinfo_spinor.bin`, not the block or SPI-NAND variants.
  Do not add an `esp` flash target: the universal layout stores ESP contents
  inside `bootfs`.
- Keep CLI behavior and hardware findings synchronized with
  `k3-flash-bianbu/README.md` and the tool's handoff. The handoff's
  development ideas are proposals, not implemented options or established
  hardware results.
