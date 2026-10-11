# TI-84 Evo technical reference (2026-10-11)

The target here is the **US TI-84 Evo**, product ID 23. The Evo-T is a
related model, and TI-84 Plus CE hardware findings are not transferred to
this device. Labels below describe evidence quality, not confidence rhetoric.

## Hardware and firmware counters

| Item | Current finding | Status and source |
| --- | --- | --- |
| Processor speed | 156 MHz | **Verified:** [TI Evo specification](https://education.ti.com/en-au/products/calculators/graphing-calculators/ti-84-evo). |
| CPU instruction family | ARM Thumb-style vector tables in the official 7.1 package; Cortex-M family is plausible. Exact core is unestablished. | **Inferred:** first image vector words at package offset `0x400` are initial SP `0x300007f8` and odd reset entry `0x100b1add`. [MCUboot format](https://github.com/mcu-tools/mcuboot/blob/main/docs/design.md) plus offline inspection. |
| Cortex-M33 and TrustZone-M | Community analysis suggests both; no independent core identifier or secure/nonsecure configuration has been verified on this US unit. | **Unknown:** [community report](https://www.reddit.com/r/calculators/comments/1vzew7f/ti84_inside_the_evo/). |
| Physical RAM | Chip capacity and address map on the US unit are unestablished. | **Unknown.** The firmware's `total-ram` counter is a user-memory figure, not a chip identification. |
| Firmware total/free RAM | 961,536 B total and 481,256 B free before the Phase 3 run. | **Observed:** `get_device_info` / `get_dynamic_info` on OS 7.0.0.3996. Free changes with variables and sessions. |
| Python GC heap | Standalone staged session: 153,776 B free after GC at start in Phase 2; full Arch84 Phase 3 prompt: 54,960 B free of 156,736 B reported heap. | **Observed:** [profile](evo-memory-profile.md) and [Phase 3 baseline](evo-phase3-hardware-validation.md). Different sessions; do not directly subtract as controlled stages. |
| Official user memory | 3.5 MB available to calculator users. | **Verified:** [TI Evo specification](https://education.ti.com/en-au/products/calculators/graphing-calculators/ti-84-evo). This is a product figure, not Python heap size. |
| Firmware flash counters | 3,141,632 B total; 2,187,276 B free Archive on this device. | **Observed:** USB information response. These counters do not identify physical flash size. |
| Physical flash | Unknown on this US unit. A teardown of a related Evo-T found a 16 MiB NOR chip. | **Unknown** for this device; [Evo-T teardown](https://tiplanet.org/forum/viewtopic.php?p=280662). |
| Display | 320×240, 16-bit color; firmware uses a 319×209 graphing area. | **Verified:** [TI Evo specification](https://education.ti.com/en-au/products/calculators/graphing-calculators/ti-84-evo). Exact Python display-buffer allocation is **Unknown**. |
| USB | VID:PID `0451:e018`; CDC ACM serial interface plus HID and vendor interfaces seen in Linux sysfs. | **Observed** on the connected Evo. Protocol semantics beyond documented tools remain **Unknown**. |

The USB identity, firmware counters, BL1 `1.0.0.260`, BL2 `7.0.0.3386`,
BSP `7.0.0.3992`, and package version `7.0.0.3996` came from supported
read-only queries through `tools/evo_research.py device`. The USB library
uses Kermit over the serial device and documents screenshot, directory,
variable retrieval/transfer, and OS transfer operations
([source](https://github.com/Evo-Programming/evo_usb_py)). The presence of
an OS-transfer command is not evidence of a safe downgrade or recovery path.

## Storage and Python boundary

**Observed:** `ti_system.store_list/recall_list` provides named calculator
lists of at most 100 numeric elements. Arch84 packs 40 payload bits per
element as a half-integer. A full `X` list holds 485 file bytes in 97 data
elements plus three header elements. One `X0002` list occupied 1,314 bytes
in the firmware directory, a 36.9% payload-to-reported-size ratio. The
directory also contains `S` snapshot lists; `A84ST` keeps two verified save
slots. [Arch84 format](FILES_IN_LISTS.md) and [storage model](evo-memory-research.md)
give the method and limitations.

**Inferred:** firmware user RAM backs both calculator variables and the
Python environment. More lists can shrink the Python heap, so available
firmware RAM cannot all be allocated to Arch84 data. The standalone GC heap
is an interpreter-managed subset of resources reported by the firmware;
Arch84 imports, code objects, VFS nodes, shell state and graphics state use
part of that heap. On the baseline full boot, GC reported 54,960 B free but
`free -l` could find only a 2,146 B block. That is a bounded contiguous
lower bound, consistent with fragmentation. It does not reveal the firmware
heap-size policy or a way to enlarge it.

**Unknown:** a supported TI-Python API for moving a list into Archive, for
recalling archived lists from Python, or for resizing the interpreter heap.
The desktop USB tool can move variables while Arch84 is stopped, but any
variable transfer closes the Python app. Archive's free-space counter is
therefore not a mounted Python filesystem. Direct `open()` on this runtime
has been observed to return `None`, and `os` is absent.

## Static OS 7.1 package inspection

**Verified source:** TI Connect Evo currently serves
[`TI84Evo_Bundle_7.1.0.4421.84b2`](https://connectevo.ti.com/ticevo/en/assets/os/TI84Evo_Bundle_7.1.0.4421.84b2).
The package is for `84US`, product ID 23, per its own metadata. It was
downloaded to `/tmp`, never sent to the calculator. `tools/evo_firmware_inspect.py`
records the reproducible [JSON inventory](../research/results/evo-phase3-firmware-7.1-static.json).

**Observed in that file:** 4,148,077 bytes, SHA-256
`86fe1b026bbea4538511f6b3241b19c77361dfb95259d0105c941a2459953a96`.
It is a ZIP with `METADATA`, `Archive/`, and one `.84pk2` package. The latter
contains ten recognizable MCUboot headers. Their embedded SHA-256 values
match the header/body/protected-TLV bytes, and each has `0x01` key-hash and
`0x23` 384-byte signature TLVs. `0x23` is the
[MCUboot RSA-3072-PSS signature type](https://github.com/mcu-tools/mcuboot/blob/main/docs/design.md).
The second image's protected TLVs include vendor-specific entries; their
meanings have not been established. The first two image headers begin at
package offsets `0x0` and `0x100000`; this is a file layout, **not** a
validated physical partition map. The package's first image version is
7.1.0.4413, the other nine are 7.1.0.4421. The actual device remains on
7.0.0.3996.

**Inferred:** TI distributes signed MCUboot-format images. **Unknown:**
which component checks the signatures, what keys the physical unit trusts,
whether rollback protection is enabled, which core executes each image,
and whether TrustZone is configured. A matching SHA-256 TLV proves only
internal consistency; the tool does **not** verify RSA signatures or establish
a secure boot chain. These findings do not justify flashing or modifying the
device.

## Execution and privilege boundaries

**Verified:** TI documents Python and TI-BASIC programming on the Evo
([product page](https://education.ti.com/en-au/products/calculators/graphing-calculators/ti-84-evo)).
The [Evo USB project](https://github.com/Evo-Programming/evo_usb_py) documents
type-15 `.8xpy2` modules on OS 7.0 and type-18 `.8mp2` modules on OS 7.1+;
these carry MicroPython bytecode rather than arbitrary native ARM programs.
Transfer/readback on OS 7.1 is reported by that project's author, but
calculator-side execution of those particular bytecode transfers is not
established by that report. No supported native-code application interface
has been identified in the sources reviewed here.

**Unknown:** whether application pages can be executable/writable, what MPU
or TrustZone settings apply to TI-Python, whether an application can request
more heap, and what privilege boundary separates Python from firmware.
Generic Cortex-M emulation would prove only that a compiled program can
run on a simulated core. It would not establish an Evo loading path. Before
native execution becomes a responsible device experiment, identify the
exact core and image-to-component map, document a supported loader or
authorized development mode, independently validate signature and recovery
behavior, and obtain a restorable device-state backup. Current evidence is
insufficient for an on-device native prototype.
