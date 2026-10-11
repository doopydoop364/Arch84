# Evo memory profile, phase 2

## Phase 3 update (2026-10-11)

The connected Evo's [full-build baseline](evo-phase3-hardware-validation.md)
on the installed, pre-Phase-2 modules was 54,960 B free GC heap and a
2,146 B bounded block at the first prompt. After `pwd; ls`, it was 55,680 B
and 1,957 B. After `pacman -Q`, it was 53,536 B and 1,934 B. These are
**Observed** physical readings. No optimized modules were deployed for this
baseline. The staged `EVOPROF` runner again showed 80,208 B after imports
and 68,224 B after temporary kernel/shell construction in a separate session.

`A84SH` previously imported `A84CP` at shell import time, retaining its
completion parser and argument-kind table before any Tab press. Phase 3 now
imports it on first completion. A direct emulator import probe charged
about 6.5 KiB to `A84CP` with the other base modules preloaded at a 160 KiB
requested heap; that is an inclusive import increment, not guaranteed idle
heap savings. The controlled whole-shell benchmark at a 127,800 B requested
heap provides the relevant retained result:

| 32-bit MicroPython emulator metric | Before | Deferred completion | Change |
| --- | ---: | ---: | ---: |
| Prompt free heap after GC | 37,536 B | 39,424 B | +1,888 B |
| File-cycle minimum free after GC | 32,528 B | 34,432 B | +1,904 B |
| Prompt bounded block lower bound | 4,741 B | 4,977 B | +236 B |

The matched [before](../research/results/emu-phase3-before.json) and
[after](../research/results/emu-phase3-lazy-completion.json) JSON include
the full import and command profile. A 159,000 B requested emulator heap
showed +1,904 B boot free and +1,872 B package-scenario minimum after GC.
In an emulator key test, typing `mkd` then Tab completed to `mkdir` and
executed without an error or crash. This verifies the deferred import path
in the emulator, not on the Evo. The first Tab may now pause while `A84CP`
compiles, and later Tabs keep the module loaded. Device compile latency,
post-Tab heap and fragmented-heap behavior are still unmeasured.
At a 103 KiB requested emulator heap, a deferred Tab import could fail and
originally triggered terminal fallback. `Shell.complete` now catches that
allocation/import failure, removes a partial module entry, and leaves the
input line intact with no completion candidates. Four constrained key-fuzz
seeds passed after this fix; the prior branch had failed them during boot.

The final [quick emulator gate](../research/results/emu-phase3-quick-gate.txt)
passed all 18 desktop test files, differential fuzz, normal and 103 KiB
key fuzz, command fuzz, and the editor scenario. It still failed three
constrained scenarios: flash repositories, archive extract, and 40-file
power-cut. Phase 2 recorded these same three as baseline failures. The gate
is **not green**; passing desktop tests does not establish device reliability.

## What the counters mean

**Observed on the Evo (phase 1):** the firmware reported 961,536 bytes of
total user RAM and 489,140 bytes free in one device query. A separate fresh
Python app run reported 152,848 bytes of free GC heap after collection.
Arch84 reported 56,752 bytes free after GC and a 2,216-byte largest tested
block in another run. These runs had different programs and variable states;
their subtraction is a useful hypothesis, not a controlled device result.

**Inferred:** firmware free RAM includes space outside the Python GC heap.
The Python interpreter, its heap allocation policy, calculator variables,
firmware work buffers and other uses divide that space. `gc.mem_free()` counts
free blocks *inside* the Python heap only. It is not physical free RAM. Even
within that heap, fragmentation can make a large object fail. Arch84's resident
code, VFS tree, shell state and loaded modules then occupy much of the heap
available to a standalone program. A display buffer's exact cost and the
firmware's heap-sizing policy remain **Unknown**.

## Reproducible emulator method

`emu/profile_run.py` follows the real `ARCH84.py` import order under the
32-bit MicroPython 1.20 unix port. It marks imports, kernel boot, filesystem
load, shell creation, greeting and command boundaries. Each mark collects GC
and records free/allocated heap. Selected marks also bisect a `bytearray`
allocation, bounded to 8,192 bytes and one eighth of free heap. The largest
successful size is a **lower bound**; the probe does not seek exhaustion.
`emu/run.py` remains the normal test driver, so instrumentation does not alter
the regular emulator gate. Run with:

```sh
A84_MICROPYTHON=/path/to/32-bit/micropython python3 tools/evo_bench.py --output /tmp/evo-bench.json
python3 tools/evo_bench.py --compare research/results/emu-phase2-before.json research/results/emu-phase2-after.json
```

JSON includes per-command free-heap changes, a filesystem-load interval,
bounded contiguous results, storage call counts and explicit unmeasured
fields. It also runs two launches in the same emulator list store to detect
saved-filesystem startup differences. The file-cycle scenario writes, reads
and removes one small VFS file. A tiny `makepkg; pacman -U; pacman -Q`
scenario uses an explicitly labeled **159,000-byte requested emulator heap**
because the instrumented run cannot compile the package commands at the
default 127,800-byte request. It records the scenario's minimum free after GC
and the before/after install command delta, but not the instantaneous peak
within a command. The separate capacity model estimates storage efficiency.
Flash-write latency remains unmeasured.

The 127,800-byte requested heap resulted in 124,864 bytes reported by
MicroPython. The scenario is an emulator result, not an Evo measurement.
Absolute numbers depend on interpreter build, checkout path length, instrumentation,
the emulated saved VFS and command sequence. Compare revisions with identical
conditions. The saved runs are
[`before`](../research/results/emu-phase2-before.json) and
[`after`](../research/results/emu-phase2-after.json).

| Emulator metric | Before | After | Change |
| --- | ---: | ---: | ---: |
| Prompt free heap after GC, `pwd; ls` | 35,808 B | 37,536 B | +1,728 B |
| Minimum free after GC, file cycle | 30,944 B | 32,528 B | +1,584 B |
| Prompt bounded contiguous lower bound | 4,551 B | 4,741 B | +190 B |

The file-cycle `end_free` after `exit` was 3,712 B lower in the changed run,
despite the better prompt and minimum readings. A repeat of the changed run
was byte-for-byte consistent on these metrics. The exit stage includes save
and emulator cleanup; it is not the idle memory objective. This difference
still needs hardware interpretation before broadening the optimization.
On two successive emulator launches sharing one list store, prompt free heap
was 37,536 B then 37,392 B (−144 B); the second launch loaded the first
run's saved filesystem. This does not model repeated launches in one Evo
Python process, because each emulator launch starts a new interpreter.
At the separately labeled 159,000-byte requested heap, the tiny package
installed and `pacman -Q` found it. Free heap fell from 65,632 B before
`pacman -U` to 60,784 B after GC (4,848 B retained); the scenario minimum
after GC was 60,160 B. These are staged emulator observations, not the
instantaneous install peak or a device package measurement.

**Measured cause:** the login greeting lazily imports `A84NF`, then its
neofetch command was retained for the session. `A84NF.cmd_neofetch` now calls
`A84CD.unload` in `finally`, removing its command registration and module
reference after display. A manual `neofetch` reloads normally. The tradeoff is
compile time on each later invocation. `test_neofetch.py` covers the greeting,
unload and reload. The `A84NF` code is not counted as a general shell saving
when `.hushlogin` skips the greeting.

## Largest retained import increments

These are *inclusive* free-heap deltas across each top-level import in the
emulator baseline. Nested imports are charged to the importer; these are not
isolated module sizes. They explain why many small source modules together
consume far more than the standalone probe.

| Import boundary | Retained free delta |
| --- | ---: |
| `A84CE` (also loads command dependencies) | 11,376 B |
| `A84SH` (also loads completion and lifecycle) | 9,296 B |
| `A84FS` | 7,152 B |
| `A84CZ` | 7,152 B |
| `A84KN` | 6,208 B |
| `A84GX` | 5,648 B |
| `A84CD` | 5,136 B |
| `A84UI` | 4,960 B |

The VFS and shell allocations follow these imports. `Kernel.boot()` reads the
saved list snapshot, rebuilds the tree, and loads shell history. Node costs in
the prior devlog were roughly 150 bytes for a file and 250 bytes for a
directory on desktop MicroPython. Exact device retained sizes remain
**Unknown**. Streaming large file data into `X` lists already avoids keeping
all package payloads in the Python heap; moving more data to a swap pager has
no measured case yet.

## Device profile

`research/EVOPROF.py` is a standalone, read-only staged import and boot
profile. It records `before-GC/after-GC/allocated` per stage, releases its
temporary kernel and shell references, then tests one bounded 4 KiB block.
It reads existing filesystem lists during boot but never saves them.

**Observed on hardware, OS 7.0.0.3996:**
[`transcript`](../research/results/evo-2026-10-11-profile.txt) records
153,776 B free after GC at the start, 80,144 B after the launcher import
sequence, 68,384 B after constructing the kernel and loading the saved VFS,
and 68,160 B after creating the shell. After dropping the temporary kernel
and shell references, 78,672 B was free. The 4,096 B allocation cap was
reached (4,064 B lower bound under the bisector's 64 B tolerance). The
constructor stage recovered 15,360 B on GC, illustrating why readings
without collection can be misleading.

Within this one Python session, the imports retained about **73,632 B**
(153,776 − 80,144), and temporary kernel plus shell construction retained
another **11,984 B** (80,144 − 68,160). Together they explain **85,616 B**
of the standalone-to-staged gap. The remaining gap to the earlier 56,752 B
full-Arch84 reading is not controlled: launcher/graphics state, greeting,
history, saved variables and the different session can all contribute. The
firmware's 489 KiB free-RAM counter is outside this Python-heap accounting.

| Device import boundary | Free after GC | Inclusive retained delta |
| --- | ---: | ---: |
| Start | 153,776 B | — |
| `A84FS` | 142,560 B | 11,216 B |
| `A84CZ` | 137,824 B | 4,736 B |
| `A84ST` | 134,448 B | 3,376 B |
| `A84KN` | 125,536 B | 8,912 B |
| `A84CD` | 119,776 B | 5,760 B |
| `A84CE` | 111,232 B | 8,544 B |
| `A84UI` | 105,920 B | 5,312 B |
| `A84SH` | 92,992 B | 12,928 B |
| `A84GX` | 80,144 B | 12,848 B |

The biggest device import increments are the shell and graphics modules,
followed by `A84FS`. `A84SH` includes nested imports such as the parser,
completion and lifecycle modules; `A84CE` includes command registrations.
The staged runner does not create the real graphics terminal, show the login
greeting, retain the Arch84 launcher, or enter the full shell loop. It cannot
replace a controlled `free -l` comparison on two deployed builds. The
existing Arch84 deployment predates the `A84NF` change, so no *device*
improvement from that change is claimed. Archive backup copies were not
refreshed.

## Reliability of comparisons

At a 103 KiB emulator heap, the key fuzz case fails on both `bf28517` and
`c9d8259` when their checkout paths have the same length as this worktree.
Shorter `/tmp` worktrees can pass that case by saving source-path string
bytes. The editor create/save/cat case also fails on both matched-length
revisions. These stress cases are not evidence of a new regression here.
The emulator does not model the Evo's post-boot fragmentation, real list I/O
timing, display allocation, or firmware memory policy. Repeat controlled
hardware `free -l` runs after a fresh boot before calling this optimization
hardware-validated.
