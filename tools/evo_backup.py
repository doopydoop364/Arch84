#!/usr/bin/env python3
"""Read-only, resumable desktop backup of Evo user variables.

Exit the Python app before running: USB variable reads close it. This tool
never sends, deletes, archives, or restores a calculator variable.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from evo_research import list_files_with_timeout, long_read_timeout

SCHEMA = 1


def digest(data):
    return hashlib.sha256(data).hexdigest()


def key(item):
    return str(item["type"]) + ":" + item["name"].upper()


def filename(item):
    return "var-%02d-%s.evo" % (item["type"], digest(key(item).encode())[:20])


def inventory(entries):
    return sorted([{"name": e["name"], "type": int(e["type"]),
                    "size": int(e.get("size", 0)), "archive": bool(e.get("mem"))}
                   for e in entries], key=lambda e: key(e))


def device_inventory(evo):
    """One directory request; retain tokens for direct read-only retrieval."""
    if not all(hasattr(evo, name) for name in ("_get_request", "variable_resource_name",
                                               "directory_display_name")):
        return inventory(list_files_with_timeout(evo)), {}
    with long_read_timeout(evo):
        raw = evo._get_request("hh01/get/hh01/inf/res?name=directory&gotohome=1")
    directory = evo.cbor_loads(raw).get("data", [])
    raw_by_key = {}
    entries = []
    for item in directory:
        entry = {"name": evo.directory_display_name(item), "type": item.get("type", 0),
                 "size": item.get("size", 0), "mem": item.get("mem", False)}
        entries.append(entry)
        raw_by_key[key(entry)] = item
    return inventory(entries), raw_by_key


def fetch_variable(evo, item, raw_item, output):
    if raw_item is None:
        with long_read_timeout(evo):
            evo.get_variable(item["name"], item["type"], str(output))
        return
    with long_read_timeout(evo):
        payload = evo._get_request("hh01/get/hh01/xfr/" + evo.variable_resource_name(raw_item))
    checksum = evo.evo_checksum(payload)
    Path(output).write_bytes(payload + checksum.to_bytes(2, "big"))


def validate_container(evo, data, item):
    if len(data) < 4 or evo.evo_checksum(data[:-2]) != int.from_bytes(data[-2:], "big"):
        raise ValueError("container checksum mismatch")
    obj = evo.cbor_loads(data[:-2], reject_duplicate_keys=True)
    meta = obj.get("metaData", {})
    payload = obj.get("data")
    if meta.get("type") != item["type"]:
        raise ValueError("container type mismatch")
    if hasattr(evo, "directory_display_name"):
        token = meta.get("name")
        if not isinstance(token, bytes) or evo.directory_display_name(
                {"type": item["type"], "tokName": token}).upper() != item["name"].upper():
            raise ValueError("container name mismatch")
    if isinstance(payload, bytes):
        if obj.get("size") != len(payload):
            raise ValueError("container size mismatch")
        integrity = "checksum, CBOR, type and payload length; restore untested"
    elif isinstance(payload, list) and item["type"] in (12, 13, 14):
        # Evo settings variables use a CBOR array and omit the byte count.
        integrity = "checksum, CBOR and type; settings structure and restore untested"
    elif payload is None and item["type"] == 1 and obj.get("type") in (0, 1) and obj.get("len") == 0:
        # The calculator's six empty built-in lists have a header but no data.
        integrity = "checksum, CBOR and empty-list length; restore untested"
    else:
        raise ValueError("unsupported container structure (type=%r, data=%s, header_type=%r, length=%r)" %
                         (item["type"], type(payload).__name__, obj.get("type"), obj.get("len")))
    return {"sha256": digest(data), "bytes": len(data),
            "integrity": integrity}


def atomic_json(path, data):
    fd, temp = tempfile.mkstemp(prefix=".manifest-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def verify_backup(evo, destination):
    destination = Path(destination)
    manifest = json.loads((destination / "manifest.json").read_text())
    if manifest.get("schema") != SCHEMA or not isinstance(manifest.get("inventory"), list):
        raise ValueError("unsupported backup manifest")
    rows = manifest.get("results", {})
    expected = {key(e) for e in manifest["inventory"]}
    if not isinstance(rows, dict) or not set(rows).issubset(expected):
        raise ValueError("manifest result keys are inconsistent")
    for item in manifest["inventory"]:
        row = rows.get(key(item), {})
        if row.get("status") != "exported":
            continue
        if row.get("file") != filename(item):
            raise ValueError("manifest file name mismatch")
        data = (destination / row["file"]).read_bytes()
        validated = validate_container(evo, data, item)
        if validated["sha256"] != row.get("sha256") or validated["bytes"] != row.get("bytes"):
            raise ValueError("backup file hash or length mismatch: " + key(item))
    manifest["summary"] = {
        "exported": sum(r.get("status") == "exported" for r in rows.values()),
        "failed": sum(r.get("status") == "failed" for r in rows.values()),
        "pending": len(expected - set(rows)),
        "restore_verified": False,
    }
    return manifest


def backup(evo, lock, destination, resume=False):
    destination = Path(destination)
    manifest_path = destination / "manifest.json"
    if resume:
        old = verify_backup(evo, destination)
    else:
        if destination.exists():
            raise FileExistsError(str(destination))
        old = None
    with lock(timeout=120):
        entries, raw_by_key = device_inventory(evo)
        if len({key(e) for e in entries}) != len(entries):
            raise ValueError("ambiguous duplicate names and types in device directory")
        if old is None:
            destination.mkdir(mode=0o700, parents=False, exist_ok=False)
            manifest = {"schema": SCHEMA, "source": "TI-84 Evo USB directory",
                        "inventory": entries, "results": {}}
            atomic_json(manifest_path, manifest)
        else:
            manifest = old
            if entries != manifest["inventory"]:
                raise RuntimeError("device directory changed; cannot resume this snapshot")
        for item in entries:
            ident = key(item)
            row = manifest["results"].get(ident, {})
            if row.get("status") == "exported":
                continue
            target = destination / filename(item)
            try:
                if target.exists():
                    # Crash after the file link but before manifest update.
                    data = target.read_bytes()
                    result = validate_container(evo, data, item)
                else:
                    with tempfile.TemporaryDirectory(prefix=".partial-", dir=destination) as td:
                        temp = Path(td) / "variable.evo"
                        fetch_variable(evo, item, raw_by_key.get(ident), temp)
                        data = temp.read_bytes()
                        result = validate_container(evo, data, item)
                        with temp.open("rb") as f:
                            os.fsync(f.fileno())
                        os.link(temp, target)  # atomic and refuses an existing backup
                manifest["results"][ident] = dict(result, status="exported", file=target.name)
            except Exception as exc:
                manifest["results"][ident] = {"status": "failed", "error": type(exc).__name__ + ": " + str(exc)}
            atomic_json(manifest_path, manifest)
    return verify_backup(evo, destination)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--verify", action="store_true", help="verify desktop files only; no USB access")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    import evo_usb
    if args.verify:
        result = verify_backup(evo_usb, args.destination)
    else:
        from usblock import usb_lock
        result = backup(evo_usb, usb_lock, args.destination, args.resume)
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    return 0 if result["summary"]["failed"] == 0 and result["summary"]["pending"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
