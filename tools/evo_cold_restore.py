#!/usr/bin/env python3
"""Preflight an exported X list and optionally restore it to an unused RAM name.

The exact embedded name is restored. Existing calculator variables are never
replaced. Default mode only validates the local container; --write is explicit.
Exit the Python app before a transfer, since variable I/O closes it.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from evo_research import list_files_with_timeout, long_read_timeout
from evo_backup import verify_backup


def inspect_container(evo, path):
    data = Path(path).read_bytes()
    if len(data) < 4 or evo.evo_checksum(data[:-2]) != int.from_bytes(data[-2:], "big"):
        raise ValueError("invalid Evo checksum")
    obj = evo.cbor_loads(data[:-2], reject_duplicate_keys=True)
    meta = obj.get("metaData", {})
    token = meta.get("name", b"")
    name = evo._decode_custom_name(token[2:]) if isinstance(token, bytes) and token[:2] == b"6\xe8" else None
    if meta.get("type") != 1 or not name or not re.fullmatch(r"X[0-9]{4}", name):
        raise ValueError("container is not an Arch84 X list")
    if obj.get("size") != len(obj.get("data", b"")):
        raise ValueError("container size mismatch")
    return {"name": name, "type": 1, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def restore(evo, lock, path, write=False, expected_sha256=None):
    info = inspect_container(evo, path)
    info["written"] = False
    info["verified"] = False
    if not write:
        return info
    if not expected_sha256 or info["sha256"] != expected_sha256.lower():
        raise ValueError("--write requires the matching SHA-256 from a trusted export manifest")
    with lock(timeout=120):
        entries = list_files_with_timeout(evo)
        if any(item.get("name", "").upper() == info["name"] for item in entries):
            raise FileExistsError("calculator variable already exists: " + info["name"])
        # A send error may still create or remove a variable. Never retry it
        # automatically, even if the transport reports an invalid payload.
        try:
            evo.send_var_file(str(path), "ram")
        except Exception as exc:
            raise RuntimeError("transfer outcome unknown; inspect the calculator before retrying") from exc
        info["written"] = True
        try:
            with tempfile.TemporaryDirectory() as td:
                returned = Path(td) / "readback.evo"
                with long_read_timeout(evo):
                    evo.get_variable(info["name"], info["type"], str(returned))
                if hashlib.sha256(returned.read_bytes()).hexdigest() != info["sha256"]:
                    raise ValueError("readback hash mismatch")
        except Exception as exc:
            raise RuntimeError("transfer sent but readback not verified; preserve the source and inspect the calculator") from exc
        info["verified"] = True
    return info


def restore_from_backup(evo, lock, directory, name, write=False):
    """Restore only an X list from a fully verified local backup manifest."""
    if not re.fullmatch(r"X[0-9]{4}", name):
        raise ValueError("only Arch84 X lists are supported for restore")
    manifest = verify_backup(evo, directory)
    row = manifest["results"].get("1:" + name)
    if row is None or row.get("status") != "exported":
        raise ValueError("list is absent from verified backup: " + name)
    if manifest["summary"]["failed"] or manifest["summary"]["pending"]:
        raise ValueError("backup is incomplete; verify all exports first")
    path = Path(directory) / row["file"]
    info = inspect_container(evo, path)
    if info["name"] != name:
        raise ValueError("embedded list name differs from manifest")
    return restore(evo, lock, path, write=write, expected_sha256=row["sha256"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("container", type=Path, nargs="?")
    parser.add_argument("--backup", type=Path, help="verified evo_backup.py directory")
    parser.add_argument("--name", help="X list name inside --backup")
    parser.add_argument("--write", action="store_true", help="restore only after exact-name collision preflight")
    parser.add_argument("--sha256", help="required with --write; digest from the trusted export manifest")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    import evo_usb
    from usblock import usb_lock
    if args.backup:
        if args.container or not args.name or args.sha256:
            parser.error("--backup requires --name and excludes container/--sha256")
        result = restore_from_backup(evo_usb, usb_lock, args.backup, args.name, args.write)
    else:
        if args.container is None or args.name:
            parser.error("provide one container, or --backup with --name")
        result = restore(evo_usb, usb_lock, args.container, args.write, args.sha256)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
