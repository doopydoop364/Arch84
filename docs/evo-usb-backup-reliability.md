# Evo USB backup reliability

## Verified workflow

`python3 tools/evo_backup.py DEST` exports every entry in one read-only Evo
directory snapshot. It holds `/tmp/arch84-usb.lock` for the USB session, uses
one directory request and documented variable-read requests, writes each
container through a private temporary directory, and links the validated
file into place without replacing an existing file. The manifest is replaced
atomically after each variable, with `fsync` on file and parent directory.
`--resume` verifies all recorded files before retrying failed entries and
refuses a changed directory. `--verify` checks desktop files without USB.
Neither command sends a variable to the calculator. A USB read closes the
Python app, so exit it first.

**Observed, US Evo OS 7.0.0.3996, 2026-10-11:** A complete read-only export
of **187/187** directory entries passed local checksum, CBOR, embedded-name, type and
SHA-256 validation. It is stored privately at
`/home/iuselinuxbtw/Arch84Backups/evo-phase4-2026-10-11` (directory mode
0700, about 1.5 MiB on disk). The manifest SHA-256 is
`806b5d8c769f2ce47bbfa2a46ddcdee03030be34df984e2b51021c6573782ec7`.
An offline `--verify` passed after moving the directory. A subsequent
read-only directory query was identical to the pre-backup 187-entry list,
including `X0002` and all three `*BAK` programs. The backup contains user
variables and is deliberately outside Git.

The first pass validated 178 containers. Three settings variables use a CBOR
array rather than a byte string. Six empty built-in lists (`L1`–`L6`) have
no `data` field and declare zero length. After confirming those structures
with read-only retries, the validator accepted them with narrower integrity
claims. Each manifest entry says which checks were performed. **A verified
export is not a verified restore.** The six empty lists and three settings
variables have not been restored, and the manifest records
`restore_verified: false`.

## Restore boundary

`tools/evo_cold_restore.py` remains opt-in and supports only an Arch84 `X`
list. `--backup DIRECTORY --name X0002` verifies the full manifest and the
exact embedded name before considering a write. A write requires `--write`,
refuses any destination name already listed on the Evo, then reads the
transferred variable back and compares its full SHA-256. A send exception
or failed readback reports an **indeterminate** outcome and is never retried
automatically. It does not delete or replace a variable to make room.
No Phase 4 restore was performed on hardware.

The previous `X0002` incident establishes that `INVALID_DATA_PAYLOAD` can
follow a partial mutation. USB preflight cannot make the firmware's
replacement operation atomic, and a directory can change between checks
when another process or device action intervenes. The shared lock excludes
cooperating Arch84 tools, but not TI Connect Evo or other uncooperative
software. After any failed send, stop and inspect the directory and an
independent backup before deciding on a manual recovery. Never retry a
possibly partial send into an occupied name.

## Failure tests and remaining limits

Mock tests cover directory timeout, disconnection during retrieval, partial
manifest resume, an orphan file linked before manifest update, corrupted
desktop files, destination collisions, changed directory, invalid checksum,
failed send, and failed readback. They cannot model firmware transaction
behavior, USB electrical disconnects, or the Evo's data parser. `--resume`
only detects directory changes visible through name/type/size/location; a
variable changing contents without changing size is not detectable from the
directory alone. A validated backup should be copied to a second durable
desktop location before depending on it for disaster recovery.

The [Evo USB library](https://github.com/Evo-Programming/evo_usb_py)
documents variable retrieval and warns that its transfer commands can
overwrite existing names. Arch84 uses its library through locked wrappers;
the gitignored `evo_usb.py` was not modified.
