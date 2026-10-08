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

## Baseline (original commit 077bca7, same harness)
boot free 48,688 B; cap.py: only **51** small files survive save->reload->re-save with full
verification (154 with the verify step allowed to skip, flaky); 100 files: reload then exit-sync
fails OOM. Phase churn (bytes allocated, 60 files): load 84 KB, stream+feed 57 KB, verify 77 KB.

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

## Results so far (emulator, heap 127800)
| metric | before | after |
|---|---|---|
| free heap at prompt | 48,688 B | 48,528 B |
| files surviving save/reload/re-save (full verify) | 51 | ~120-130 |
| load churn (60 files) | 84 KB | 37 KB |
| stream+feed churn | 57 KB | 29 KB |
| verify churn | 77 KB | 31 KB |
| 8.7 KB single file saves | no (low memory) | yes |
Leak check (emu/leak.py): heap flat after history fills (x10 vs x40 within 0.7 KB).

## Status
Discovery pass 1 in progress (VFS, codec, storage, sort/grep/wc reviewed). Consecutive clean passes: 0.
Next: review A84PE (parser/editor), A84CP (completion), A84C5 (date), A84UI/GX rendering; fuzz the
line editor; re-run all tools; revisit load/resync failures at 150+ files (lazy-module compile
fragmentation); `mkdir -p`/`cp -r` are unsupported (feature gaps, not changed).

## Unverified
Everything on real hardware. Device `bytes+bytearray`, `bytearray.decode`, float rounding of
`x * 2**-20` are standard but only checked on MicroPython 1.20 and CPython.
