# Repository Guidelines

## Project Structure & Module Organization

Arch84 is an Arch-inspired shell and filesystem for the TI-84 Evo. `ARCH84.py` launches root-level `A84*.py` modules. Lazy commands are registered in `A84CD.py` (`MODS`/`LAZY`); add new modules to `deploy.py`'s `MODULES` list too. Root-level `test_*.py` files cover desktop behavior; `emu/` holds the MicroPython harness, `tools/` holds USB utilities, and `repo/src/` holds demo packages. Read `README.md`, recent `ARCH84_DEVLOG.md` entries, and relevant `docs/` pages before device changes.

## Build, Test, and Development Commands

No general build or pip setup is needed. Run focused desktop tests, for example `python3 test_storage.py` or `python3 test_net.py`. Run `python3 emu/run_all.py --quick` for a shorter gate or omit `--quick` for the full gate; set `A84_MICROPYTHON` to the 32-bit MicroPython binary described in `emu/README.md`. Run `python3 tools/genman.py --check` when changing man pages; inspect `tools/gen_selftest.py` when changing self-tests. Preview transfers with `python3 deploy.py --dry-run`.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` functions, `A84XX.py` module names, and `test_<feature>.py` tests. Follow nearby compact Python style; no formatter or linter is configured. Keep modules small enough to compile in the fragmented heap. Device persistence uses `ti_system` lists; `open()` returns `None` and `os` is absent. Detect desktop Python with `sys.implementation.name == "cpython"`, not a check for `"micropython"` on the device. Never modify the gitignored `evo_usb.py`, leave debug prints in modules, or put temporary files in the repository root.

## Testing Guidelines

Desktop tests use `unittest` classes and `test_` methods. Add focused regression tests, then run affected files and the emulator gate for device-facing work. `test_vm_pressure.py` needs small-heap MicroPython. On hardware, run `selftest 2` from a fresh boot; reboot after self-test before other commands. There is no coverage threshold.

## Calculator and USB Operations

Use the shared USB lock through `tools/evo`, `tools/type.py`, or `deploy.py`; never call `evo_usb.py` directly. Check screenshots between key sequences. Deploy experimental builds with `python3 deploy.py --archive-modules --no-bak`, then verify on the calculator. Keep Archive `*BAK` copies and refresh them with a plain `--archive-modules` deploy only after verification. USB transfers close a running Python app, so exit it before deploying.

## Commits & Pull Requests

Commit and push only when the user asks; ask before pushing to `main`. Use a short, descriptive subject, often with a subsystem prefix (`A84VM: ...`). For agent-authored commits, use the actual agent's `Co-Authored-By` attribution and session footer when available. Pull requests should summarize behavior, tests, device or heap impact, related issues, and screenshots for visible UI changes.
