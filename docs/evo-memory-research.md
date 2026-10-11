# TI-84 Evo memory and storage research

**Phase 4 continuation:** The [verified USB backup workflow](evo-usb-backup-reliability.md),
[compressed-block candidate](evo-compressed-storage.md),
[native-execution evidence](evo-native-execution.md), and
[Phase 5 roadmap](evo-phase5-roadmap.md) contain the latest results. On the
physical US Evo, 187/187 listed variables were exported read-only and
validated locally; restoration of the full set remains unverified. The
calculator still runs OS 7.0.0.3996. No installed programs, existing
variables, Archive backups, or firmware were changed in Phase 4.

**Phase 3 continuation:** The [physical baseline and deployment plan](evo-phase3-hardware-validation.md),
[technical hardware reference](evo-hardware-architecture.md), and
[ranked Phase 4 roadmap](evo-phase4-roadmap.md) supersede the Phase 3
proposals at the end of this document. They add a same-build full-shell
baseline, a 1,888 B emulator idle-heap optimization, an offline compressed
list format proof, an explicit cold-list restore prototype, and static
inspection of TI's official 7.1 Evo bundle. The current device remained on
OS 7.0.0.3996; static firmware results are not hardware execution results.

Status: 2026-10-11. This is a reproducible baseline, not a hardware memory map.
**Verified** means published by the cited vendor or proved by source/tests;
**Observed** means measured on one calculator or reported by a first-hand
teardown; **Inferred** is a reasoned interpretation; **Unknown** needs a test.
The device in this work is a TI-84 Evo, not a TI-84 Plus CE Python.

## Resource ledger

| Status | Finding | Evidence and limit |
| --- | --- | --- |
| Verified | TI advertises 156 MHz and 3.5 MB user-available memory for the Evo. Its comparison chart lists 3.5 MB ROM / 149+ KB RAM. | [TI Evo product page](https://education.ti.com/en/products/calculators/graphing-calculators/ti-84-evo), [TI comparison chart](https://education.ti.com/en/product-resources/graphing-course-comparison). These are user-facing figures, not chip capacity or a Python heap size. |
| Observed | A first-hand Evo-T teardown identifies a Winbond 25Q128JVSQ flash chip and Q21A-007-AE ASIC. | [TI-Planet teardown](https://tiplanet.org/forum/viewtopic.php?p=280662). The [Winbond datasheet](https://www.winbond.com/resource-files/w25q128jv%20revf%2003272018%20plus.pdf) confirms 128 Mbit = 16 MiB for that flash part. The US Evo PCB has not been inspected in this project; do not equate 16 MiB with user-addressable space. |
| Observed | TI-Planet reports 592.9 KB working memory on a new Evo-T and 2826 KB archive free, rising to 3060 KB after a full reset. | [First-hand Evo-T report](https://tiplanet.org/forum/viewtopic.php?p=280662). We will not perform a reset to reproduce this. It differs from TI's 149+ KB comparison-chart RAM entry; the definition of each figure needs clarification. |
| Inferred | Physical RAM may be at least 1 MiB if TI-Planet's 592.9 KB is genuine RAM availability. | TI-Planet explicitly calls this a conjecture. ASIC RAM capacity has no confirmed part datasheet in this investigation. |
| Observed | On this Evo, Arch84 `free -l` after a fresh relaunch reported Python heap total **158,848 B**, used **102,096 B**, free **56,752 B**, largest allocatable block **2,216 B**. | Screenshot `/tmp/evo-research-free.png`, 2026-10-10. The command runs `gc.collect()` and a bisection allocation probe. The result is a session measurement, not physical RAM. |
| Observed | The Evo's device-info API reports `total-ram=961536` B and `total-flash=3141632` B on firmware package `7.0.0.3996`. Its dynamic-info API reported free `ram=489140` B and `archive=2187276` B before the two probes were transferred. | Read-only USB requests on 2026-10-11. These are firmware-reported capacities/counters, not verified physical chip sizes or Python heap sizes. |
| Observed | In a fresh Python app shell, the standalone `EVOMEM` probe reported **152,848 B free after GC**, `gc.mem_free`/`gc.mem_alloc` present, and a successful **8,192 B** single-object allocation at its safety cap. | [Transcribed device output](../research/results/evo-2026-10-11-memory.txt) from shell screenshots. The 8,192 B result is a lower bound, not the largest possible allocation. |
| Observed | The standalone `EVOSTO` probe confirmed `ti_system.store_list` and `recall_list`; opening a missing file for reading returned `None`. Tested string and storage-info APIs were absent. | [Transcribed device output](../research/results/evo-2026-10-11-storage.txt) from shell screenshots. This tests only the named APIs. |
| Observed | Linux sysfs exposed USB `0451:e018`, product `TI-84 Evo`, interfaces CDC control `02/02/01`, CDC data `0a/00/00`, vendor-specific `ff/00/00`, and HID `03/01/01`; `cdc_acm` bound to the two CDC interfaces. | `python3 tools/evo_research.py usb`. Descriptors show interface types, not the privileges or internal memory behind them. |
| Verified | The current [Evo-specific `evo_usb_py`](https://github.com/Evo-Programming/evo_usb_py) documents Kermit over CDC serial, screenshots, info queries, directory listing, file send/get, key injection, and OS transfer. | [README](https://github.com/Evo-Programming/evo_usb_py/blob/main/README.md), [source](https://github.com/Evo-Programming/evo_usb_py/blob/main/evo_usb.py). This project uses only the documented read-only requests and source-program transfer; it does not use OS transfer, reboot, break, or deletion. |
| Observed | `open()` returned `None` on the current Evo; `ti_system.store_list`/`recall_list` are the working Arch84 persistence API. A list can hold at most 100 elements; Arch84 uses 99 data elements of 5 bytes each. | [Arch84 storage implementation](../A84ST.py), [project devlog](../ARCH84_DEVLOG.md), and the storage probe above. The 100-element limit was established by earlier project work, not retested by the read-only probe. |
| Unknown | Exact physical RAM, RAM map, flash partition map, Python heap sizing policy, native execution permission, and whether unused flash can be reached through a supported API. | Do not infer access from a chip's capacity, USB descriptors, or an update package. |

The community [Evo firmware analysis](https://www.reddit.com/r/calculators/comments/1vzew7f/ti84_inside_the_evo/) reports evidence consistent with Cortex-M33, TrustZone-M, and signed MCUboot images. This is a first-hand but unreplicated report; CPU core, privilege boundaries, bootloader behavior, and signature enforcement remain **Unknown** here. TI-Planet's [Evo family page](https://wiki.tiplanet.org/TI-84_Evo-T) also describes the M33 identification, but its information is not an independent device measurement by this project. No CE jailbreak or toolchain is presumed compatible with the Evo.

## Arch84 resource path

`ARCH84.py` imports the core shell, VFS, codec, and display modules, then runs
`boot_once`. `A84CD.py` lazily imports most commands; `A84VM.py` is an optional
pager library and currently backs no production data. The VFS tree stays in
the Python heap. Data of selected large files lives in calculator `X` lists
through `A84BL`/`A84BM`; `A84ST` writes two checked snapshot slots in `S`
lists. These lists consume calculator user RAM, which can indirectly shrink the
Python heap. Archive programs can be imported without putting all module
sources in RAM. [Files in lists](FILES_IN_LISTS.md), [swap](SWAP.md), and
[recovery](RELIABILITY.md) describe the boundaries.

Current **Arch84 software limits**, not proven firmware quotas: path components
are at most 255 UTF-8 bytes (`A84FS.MAXNAME`); file data is split into 512
character pieces after 1024 characters (`A84FS.SPLIT/BIGMIN`); shell input is
limited to 4096 characters (`A84PE.MAX_LINE`); package archives allow at most
300 entries and 20,000 characters per file, with 1024-character records
(`A84PS` and [recovery](RELIABILITY.md)). The two-slot store allows at most
999 blocks (`A84ST.MAXNBLOCKS`), each carrying 495 bytes before framing. These
limits should not be used as evidence of the Evo's physical storage size.

## Reproducible tools

Run from the repository root. They require only desktop Python 3 for mock
testing. `research/EVOMEM.py` and `research/EVOSTO.py` are standalone Python
programs with no Arch84 imports. The memory program uses no storage writes;
its bytearray search stops at 8 KiB or one eighth of reported free heap,
whichever is lower. It reports a **lower bound within that cap**, not an
unbounded maximum. It catches `MemoryError` for each optional allocation and
checks `gc.mem_free`/`gc.mem_alloc` availability at runtime. Its final `sum`
line is `free_after_gc / allocatable_lower_bound / probe_cap`, short enough for
the small screen. The storage
program only checks API presence and attempts to open an unlikely name in
read mode; it never creates, overwrites, or deletes a calculator file.

```sh
python3 test_evo_research.py
python3 tools/evo_research.py usb > /tmp/evo-usb.json
python3 tools/evo_research.py usb --sysfs /path/to/mock/sysfs
```

`tools/evo_research.py device` uses the shared USB lock and documented
attribute, dynamic-info, and directory requests. Its JSON contains device
metadata, file names, and RAM/archive counts and byte totals from the
directory; keep captures outside the repository if private.
Directory requests use `gotohome=1` in `evo_usb_py`, so exit any running Python
app before this command. The research wrapper permits 30 seconds for directory
response packets because a directory of 184 entries took about 37 seconds in
this session. The USB library's ordinary 5-second read timed out and left the
calculator rejecting immediate follow-up requests. The longer wait succeeded
twice without changing the gitignored USB library.

### Local USB access diagnosis (2026-10-11)

The earlier restricted workspace exposed USB sysfs and `cdc_acm`, but mounted
a private `/dev` over the host device nodes. It lacked `/dev/ttyACM0` and
`/dev/serial/by-id`, so direct serial access failed before any packet. Its
process also lacked the `uucp` group. The current full-access session exposes
`/dev/ttyACM0` as `root:uucp`, and this process belongs to `uucp`. Read-only
info and directory requests now work. This was a workspace access problem,
not a missing calculator or kernel driver. If it recurs, check `ls -l
/dev/ttyACM0` and `id -nG` inside the failing session. The separate directory
timeout was resolved by the longer receive wait described above.

To transfer a **new** diagnostic program after the link is healthy, first exit
the Python app and check the directory. `send` refuses to overwrite a name it
finds and stops if the directory query fails. It writes only the named new
Python source program to calculator RAM; it never deletes it.

```sh
python3 tools/evo_research.py device > /tmp/evo-device.json
python3 tools/evo_research.py send research/EVOMEM.py --name EVOMEM
python3 tools/evo_research.py send research/EVOSTO.py --name EVOSTO
```

Both names were transferred on 2026-10-11 and are now occupied; the guarded
`send` command will refuse a repeat. Those first device copies require calling
`main()` in the Python shell after selecting the program because the file
manager imports programs. The source files here now autorun when imported by
`tipython`; a simulated file-manager import passes on desktop, but this source
revision has not been re-transferred or device-verified.
Run each program from the Evo Python app, screenshot the output and use
2nd+Up to scroll through earlier lines. Transcribe lines beginning `EVO_MEM`
or `EVO_STORAGE` into text files. The desktop tool converts the transcript to
JSON and compares runs:

For the next **repeat measurement**, start at the Calculator home screen,
press `prgm`, select Python App, and select `EVOMEM` in its file manager.
At the Python prompt, call `main()` on the calculator. With the current
USB key typer, the exact scancodes used successfully in this run were:

```sh
python3 tools/type.py --sc 0x36,0x30,0x0d,0x2f,0x2d,0x2c,0x36,0x30,0x1d,0x15,0x09
tools/evo --screenshot /tmp/evo-mem-repeat.png
```

The scancode sequence assumes alpha lock is off at the Python prompt; check
the screen indicator before sending it. Use `2nd+Up` to inspect older output,
then quit the Python app with `2nd+Mode`, confirm Yes, and return to Calculator.
Repeat from a fresh app launch for a comparable heap state.

```sh
python3 tools/evo_research.py parse /tmp/evo-run-1.txt > /tmp/evo-run-1.json
python3 tools/evo_research.py parse /tmp/evo-run-2.txt > /tmp/evo-run-2.json
python3 tools/evo_research.py compare /tmp/evo-run-1.json /tmp/evo-run-2.json
```

The 32-bit MicroPython binary named in the devlog exited with status 159 in
the earlier restricted workspace. The standalone probes have since run on the
physical Evo. The earlier `selftest 2` passed 50/50 on a fresh boot, and
Arch84 was exited cleanly before these USB requests.
In the current full-access session, `python3 emu/run_all.py --quick` passed
its 18 desktop test files, then stopped because its default
`/tmp/a84-micropython` executable is absent. MicroPython fuzz and device-shim
cases therefore remain unrun here; the hardware probes above provide direct
evidence for their own behavior.

### Device run on 2026-10-11

**Observed:** Before transfer, the firmware reported 489,140 B free RAM and
2,187,276 B free archive. Its directory had 184 entries: 49 in RAM and 135
in Archive. After transferring `EVOMEM` and `EVOSTO` to RAM, the directory had
186 entries and free RAM was 483,488 B, a decrease of 5,652 B. The two new
programs appeared as type 15, with directory sizes 3,964 and 1,576 B.
Directory sizes and free-space deltas use different accounting; neither is
a physical-memory measurement. No existing variable was overwritten or deleted.

**Observed:** In the Python shell, GC raised reported free heap from 151,936
to 152,848 B. Representative transient heap costs were 272 B for a 256-byte
bytearray, 176 B for a 32-entry list, and 784 B for a 16-entry dict or the
eight sample VFS nodes. Repeated allocation of twelve 128-byte bytearrays
showed a 1,840 B peak delta. Negative restoration deltas in some cases show
that the live shell changed during measurement; treat single-run deltas as
approximate. See the [full transcribed memory output](../research/results/evo-2026-10-11-memory.txt).

**Observed:** `EVOSTO` found the `ti_system` module and its list store/recall
functions. `open()` on a missing filename in read mode returned `None`.
No data write was attempted. See the [full transcribed storage output](../research/results/evo-2026-10-11-storage.txt).

## Next experiments, in order

1. **Low risk:** repeat `EVOMEM` after a fresh Python app launch and compare
   the transcript with the first device run. The first 8,192 B result only
   reaches the probe's cap; a separate carefully bounded experiment would be
   needed to find a practical contiguous-allocation ceiling outside Arch84.
2. **Low risk:** correlate firmware dynamic-info counters with the calculator
   UI and Arch84 `free -l` while recording whether files/lists reside in RAM
   or Archive. Keep all reads non-destructive.
3. **Moderate risk:** design an opt-in scratch-list capacity experiment with a
   preflight collision check and a documented cleanup plan. Do not use an
   existing list or Arch84 namespace. This is needed for a *measured* list
   count/size limit and write latency; current read-only probes cannot answer
   those questions.
4. **Research only:** obtain an officially distributed firmware package with
   clear provenance and hash it; perform static format and signature analysis.
   Compare that with Evo-specific first-hand reports. No firmware installation,
   memory-address probing, or native payload execution belongs in this phase.

## Progress log

- 2026-10-10: Created `research/evo-memory-storage` from the clean
  `feat/reliability-overhaul` branch. Inspected launcher, VFS, list storage,
  lazy commands, emulator, USB wrapper, and current Evo-specific sources.
- 2026-10-10: Added bounded standalone heap and read-only storage probes,
  sysfs/device inventory, guarded source transfer, JSON transcript parsing and
  comparison, and eleven desktop mock tests. No Arch84 subsystem was changed.
- 2026-10-10: Measured Arch84 `free -l` on the physical Evo (values above).
  USB sysfs inventory succeeded. A subsequent directory query timed out and
  screenshot query NAKed; no new hardware files were written.
- 2026-10-10: Focused desktop checks passed: 11 new tests, `test_arch84.py`
  156, `test_storage.py` 68, and `test_deploy.py` 6. The quick emulator gate
  passed its early desktop files but failed `test_net` because sandbox sockets
  are denied. All MicroPython-backed cases failed to start because the
  available 32-bit binary exits with status 159 here; these are environment
  failures and do not validate or invalidate the new device programs.
- 2026-10-11: Retried on the connected Evo. USB sysfs and screenshots worked.
  The sandbox still exposed no `/dev/ttyACM0` or `/dev/serial/by-id` node;
  device-info and dynamic-info returned `no Evo CDC serial device found`,
  while one directory request reached a transient serial path but timed out.
  No program transfer was attempted because the directory preflight did not
  confirm that EVOMEM and EVOSTO names were unused.
- 2026-10-11: Isolated the missing serial node to the workspace's private
  `/dev` mount, not Evo enumeration or `cdc_acm`. Direct library access and an
  explicit serial path both fail before any USB packet; see diagnosis above.
- 2026-10-11: In a full-access session, `/dev/ttyACM0` and `uucp` membership
  were present. The device-info request succeeded. The directory needed a
  30-second per-packet receive wait; the previous 5-second default timed out.
  Added that wait only in the research wrapper and a desktop regression test.
- 2026-10-11: Captured firmware resource counters and a 184-entry directory,
  transferred two new probe programs to RAM after collision checks, and
  verified both appeared in a 186-entry directory. Ran each probe in the Evo
  Python shell and transcribed its output. Fixed the local sources to autorun
  when imported by `tipython`; the already transferred copies still require
  manual `main()` invocation. Left the calculator at the Calculator home screen
  with the bridge running. No existing variables or Archive backups changed.
- 2026-10-11: Fourteen research-tool desktop tests and standalone CPython smoke
  runs passed. The quick emulator gate passed all 18 desktop files, then stopped
  at the missing `/tmp/a84-micropython` binary. No emulator result is claimed.

## Phase 2 findings (2026-10-11)

**Observed:** A compatible 32-bit MicroPython 1.20 unix binary was found at
`/home/iuselinuxbtw/.claude/jobs/0160a791/tmp/mp/ports/unix/build-standard/micropython`.
The emulator now runs with `A84_MICROPYTHON` pointing there. It is a useful
code and heap gate, but does not model Evo firmware memory partitioning,
real display allocation, or post-boot heap fragmentation. See the
[staged memory profile](evo-memory-profile.md) for controlled emulator and
device readings. The safe `A84NF` unload change improved the emulator's
prompt free heap by 1,728 B; it has not been deployed to the Evo.

**Observed:** On OS 7.0.0.3996, a new `EVOPROF` program was transferred only
after the directory proved the name unused. Its [device transcript](../research/results/evo-2026-10-11-profile.txt)
shows 153,776 B free Python heap after GC at the start and 68,160 B after
staged Arch84 imports plus temporary kernel/shell construction. The staged
test succeeded within a 4,096 B contiguous-allocation cap. It performed
no list writes. This is the first same-session evidence of the import and
VFS cost, although the staged runner is not the complete Arch84 process.
The calculator was returned to its launcher afterward; no Archive backup
variables were touched.

`EVOMEM.probe(max_probe=...)` now accepts a cap from 64 to 8,192 bytes while
retaining the conservative default. `EVOMEM.experiment(max_probe=4096,
rounds=3)` is an explicit optional call: each of at most five rounds creates
24 small bytearrays (about 5.4 KiB payload), drops alternating ones, collects
GC and measures a bounded contiguous-allocation lower bound. It stops after
`MemoryError` and releases the blocks. Lines prefixed `EVO_MEM_EXP` are parsed
into a separate JSON group by `tools/evo_research.py`. This experiment has
desktop mock coverage but has **not** run on the device. Stop if the Python
app becomes unresponsive; exit normally. It does not write variables.

### Supported-storage capacity model

`A84ST` stores at most 495 payload bytes per 100-element `S` snapshot list,
with two checked slots of at most 999 blocks. `A84BL`/`A84BM` store at most
485 file-data bytes in each `X0000`–`X9999` list (three header elements and
97 data elements). File names and VFS nodes stay in the Python heap, while
the list variables consume firmware user RAM. The full `X0002` list in the
2026-10-11 directory occupied 1,314 firmware-reported bytes for 485 payload
bytes: **36.9% measured payload density for that one full list**. The
firmware counter's allocation granularity and per-list overhead are not yet
calibrated; do not extrapolate this as an exact quota.

`tools/evo_storage_model.py` uses those measured inputs and the directory
snapshot without writing to the device. Its [saved result](../research/results/evo-phase2-capacity-model.json)
is an **Inferred upper bound**, not a capacity test:

| Storage layer | Current evidence / modeled bound |
| --- | --- |
| Physical storage | **Unknown** for this US Evo; a similar Evo-T teardown identified a 16 MiB flash part, not its partition map. |
| Firmware total / free | **Observed:** 3,141,632 B total flash counter; 2,187,276 B free Archive and 483,448 B free user RAM on this run. |
| Calculator-variable space | **Observed:** 100 elements/list; current directory includes 13 `X` lists. Namespace allows at most 10,000 `X` names in Arch84's format. |
| Python-accessible persistence | **Verified in project:** `ti_system.store_list/recall_list` in user RAM. Direct Python Archive writes remain **Unknown/unsupported by the tested API**. |
| Current RAM, zero reserve | **Inferred upper bound:** 367 additional full lists × 485 = 177,995 B of file data, before VFS/snapshot overhead or heap shrinkage. Unsafe as a target. |
| Current RAM, 300,000 B reserve | **Inferred:** 139 lists × 485 = 67,415 B. Reserve is illustrative, not a proven safety threshold. |
| Archive, if readable as lists | **Hypothetical only:** 1,664 lists × 485 = 807,040 B at the same directory size. No Python Archive list read or write has been demonstrated here. |

The gap between physical flash, firmware Archive counters, calculator-variable
capacity, Python access, and effective file capacity is real. Filling user
RAM with lists would also reduce the Python heap. `A84ST` snapshots, list
headers, partial last lists, VFS metadata, foreign variables, firmware
allocation, and free-space reserve further reduce usable file data. A list
namespace count is not proof that the firmware accepts that many variables.

### Storage approaches

| Approach | Capacity/performance | Reliability and prerequisites |
| --- | --- | --- |
| Better list packing | Small gains: current full `X` list already uses 97 of 100 elements for data. | Format migration would be needed; preserve old snapshots. Low priority. |
| Archive-backed cold lists | Potentially hundreds of KiB from the reported free Archive. | **Unknown** whether Python can recall archived lists, and Python cannot archive them through the tested `ti_system` API. USB moves interrupt a running Python app. Test one new scratch list before design. |
| USB-assisted export | Desktop space is large; transfer is slow and stops the Python app. | **Observed supported path:** `evo_usb_py` documents list retrieval. `tools/evo_cold_export.py` provides a read-only, collision-safe `X` list export with a SHA-256 manifest. Restore/sync and Arch84 integration are not implemented. |
| Lightweight compression | Good for repetitive text, weak for already compressed or random data; CPU and temporary buffers cost heap. | Existing `A84CY` LZ codec is lazy and used for snapshots. Per-file compression needs a versioned format and bounded decode test before adoption. |
| Hybrid desktop cache | Desktop capacity with current calculator hot files. | Requires a consistent version/manifest protocol and recovery when PC is absent. Current network bridge may support a future explicit sync command, but durability must be designed first. |

The optional `research/EVOSCR.py` writes **one** 16-element list `Z84P` only
when `run("WRITE_Z84P")` is called. It checks `recall_list` first, refuses
collision or uncertain reads (a missing-list `NameError` is accepted), verifies the result, and never deletes the
variable. Importing it does not write. This scratch write was **not run**.
Before any device use, check the directory for `Z84P` and record available
RAM; exit Arch84. To clean up after a successful test, inspect the list and
delete exactly `Z84P` with the supported USB command only after confirming
its content and ownership. Never bulk-clear lists.

**Observed USB export proof:** after exiting the Python app, the guarded
desktop utility fetched existing list `X0002` as a 1,410-byte Evo container
without deleting or rewriting it. The [manifest](../research/results/evo-phase2-export.json)
records its SHA-256. The exported container size includes USB wrapper bytes;
the directory had reported 1,314 bytes for this variable, so these sizes
measure different layers. The local copy remains outside the repository at
`/tmp/evo-phase2-X0002.evo`. This demonstrates read-only backup of one list,
not a tested restore or an increase in live on-device capacity.

### Native execution and firmware evidence

TI's [Evo product comparison](https://education.ti.com/en/customer-support/knowledge-base/ti-83-84-plus-family/general-information/40502)
**verifies** a 156 MHz processor, but does not publish the core or memory
map. The Evo-T [teardown](https://tiplanet.org/forum/viewtopic.php?p=280662)
and [community firmware analysis](https://www.reddit.com/r/calculators/comments/1vzew7f/ti84_inside_the_evo/)
suggest Cortex-M33, TrustZone-M and signed MCUboot images. Those details are
**unverified on this US device**. No firmware image was downloaded or parsed
in this phase. TI's [OS 7.1 page](https://education.ti.com/en/products/calculators/graphing-calculators/ti-84-evo/update)
confirms a newer OS exists; this device remains on 7.0.0.3996.

The current [Evo-specific USB library README](https://github.com/Evo-Programming/evo_usb_py/blob/main/README.md)
reports type-15 `.8xpy2` MicroPython bytecode containers on 7.0 and type-18
`.8mp2` on 7.1+. Its author reports byte-exact transfer/readback on 7.1,
explicitly without proving calculator-side execution. **Inferred:** `.mpy`
is interpreter bytecode, not arbitrary native ARM execution. Precompiled
module loading might reduce Python compile peaks, but needs a separate safe
OS-7.0 device experiment with a unique program name and a known-good recovery
path. The library's own transfer routines overwrite existing variables by
default; all research transfers here use the collision-checking wrapper.

For future native-execution research, first obtain an authentic TI-distributed
update with documented provenance, hash it, identify its container and
signature layout by static analysis, and compare with independent Evo-specific
reports. A chip datasheet or CE jailbreak does not establish a usable Evo
privilege boundary. Firmware flashing, bootloader modification and payload
execution remain outside this phase. Recovery from a failed firmware change
is **Unknown**, so the risk is high.

### Phase 3 priorities

1. **Low risk:** deploy the tested memory change with `--no-bak` only after a
   controlled baseline of `free -l` and startup commands on the existing
   build. Verify boot, file operations, `fsck`, and a fresh-boot `selftest 2`;
   then repeat the same measurements. Backup variables stay untouched until
   the new build passes on-device validation.
2. **Low risk:** repeat `EVOPROF` from fresh Python sessions and measure
   variance. Extend the emulator benchmark with package peak metrics only
   when the instrumentation overhead and package fixture are controlled.
3. **Opt-in write:** run the one-list `Z84P` benchmark after a second directory
   preflight. Measure the firmware free-RAM delta and readback, then perform
   explicit targeted cleanup. Do not perform a fill-to-capacity experiment.
4. **Low risk:** test read-only export of one existing `X` list through the
   desktop companion, hash it, and compare its data format with `A84BL`.
   Design restore/conflict rules before any bidirectional sync.
5. **Research only:** inspect a publicly distributed, authenticated Evo OS
   bundle statically; seek independent evidence for RAM, privilege, signing
   and supported execution formats before considering invasive work.

### Phase 5 update (2026-10-11)

The older Phase 3 priorities above are historical. The [Phase 5 scratch
experiment](evo-phase5-experiments.md) created, verified and removed one
eight-element RAM list and one eight-element Archive list. USB could read
both. **Observed:** `ti_system.recall_list` on the archived list caused the
firmware `ARCHIVED` error and stopped Python until the variable was
unarchived. Archive capacity is therefore not directly usable as an
in-process Arch84 file store through that call on OS 7.0.0.3996. A
USB-assisted RAM staging workflow remains untested. These experiments did
not establish maximum capacity or a way to enlarge the Python heap.
