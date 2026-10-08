# Arch84

An Arch Linux-inspired CLI operating environment for the TI-84 Evo, written in
Python (MicroPython on the calculator). Not Linux; it reproduces the Arch-style
filesystem layout, shell workflow, fish-like completion and (planned) package
management on top of a small persistent VFS.

* `ARCH84.py` launcher; `A84*.py` the system, split into small modules so each one
  compiles within the calculator's tiny Python heap (see `ARCH84_DEVLOG.md`).
* `test_*.py` desktop tests (`python3 test_arch84.py`, `test_storage.py`,
  `test_bigfiles.py`, `test_deploy.py`); the `selftest` command runs checks on the device.
* `deploy.py` sends the modules to the calculator (plus Archive backups, `<name>BAK`).

Deploying needs `evo_usb.py` from https://github.com/Evo-Programming/evo_usb_py placed in this
folder (it is not part of this repository).
