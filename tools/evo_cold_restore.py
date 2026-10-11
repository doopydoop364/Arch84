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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from evo_research import list_files_with_timeout


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
    if not write:
        return info
    if not expected_sha256 or info["sha256"] != expected_sha256.lower():
        raise ValueError("--write requires the matching SHA-256 from a trusted export manifest")
    with lock(timeout=120):
        entries = list_files_with_timeout(evo)
        if any(item.get("name", "").upper() == info["name"] for item in entries):
            raise FileExistsError("calculator variable already exists: " + info["name"])
        evo.send_var_file(str(path), "ram")
        info["written"] = True
    return info


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("container", type=Path)
    parser.add_argument("--write", action="store_true", help="restore only after exact-name collision preflight")
    parser.add_argument("--sha256", help="required with --write; digest from the trusted export manifest")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    import evo_usb
    from usblock import usb_lock
    print(json.dumps(restore(evo_usb, usb_lock, args.container, args.write, args.sha256), indent=2))


if __name__ == "__main__":
    main()
