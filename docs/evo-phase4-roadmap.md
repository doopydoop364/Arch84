# Phase 4 research priorities

## Ranked paths

| Rank/path | Expected benefit | Usable RAM / storage | Complexity and risk | Evidence / next gate |
| --- | --- | --- | --- | --- |
| **1. Python optimization** | Immediate, measurable prompt and command headroom. | The approved three-program Evo comparison raised first-prompt free heap by 3,744–4,016 B across two optimized boots; no extra physical RAM. | Low implementation risk, medium device-fragmentation uncertainty. | Repeat with more boots and on-device monotonic timings; profile the next retained import and verify bounded-block behavior. |
| **2. USB-assisted cold storage** | Local desktop capacity can preserve cold list variables and enable recovery. | Large external capacity, but no added live on-device Python heap or Archive mount. Transfer closes the Python app. | Medium workflow/reliability cost; low firmware risk when name collisions and hashes are checked. | Use the existing read-only export and optional restore tool with trusted manifests; design a transactional manifest before any automatic sync. |
| **3. Native execution research** | Potentially large performance gain if a supported loader exists. | RAM/storage gain unknown; the interpreter heap cannot be bypassed by assumption. | High complexity and hardware risk. | Identify exact core, privilege map, memory map, loader rules, key trust, and verified recovery. Static OS analysis only until then. |

Python optimization is the best near-term route. The measured 2 KiB emulator
gain is modest relative to the approximately 55 KiB free full-build device
heap, but it costs no storage format change and no firmware modification.
The [staged hardware test](evo-phase3-hardware-validation.md) confirms an
Evo free-heap improvement, while its bounded block varied enough that
contiguous capacity remains uncertain. A supported way to enlarge the
Python heap remains **Unknown**.

## Storage candidates

| Candidate | Capacity and performance | Reliability and compatibility | Decision |
| --- | --- | --- | --- |
| Current 40-bit list packing | Up to 485 file bytes/full `X` list; one list measured as 1,314 firmware bytes. | Existing checked format and snapshots. | Retain as default. Numeric encoding is already 5 bytes/element; changing radix cannot add payload bits. |
| Candidate compressed block | Offline proof packs up to 768 raw bytes into one list when LZSS produces ≤485 bytes. Each list is independently decodable. | New magic values and size field require a versioned VFS record, dual reader, migration and crash tests. Compression needs temporary heap and time. | Prototype only; no device format change. |
| Archive-backed cold lists | Firmware reports ~2.09 MiB free Archive. | Python list access in Archive and Python-driven archive movement remain unverified. | One collision-checked scratch test only if needed; no capacity fill. |
| USB cold export/restore | Desktop capacity is much larger; reading/writing a variable interrupts Python. | Exact-name and SHA checks plus existing backup provide recovery. A failed invalid transfer removed a variable in Phase 3, so every write must be followed by readback. | Small companion prototype exists; no automatic sync. |
| Hybrid desktop cache | May keep cold payloads off-device. | Offline behavior, version conflicts, durable commit, and interrupted transfer need design. | Defer until a manifest protocol is tested. |

### Compression proof of concept

`tools/evo_storage_codec.py` uses Arch84's bounded LZSS implementation
without writing variables. Its candidate block header packs raw and stored
lengths in one 40-bit numeric field and uses new magic numbers, so an old
Arch84 reader will reject it. On the five demo packages' individual files,
every file was shorter than one full list and **zero lists were saved**.
Across those 12 separate files the candidate encoded 268 numeric elements
versus 300 for the current scheme, a 32-element reduction; many of those
short files are not actually externalized by Arch84, so this is not an
installed-package saving.
On representative larger source text, `A84PX.py` used 19 candidate lists
versus 23 current lists, `A84SH.py` 18 versus 26, and `A84FS.py` 24 versus
31. `docs/NETWORK.md` used 17 either way. These are **offline file samples**,
not a projected gain for installed packages or a device latency result.
The raw fallback never uses more lists than the current 485-byte scheme.
Before adoption: profile compressor/decompressor peak heap on the Evo,
benchmark flash/list write cost, define a versioned storage record, and
prove old snapshots load unmodified and interrupted migrations roll back.

### Supported USB companion proof

`tools/evo_cold_export.py X0002 /tmp/X0002.8xl2` exports a present list to
a new desktop path with SHA-256. `tools/evo_cold_restore.py FILE` validates
an exported container without device I/O. `--write --sha256 DIGEST` requires
the recorded digest, checks that its embedded `X` name is unused, and sends
that one list to RAM. Do not restore to a different name: Arch84's saved VFS
refers to the original `X` index. The existing vendor library's raw-file
transfer uses a replacement policy, so directory preflight and the USB lock
are mandatory; a post-write readback is required before treating a restore
as successful. The demonstrated restoration of `X0002` in Phase 3 was
verified byte for byte. This is a recovery workflow, not live extra storage.

## Native execution evidence gates

The TI 7.1 bundle includes MCUboot-format, signed-image TLVs, but the
currently running device is on 7.0. `0x23` indicates an RSA-3072-PSS
signature field; only the embedded SHA hashes have been checked. The exact
CPU core, TrustZone configuration, secure boot enforcement, privilege map,
native application format, and recoverable downgrade path are **Unknown**.
No supported API for native programs has been found. Compiling a generic
ARM sample would not establish an Evo loading path. Phase 4 should:

1. Reproduce the static package inventory on another official bundle and
   compare component versions and protected TLVs.
2. Identify image roles and the exact CPU from authoritative hardware or
   independently reproducible firmware evidence.
3. Determine whether an official native SDK, signed app pathway, or
   development mode exists.
4. Establish tested backup and recovery mechanisms before considering any
   firmware or bootloader experiment.

Firmware flashing, unsigned payload trials, and arbitrary memory probes are
unnecessary for these gates. Current evidence does **not** support an
on-device native-execution proof.
