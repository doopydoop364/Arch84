# Phase 5 priorities

| Rank | Path | Measured or plausible benefit | Cost and hardware risk | Evidence needed next |
| --- | --- | --- | --- | --- |
| 1 | USB backup and recovery | All 187 variables were exported and validated locally; useful before any storage experiment. | Moderate software complexity; read-only export has low device risk, restore is non-atomic. | Copy the private backup to a second durable disk, audit special variable restore formats offline, and test mock disconnections at every transfer stage. |
| 2 | Further Python heap recovery | Phase 3 gained 3,744–4,016 B at the first Evo prompt. Phase 4 pressure eviction recovered 1,808 B in a MicroPython test after Tab. | Low firmware risk; changes can affect command latency and fragmented allocation. | Repeat matched emulator profiles, measure contiguous blocks, and obtain approval before replacing installed `A84CD` on the Evo. |
| 3 | Production compressed lists | Offline source samples save 7–9 lists; random data saves none. | Medium implementation and migration risk; 55–73 KiB whole-file CPython encode peaks are not device-safe. | Design a streaming writer, dual reader, versioned snapshot record and power-cut tests; measure heap and list latency on hardware before enabling writes. |
| 4 | USB-assisted cold storage | Desktop capacity can hold exported variables, but transfer closes Python. | Medium consistency cost; destination writes are not atomic. | Define a manifest and explicit offline staging protocol; retain local copies until readback and filesystem checks pass. |
| 5 | Archive-backed Python storage | Firmware reports about 2.09 MiB free Archive. | Benefit unknown; no supported live Archive list API established. | Find an Evo-specific documented API or perform a read-only Python probe on a known archived scratch list. No existing Archive variable may be modified. |
| 6 | Native execution and jailbreak research | Potentially large, unquantified performance gain. | High complexity and hardware risk. | Identify exact core, executable memory policy, trusted-key/loader rules, image roles and recovery path. Continue static analysis only. |

The strongest immediate work is completing backup recovery guarantees and
reducing Arch84's memory pressure with measured, reversible code changes.
Compression is promising for large text but needs a bounded on-device
implementation. The current evidence does not justify firmware modification,
a native payload, or a jailbreak attempt. See [native evidence](evo-native-execution.md),
[compression candidate](evo-compressed-storage.md), and
[Phase 4 benchmark](../research/results/evo-phase4-benchmark.md).
