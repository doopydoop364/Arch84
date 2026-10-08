# Arch84 progress report (campaign + feature work)

All numbers come from the **emulator** (32-bit MicroPython 1.20 unix port, 127 800-byte heap, shims for
`ti_system`/`ti_draw`). Nothing here has been run on a real TI-84 Evo; host timings are relative only.

## 1. Engineering campaign (bugs, memory, speed)
Details and the before/after table: `docs/OPTIMIZATION_CAMPAIGN.md`.
* Bugs fixed: names > 255 bytes poisoning sync; unstable `sort -n`; doubled quote in tab completion;
  startup hang on tick-counter wrap; out-of-memory in the post-save compare aborting a finished save;
  `rm -f/-fr/--`; reboot keeping the old session alive (GC pin); `cp -r /` infinite loop; half-imported
  modules after a MemoryError; shell dying when its own out-of-memory message ran out of memory;
  archive extract/create ordering problems; `exit` retried forever when it kept failing after input ended.
* Memory/speed: fixed-size LZSS hash table, in-place block writer, float-based 40-bit packing, frugal
  verify, retry-after-GC on load/sync, lazy command modules that evict/unload themselves.

## 2. Features added
| Area | What |
|---|---|
| Shell | pipes `\|`, `<` stdin, `;` `&&` `\|\|`, scripts with `$0-$9`/`$#`, typeable `\| < \ ; &` |
| Editor | `edit FILE` full-screen editor with undo |
| Commands | `uniq tee cut tr nl seq test [ expr sed rev uname whoami hostname which keys selftest man`, `mkdir -p`, `cp -r`, `ls -l`, `head/tail -N`, `grep -r/-l`, `sed $` addresses |
| Packages | `.ar84` format, `makepkg`, `pacman -U -S -R -Q[ilkop]`, rollback on failure, checksums |
| pacman (latest) | `pacman.lock`, repo index `repo.db` (`-Sy -Ss -Si -Sl`), `-Su/-Qu` upgrades, fsck stale-lock check |
| Archive | `archive create/extract/list/check/delete` moves files into compressed calculator lists (off the Python heap) |
| System | `fsck [-r]`, generated `/proc` and `/dev/null`, man pages generated from `docs/manpages.txt` |

## 3. Verification
`python3 emu/run_all.py` (gate used before every push to main): 11 unit-test modules, CPython==MicroPython
differential fuzzers (shell x60, packages, archive, codec), key fuzz (normal and 103 KB heap), command
fuzz (`emu/cmdfuzz.py`), editor / archive on the emulated device, power-cut sweep, leak check. Last gate: ALL OK
at `39cc942`.

## 4. Memory (emulator, 127 800-byte heap)
Free at prompt ~44.6 KB (original 48.7 KB: the resident cost of pipes/lists/scripts/lazy table);
strict save-reload-resave capacity ~112 small files. Features beyond the core are lazy and need free heap
to load (archive ~25 KB).

## 5. Not done / caveats
* Real hardware: nothing verified.
* Git tag/GitHub release for 0.0.7 could not be pushed from this environment (`docs/RELEASE_0.0.7.md`).
* Ideas left: `yes`/background jobs, users/ownership, init/services, journal.
