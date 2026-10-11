# TI-84 Evo native execution evidence

## Established facts and observations

- **Verified:** [TI's US product page](https://education.ti.com/en/products/calculators/graphing-calculators/ti-84-evo)
  specifies a 156 MHz processor, 3.5 MB user-available memory, and Python
  and TI-BASIC programming. It does not identify the exact CPU core, physical
  RAM chip, MPU policy, or native application loader.
- **Observed:** The connected US Evo runs OS 7.0.0.3996. Its USB directory
  exposes type-15 Python programs. The [Evo-specific USB project](https://github.com/Evo-Programming/evo_usb_py)
  documents type-15 source/bytecode containers on 7.0 and type-18 `.8mp2`
  bytecode containers on 7.1+. Its 7.1 transfer and readback result does not
  prove native ARM execution or execution of every transferred module.
- **Verified static file:** TI's official
  [7.1.0.4421 US bundle](https://connectevo.ti.com/ticevo/en/assets/os/TI84Evo_Bundle_7.1.0.4421.84b2)
  has SHA-256 `86fe1b026bbea4538511f6b3241b19c77361dfb95259d0105c941a2459953a96`.
  [The extended static inventory](../research/results/evo-phase4-firmware-7.1-static.json)
  identifies ten MCUboot-format images. All ten embedded SHA-256 TLVs match
  their hashed regions; each has a 384-byte `0x23` RSA-3072-PSS signature
  field and a key-hash TLV. Two distinct key-hash values appear. No protected
  dependency TLV (`0x40`) was found. The first two protected security-counter
  fields decode to 117506048 and the remaining eight to 4294967295. Their
  operational meaning on this product is **unknown**.
- **Inferred:** The first image body begins with words that resemble a
  Cortex-M vector table: initial stack pointer `0x300007f8` and odd reset
  vector `0x100b1add`. This is consistent with Thumb execution, but neither
  word identifies the exact core or proves how the image is loaded. The
  other image bodies do not all begin with the same pattern. All ten
  MCUboot `load_address` header fields are zero; no physical RAM/flash map
  can be derived from them.

The parser now records image end offsets, body digests, key-hash bytes,
signature fingerprints, protected dependencies and security counters. Its
tests use synthetic images. It does **not** verify the RSA signatures, find
trusted keys, or establish device-side enforcement. The
[MCUboot design](https://github.com/mcu-tools/mcuboot/blob/main/docs/design.md)
defines those TLVs and possible validation behavior; whether TI enabled a
given MCUboot option is unknown. A matching embedded hash only proves
package consistency.

An official-looking 7.0.0.3996 URL reported in a
[Cemetech discussion](https://www.cemetech.net/forum/viewtopic.php?postdays=0&postorder=asc&start=40&t=21093) returned
HTTP 404 when fetched on 2026-10-11. TI's current
[version endpoint](https://connectevo.ti.com/ticevo/en/assets/os/version)
reported 7.1.0.4421 for the US TI-84 bundle. No second authentic bundle was
available locally for a controlled version diff. No firmware was installed.

## Native prototype decision

The exact CPU core, memory map, privilege state, TrustZone configuration,
executable regions, signed third-party app policy, and supported native
loader remain **Unknown**. A generic ARM or Cortex-M desktop program could
be built with Clang, but its execution in a generic emulator would not
establish an Evo loading route. No hardware native payload or speculative
desktop compatibility demonstration was created. Current evidence supports
continued static analysis, not a device native-execution test.

The next evidence gates are: identify the first image's component and exact
CPU from authoritative material or reproducible disassembly; map image
roles and trusted key IDs; establish whether Python programs can load only
bytecode; document an official native loader or authorized development
mode; and verify a recovery path before considering firmware changes.

## Phase 5 static continuation

The [Phase 5 inventory](../research/results/evo-phase5-firmware-7.1-static.json)
adds bounded printable-marker offsets within each image body and reports
only *candidate* Cortex-M vector words. Image 0 begins with aligned
`0x300007f8` and odd `0x100b1add`; image 1 begins with aligned
`0x20093000` and odd `0x0044bc91`. These are **Inferred** vector-table
candidates, not verified entry points or a memory map. The distinct address
ranges could have several explanations; package headers still report zero
load addresses. Image 1 contains `tipython`, `micropython`, `heap_lock`,
and `heap_unlock` text. Image 7 contains `micropython` and two
`memory allocation failed` strings. These are reproducible static markers,
not identified heap boundaries or proven image roles.

A [public Evo reverse-engineering discussion](https://www.reddit.com/r/calculators/comments/1vzew7f/ti84_inside_the_evo/)
claims Cortex-M33 and TrustZone-M features, but provides no independently
checkable device identifier or code addresses. Treat that as a community
hypothesis. [TI's Evo specifications](https://education.ti.com/en/customer-support/knowledge-base/ti-83-84-plus-family/general-information/40502)
confirm 156 MHz, not the core model. The 7.1 signatures remain unverified
against a trusted key and device-side enforcement is unknown. No firmware
was modified or flashed, and no native payload was sent to the Evo.
