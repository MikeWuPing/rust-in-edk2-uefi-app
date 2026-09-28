# Rust-in-EDK2 UEFI Application Skill

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Skill](https://img.shields.io/badge/WorkBuddy-Skill-blue.svg)](https://www.workbuddy.cn/docs/workbuddy/Overview)

> Write the **application logic** of a UEFI app in Rust and keep graphics and
> firmware plumbing on the C side (EDK2 + LVGL). This skill records every trap
> on that road — above all the ones that never raise an error and are simply,
> quietly wrong.

[简体中文](README.md) | English

## Overview

There are two ways to write a UEFI application in Rust:

1. **Pure Rust** — use the `uefi` crate (rust-osdev/uefi-rs); cargo emits the
   `.efi` directly and EDK2 is not involved.
2. **Hybrid (this skill)** — Rust produces a static library and **EDK2 acts as
   the top-level linker**; rendering goes through LVGL (C).

The second route buys you the whole set of conventions an existing EDK2 tree
already has: DSC/INF, third-party C packages, the serial version-assert channel,
a vendored OVMF. The price is serving three toolchains at once (cargo, EDK2
build, QEMU), each with its own unpleasant failure modes.

This skill is not a tutorial. It is a list of **concrete, executable
countermeasures**, each with the reason it blows up.

### This came out of a project that actually runs

Nothing here is armchair reasoning. Every section was extracted from
[rustpaint](https://github.com/MikeWuPing/rustpaint) — a paint application that
runs under the UEFI Shell (Rust logic + EDK2 linker + LVGL 9.2.2 + a Chinese
UI), verified on QEMU up to v0.1.0.24. Its C/Rust ABI boundary today is
**58 functions and 50 constants**, all in agreement.

## Features

- **Three hard link rules** — `/NODEFAULTLIB` makes `/DEFAULTLIB:` a no-op, the
  library name must not equal `BASE_NAME`, and the `[Binaries]` section does not
  take part in linking
- **Build environment repair** — a missing UCRT in `INCLUDE` kills every C file
  at `<stddef.h>`; `GenFw` invoked by bare name is not found
- **PowerShell 5.1 traps** — comment encoding that eats line endings, native
  stderr redirection, `Start-Process` crashing on a duplicated `Path`/`PATH`
- **QEMU launch matrix** — only one spelling gives you both a window on the
  desktop and output captured to disk
- **QMP loop** — `screendump` capture (SDL window grabs come out black), pointer
  injection, and the `os.kill` trap on Windows
- **Silent LVGL traps** — 888 pixels are **B,G,R**; CJK font coverage must be
  read from the cmap; children are not clipped by default
- **ABI drift check** — ships `check_abi.py`, turning "keep the C header and the
  Rust declarations in sync" from a rule into an executable check

## Layout

```
rust-in-edk2-uefi-app/
├── LICENSE
├── README.md
├── README_EN.md                           this file
└── Skills/
    └── rust-in-edk2-uefi-app/
        ├── SKILL.md                        the skill itself (278 lines, single file)
        ├── evals/
        │   └── evals.json                  10 evaluation cases
        └── templates/
            └── check_abi.py                C header <-> Rust extern agreement check
```

## Installation

### Method 1: copy

```bash
# WorkBuddy
mkdir -p ~/.workbuddy/skills/rust-in-edk2-uefi-app
cp Skills/rust-in-edk2-uefi-app/SKILL.md ~/.workbuddy/skills/rust-in-edk2-uefi-app/

# Claude Code
mkdir -p ~/.claude/skills/rust-in-edk2-uefi-app
cp Skills/rust-in-edk2-uefi-app/SKILL.md ~/.claude/skills/rust-in-edk2-uefi-app/

# Windows (cmd)
mkdir "%USERPROFILE%\.workbuddy\skills\rust-in-edk2-uefi-app"
copy Skills\rust-in-edk2-uefi-app\SKILL.md "%USERPROFILE%\.workbuddy\skills\rust-in-edk2-uefi-app\"
```

Copy `templates/` as well if you want the companion script.

### Method 2: git clone

```bash
git clone https://github.com/MikeWuPing/rust-in-edk2-uefi-app.git

# Linux/macOS
cp -r rust-in-edk2-uefi-app/Skills/rust-in-edk2-uefi-app ~/.workbuddy/skills/

# Windows (cmd)
xcopy /E /I rust-in-edk2-uefi-app\Skills\rust-in-edk2-uefi-app "%USERPROFILE%\.workbuddy\skills\rust-in-edk2-uefi-app"
```

## Quick start

Once installed, just ask. Examples that trigger it:

```
I want to write a UEFI Shell app in Rust but keep using LVGL for graphics. How should I structure it?
My Rust staticlib fails to link inside EDK2 with a wall of LNK2001. Why?
How do I drive QEMU from a script to screenshot my .efi and inject mouse input?
I write 888 pixels as RGB in LVGL and the colours come out swapped. Why?
My Chinese text is all boxes. How do I check what the font actually covers?
```

## Contents

| Section | Topic |
|---------|-------|
| 0 | The UEFI Shell is language-agnostic: PE/COFF + `EFI_APPLICATION` is all it checks |
| 1 | Architecture: Rust emits a static library, EDK2 links |
| 1.1 | A shim boundary needs a checker script, not just a rule |
| 2 | Three hard link rules (`/NODEFAULTLIB`, `BASE_NAME` collision, `[Binaries]`, Version.h not forcing a rebuild) |
| 3 | Build environment (missing UCRT, bare `GenFw`, bootable QEMU disk) |
| 4 | Four PowerShell 5.1 traps |
| 5 | Launching QEMU from PowerShell: only one spelling works |
| 6 | Three QMP capture traps |
| 7 | Token design for automated interaction |
| 8 | Silent LVGL traps: B,G,R order, cmap coverage, no child clipping, right-align discipline |
| 9 | Acceptance checklist (leave evidence for every item) |
| 10 | Debugging order |
| Appendix | Click coordinates can be computed, not guessed |

## When it triggers

- Application logic in Rust, rendering/firmware layer in C (EDK2 + LVGL)
- Linking a cargo `staticlib` into an EDK2 module
- A Rust `.efi` that must run as a plain `EFI_APPLICATION` under the classic UEFI Shell
- A Chinese UI on LVGL (font coverage checks)
- Driving QEMU from Windows PowerShell (launch + QMP capture/pointer injection)

**Not for:** pure-Rust UEFI firmware (use the `uefi` crate and emit `.efi`
directly); pure-C EDK2 applications.

## Companion script: check_abi.py

With a hand-written C ABI shim, the header and the Rust `extern` block are twin
declarations, and manual syncing always drifts. **The two kinds of drift are not
equally dangerous**:

| Missed change | Consequence |
|---------------|-------------|
| A function declaration | `LNK2001` at link time. Loud. Easy. |
| A **constant** | **No error at compile or link time.** Silently reads a wrong value at run time. |

Usage:

```bash
# Default layout: script in <repo>/tools/, header and ffi.rs located automatically
python check_abi.py

# Other projects: point it at the files and give the prefix
python check_abi.py --header path/to/shim.h --ffi path/to/ffi.rs --prefix RP_

# Both sides use identical constant names
python check_abi.py --prefix ''

python check_abi.py --verbose     # list every symbol
```

Exit codes: `0` in agreement, `1` drift, `2` file missing. Hook it into the very
front of the build (before cargo); skip rather than fail when python is not on
PATH.

> When you write a checker like this, **inject a fake drift and confirm it is
> caught**. If both sides parse to zero symbols the script also "passes" — a
> false green.

## Quick reference

| Task | Key point |
|------|-----------|
| Rust static library | `crate-type = ["staticlib"]`, `no_std`, `panic = "abort"`, target `x86_64-unknown-uefi` |
| Link into EDK2 | Library as an **input file**; `/DEFAULTLIB:` does nothing; name ≠ `BASE_NAME` |
| Entry return type | Carry `EFI_STATUS` in `UINT64`; truncating to 32 bits turns errors into a success-looking `0x00000002` |
| INCLUDE repair | Enumerate MSVC/SDK dirs yourself, verify with `Test-Path <dir>\ucrt\stddef.h`, override **after** `edksetup.bat` |
| Launch QEMU | `cmd /c "start /b qemu.exe ... > out.log 2>&1"` |
| Capture frames | monitor `screendump` (SDL window grabs are black); sniff the magic to confirm PPM |
| Pointer injection | Dragging only works with relative moves; absolute positioning for exact hit checks |
| Pixel writes | 888 is **B,G,R**; row stride from `stride`, not `w*3` |
| Font coverage | Parse the cmap; in a SPARSE table `unicode_list` holds **relative offsets**, not codepoints |

## Related

- [rustpaint](https://github.com/MikeWuPing/rustpaint) — the project this skill came from
- [EDK2](https://github.com/tianocore/edk2) — the UEFI reference implementation
- [uefi-rs](https://github.com/rust-osdev/uefi-rs) — the pure-Rust application wrapper
- [Patina](https://github.com/OpenDevicePartnership/patina) — Microsoft's Rust UEFI firmware framework
- [LVGL](https://github.com/lvgl/lvgl) — the graphics library used here (9.2.2)
- [UEFI specification](https://uefi.org/specifications)

## Contributing

Issues and pull requests are welcome — especially **new traps**, since the whole
value of this skill is that things here actually blew up. Please include:

1. The error, or the symptom when there is no error (those matter most)
2. The root cause
3. An executable fix

1. Fork this repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit (`git commit -m 'Add some amazing feature'`)
4. Push (`git push origin feature/amazing-feature`)
5. Open a pull request

## License

[MIT](LICENSE).

---

**Note:** `SKILL.md` is meant to be auto-loaded by an AI coding assistant
(WorkBuddy, Claude Code, etc.) during a session.
