# Arch84 optimisation / bug-fix campaign log

Resume point for any session. Keep concise. Branch: `claude/compassionate-planck-0bthwm`.

## Target hardware (from ARCH84_DEVLOG.md, measured on the device by the author)
TI-84 Evo (OS 7.0.0.3996), MicroPython ("Python 3.4-flavoured"). Python heap ~152 KB free
at start of a bare program, **127,440 B free** in the author's probes, ~50 KB free after all
Arch84 modules load. Single allocations of 8-16 KB fail from fragmentation. Screen 320x210,
32 columns x 11 rows. `store_list` max 100 elements, big ints flaky above 2^29, half values
exact to ~46 bits. No wall clock. CPU model/clock are NOT documented in the repo; none is
modelled. Calculator lists live in OS memory, not on the Python heap.

## Emulation environment (`emu/`) - fidelity
* 32-bit MicroPython **1.20.0 unix port** built with `MICROPY_FORCE_32BIT=1` (see emu/README.md),
  `-X heapsize=127800`; shims for `ti_system`/`ti_draw`; lists stored in files (off-heap, like the
  device); scripted key presses through the real key tables (A84UI).
* Calibration: free heap at the shell prompt = 48.7 KB (device: ~48.5-50 KB).
* **Approximate simulation, not hardware-accurate**: same bytecode VM/GC/object sizes as
  MicroPython, but not the calculator firmware, CPU, fragmentation history or `ti_system`.
  Host timings (ms) are relative only. Stack limit is the unix port's (40 KB), unknown on device.
* Harness quirks fixed: key list on heap inflated boot memory; 1.20 unix port closes fd 0 after a
  failed `open()` (shim uses `os.stat` first).

## Tools
`emu/bench.py` (workload heap table), `emu/minheap.py` (smallest clean heap per workload),
`emu/leak.py` (flat-heap check), `emu/stress.py` (big file / many files), `emu/cap.py` (max
files that save, reload and re-save), `emu/loadheap.py`, `emu/mp/*_probe.py` (allocation per
phase), `fuzz_shell.py` (CPython-vs-MicroPython differential shell fuzzer, deterministic seeds).
Run with `A84_MICROPYTHON=<path>` or a binary at `/tmp/a84-micropython`.

## Baseline vs now (SAME harness, heap 127800; baseline = original commit 077bca7 in a separate worktree)
| metric | baseline | now |
|---|---|---|
| free heap at prompt (resident code) | 47,648 B | 47,136 B (-512 B) |
| files surviving save -> fresh boot -> edit -> re-save, full verify | 51 | 124 |
| same, verify allowed to skip its tree compare | 132 | 135 (noise level) |
| 100 small files: smallest heap that loads | ~126,000 | ~99,000 |
| 100 small files: smallest heap that saves | ~112,000 | ~107,000 |
| `reboot` with 100 files, then keep working | fails | works (stale-GC-root scrub, ARCH84.py) |
| min clean heap: boot / cmd_mix / files_create_delete / 8 KB file + sync | 87.1 / 102.1 / 97.7 / 128.2 K | 87.8 / 92.5 / 94.9 / 124.5 K |
| allocation churn, 60 files: load / stream+feed / verify | 84 / 57 / 77 KB | 37 / 29 / 31 KB |
| host time (relative, 100 files): sync / load | 12.8 / 5.3 ms | 10.8 / 3.1 ms |
| 8.7 KB single file saves | yes | yes; 17 KB: both fail (low memory) |
Honest reading: the biggest gains are in garbage churn (-50%), robustness at 50-120 files and after
`reboot`; the absolute ceiling (~130-135 small files / ~12-17 KB of file data at this heap) barely moved
because the whole tree lives in RAM (~120 B per file node + resident modules ~60 KB of a 125 KB heap).
Host-MicroPython timings are not device timings.

## Fixed / optimised (all with desktop regression tests in test_campaign.py unless noted)
1. **Names > 255 UTF-8 bytes were accepted, then every sync failed** (`verify failed: bad name
   length`) -> nothing could be saved again. VFS now rejects them ("File name too long").
2. **`sort -n` order of equal keys was arbitrary on MicroPython** (unstable sort); now ties break
   on the whole line like sort(1). Found by fuzz_shell.py differential run.
3. LZSS: fixed 2 KB hash table (sized to input) + presized output instead of a per-position dict
   (worst case >10 KB of reallocation on incompressible frames). Format unchanged; text ratio
   -1.6% (17109 vs 16837 B on 25 KB of repo text).
4. 40-bit pack/unpack with float arithmetic instead of big ints (36 KB of garbage per list read
   -> 10 KB); presized buffers; fewer copies in the frame reader; payload decompressed in place.
5. Writer fills the 100-element block in place (no slice/concat copies); small files encoded
   inline; names/data decoded straight from the frame.
6. `Kernel.sync` retries once after `gc.collect()` on a first MemoryError (the same save worked a
   moment later in the emulator); still reports "out of memory (nothing was changed)" if it repeats.
7. `rm -r` and `VFS.count` iterative (no recursion limit risk on a deep tree).
8. v1 text *writer* moved to A84V1 (tests/self-test only), recovering ~1 KB resident heap
   (deploy.py MODULES updated).
9. **Tab completion inside an open quote doubled the quote** (`cat "my f<Tab>` -> `cat ""my file`).
10. **Startup could hang forever** if the tick counter wrapped inside the 0.5 s hold-CLEAR window
    (raw `t1 - t0 > 500`); now `ticks_diff`.
11. **A MemoryError in the post-save tree compare aborted a finished save** ("out of memory (nothing
    was changed)" after every list was written); now downgraded to the existing "compare skipped"
    warning, and `same_tree` no longer queues one tuple per file.
12. Boot retries a failed (out-of-memory) load once after `gc.collect()` before disabling saving.
14. `rm -fr`/`-Rf`/`-f`/`--` were not understood (`rm -f x` treated `-f` as a file name); flags now combine.
13. `reboot` frees the finished session first (`boot_once`) and scrubs stale GC roots: the
    conservative GC kept the old filesystem tree alive (9-15 KB less free after reboot).

## Verification tooling (all green at last run)
`python3 emu/run_all.py` (unit tests 239 + bigfiles, CPython==MicroPython differential shell fuzz x60,
codec fuzz with byte-identical streams on both interpreters, key fuzz, power-cut sweep, leak check).
Also `emu/powercut.py N --fail` (store_list raising), `emu/keyfuzz.py ... --nodraw` (TiTerm path).
Cross-version: streams written by the new code decode with the original code and vice versa (149 trees).
`selftest` passes 112/112 on a 250 KB heap and never stores a list (power-cut at store 0 not reached);
at the device-like heap it reports LOWMEM for the heavy checks (same class as the original).

## Status
Discovery passes: 1 complete (all modules read or fuzzed, coverage 92% lines by unit tests).
Consecutive clean passes: 0 (pass 1 found work). Next: pass 2 = re-run every tool + re-review.
Known/unchanged: ~130 small files / ~12 KB file data ceiling; lazy commands fail to compile
("out of memory loading A84Cx") when <~30 KB is free; `mkdir -p`/`cp -r` unsupported; unquoted empty
`$VAR` is not dropped from argv like in sh; `sync -x`/`reboot x` ignore bad args; per-key display cost
~7 draw calls / ~14k filled pixels (full-row clears) - not optimised, no device timing available.

## Unverified
Everything on real hardware. Device `bytes+bytearray`, `bytearray.decode`, float rounding of
`x * 2**-20` are standard but only checked on MicroPython 1.20 and CPython.
