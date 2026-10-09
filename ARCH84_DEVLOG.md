# Arch84 development log

Single-file source: `ARCH84.py`. Local tests: `python3 test_arch84.py`
(fake `ti_system`, desktop CPython 3.14 -- proves logic only, NOT calculator
compatibility). No MicroPython / mpy-cross was available locally.

Honest note on process: the code was written in one pass and the milestones
below are *feature groups*, not separately-tested snapshots. The pre-existing
0.0.2 file (VFS + `input()` shell) was the starting point; its VFS was reworked
to raise `VFSError` with real messages instead of returning booleans.

## 0.0.2-dev -- VFS foundation
- In-memory VFS (`VFS`, `Node`), default layout incl. `/etc/hostname`, `/etc/version`.
- `normalize()`: absolute/relative, `.`, `..`, `~`, clamps `..` at `/`.
- API: get/exists/isdir/isfile/mkdir/touch/write/append/read/listdir/remove/rename.
- Commands: help clear pwd ls cd mkdir touch cat echo rm uname whoami hostname exit.
- Tested: path normalization table, default layout, all VFS ops + error cases.

## 0.0.3-dev -- line editor
- `LineEditor` is a pure state machine (`feed(keyname)`), `TiTerm` draws it.
- left/right/home/end, backspace, delete, clear-line, history up/down
  (prefix search, newest first), autosuggestion shown on the hint row,
  accepted with Right at end of line.
- Tab completion: commands, paths (dirs get `/`, hidden files only when prefix
  starts with `.`), common-prefix extension, then cycling with `[current]`
  marked on the hint row. Mid-line completion works.
- Key names are NOT documented anywhere in this repo. Defaults in
  `DEFAULT_BINDS` (`left right up down enter del clear tab home end pgup pgdn`)
  are GUESSES. `keytest` shows what `get_key()` really returns and
  `bind NAME ACTION` remaps (persisted in `/etc/keymap` after `sync`).
  Ints from `get_key()` are named by `str(k)` (e.g. `bind 105 enter`,
  `bind 22 ins:q`).
- Startup asks `Enter=editor k=keytest p=plain`; `p` is the pure
  `input()` fallback so the shell is always usable.

## 0.0.4-dev -- parser
- Quotes ('..' literal, ".." expands vars), backslash escape, `$VAR`, `${VAR}`,
  `$?`, `~` at word start, `>` and `>>` (one per line), `#` comments,
  aliases (`alias`/`unalias`, recursion-guarded). `| ; & <` give a clear error.
- `env`, `export`, `which` (builtins/aliases/PATH lookup in the VFS).
- Env defaults USER/HOME/PATH/SHELL as specified.

## 0.0.5-dev -- persistence
- `encode_fs/decode_fs`: text format `A84FS1`, `D`/`F` records, `END` marker,
  escapes for `\\ \n \t \r`; strict validation (bad paths, missing parents,
  duplicates, truncation, version).
- `TIListStorage` (the only TI storage code): 2 chars/number, blocks of 200
  elements, double-buffered slots `S0xxx`/`S1xxx`, meta list `A84` written
  last (commit point) with magic, version, slot, nblocks, nchars, checksum.
  Lists whose first element is not the magic are never overwritten.
- Failed/corrupt load => fresh in-memory FS, `sync_ok=False`: `sync` and
  `exit` refuse to overwrite (`sync -f` overrides for our own corrupt data).
- `sync`; automatic sync on `exit` when dirty and safe.
- Tested with a dict-backed fake: multi-block, slot flip, corruption,
  foreign lists, failed store keeps previous state, the spec scenario
  (mkdir/echo/sync/exit/relaunch/cat).

## 0.0.6-dev -- quality pass
- cp, mv, rmdir, head, tail (`-n`), history (`-c`), `uname -a/-s/-n/-r`,
  `rm -r`, `ls -a`, Unix-style error messages, argument completion
  (dir-only for cd/rmdir, `which`/`help` -> commands, `export` -> vars,
  `unalias` -> aliases, `uname -`, `>` targets, `$VAR`), quote-aware completion.
- History persisted to `~/.ash_history` (last 40) on sync.
- `clear` empties the scrollback; screen is fully redrawn every key, wrapped
  to `cols`, input window follows the cursor; `term ROWS COLS` re-tunes geometry.

## Calculator-dependent / unverified (must be checked by hand)
1. `import ti_system` exists and has `get_key`, `disp_at`, `disp_clr`,
   `store_list`, `recall_list`. Missing pieces degrade: no store_list =>
   RAM-only FS (MemStorage); no get_key/disp_at => plain `input()` shell.
2. `disp_at(row, text, "left")` signature and rows 1..10 / 26 columns are
   ASSUMED (TI-84 CE Python recollection). Wrong => draw raises; use mode `p`
   and fix `TiTerm.draw`. Adjust with `term ROWS COLS`.
3. `get_key()` return type/values and whether it blocks. TiTerm auto-detects
   non-blocking (falsy return) and debounces held keys; blocking keeps doubles.
   Run `keytest`, then `bind` anything that differs. Also pick a Tab key.
4. `store_list/recall_list`: list name rules (`A84`, `S0001`-style names with
   digits), max list length (block size 200 assumed), whether recall of a
   missing list raises or returns empty (both handled), element precision.
   Test: `mkdir p; echo hi > p/t; sync; exit`, relaunch, `cat p/t`.
5. Source is ~51 KB; compiling it needs heap. If it fails with MemoryError
   on the calculator, the source must be trimmed or sent as bytecode.
6. Runs `main()` at import unless `_ARCH84_NORUN` is defined (tests do that).

## Pre-transfer review fixes
- `make_term` probes `disp_clr`/`disp_at` before using TiTerm; failure => plain shell.
- `Shell.run` catches terminal exceptions and degrades to `PlainTerm`
  (stops cleanly if PlainTerm itself fails -- no infinite loop).
- `history -c` no longer uses slice deletion (safer on MicroPython ports).
- Device inspection before transfer (`--list-files`): no `A84`/`S0xxx` lists
  existed; an old `ARCH84` (type 15, the 0.0.2 build) existed and was the
  intended overwrite target. No ti_system module file is visible in the
  listing, so the API could not be read from the device; assumptions stand.

## Transfer (2026-10-07)
    python3 evo_usb.py --get-info          # OK (OS pkg 7.0.0.3996)
    python3 evo_usb.py ARCH84.py ARCH84
    -> sent ARCH84.py -> 'ARCH84' (51916B source, 52011B payload)
    python3 evo_usb.py --list-files
    -> ARCH84  type=15  size=51940  RAM
    python3 evo_usb.py --get-file ARCH84 15 <tmp>   # source found verbatim in the object
Only ARCH84 was written; no other variables touched. The program was NOT run on
the calculator (launch it from the Python app, then do the checks above).

## Manual checks on the calculator, in order
1. Launch ARCH84. If it prints a probe/terminal error, use `p` (plain mode).
2. Enter -> editor. Check text appears, no traceback. If rows/cols look wrong: `term R C`.
3. `keytest`: note names for arrows, Enter, DEL, CLEAR; `bind` as needed; choose a Tab key.
4. Typing, arrows, history, completion (`mk`<tab>, `cd pro`<tab>, `cat /etc/ho`<tab>).
5. Persistence: `mkdir projects`, `echo hello > projects/test.txt`, `sync`, `exit`,
   relaunch, `cat projects/test.txt` => hello. Then `--list-files` should show
   lists `A84` and `S0000`/`S1000`... (cheapest proof store_list accepted the names).
6. If launch fails with MemoryError, the 51 KB source is too big to compile: trim or ship bytecode.

---
# Update: hardware findings and module split (2026-10-07, later)

The first single-file build (51 KB) failed on the calculator with
"memory allocation failed, allocating 214 bytes" while compiling (heap is
~152 KB free). Probe programs sent to the device established the real API:

| Fact | Result |
|---|---|
| Free heap | 152832 bytes; Python 3.4-flavoured MicroPython |
| `ti_system` | disp_at, disp_clr, disp_cursor, disp_wait, escape, getKey, get_key, recall_RegEQ, recall_list, sleep, store_list, wait, wait_key |
| `get_key` | needs an argument: `get_key(1)` blocks and returns an int key code, `get_key(0)` returns 0 when idle. `get_key()` raises TypeError |
| Key codes | positional, row*10+col (Enter 105, left 24, up 25, right 26, down 34, 2nd 21, alpha 31 ...). All 49 keys checked against my table, 0 mismatches |
| `disp_at(row, text, align)` | 3 args only, rows 1..11 valid (row 30 = "Invalid row"), 31 columns, left/center/right work |
| Lists | `store_list` max **100** elements ("List length > 100"); big ints and floats round-trip |
| ANSI escapes | swallowed silently, NO colour (via print or disp_at) |
| `ti_draw` | set_color, fill_rect, draw_text, draw_rect, ... ; screen dim [319, 209] below the status bar; font 10 px wide, 16 px rows -> 32 cols; `draw_text` y is NOT the baseline (glyph spans y-18..y-7); `paint_buffer` = "Unsupported operation"; `show_draw()` BLOCKS (hung a probe) |
| Imports | stored programs import each other by name (`from A84PRB4 import *`) |

## Resulting design
Split into modules that compile separately (each parse tree is freed after
compiling): `A84FS` (paths, VFS, codec, storage), `A84KN` (parser, kernel,
line editor), `A84UI` (PlainTerm, TiTerm/disp_at, key tables), `A84GX`
(GfxTerm colour terminal on ti_draw, `pick_term`), `A84CD` (commands),
`A84SH` (shell), `ARCH84` (launcher). Send each as its own program:
`python3 evo_usb.py A84FS.py A84FS` etc. (RAM; programs must be in RAM to run;
a RAM clear removes them and the saved `A84`/`S0xxx` lists).

## Features added since the first pass
- Typing with alpha / 2nd+alpha lock / 2nd for uppercase; symbols on spare
  keys (see `keys`): mem=space, (-)=_, stat=~, Y="  window=' zoom=$
  trace/math=>  graph==  2nd+( ) - + = { } [ ].  mode=Tab, del=backspace.
- Boot sequence: each step shows `[ *** ]` while it runs and is replaced by
  its real result (`[  OK  ]`, `[FAILED]`, `[ WARN ]`, `[ FIX  ]`).
  Lines are reported live by the kernel as steps finish.
- Colour terminal (green OK, red FAILED/errors, yellow WARN/FIX, coloured
  prompt, grey inline autosuggestion, block cursor), hint line pinned to the
  bottom row. Falls back GfxTerm -> TiTerm -> PlainTerm if a first draw fails.
- No startup prompt any more.
- `bind`, `keytest`, `term` and keymap persistence were removed (key codes
  are now known).

## Verified on the calculator (by screenshot / user)
Memory error gone; editor typing; Tab completion (`cd pro` -> `cd projects/`);
persistence across relaunch (`echo hi > t; sync; exit; relaunch; cat t`);
colour boot screen; cursor/row alignment after the y-offset fix.

## Still unverified
Long-session behaviour, scrollback keys (2nd+up/down), `sync` with a large
filesystem (list RAM use: ~9 bytes/element, two slots briefly), uppercase
input path, and every command beyond those exercised by hand.
Local tests: `python3 test_arch84.py` (76 tests).

---
# Roadmap status (mapped 2026-10-07)

Direction: the 24-phase roadmap supplied by the user (CLI first, Arch conventions
where they fit, no faked capabilities, TI code isolated, low RAM, conservative
writes). Status of the current code against it:

| Phase | Status | Notes |
|---|---|---|
| 1 Core shell + VFS | **mostly done** | Missing: roadmap directory tree (boot, dev, proc, root, run, usr/lib, usr/share, var/cache, var/lib, var/log). `/proc` and `/dev` are plain empty dirs until Phase 7 makes them generated; nothing may ever be persisted under them. |
| 2 Line editor | **done** | History, prefix search, Tab cycle + common prefix, inline gray suggestion, Home/End/Del, scroll. Deferred: `/usr/share/ash/completions/`, persistent per-command completions. |
| 3 Shell parser | **mostly done** | Missing: `PATH=/usr/local/bin:/usr/bin:/bin`, startup files `/etc/profile`, `~/.profile`, `~/.ashrc`. |
| 4 Persistence | **done (v1)** | Versioned text format, checksum, double-buffered slots, foreign-list guard, no overwrite after a failed load, `sync`, auto-sync on exit. Later: recovery path, block packing (Phase 19/20). |
| 5 Core command set | partial | Have cp mv head tail history sync. Missing: grep find sort wc basename dirname true false yes date uptime du df free mount umount reboot poweroff. |
| 6-20 | not started | users/ownership, /proc /dev, processes, init/services, journal, editor, packages, pacman, repos, makepkg, man, app framework, apps, fsck, optimisation |
| 21 Boot experience | **partly done, ahead of order** | Live systemd-style lines with `[ *** ]` pending state, colours. Kept (user asked for this style; the roadmap's `::` style was only a suggestion). |
| 22 Safe mode | minimal piece being added with startup files | |
| 23 Dev tooling | partial | `test_arch84.py` (desktop) and the `selftest` command (on-device). |
| 24 Release hardening | not started | |

Deviations from the roadmap, deliberately: boot lines use `[  OK  ]`; commands
needing pipes (`grep`, `sort`, `wc`) take file arguments because the parser
rejects `|`; the calculator has no confirmed clock so `date`/`uptime` report
what is actually available.

---
# Milestone: roadmap phases 1/3 gap-fill + phase 5 (2026-10-07)

## Clock probe results (on the calculator)
`time` has `ticks_ms`, `ticks_diff`, `monotonic`, `sleep` and nothing else:
no `time()`, no `localtime()`, no `ticks_us`. `utime` and `os` do not exist.
`gc` has `mem_free` (and `mem_alloc`, `collect`). ticks_ms was ~10,158,000 ms
(counts from calculator start). So: there is no wall clock, and `date`
cannot be derived; uptime can.

## Phase 1 / 3 gaps closed
- Directory tree per roadmap (boot dev proc root run usr/lib usr/share
  var/cache var/lib var/log). `/proc` and `/dev` are empty placeholders.
  An existing saved filesystem gets the new dirs through `fix_system_files`
  and shows one `[ FIX  ] Repaired N system files` line on first boot.
- `PATH=/usr/local/bin:/usr/bin:/bin`.
- Startup files `/etc/profile`, `~/.profile`, `~/.ashrc`, one command per
  line, run from `Shell.run` (not from `Kernel.boot`, so `selftest` sandboxes
  and unit tests do not run them). `/etc/profile` is also re-created if
  missing; the two user files are seeded only on a brand-new filesystem so a
  deliberate deletion sticks.
- Safety (there is no editor yet): `exit`, `reboot`, `poweroff` are refused
  inside startup files, each file reports `[  OK  ]` or `[ WARN ] N errors`,
  and holding CLEAR while Arch84 starts (a 0.5 s window, shown as
  `[ *** ] Startup (hold CLEAR to skip)`) skips them all. Minimal phase 22.

## Phase 5 commands (module A84C2, registers into COMMANDS)
grep (-i -n -v -c), find (-name with * and ?, -type f|d), sort (-r -n -u),
wc (-l -w -c), basename, dirname, true, false, du (-s), df, free, mount,
umount, uptime, date, reboot, poweroff.
- They take FILE arguments only: the parser rejects `|` by design, so there
  is no stdin. The usage messages say "(no pipes yet)".
- `yes` is deliberately NOT implemented: output is collected until a command
  returns, so an endless command would exhaust RAM. Needs phase 8 jobs.
- `find`/`du` walk iteratively (MicroPython recursion limit is low).
- `df` shows encoded size and block count; capacity is unknown to Python.
- `free` uses gc.mem_free/mem_alloc (run it right after boot to see the heap
  left after all modules load).
- `uptime`: Arch84 uptime plus the calculator tick counter.
- `date`: no wall clock exists, so `date -s 'YYYY-MM-DD HH:MM[:SS]'` stores
  (day, seconds, monotonic counter) in `/etc/clock`; `date` adds the elapsed
  counter. It survives relaunching Arch84 (and `sync`) but NOT a calculator
  restart (detected: "clock lost") and may drift if the counter pauses while
  the calculator sleeps (unverified). Date arithmetic checked against
  Python's calendar for 800+ days.
- `reboot`: syncs, refuses if the sync fails, then `main()` rebuilds the
  kernel from storage (a real reload). `poweroff` = sync + exit.

## Tests
`python3 test_arch84.py`: 114 tests (desktop). `selftest` on the device: 97
cases covering every command, with an UNTESTED check against the command
table. New module sizes: A84C2 15.3 KB, A84FS 15.0 KB (previous rule of
thumb was ~13 KB: watch for MemoryError on first launch; split if needed).

## Not yet verified on the calculator
Startup files and the CLEAR bypass, reboot, date persistence across a
relaunch, free/uptime values, and whether A84C2/A84FS still compile within
the heap.

## Shutdown sequence (exit / poweroff / reboot)
`Shell.shutdown(kind)` reports each real task like boot does (`[ *** ]` pending,
then `[  OK  ]` / `[ WARN ]` / `[FAILED]`): save command history (only written
if it changed, so it does not dirty the fs), sync filesystem (skipped with
"Filesystem already synced" when clean; "Unsaved changes NOT synced" if storage
did not load cleanly; `[FAILED] Sync` on error), then `Reached target
Shutdown` / `Power-Off` / `Reboot`, or `Shutdown finished with errors`.
A failed sync aborts `reboot` ("Reboot aborted") but not `exit`/`poweroff`.
Tests: ShutdownTests (123 desktop tests total).

---
# Standing rule: archived backups (from now on)

Every deploy also stores a backup of the whole OS in the calculator's Archive
(survives a RAM clear), named `<name>BAK`: A84FSBAK A84KNBAK A84UIBAK A84GXBAK
A84CDBAK A84C2BAK A84SHBAK A84TSBAK, and `ARC84BAK` for the launcher
(`ARCH84BAK` would be 9 characters; names allow 8).

- Deploy with `python3 deploy.py` (`--no-bak`, `--bak-only`, `--dry-run`).
  It sends the RAM copies that run and re-archives a backup only when its
  content changed (hash in `.deploy_state.json`) to spare flash.
- Each backup is a complete second system: its imports are renamed to the
  *BAK modules, so after unarchiving the *BAK programs to RAM, `ARC84BAK`
  runs on its own (tested on the desktop with only the *BAK modules present).
- The backup is the version just deployed, not the previous one. It protects
  against RAM clears, not against a bad deploy.
- It does not include the saved filesystem lists (`A84`, `S0xxx`).
- Tests: `python3 test_deploy.py` (5 tests).
- New modules must be added to `MODULES` in deploy.py.

---
# Storage density investigation (planned as "Phase 4b")

Not in the roadmap as written (Phase 4 only says "later: optimize block
packing"). Proposed as Phase 4b, before the package phases (12-13), because it
changes the saved format (needs an FS version bump + migration, and the
`*BAK` backup of the programs).

## Why
Current format: 2 chars (16 bits) per list element, 99 data elements per list.
A 5.6 KB "used" filesystem (synthetic: notes, scripts, history) = 29 lists,
~25 KB of list RAM; a sync holds two copies briefly.

## Measured on the calculator (probe programs, since deleted)
- `recall_list` returns plain `int`.
- Memory per list element depends on the stored number: 8-16 bit ints ~7 B,
  24-32 bit ints ~9 B, 40-46 bit ints ~11 B, half-integers (`v + 0.5`) ~13 B
  (99-element lists: 707 / 905-907 / 1097 / 1301 bytes).
- Integers are NOT always exact above ~29 bits: 2 of 3661 32-bit values and 1
  of ~300 at 33 and 44 bits came back exactly 1 too low (e.g. 988593390 ->
  988593389). 24-bit: 0 of 3637. 47/48-bit ints are clearly lossy.
- Storing `v + 0.5` and reading back with `int()` removes that error: 0 bad of
  ~18,000 values at 32, 36, 40, 44 and 46 bits (random + all 2^k, 2^k+-1).
- Heap: ~152 KB free at start but even 8 KB and 16 KB single allocations
  failed (fragmentation). Any large list/string must be avoided: work in
  chunks of a few KB, stream records, never build a whole-filesystem string.
- Pure-Python speed (2000-char sample): pack 2/5 chars 51/68 ms, unpack
  80/214 ms; LZSS (255-byte window, int-keyed dict) 2000 -> 874 B in 145 ms,
  decompress 47 ms; static 16-word dictionary 16 ms (flattering sample).

## Conclusions
| option | bytes of list RAM per char | gain vs now |
|---|---|---|
| now: 16-bit ints | 3.5 | 1.0x |
| 24-bit ints | 3.0 | 1.2x (error rate unproven) |
| 32-bit +0.5 | 3.25 | 1.1x |
| 40-bit +0.5 (5 chars) | 2.6 | 1.35x |
| 46-bit +0.5 bit-stream | 2.26 | 1.55x (edge of range) |

Packing alone is a modest win (my first estimate of 2.5x assumed a flat
9 B/element). Compression is the bigger lever: LZSS ~2x on text-like data
(synthetic sample 2.3x; real files will differ). Combined ~2.5-3.5x less list
RAM, and 5 chars/element means 495 chars per list instead of 198 (2.5x fewer
lists to write).

## Recommended design (not started)
1. 40-bit `+0.5` packing (byte aligned, 6 bits of margin).
2. Compress per chunk of ~2 KB with LZSS (bounded RAM/time), flagged per chunk
   so incompressible data is stored raw.
3. Tree encoding (parent index instead of full paths, ~13% of the sample) and
   omit unchanged default nodes.
4. New format version; keep reading v1 and migrate on the first sync; keep the
   existing checksum; double-buffered slots stay.
5. Compress only during `sync` (shown with a `[ *** ]` line); decompress at boot.

---
# Storage v2 implemented (phase "4b"): packing + compression + compact tree

Implements all five agreed pieces. New/changed modules: A84CZ (codec), A84ST
(list storage), A84FS (now VFS + the old v1 text codec only), A84KN (kernel
sync/boot), A84CD/A84SH (lazy commands), A84TS (device-side checks).

## What was built
1. **40-bit packing**: 5 bytes per list element stored as `v + 0.5`
   (meta list and magic included). 99 data elements per list (495 bytes).
2. **LZSS compression** per frame of <= 2048 raw bytes (12-bit distance,
   length 3-18); a frame is stored raw when LZSS is not smaller or when
   compression hits MemoryError (a sync never fails for that).
3. **Compact tree**: directories referenced by number (0 root, 1-18 the frozen
   factory dirs, then new dirs in record order); files/dirs identical to the
   frozen FACTORY1 image are not stored, differences and deletions are
   (records D/F/X/E, LEB128 lengths, UTF-8). `/etc/version` is never stored
   (always the running VERSION). A fresh filesystem is ~20 bytes raw.
4. **Versioned format, migration**: meta version 2 written; version 1 (old
   text format) is still read; loading a v1 save marks the fs dirty so the
   next sync/exit writes v2 and shrinks the v1 lists. The v1 reader accepts a
   stored checksum 1 below the computed one (plain ints can read back 1 low).
5. **Compress only at sync, decompress at boot**, with the `[ *** ]` lines.

## Safety
- Two slots; a save writes the inactive slot, **reads it back, verifies the
  checksum and (memory permitting) decodes it and compares with the live
  tree**, and only then writes the meta list. Failure at any point leaves the
  previous save live. Low memory skips only the tree compare (warning).
- FACTORY1 is frozen (a test pins its hash). Changing shipped defaults needs a
  FACTORY2, never an edit.
- Lists whose first element is not our magic are never overwritten.
- `Kernel.sync` turns MemoryError into StorageError("out of memory (nothing
  was changed)"); boot reports `Load fs: out of memory (needed N B)` and
  disables saving instead of calling the save corrupt.
- Decoder: bounded name/data lengths, strict record checks, every failure is a
  ValueError; file data is decoded in <= 1 frame pieces (peak ~2x the text).

## Measured on the calculator (new probes, since deleted)
- Real `store_list/recall_list` accept the 40-bit half-value lists; write +
  read-back + checksum verify + commit + reload all worked on real lists.
- Sample filesystem 6,987 B raw -> 1,038 stored (6.7x); 7,370 -> 1,118.
- Real save in the dry boot: 12 nodes, v2 would be 46 -> 51 B (one list).
- Heap: 127,440 free at start; module costs (heap bytes): A84FS 9.5K, CZ 6.0K,
  ST 5.9K, KN 10.9K, UI 5.4K, GX 10.4K, CD 9.6K, C2 13.3K, SH 6.9K. All loaded:
  ~49.6K free. Largest single block ~16K at start, ~12K later.
- **Known limit**: with ~50K free a filesystem of roughly 8-9 KB of file data
  loaded fine at ~7.9 KB but failed at ~8.9 KB with `MemoryError allocating
  4801 bytes` (joining one 4.8 KB file): fragmentation, not total memory.
  Safe failure (nothing lost, saving disabled). Real fix = chunked file
  storage in the VFS (roadmap phase 20); not done yet.
- `Kernel.__new__` does not exist on this firmware (fixed in A84TS).

## Memory work
- `A84C2` (phase 5 commands, 13 KB of heap) is loaded on first use (LAZY map in
  A84CD; names still show in help/which/completion). `A84TS` also lazy.
- `Kernel` no longer builds a throw-away default tree before loading.
- `lz_decompress` uses a pre-sized buffer.

## Tests
`python3 test_arch84.py` (123), `python3 test_storage.py` (68: packing, LZSS
fuzz, codec fuzz incl. every chunk-boundary size and dir/file swaps on factory
paths, corrupt/truncated/malicious streams, flaky-recall FakeTI that
reproduces the probed -1 error, fault injection, verify, memory failures,
v1 -> v2 migration), `python3 test_deploy.py` (5). On the device: `selftest`
now runs 8 extra storage/codec checks in memory (utf8, pack, lzss, codec,
ratio, store+reload, corruption, migration).

## Pending
Real migration on the user's calculator (launch, exit to sync, relaunch),
then `python3 deploy.py --bak-only` to refresh the *BAK backups. The OLD *BAK
set cannot read a v2 save (it refuses to save rather than damage anything).
PC copies of the v1 save: fsbackup_20261007/ (A84.8xl, S0000.8xl).

## Self-test made memory-aware (after the first real migration)
Migration confirmed on the calculator: `df` shows 46 raw -> 51 stored, 1 block.
`selftest` then reported 99/105 with MemoryErrors: with all modules plus the
lazy A84C2 and A84TS loaded only ~20 KB of heap is left, and the storage checks
built a 7 KB sample plus several copies. Changes: smaller samples (a 2080-char
file still crosses the 2048-byte frame boundary), storage checks run BEFORE the
lazy command module loads, gc.collect() before every check with one retry, and a
persistent memory shortage is reported as `LOWMEM <label>` and counted
separately (never a FAIL). Summary line is now
`selftest: P/T passed, L lowmem, U untested`; failure lines are one line each.
Relaunch Arch84 after deploying (a running Arch84 keeps the old A84TS cached).
Tests: 129 + 68 + 5.

## Backups refreshed (python3 deploy.py --bak-only)
*BAK set now = the version with storage v2 + lazy commands + memory-aware
selftest. ARC84BAK can read/write v2 saves.

---
# Big files (chunked file storage) + animated progress bar

## Chunked file data (A84FS, A84CZ, commands, shell)
Cause: loading a filesystem with one ~4.8 KB file failed on the calculator
(`MemoryError allocating 4801 bytes` while joining it) because the heap
fragments even with ~50 KB free. Fix: a file's `data` is a `str` up to
BIGMIN=2048 chars, otherwise a list of SPLIT=1024-char pieces (last piece
1..1024). The shape is CANONICAL (equal text -> equal representation), so
`==` still works on data, and decoded/appended/copied data always matches
`dnew(text)`. Nothing on these paths joins a big file into one string:
- codec: the writer encodes slice by slice from the pieces; the reader
  decodes into pieces (`Rd.take_data` = `dchunks(text_pieces(n))`).
- `VFS.append` only touches the last piece; `VFS.copyfile` shares the (immutable)
  pieces, so `cp` of a 100 KB file costs a small list; `mv` moves the node.
- `cat`, `head`, `tail`, `grep`, `wc` stream line by line (`VFS.lines`);
  `du` uses `dlen`; `sort` still needs the lines in memory.
- Shell output is flushed to the terminal / redirect target in ~1 KB batches
  on line boundaries, and a redirect target is opened (and `>` truncated)
  BEFORE the command runs, like a real shell (so `cat f > f` empties f, and
  `cat f >> f` reads a snapshot and terminates).
Limits that remain: the whole filesystem still lives in RAM. Chunking removes
the fragmentation failure, not the total: with ~50 KB of heap free expect
roughly 30-40 KB of file data in total. `read()` of a big file (used by few
code paths) still needs one contiguous string.
Tests: test_bigfiles.py (31): canonical shape fuzz, append/copy sharing,
codec round trips up to 150 KB, "never joins" patches, tracemalloc proof that
transient memory of save/load/cat/cp does not grow with file size (a
mutation check confirmed the old joining decoder fails it), streaming command
output equality, redirect semantics. On the device: `selftest` builds a 3 KB
file by doubling with `cat` and checks wc/grep/head/tail/du/cp on it.

## Progress animation (systemd style)
`[*     ]` -> `[***   ]` -> `[ ***  ]` ... `[     *]` (8 frames, an 8-char tag
like `[  OK  ]`, asterisks red on the colour terminal). Steps are blocking
calls, so the animation advances only when real work is reported:
`ListStore.progress` fires after each list read/written, `Kernel.sync` after
each compressed frame, the startup loop after each command and the
hold-CLEAR wait on every poll; `Kernel.tick()` advances at most every 90 ms
(frame order is strictly sequential). Used by boot, startup files, shutdown,
`sync`. Very fast steps flash by without moving (nothing to report).
Tests: SpinnerTests (15). Total tests: 248.

---
# MemoryError regression on the calculator: cause and fix

## Symptom
`MemoryError` during ordinary use on the real calculator, before any big-file
test; an earlier build did not show it.

## Method
The calculator was not attached, so a real MicroPython (32-bit unix port,
v1.20.0, built with `MICROPY_FORCE_32BIT=1 MICROPY_NLR_SETJMP=1`) was run with
`-X heapsize=N`, one CPU core, 64 MB address-space cap, CPU/wall timeouts, and
shims for `ti_system`/`ti_draw` (scripted keys, lists on disk, screen capture).
Calibration: the emulator starts with ~126 KB free like the device (127 KB) but
has ~25 KB more free after all modules load (device ~50 KB vs ~75 KB), so
`HEAP=127800` is the device-like setting. It is NOT the real firmware: treat
it as a relative measure. The harness lives outside the repo (not committed).

## Cause
Not a leak (free heap is flat over 400 repeated commands). The heap was too
thin for the COMPILE of late-loaded modules. MicroPython builds the parse tree
of a whole module before compiling, so a module needs roughly 4x its source
size free on top of what is already resident:
- A84KN (16.9 KB), A84CD (12.8 KB), A84SH (12.9 KB) and the lazily loaded
  A84C2 (15 KB) / A84TS (15 KB) each needed 50-60 KB at the moment they loaded.
- With ~44 KB free after boot, the first use of `grep`/`date`/`df`/`sort`...
  failed with `out of memory loading A84C2` (reproduced in the emulator).
- A MemoryError while typing/drawing also dropped the shell into the bare
  `input()` fallback for good, and one in `echo`/`busy` escaped and ended the
  program.

## Fix
- Smaller modules (each compiles with a small peak): A84PE (parser, line
  editor; split from A84KN), A84CE (env/shell commands) and A84CP (tab
  completion) split from A84CD/A84SH, A84C2..C5 (phase-5 commands, four lazy
  pieces of ~4 KB each), A84TD/A84TX/A84TS (selftest, three lazy pieces).
  `deploy.py` MODULES updated.
- `from X import *` replaced by explicit imports in all modules except the
  launcher (smaller module namespaces; ~4.6 KB more free after boot).
- Load order: biggest compiles first (A84CD right after A84KN), A84GX last.
- The shell survives MemoryError: readline errors gc and retry (4 tries, then
  "ash: low memory"), echo/busy/history failures are ignored, a command that
  runs out of memory prints "ash: out of memory" and the shell continues.
  `selftest` reports low memory clearly, and unloads its modules afterwards
  (calculator only) so a later `sync` has the memory back.
- Storage unchanged: a failed sync still raises StorageError("out of memory
  (nothing was changed)") and the previous slot stays live.

## Measured (emulator, HEAP=127800, 300-command session with Tab/up-arrow,
## cp/mv/grep/find/sort/..., sync)
- Before: first `grep` after boot -> out of memory; later in the session the
  shell fell back to input() or exited.
- After: 304 commands + sync clean, minimum free 37 KB; free after boot 48.5 KB
  (was 43.9 KB), after loading all four lazy modules 39 KB (was 31 KB).
- Still true: `selftest` does not complete from a fresh boot at this heap
  (it does at 152 KB: 103/112 passed, 9 skipped for low memory). Everything
  else in ordinary use is clean.

## Tests
149 + 68 + 31 + 5 desktop tests pass (new: MemoryResilienceTests; lazy tests
updated for the four pieces).

## Not verified on the calculator yet
Everything above is emulator + desktop. Needs a deploy and a hand test:
boot, `free`, ~20 ordinary commands, `grep`/`date`/`df`/`sort` as first
commands, `sync`, `exit`, relaunch.

## Next ideas (not done)
Precompiled bytecode (mpy v5) would remove compile peaks entirely, but device
execution of .mpy modules is unverified (README says only transfer was
validated).

---
# Big-file save runs out of memory (found on the calculator) and the fix

On the device the doubling test (`cat a b`-style) stopped at 8 KB total.
Reproduced in the emulator: the doubling works, but `sync`/`df` then fail with
`MemoryError` allocating ~1.4 KB while 28 KB are free: the heap is fragmented
(`max free sz` was ~1 KB), and the writer needs contiguous buffers.

- File pieces are 512 chars (BIGMIN 1024) instead of 1024/2048, output flush
  batches are 512 B, frames are 1024 raw bytes (readers still accept frames up
  to 2 * CHUNK, so older saves load). In-memory shape only: the saved format is
  unchanged.
- `Kernel` reserves a 3 KB block at boot (`hold_spare`) and hands it back just
  before a save or `df` (`release_spare`), re-reserving it afterwards, so the
  writer's buffers find a contiguous hole. Costs 3 KB of free heap.
- Emulator, HEAP=127800: one file doubled in place to 12,288 bytes with
  `cat a >> a` saves (12,724 -> 1,962 bytes, 4 blocks) and reloads. Two files
  of that size (`cat a a > b`, ~18 KB total) are still over the limit: the
  whole filesystem lives in RAM, so keep the total file data under ~12 KB on
  the device. Use `cat a >> a` to double a file; it needs one copy only.


---
# Pipes, stdin, editor, scripts and .ar84 packages (campaign follow-up)

All of this was developed and tested on the desktop and in the MicroPython emulator (emu/); none of it has
run on the calculator yet.

* **Pipes / stdin**: `parse(..., pipes=True)` returns stages `[(words, redir, infile)]`; `Shell.execute` runs them
  in order, keeping each non-final stage's output as canonical file data (pieces, never one big string) and feeding
  it as `sh.stdin`. `<` shares the file's own pieces. `cat head tail grep sort wc` read stdin (or `-`);
  new lazy module A84C6: `uniq`, `tee`. Aliases expand only on the first word of the line; `;` and `&` are still
  unsupported. `$0..$9` and `$#` expand (so `$5.00` now prints `.00`, like sh).
* **Keys**: the calculator had no `|`, `<` or `\`: now x^-1, sin and x^2 (A84UI.NORM; `keys` lists them).
* **edit**: A84ED (pure state machine) + A84EV (terminal driver), both lazy. Whole file as a list of lines
  (limit 20000 chars / 1500 lines); saving builds the new data first and swaps it in (`VFS.put`), so a failed save
  leaves the old file. `qq` discards because `!` has no key.
* **Scripts**: A84SC, loaded when a command is not built in: PATH lookup, `$1..$9 $#`, output goes through the
  caller's pipe/redirect, `exit/reboot/poweroff` refused, nesting limit 4. No control flow yet.
* **.ar84 packages / pacman / makepkg**: A84PM (format, validation), A84PD (database in
  `/var/lib/pacman/local/NAME/{desc,files}`), A84PI (install/remove with rollback), A84PB (build, local repository
  `/var/cache/pacman/pkg`), A84PX (commands). Packages may only write under /usr /opt /etc /home /var, never the
  system files or the pacman database; everything is validated (paths, sizes, per-file and whole-package checksums)
  before anything is written; a failure mid-install restores the previous state. Packages are plain text, so they
  can be written by hand or built on the device; there is no download path yet (the calculator has no network).
* **Memory**: resident heap after boot 47.1 KB -> 44.7 KB (parser, pipeline executor, hooks); boot compile peak
  87.8 KB -> 90.2 KB min heap. The new commands are lazy modules (each <= ~8 KB source).
* **Tests**: test_pipes.py, test_editor.py, test_pacman.py (damaged-package fuzz, rollback sweep), fuzz_pkg.py
  (CPython == MicroPython), emu/edtest.py; selftest gained 13 cases.


---
# archive and fsck (autonomous follow-up session)

* **Why not the real Archive**: the probed `ti_system` API has `store_list`/`recall_list` only; nothing moves data into
  the flash Archive from Python. The saved filesystem already lives in list memory, off the Python heap; what runs
  out is the heap, because the whole tree is loaded at boot. `archive` therefore keeps selected files only in lists.
* **Format/commit**: stream `Q1` + records (68 dir / 70 file, varint path, varint data) in the usual compressed
  frames (512-byte raw frames: smaller buffers fit a fragmented heap), lists `Q<id><nnn>` (ids 0-9), catalogue in
  `/var/lib/archive/index`. Create writes + reads back the lists, removes the files from RAM, then saves; extract
  restores in RAM, saves, and only then clears the old lists; a failed save is a warning ("run sync"), never data loss.
* **Modules** (all lazy): A84AX (command line, list/check/delete), A84AI (catalogue helpers), A84AR (create),
  A84AE (extract), A84FK (fsck). They unload themselves before the save so their code is not resident while saving.
* **Eviction**: `A84CD.evict()` drops every idle lazy module when loading the next one hits MemoryError, then retries.
  (MicroPython keeps interned names after a module is dropped, so the first use of a module still costs a few KB.)
* Emulator: with 5 files of ~1.4 KB, `archive create` frees about 6.4 KB net of the heap; 6 files 10.9 KB.

* **Command lists**: `;`, `&&`, `||` (`split_commands` in A84PE, run by `Shell.execute`; each piece is a pipeline;
  a syntax error runs nothing). Typeable: `;` = cos key, `&` = 2nd + x^-1 (a single `&` is still unsupported).
* **Resident memory**: uname/whoami/hostname/which/keys/selftest moved to lazy A84C7 (-1.5 KB resident);
  free heap at the prompt is now 44.9 KB.
* **/proc and /dev (phase 7)**: `VFS.proc` is a hook the kernel sets (`Kernel.procfs` -> lazy A84PF). `VFS.get`
  asks it for `/proc/*` and `/dev/*` paths the saved tree lacks; `/proc/{meminfo,modules,mounts,uptime,version}`
  are generated on every read, `/dev/null` discards writes. Everything under /proc and /dev is read-only
  ("Read-only file system") and never stored. `ls` no longer assumes listed names are tree children.
* **More commands**: `mkdir -p`, `cp -r` (iterative, shares file pieces; refuses to copy a directory into itself -
  found by the shell fuzzer when `cp -r / x` looped forever), `ls -l` (sizes), lazy A84C8 (`cut tr nl seq`) and
  A84C9 (`test [ expr`), which make scripts with `&&`/`||` practical.
* `emu/push_main.sh` runs the full validation and pushes to main only when it passes.
* **man / help COMMAND (phase 16)**: lazy A84MN, one page per command (usage + description), `man -k WORD`;
  `test_manpages.py` fails if a command has no page or a page names an unknown command.
* **Resident memory** again: the lazy-command table is one string per module (class `Lazy`), and the v1 text
  reader (`decode_fs`) lives in A84V1, loaded only when a v1 save is found: free heap at the prompt 45.0 KB.

## pacman: lock file, repository index, upgrades
- `pacman.lock` (/var/lib/pacman/pacman.lock) is taken by -U/-S/-R and released in a `finally`; an existing
  lock aborts with a hint and is never removed by the loser. `fsck` reports it as stale, `fsck -r` removes it.
- /var/lib/pacman/sync/repo.db: one line per repository package (name, version, file, depends, desc). Used by
  -S (dependency planning no longer scans every package), -Sl, -Ss, -Si, -Qu, -Su. Rebuilt by -Sy, when the
  file list of the repository differs from the index, or when missing; makepkg deletes it. It is regenerable, so
  it is never trusted over the package files (install still validates the package).
- -Su/-Syu upgrade installed packages that have a newer repository version; -Qu lists them.

## grep -r/-l, sed `$`
- `grep -r` walks directories in name order (`.` by default, paths printed relative to what was given),
  `-l` prints matching file names only. `sed` accepts `$` and `N,$` addresses (one line of lookahead).
- Found by low-heap cmdfuzz: when `exit` failed (out of memory) and input then ended, the shell retried `exit`
  forever (emulator-only: the device never sees end of input). It now gives up after a few attempts, and
  `exit` evicts lazy modules and retries once when out of memory.

## Global environment: /etc/environment
- `/etc/environment` (created by the first `setenv`; it is not part of the factory tree, which the storage
  format uses as its baseline, so without it the built-in defaults apply) holds NAME=value lines read at every
  startup (not in safe mode) over the built-in defaults: USER, HOME, PATH, SHELL, HISTSIZE (1..500),
  HISTFILE, HOSTNAME (used when /etc/hostname is empty). Invalid lines are ignored.
- Replaced hardcoded values: history file/size now follow $HISTFILE/$HOME/$HISTSIZE, the startup cwd and `~`
  follow $HOME, pacman protects `$HOME/.profile .ashrc .ash_history`, the factory /etc/profile exports of PATH/SHELL are ignored
  (that file is part of the storage baseline, so it stays unchanged; other exports in it still apply).
- New: `unset` (session), lazy `printenv setenv unsetenv` (setenv/unsetenv rewrite /etc/environment, keeping
  comments, and change the running session). Cost: ~1.1 KB of resident heap.

## pacman: dependency handling, -Sc, -Rns
- Dependencies are `name` or `name OP version` (>= <= = > <, compared with the package version order). `-S`
  plans them (installs or upgrades what is missing/too old, reports `cannot satisfy`), `-U` reports every
  missing/unsatisfied dependency at once.
- Install reason: packages pulled in only to satisfy a dependency get `reason dep` in their database entry;
  naming a package with `-S` makes it explicit. `-Qe/-Qd/-Qt/-Qdt` list explicit/dependency/unrequired/orphans,
  `-Qi` shows Reason and Required By.
- `-R` now works on a set (dependents first; refuses if something that stays still needs a target);
  `-Rs`/`-Rns` also remove dependency-only packages nothing else needs (`n` is accepted: there are no .pacsave files).
- `-Sc` removes cached package files that are not the installed version, `-Scc` all of them. The cache is also
  the repository here, so packages built with makepkg but not installed are removed too.

## Flash repositories (packages as calculator modules)
- Python on the calculator can only import modules, so packages from outside travel as modules (the calculator allows
  8 capital letters/digits per program name, hence hashed ids): `K<6 hex><n>` = part n of one package (a LINES tuple of the
  .ar84 text), `QR<NAME>` = a repository's index (ROWS), `R84REG` = the list of repositories. `tools/ar84pack.py` writes them
  (it validates packages with the pacman parser; a repository is always rebuilt from its folder; with `--send` the registry
  is rebuilt from the calculator's program list, so other repositories are never forgotten).
- pacman: `-Sy` imports the registry and indexes (A84PL) and merges their rows into /var/lib/pacman/sync/repo.db; installs read
  the package straight from its modules (`mod:<repo>:<id>:<parts>` path, one part in memory at a time, freed afterwards).
  The local .ar84 repository still works and wins ties.
- Memory: the package modules had grown past what loads at the stock heap (min heap for `pacman -Q` 124000 -> 125500).
  Fixed by splitting A84PM (parser/validator -> A84PS), A84PX (queries -> A84PQ), flash code in A84PL, lazy helper imports
  (with a gc.collect() first), dropping the planner before installing and releasing the reserved block during an install.
  `Kernel.sync` now also evicts lazy modules before its retry (a save after `pacman -S` used to fail out of memory).
- `emu/flashtest.py` runs the whole flow on the emulated device (sync, list, info, install with a dependency and a
  multi-part package, verify, run, remove); `test_flashrepo.py` has 15 unit tests.

## 2026-10-08 (late): key injection and a smaller selftest

- `evo_usb.py --key/--keys` send TI-84 CE scancodes (Enter 9, `)` 0x15, prgm 0x1F, 2nd 0x36, mode 0x37);
  get_key reports the positional code Arch84 already uses (all 49 keys verified). `tools/type.py` turns text
  into key presses using the A84UI tables (`test_type.py` checks the round trip), so commands can be typed
  into the calculator from the PC. On/home cannot be injected. From the home screen, prgm, down, enter,
  enter starts ARCH84; 2nd+mode, enter quits the Python app. Always screenshot first: keys sent to the
  wrong screen (the apps menu) cleared RAM twice.
- selftest was resetting the calculator (hard reset, RAM cleared): the ~25 KB of test data left ~21 KB of
  heap, too little for the lazy command modules. The cases are now generated into A84T1..A84T4
  (`tools/gen_selftest.py` from A84TD + A84TY) and loaded one quarter at a time: `selftest N [-r] [-p] [name]`.
  Parts 2 and 3 pass (48/48, 47/48). Part 4 (pacman, archive, fsck) reports LOWMEM for most cases even at
  50 KB free: the heap is fragmented; pacman itself works from a fresh launch (makepkg, -U, run, -Q by hand).
- Do not run selftest after `reboot`: the reboot leaves less usable heap (lazy commands fail to load).
- A failed import leaves a half-built module in sys.modules on MicroPython; `mod()` in A84PX now drops the
  helper modules on failure (before, makepkg/pacman raised "no attribute" until the next launch).

### Measured heap use (device, fresh launch, 2026-10-08)
Heap 167 KB total; 103 KB used at the prompt, ~64 KB free. Resident cost of each boot module
(gc.mem_alloc delta): A84FS 21k, A84CZ 9k, A84ST 6k, A84KN 7k, A84CD 9k, A84CE 10k, A84UI 5k,
A84SH 10k, A84GX 5k (~82 KB; the rest is interpreter, terminal and the saved filesystem tree).
Lazy modules add: A84C4 (free/mount/...) and A84C2 ~+3 KB each, pacman+archive ~+14 KB, date ~+3 KB.
Candidates to shrink: A84FS (21k), A84CE (10k, env commands: could be lazy), A84CZ (9k: only boot/sync),
A84SH (10k).

### Does evict() free memory? (device probe, 2026-10-08)
A temporary `memprobe` command loaded a lazy module and evicted it: A84C8 +2992 B -> 240 B left; A84PX
(pacman) +9936 B -> 1408 B left (and 1312 B after a stack scrub). So eviction does release the code; the
selftest LOWMEMs are heap FRAGMENTATION (free bytes exist but no block big enough to compile a module),
not leaks. Also: the per-module boot costs above include the modules each one imports first (A84CE's
10k mostly was A84PE), so splitting A84CE into a lazy part saved nothing (tried, reverted).
Tried: on a failed lazy load, release the kernel's 3 KB spare block and retry (A84SH.run_stage): no change
(selftest part 4 still 33/48, 14 LOWMEM), reverted. Module sources are small (A84PX 8 KB, A84AX/A84PB < 8 KB),
so the compile peak is not what fails; the pacman/archive cases run out of memory while WORKING (packing,
scanning, hashing) next to the test harness. They pass by hand from a fresh launch.

### Hand verification on the device, 2026-10-08 (fresh launch, typed with tools/type.py)
makepkg, pacman -U / -Q / -Qi / -Ql / -Qk / -R (removed command is gone), archive create / list / check /
extract -k / delete (files really leave and come back), fsck ("no problems found"), & typed from the vars
key, echo > file / cat: all correct. selftest parts 1-3 pass except memory-induced failures; the pacman/
archive/fsck cases of part 4 report LOWMEM inside selftest (the sandbox leaves too little contiguous heap:
A84PX imports fine with 40 KB free in a clean heap but not at 47 KB next to the harness).
Tried a lighter selftest harness (no spare block in the throwaway kernels, the real shell's block released
while testing): part 4 still 33/48 with 14 LOWMEM, reverted. Pacman/archive/fsck are verified by hand
(see above); selftest reports them as LOWMEM on the device.
