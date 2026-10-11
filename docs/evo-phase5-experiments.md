# Phase 5 reversible Evo experiments (2026-10-11)

## Recovery baseline

**Observed:** The US Evo ran OS `7.0.0.3996` and listed 187 variables before
the first write. The Phase 4 export verified 187/187 containers locally with
no failed or pending entries. Its original is at
`/home/iuselinuxbtw/Arch84Backups/evo-phase4-2026-10-11`. A non-overwriting
copy was made on the separately mounted 1 TB HDD at
`/mnt/1TB HDD/Arch84Backups/evo-phase4-2026-10-11`; both passed
`tools/evo_backup.py --verify` and their manifest SHA-256 was
`806b5d8c769f2ce47bbfa2a46ddcdee03030be34df984e2b51021c6573782ec7`.
The exported variable types are **not** all restore-tested.

`tools/evo_scratch.py` holds the shared USB lock; refuses names already
present under any type; checks both free-RAM and free-Archive reserves; writes
an fsynced intent journal before a transfer; sends with firmware overwrite
policy 0; and checks the returned variable's type, name, location, list
length, container checksum and SHA-256. Cleanup rereads the same variable and
refuses deletion if its content or location changed. A transfer or deletion
timeout is journaled as indeterminate. The journal and live directory must be
checked before retry. Mock tests cover these failure paths. The tool is
restricted to `Z84R` in RAM and `Z84A` in Archive, eight integers each, and
requires at least 400,000 B firmware-reported free RAM and 2,000,000 B free
Archive. These are conservative stopping limits, not capacity measurements.

## Physical results

| Experiment | Evidence | Result |
| --- | --- | --- |
| `Z84R` RAM list | [transaction journal](../research/results/evo-phase5-scratch-ram.jsonl) | Created, read back (176 B Evo container, 86 B directory size), then hash-verified and deleted. Firmware free RAM changed 481,692 to 481,420 B during creation; this is a counter delta of 272 B, not a guaranteed per-list cost. |
| `Z84A` Archive list | [transaction journal](../research/results/evo-phase5-scratch-archive.jsonl) | Created, read back (176 B container, 86 B directory size), then hash-verified and deleted. Firmware free Archive changed 2,186,436 to 2,186,296 B during creation, a 140 B delta. Free RAM changed 481,584 to 481,520 B. |
| Python recall of `Z84A` | [device screenshot](../research/results/evo-phase5-archive-python-error.png) | The fresh `EVOCOLD` program called `ti_system.recall_list("Z84A")`. The Python app stopped with firmware error `ARCHIVED` and instruction to unarchive the variable before use. This established that this archived scratch list was not directly usable through `recall_list` on OS 7.0.0.3996. The Python `try/except` did not catch the firmware-level interruption. |
| `EVOCOLD` cleanup | [transaction journal](../research/results/evo-phase5-probe-cleanup.jsonl) | The type-15 RAM program was read back, its embedded appvar matched the exact repository source, then it was deleted. |

An initial `Z84R` cleanup attempt timed out while the upstream library
re-fetched the directory, before sending a delete request. The subsequent
USB session start was NAKed while the calculator was unresponsive. The
runner recorded `indeterminate_delete` and stopped. When the calculator
responded again, a screenshot and fresh directory/readback were obtained;
cleanup then succeeded with a longer directory-read timeout. The timeout
shows why a failed operation must not be assumed harmless. No `X`, `S`,
`*BAK`, or other pre-existing variable was intentionally modified.

The final deletion operations each obtained a post-delete directory with
the scratch name absent; the last directory again contained 187 variables.
A complete post-experiment 187-variable backup
and content comparison was **not** performed, so preservation of every
pre-existing byte is not independently proven by these experiments.

## Reproduction and limits

From a closed Python app, with the Evo connected and the backup verified:

```sh
python3 tools/evo_scratch.py create --location ram --journal research/results/my-ram.jsonl
python3 tools/evo_scratch.py cleanup --journal research/results/my-ram.jsonl
python3 tools/evo_scratch.py create --location archive --journal research/results/my-archive.jsonl
python3 tools/evo_scratch.py cleanup --journal research/results/my-archive.jsonl
```

Do not reuse an existing journal or name. Inspect any indeterminate event
and the live device before another operation. `cleanup-probe` is restricted
to the exact `research/EVOCOLD.py` source and the `EVOCOLD` type-15 RAM name.
This experiment did not measure the maximum list count, maximum Archive
capacity, flash wear, or Python heap size. USB transfer interrupts Python,
so archived lists can serve as explicit cold storage only after a supported
unarchive/staging operation, which is not yet implemented or validated.

## Verification status

The 64 `test_evo_*.py` tests and four lazy-completion tests passed together.
The shell suite (156), storage suite (68), package suite (56), and VFS
transaction suite (3) passed in their normal separate-file runs.
`tools/genman.py --check` passed. The
[quick emulator gate](../research/results/emu-phase5-quick-gate.txt)
retained its three documented Phase 3/4 failures: flash repositories,
archive extraction, and 40-file power cut. A combined in-process unittest
run also failed `test_storage.py`'s monkeypatch test because prior
`test_arch84.py` tests reload `A84CY`, leaving the wildcard import in
`testutil` bound to a different module object. The same combined-run failure
was reproduced on unchanged commit `b6b22e2`; separate-file test execution
avoids that existing test-order interaction. Hardware self-test was not run
after these experiments because no Arch84 build was deployed.
