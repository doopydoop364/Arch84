#!/usr/bin/env python3
"""Guarded, reversible Evo list experiment. Never targets existing variables.

Each run uses one of two dedicated names: Z84R in RAM or Z84A in Archive.
The journal is durable before a write. A failed transfer is indeterminate:
inspect the device and journal instead of retrying or deleting automatically.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from evo_backup import device_inventory, fetch_variable, key, validate_container
from evo_research import long_read_timeout

NAMES = {"ram": "Z84R", "archive": "Z84A"}
VALUES = "{840501,840502,840503,840504,840505,840506,840507,840508}"
MIN_RAM = 400000
MIN_ARCHIVE = 2000000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def record(path, event, **data):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("a") as output:
        output.write(json.dumps(dict(time=time.time(), event=event, **data), sort_keys=True) + "\n")
        output.flush()
        os.fsync(output.fileno())


def read_journal(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def read_one(evo, item, raw):
    with tempfile.TemporaryDirectory(prefix="evo-scratch-") as directory:
        path = Path(directory) / "list.evo"
        fetch_variable(evo, item, raw, path)
        data = path.read_bytes()
    validate_container(evo, data, item)
    obj = evo.cbor_loads(data[:-2], reject_duplicate_keys=True)
    if obj.get("len") != 8:
        raise ValueError("scratch list length differs from expected eight elements")
    return data


def snapshot(evo):
    entries, raw = device_inventory(evo)
    if len({key(item) for item in entries}) != len(entries):
        raise RuntimeError("ambiguous device directory")
    return entries, raw


def unique_name(entries, name):
    # Name collisions across types are refused too: never rely on type alone.
    if any(item["name"].upper() == name for item in entries):
        raise FileExistsError(name)


def create(evo, journal, location, *, min_ram=MIN_RAM, min_archive=MIN_ARCHIVE):
    name = NAMES[location]
    if journal.exists():
        raise FileExistsError("experiment journal already exists")
    entries, _ = snapshot(evo)
    unique_name(entries, name)
    dynamic = evo.get_dynamic_info()
    if dynamic.get("ram", 0) < min_ram or dynamic.get("archive", 0) < min_archive:
        raise RuntimeError("free-memory reserve not met")
    record(journal, "intent", name=name, type=1, location=location,
           directory_count=len(entries), dynamic=dynamic, values=VALUES,
           risk_level=2)
    try:
        # Firmware policy=0 refuses overwrite even if state changes after preflight.
        evo.send_ascii_data("List", name, VALUES, location, overwrite=False)
    except Exception as exc:
        record(journal, "indeterminate_transfer", error=repr(exc))
        raise RuntimeError("transfer outcome unknown; inspect before any retry") from exc
    record(journal, "send_accepted")
    after, raw = snapshot(evo)
    item = next((row for row in after if row["name"].upper() == name and row["type"] == 1), None)
    if item is None or item["archive"] != (location == "archive"):
        record(journal, "verification_failed", reason="missing or wrong location")
        raise RuntimeError("scratch list missing or in unexpected location")
    data = read_one(evo, item, raw[key(item)])
    digest = sha(data)
    record(journal, "verified", sha256=digest, bytes=len(data),
           size=item["size"], directory_count=len(after), dynamic=evo.get_dynamic_info())
    return {"name": name, "location": location, "bytes": len(data),
            "firmware_size": item["size"], "sha256": digest}


def cleanup(evo, journal):
    rows = read_journal(journal)
    intents = [row for row in rows if row["event"] == "intent"]
    verified = [row for row in rows if row["event"] == "verified"]
    if len(intents) != 1 or len(verified) != 1 or any(row["event"] == "deleted" for row in rows):
        raise RuntimeError("journal does not prove ownership of a live scratch list")
    name = intents[0]["name"]
    if name not in NAMES.values():
        raise RuntimeError("unexpected scratch name")
    entries, raw = snapshot(evo)
    matches = [item for item in entries if item["name"].upper() == name]
    if not matches and any(row["event"] == "delete_intent" for row in rows):
        record(journal, "absent_after_delete_attempt", directory_count=len(entries))
        return {"name": name, "deleted": True, "method": "absent after attempted delete"}
    if len(matches) != 1 or matches[0]["type"] != 1:
        raise RuntimeError("scratch variable missing or ambiguous; no deletion")
    item = matches[0]
    if item["archive"] != (intents[0]["location"] == "archive"):
        raise RuntimeError("scratch variable location changed; no deletion")
    if sha(read_one(evo, item, raw[key(item)])) != verified[0]["sha256"]:
        raise RuntimeError("scratch variable content changed; no deletion")
    record(journal, "delete_intent", sha256=verified[0]["sha256"])
    try:
        with long_read_timeout(evo):
            evo.delete_variable(name, 1)
    except Exception as exc:
        record(journal, "indeterminate_delete", error=repr(exc))
        raise RuntimeError("delete outcome unknown; inspect directory") from exc
    after, _ = snapshot(evo)
    if any(item["name"].upper() == name for item in after):
        raise RuntimeError("scratch variable remains after delete")
    record(journal, "deleted", directory_count=len(after))
    return {"name": name, "deleted": True}


def cleanup_probe(evo, journal, source):
    """Remove only the exact EVOCOLD program built from this source revision."""
    name = "EVOCOLD"
    source = Path(source)
    expected = evo.build_appvar(name, source.read_text())
    source_sha = sha(source.read_bytes())
    if journal.exists():
        rows = read_journal(journal)
        if not rows or rows[0].get("event") != "probe_cleanup_intent" or rows[0].get("source_sha256") != source_sha:
            raise RuntimeError("probe journal does not match source")
    else:
        record(journal, "probe_cleanup_intent", name=name, type=15,
               source_sha256=source_sha, risk_level=2)
    entries, raw = snapshot(evo)
    matches = [item for item in entries if item["name"].upper() == name]
    if not matches:
        record(journal, "probe_absent", directory_count=len(entries))
        return {"name": name, "deleted": True, "method": "already absent"}
    if len(matches) != 1 or matches[0]["type"] != 15 or matches[0]["archive"]:
        raise RuntimeError("probe type or location changed; no deletion")
    item = matches[0]
    with tempfile.TemporaryDirectory(prefix="evo-probe-") as directory:
        output = Path(directory) / "program.evo"
        fetch_variable(evo, item, raw[key(item)], output)
        data = output.read_bytes()
    validate_container(evo, data, item)
    obj = evo.cbor_loads(data[:-2], reject_duplicate_keys=True)
    if obj.get("data") != expected:
        raise RuntimeError("probe program differs from expected source; no deletion")
    record(journal, "probe_verified", sha256=sha(data))
    try:
        with long_read_timeout(evo):
            evo.delete_variable(name, 15)
    except Exception as exc:
        record(journal, "indeterminate_delete", error=repr(exc))
        raise RuntimeError("probe delete outcome unknown; inspect directory") from exc
    after, _ = snapshot(evo)
    if any(item["name"].upper() == name for item in after):
        raise RuntimeError("probe remains after delete")
    record(journal, "probe_deleted", directory_count=len(after))
    return {"name": name, "deleted": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("create", "cleanup", "cleanup-probe"))
    parser.add_argument("--location", choices=NAMES, default="ram")
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=ROOT / "research" / "EVOCOLD.py")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    import evo_usb
    from usblock import usb_lock
    with usb_lock(timeout=120):
        if args.action == "create":
            result = create(evo_usb, args.journal, args.location)
        elif args.action == "cleanup":
            result = cleanup(evo_usb, args.journal)
        else:
            result = cleanup_probe(evo_usb, args.journal, args.source)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
