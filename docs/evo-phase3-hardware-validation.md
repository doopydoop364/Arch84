# Evo phase 3 hardware validation

## State and method

**Observed, 2026-10-11:** The connected US TI-84 Evo reports OS
7.0.0.3996, BL1 1.0.0.260, BL2 7.0.0.3386, 961,536 B total RAM,
481,256 B free user RAM, 3,141,632 B total flash counter, and 2,187,276 B
free Archive before the shell run. These are firmware counters; they do not
describe the Python GC heap. The read-only USB directory contained 187
variables. `ARCH84` was in RAM and the installed `A84*` modules were in
Archive.

The baseline launched the **installed pre-Phase-2 build** from a fresh Python
session, selected explicitly in the Python file manager. The same saved VFS
and five installed packages were present. `free -l` collects GC before
reporting heap totals, and its bounded bisector reports a successfully
allocated block, not the absolute largest possible block. Results and screen
captures are in [the JSON record](../research/results/evo-phase3-hardware-baseline.json).

| Point in this boot | Free GC heap | Largest tested block | Evidence |
| --- | ---: | ---: | --- |
| First prompt, after greeting | 54,960 B | 2,146 B | [screen](../research/results/evo-phase3-baseline-free.png) |
| After `pwd`, `ls` | 55,680 B | 1,957 B | [screen](../research/results/evo-phase3-baseline-commands.png) |
| After `pacman -Q` | 53,536 B | 1,934 B | [screen](../research/results/evo-phase3-baseline-pacman.png) |

**Observed:** `pacman -Q` listed the five installed demo packages. Key
injection for the next command raced with the command's redraw and produced
one incomplete shell line; `free -l` was retried separately. This limits
precise attribution of its 1,424 B drop from first prompt. USB typing time
includes host waits and is **not** command latency. Startup and command CPU
latency remain unmeasured on this run. A staged `EVOPROF` run in a separate
Python session again reported 80,208 B free after imports and 68,224 B after
temporary shell construction, close to Phase 2's 80,144/68,160 B. It is not
equivalent to the full prompt above.

**Observed, recovery check:** An accidentally triggered invalid raw-list
transfer during a desktop test returned `INVALID_DATA_PAYLOAD` and removed
`X0002`. The exact Phase 2 export was restored to the missing name. A fresh
USB readback had the same 1,410 bytes and SHA-256
`3694d0ff90bc521e673105121147648ecf590782acb2fe429c2ff248d4eb69ea`.
Arch84 booted; read-only `fsck` reported 7 list-backed files, 5 installed
packages, 0 missing files, and [no problems](../research/results/evo-phase3-recovery-fsck.png).
The restore test now uses a fake device that cannot call the real USB send
function. This incident demonstrates that an unsuccessful transfer is not
necessarily non-mutating; the desktop restore tool requires a known SHA-256
and an unused destination name before any write.

## Staged physical comparison

The current repository adds two independent idle-heap improvements:

1. Phase 2 unloads `A84NF` after the greeting.
2. Phase 3 defers importing `A84CP` until the first completion request.

**Observed, 2026-10-11:** The user approved replacing only the installed
`A84NF`, `A84SH`, and `A84CP` programs. A directory preflight found all three
and their Archive `*BAK` copies. `deploy.py --archive-modules --no-bak --only`
transferred `A84NF` first, then `A84SH,A84CP`, with a fresh Python session
between stages. No backups, launcher, other modules, or saved lists were
transfer targets. The final directory still contained 187 variables and
unchanged backup sizes. [Machine-readable results and screenshots](../research/results/evo-phase3-hardware-staged.json)
record each stage.

| Fresh-session point | Installed old build | `A84NF` only | All three, first boot | All three, repeat boot |
| --- | ---: | ---: | ---: | ---: |
| First prompt free after GC | 54,960 B | 56,832 B | 58,704 B | 58,976 B |
| First prompt bounded block | 2,146 B | 2,664 B | 2,177 B | 2,936 B |
| After `pwd; ls` free | 55,680 B | 57,552 B | — | 59,808 B |
| After `pacman -Q` free | 53,536 B | 55,264 B | — | 57,808 B |

The controlled first-prompt stage increments were **+1,872 B** for `A84NF`
and another **+1,872 B** for lazy completion in the first optimized boot.
The repeat optimized boot was 272 B higher, giving a **3,744–4,016 B**
first-prompt improvement over the earlier installed build across these two
optimized boots. After `pacman -Q`, the no-Tab comparison improved by
4,272 B. The bounded contiguous block varied by hundreds of bytes and did
not track free heap closely; no reliable improvement in contiguous capacity
is established.

On the first optimized boot, `mkd` plus Tab expanded to `mkdir`, and the
history suggestion continued to display. The next `free -l` showed
56,736 B, **1,968 B below** the pre-Tab reading, consistent with loading
`A84CP` plus command/editor allocations. On a fresh optimized boot,
read-only `fsck` found seven list-backed files, five installed packages,
zero missing files and no problems. `selftest 2` on a separate fresh boot
passed **50/50**, 0 lowmem, 0 untested. The calculator was left at the app
launcher after exiting Python. Archive backups were not refreshed.

One mistyped line from key timing occurred after `pacman -Q` in the
`A84NF` stage, before its memory reading; the reading was obtained after
the shell recovered. Startup and command latency were not measured on
hardware. Five matched-path emulator repetitions of `pwd; ls` had boot
times before `[536,529,528,528,528]` ms and after
`[534,527,528,527,528]` ms (median 528 ms both). These emulator timings
do not measure the Evo CPU or USB typing overhead.

## Confidence and gaps

All `free -l` table values and the verified list restore are **Observed** on
the physical Evo. Emulator improvements remain separate results in
[the memory profile](evo-memory-profile.md). Firmware RAM counters include resources outside
Python's GC heap, so subtracting them from `gc.mem_free()` does not identify
a specific firmware allocation. Fragmentation is directly relevant: about
54–59 KiB of free GC heap allowed only roughly 2–3 KiB bounded blocks in
these runs. The exact heap-reservation policy and true contiguous maximum remain
**Unknown**.
