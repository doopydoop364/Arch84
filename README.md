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

## Using it

* Pipes and redirection: `cat f | grep x | sort | uniq -c > out`, `wc < f`, `tee`. Typeable on the
  calculator: `|` = x^-1 key, `<` = sin key, `\` = x^2 key (`keys` lists them).
* `edit FILE` is a small full-screen editor. CLEAR opens a command line: `w` save, `q` quit,
  `qq` quit without saving, `wq`, `N` go to line, `/text` find, `n`, `d` `y` `p` line cut/copy/paste,
  `s/old/new/` and `%s/old/new/`.
* Environment: system-wide variables live in `/etc/environment` (`USER HOME PATH SHELL HISTSIZE HISTFILE HOSTNAME`);
  `setenv NAME=VALUE`/`unsetenv NAME` change the file and the session, `export`/`unset` only the session.
* Scripts: a file on `PATH` (or run with a `/`) executes line by line with `$1..$9`, `$#`.
* `.ar84` packages: `makepkg [-d DEP] DIR NAME VERSION [DESC]` packs a staging tree (DIR mirrors `/`) into
  `/var/cache/pacman/pkg/NAME-VERSION.ar84`; `pacman -U FILE` installs, `-S NAME` installs from that
  repository with dependencies, `-R` removes, `-Q`/`-Qi`/`-Ql`/`-Qk`/`-Qo`/`-Qp` query and verify, `-Sl`/`-Ss`/`-Si` list, search and describe the
  repository (index `/var/lib/pacman/sync/repo.db`, rebuilt by `-Sy` or when stale), `-Su`/`-Qu` upgrade/list
  upgradable, `-Sc`/`-Scc` clean the cache, `-Rs`/`-Rns` remove with unneeded dependencies, `-Qe -Qd -Qt -Qdt`
  list explicit / dependency / unrequired / orphan packages. Dependencies may carry versions (`makepkg -d 'lib>=1.2'`;
  quote them, `>` is a redirect). Changing operations hold `/var/lib/pacman/pacman.lock` (stale after a power cut: `fsck -r` or `rm`).
  Format and rules: header of `A84PM.py`.
* `archive create NAME PATH...` packs files/dirs into compressed calculator lists and removes them from RAM
  (frees the Python heap, which is what limits the filesystem; Python cannot reach the flash Archive itself);
  `archive extract [-k] NAME`, `archive list`, `archive check`, `archive delete NAME`. Needs ~25 KB of free
  heap to run. `fsck [-r]` checks the saved copy, archives, packages and system files and clears leftover lists.
* `man COMMAND` (or `help COMMAND`) shows a page for every command; `man -k WORD` searches.
* Also: `;` `&&` `||`, `mkdir -p`, `cp -r`, `ls -l`, `cut tr nl seq`, `test`/`[`/`expr`, generated `/proc`
  (`meminfo uptime version mounts modules`) and `/dev/null`.
