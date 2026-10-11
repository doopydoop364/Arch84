# Reliability and recovery

## Package installation and removal

`A84PS.records` reads `.ar84` records incrementally from VFS pieces. A record is limited to 1024 characters; the existing format still limits an archive to 300 entries and each file to 20,000 characters. `scan` checks paths, duplicates, sizes, file sums, and the archive sum before installation. The install pass checks the archive sum again in case the source changed. Files of at least 1024 characters are written directly to `X` lists through `A84BM.BlobWriter`, one 485-byte payload at a time. Smaller files use the normal VFS writer.

`A84TR.Transaction` records the old VFS nodes for one package install, upgrade, or removal. If a Python exception occurs before the operation finishes, it restores the old nodes and package database entry. The undo log is limited to 600 distinct paths; exceeding that limit fails the operation. The log lives in RAM and is discarded on power loss. An interrupted multi-package `pacman -S` can leave earlier packages installed while the current package rolls back.

## Persistent commits

`A84ST` already saves an inactive filesystem snapshot, verifies it, and selects it with a final metadata write. A power loss before selection loads the previous valid snapshot; one after selection loads the new valid snapshot. `X` list IDs referenced by the last saved snapshot stay reserved until a later save, so replacement data cannot overwrite that snapshot. This applies to `sync`, `exit`, and package changes once saved. It does not make an unsaved in-memory command durable. A storage failure during a new `X` list write may leave an unreferenced list. `fsck` verifies referenced lists; it does not report every orphan. Repair remains a separate, explicit operation.

Run `fsck` to verify the selected snapshot, external lists, and installed package files. Run `fsck -r` only when intentionally repairing; it can discard damaged data. Never clear calculator lists to resolve an error.

## Shell and memory

`A84PE` scans command separators by offsets and groups plain argument spans before creating strings. It preserves quotes, escapes, expansion, pipes, and redirection. Limits are 4096 characters per line, 32 chained commands, 128 arguments per stage, and 16 pipeline stages; larger input raises `ParseError`.

`A84VM.Pager` supports configurable page/window sizes, LRU write-back, pinning, zero pages, guarded allocations, bounded cache-release and unload callbacks, and `stats()`. A failed dirty-page write leaves the page resident and dirty. Its list backend uses the `V` namespace and skips foreign lists. The pager is a library, not part of the shell's resident heap: current package and VFS streams already write directly to `X` lists, and moving those streams through swap would add list traffic. The shell continues to use its existing lazy-module eviction and the kernel's save reserve. `free -l` reports the largest allocatable block; `gc.mem_free()` alone cannot predict a large allocation on the calculator.

## Verification

Run `python3 test_pacman.py`, `python3 test_vfs_transaction.py`, `python3 test_vm_reliability.py`, and the full gate `A84_MICROPYTHON=<32-bit binary> python3 emu/run_all.py`. Compare any constrained-heap failure with the same command on the starting commit. The emulator does not model calculator fragmentation or actual `ti_system` timing; use a fresh calculator boot and `selftest 2` for hardware validation. Do not refresh `*BAK` copies until an experimental build has passed device checks.

The 2026-10-09 audit in `ARCH84_DEVLOG.md` records measured results. On hardware, `free -l` reported 55,712 bytes free but only a 2,986-byte largest block. A scratch package install/remove and read-only `fsck` passed, as did an earlier 50/50 self-test; the exact final source tree was not fully rechecked after the last small fix. The full emulator gate remains non-green. With the available 32-bit interpreter, both baseline boot modules and this branch fail the 103 KB boot and editor create/save/cat cases; the leak check has not been classified against that baseline. These runs do not establish a green constrained-heap result. List-backed pager I/O and large-package extraction also await hardware measurement.

### Phase 2 audit (2026-10-11)

The reliability changes remain on `research/evo-memory-storage`. A new
transaction test injects `MemoryError` while recording the old node for a
replacement write. The old file and clean flag remain intact, and rollback
completes. Existing `test_storage.py`, `test_pacman.py`, `test_bigfiles.py`,
`test_vm_reliability.py`, and `test_vfs_transaction.py` cover interrupted
snapshot selection, old-format loads, changed package input, partial list
writes and rollback. The undo log is in heap: an abrupt power loss before
`sync` reverts to the previously selected snapshot, not to a partially
applied in-memory package transaction. Failed new `X` writes can still leave
unreferenced lists; they do not replace the selected snapshot's lists.

`A84BM.free_id` now reuses an unreferenced `X` list only when its magic,
embedded index and byte-count header are all plausible. Previously a foreign
list under an `X` name whose first element happened to equal Arch84's magic
could be overwritten. A focused regression test covers a mismatched embedded
index. The list format is unchanged. Deliberately forged full headers remain
outside what this namespace check can distinguish; avoid sharing Arch84's
`X` names with unrelated data.

The compatible 32-bit MicroPython binary was recovered and the quick emulator
gate was rerun. Its 103 KB key fuzz and editor create/save/cat failures occur
on `bf28517` and `c9d8259` when the checkout path has the same length as the
current repo path. Shorter paths can make those tests pass at this narrow
heap margin. Flash repository, archive and 40-file power-cut failures also
occur on the baseline. These cases remain unresolved reliability risks; no
test was disabled. The emulator cannot establish that the device's highly
fragmented heap or actual `ti_system` storage timing will behave the same.

The new neofetch unload has passed desktop behavior tests and emulator
profiling. It has not been deployed to hardware because the current device
already contains those program names and this research phase requires
avoiding automatic overwrite. The Archive `*BAK` copies were not refreshed.

The single-process `python3 -m unittest discover` invocation is not a valid
project-wide gate: some existing tests change the working directory or patch
module globals and do not restore them for later files. It reported seven
cross-file failures, including missing relative paths after a temporary
directory became current. `test_storage.py`, `test_archive.py`,
`test_manpages.py`, and the new VFS transaction test pass when run as separate
files; the emulator runner likewise executes desktop files separately.
Tests should continue to use separate processes until those isolation bugs
are repaired.
