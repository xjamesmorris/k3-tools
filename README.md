<!-- SPDX-License-Identifier: GPL-2.0-only -->

# k3-tools

Tools for developing, testing and recovering
[SpacemiT K3](https://www.spacemit.com/) RISC-V boards. They were developed
and tested with a **K3-CoM260** module on a Firefly carrier board. Other K3
modules and carriers have not been tested.

Board notes, hardware findings and the Fedora developer wiki are in
[k3-com260-info](https://github.com/xjamesmorris/k3-com260-info). k3ctl and
k3-flash-bianbu moved here from its `tools/` directory on 2026-11-19, with
their history.

| Tool | Purpose | Hardware status |
| --- | --- | --- |
| [`k3ctl`](k3ctl/README.md) | Control header buttons over USB using an ESP32-C3 dongle | **Reset, bounded button-power results and logo screensaver observed**; software-shutdown wake remains unresolved |
| [`k3-flash-bianbu`](k3-flash-bianbu/README.md) | Factory flash an official Bianbu K3 release using stock `fastboot` | See the [image results](k3-flash-bianbu/README.md#status); a manifest pin is not a flash result |
| [`k3val`](k3val/README.md) | Run architecture test suites on QEMU and the K3 X100, starting with XUANTIE-RV's DAMO suites | Tool only; no results are published here yet |

## k3ctl: USB button control

[`k3ctl/`](k3ctl/README.md) contains the ESP32-C3 firmware, a standard-library
Python client, a Linux udev rule, and tests against a fake dongle on a
pseudo-terminal. Its guide covers the conditional Firefly header wiring,
firmware build requirements, host setup, command protocol, and GPL-2.0-only
licensing.

**Reset is maintainer-reported working. Power-button behavior depends on the
jumper and off state.** Earlier October 30-31 power-on failures remain
recorded. In the November 6-7 attended firmware 1.1 test with pins **5/6
bridged**, DC insertion left the K3 off; a **300 ms** press powered it on.
The same press worked after forced power-off, but failed after software
shutdown. Removing/reconnecting DC, then pressing for 300 ms, restored
power-on. While running, 300 ms, 1 s, 3 s and 6 s left it on; **12 s cut
power abruptly**, not as a clean shutdown. See the
[recorded results and limitations](k3ctl/README.md#recorded-hardware-results).
Do not change the jumper with DC connected or generalize this result to
another carrier or firmware.

The 1.1.1 bright-then-dim moving logo and event-reset countdown were observed
on the dongle. On 2026-11-17, `recovery` entered BootROM USB mode once on a
halted board (`version-brom: 1.0`); with its wire unattached it only reset
the board. Power sensing, the sensed `ON` display,
external LED/DC switch and named `power on|off|force-off` modes remain
unverified; client/build checks are not hardware evidence. Reset and forced
power-off can lose unsaved data.

k3ctl is a standalone tool, not a Fedora installation prerequisite.
`k3-flash-bianbu.sh` does not invoke it and has no `-r` option; keep the
documented manual recovery procedure for factory flashing, since no flash
has followed a k3ctl recovery entry.

## k3-flash-bianbu: factory flashing

[`k3-flash-bianbu.sh`](k3-flash-bianbu/README.md) factory-flashes a board
from an official Bianbu K3 release tarball using stock `fastboot`, in place
of the vendor's TitanFlasher GUI. It follows the release's own
`fastboot.yaml` recipe and verifies the archive against
[pinned checksums](k3-flash-bianbu/k3-image-manifest.txt) before writing.

**Factory flashing erases NOR firmware and all UFS contents**, including the
environment; an attached NVMe drive is not touched. Read the
[documentation](k3-flash-bianbu/README.md) before using the script. The
[development context](k3-flash-bianbu/k3-flash-bianbu-HANDOFF.md) records
protocol findings, design decisions and ideas for further work.

## k3val: architecture test runs

[`k3val/`](k3val/README.md) builds and runs XUANTIE-RV's DAMO RV64
privileged and unprivileged architecture suites, at pinned revisions, on
workstation QEMU and on the K3's X100 cores. Unprivileged programs run under
Linux on the board. Privileged tests run as M-mode RAM payloads, entered by
the vendor SPL in the boot ROM's USB download mode through k3ctl, so nothing
is written to the board's storage. It includes a K3 X100 port of the
privileged suite and an M-mode profile probe.

## Safety

- Reset, power, recovery and flashing act on real hardware. Use them only
  when someone is at the board, its serial console is attended, and its
  power can be removed by hand.
- An `OK` reply from k3ctl acknowledges a dongle command. It does not show
  that the K3 reset, powered on or entered recovery; the K3's own serial
  console does.
- Results recorded here apply to the K3-CoM260 on a Firefly carrier with
  the stated firmware and software. Do not generalize them to other carriers
  or modules without evidence.

## Contributing

Corrections, patches and additional hardware results are welcome. Include
the module, carrier, relevant firmware or OS versions, and what you tried.
Changes to a board-facing sequence need an attended hardware test, recorded
in the pull request with what was run and what happened. Host tests and
builds are not hardware results.

Agent-assisted contributions must follow the [agent guidance](AGENTS.md) and
[LLM policy](LLM-POLICY.md), which adopts the Linux kernel's requirements.
An LLM is a tool: the human contributor remains the author responsible for
reviewing, understanding, and publishing the assisted material.

## History

The history of these tools up to k3-com260-info commit
[`7e8c58f`](https://github.com/xjamesmorris/k3-com260-info/commit/7e8c58f1308b822c857204ba600238e9699e3947)
was imported with `git filter-repo`, keeping only their files. Those commit
messages describe the original repository and may mention files, pages or
commits that are not here.

## License

GPL-2.0-only. See [LICENSE](LICENSE). The K3 X100 port in
[`k3val/damo-k3-x100/`](k3val/damo-k3-x100/README.md) keeps the licenses of
the upstream files it derives from: Apache-2.0, BSD-3-Clause and
BSD-3-Clause-Clear, with their texts in [`LICENSES/`](LICENSES/).
