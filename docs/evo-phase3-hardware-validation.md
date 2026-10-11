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

## Controlled comparison after deployment approval

The current repository adds two independent idle-heap improvements:

1. Phase 2 unloads `A84NF` after the greeting.
2. Phase 3 defers importing `A84CP` until the first completion request.

For an on-device comparison, start from the same saved VFS and five packages,
launch a fresh Python session each time, wait for the greeting, capture
`free -l`, run `pwd` then `ls`, capture `free -l`, run `pacman -Q`, wait for the
prompt, capture `free -l`, and check `fsck` from a separate fresh launch.
Record screenshots and OS counters. Repeat at least three times to quantify
boot variance. A later Tab press should load `A84CP` and preserve all
completion behavior; compare `free -l` before and afterward. Measure startup
and command latency with an on-device monotonic timer if the runtime exposes
one; host USB timings are insufficient.

### Deployment plan requiring explicit approval

Only installed programs `A84NF`, `A84SH`, and `A84CP` need replacement for
this staged comparison. Directory preflight confirms all three exist in
Archive and `A84NFBAK`, `A84SHBAK`, `A84CPBAK` also exist there. The staged
plan is: exit Arch84; transfer the new `A84NF` source to Archive with no
backup refresh; boot and measure Phase 2; exit; transfer `A84SH` and `A84CP`
source to Archive; boot and measure Phase 3; run `fsck` and focused shell
checks. Existing `*BAK` variables, `ARCH84`, other modules, and saved `S`/`X`
lists are not transfer targets. Each transfer replaces an existing program,
so the user must approve it before execution. Do not use a whole-system
`deploy.py` for this experiment: its dry run includes 58 modules plus
`ARCH84`, and two modules (`A84TR`, `A84VM`) lack `*BAK` copies in the
observed directory.

## Confidence and gaps

The three `free -l` values and verified list restore are **Observed** on the
physical Evo. Emulator improvements are separate results in
[the memory profile](evo-memory-profile.md); they are **not** physical-device
post-change measurements. Firmware RAM counters include resources outside
Python's GC heap, so subtracting them from `gc.mem_free()` does not identify
a specific firmware allocation. Fragmentation is directly relevant: about
54 KiB of free GC heap allowed only a roughly 2 KiB bounded block in this
run. The exact heap-reservation policy and true contiguous maximum remain
**Unknown**.
