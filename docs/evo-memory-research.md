# TI-84 Evo memory and storage research

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
