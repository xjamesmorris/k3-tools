<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Agent-assisted contributions

This is the entry point for external agents assisting a human contributor,
regardless of the tool or provider. Before working, read the
[project overview](README.md), [LLM policy](LLM-POLICY.md), and
[shared tool guidance](.github/copilot-instructions.md).

## Human ownership

An LLM is a tool, not an autonomous contributor or maintainer. The human is
the author responsible for reviewing, understanding, and publishing the
assisted material. Prepare work for that review; generated code or another
agent's approval does not replace it. Follow the LLM policy's disclosure,
sign-off, and publication requirements.

## Working in this repository

- Keep changes proportionate to this collection of K3 board tools. Each
  tool's README carries its usage, safety limits and recorded results.
- Check the branch and worktree before editing. Preserve unrelated changes,
  and stay within the human contributor's requested scope.
- Board notes and the Fedora developer wiki live in
  [k3-com260-info](https://github.com/xjamesmorris/k3-com260-info). Keep
  facts that appear in both repositories consistent, and use public sources
  rather than depending on unpublished files on an operator's machine.
- Preserve recorded hardware observations. Do not rewrite tested procedures,
  workarounds, release pins, or hardware results based on speculation.
  Distinguish observations, vendor guidance, and untested ideas.
- Identify the module, carrier, firmware or image version, and what was
  actually tried. Firefly carrier wiring and results must not be generalized
  to other carriers without evidence.
- Preserve imported patch authorship, licenses, trailers, and provenance.
  Identify the target project and revision; do not alter pinned patch bytes
  merely to satisfy formatting checks.

## Validation and safety

Use the relevant existing checks and report their limits. For modified Bash
scripts, run `bash -n` and `shellcheck`; for k3ctl and k3val, run their
hardware-free tests. Consult each tool's README for its requirements. Do not
equate syntax checks, hashes, builds, host tests, or patch replay with
successful hardware operation.

Never flash a board, overwrite a disk, change its boot environment, or reset,
power-cycle, or reboot it as an automated contribution check. Such work needs
the human operator's explicit approval and supervision. The flashing tool's
`--check` can download and extract large images; it is not a side-effect-free
command preview.

## Handoff

For maintainer-facing findings, provide detailed, actionable information:
exact test conditions, code changes, inspectable artifacts, results,
failure chronology, and unresolved questions. Preserve evidence and privacy
limits; a high-level status summary alone is not enough.

Give the human author the changed paths, a reviewable diff, the checks
actually performed, and any unresolved questions or untested behavior.
Never invent observations, test results, citations, or human endorsements.
Leave publication to the human author as required by the LLM policy.
