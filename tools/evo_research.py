#!/usr/bin/env python3
"""Read-only Evo inventory, safe diagnostic transfer, and result comparison.

USB protocol calls use the same lock as tools/evo and deploy.py. The default
`usb` command only reads Linux sysfs and also works with a fixture directory.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))


def _read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return None


def scan_usb(root=Path("/sys/bus/usb/devices")):
    devices = []
    for vendor_file in sorted(root.glob("*/idVendor")):
        node = vendor_file.parent
        vendor = _read(vendor_file)
        product = _read(node / "idProduct")
        if vendor is None or product is None:
            continue
        interfaces = []
        for iface in sorted(root.glob(node.name + ":*")):
            driver = iface / "driver"
            tty_dir = iface / "tty"
            interfaces.append({
                "number": _read(iface / "bInterfaceNumber"),
                "class": _read(iface / "bInterfaceClass"),
                "subclass": _read(iface / "bInterfaceSubClass"),
                "protocol": _read(iface / "bInterfaceProtocol"),
                "driver": driver.resolve().name if driver.exists() else None,
                "tty": sorted(p.name for p in tty_dir.iterdir()) if tty_dir.is_dir() else [],
            })
        devices.append({
            "sysfs_name": node.name,
            "vendor_id": vendor.lower(),
            "product_id": product.lower(),
            "manufacturer": _read(node / "manufacturer"),
            "product": _read(node / "product"),
            "interfaces": interfaces,
        })
    return devices


def evo_only(devices):
    return [d for d in devices if d["vendor_id"] == "0451" and
            d["product_id"] == "e018"]


def parse_probe(text):
    result = {"memory": {}, "storage": {}, "profile": {}, "experiments": {}}
    prefixes = {"EVO_MEM": "memory", "EVO_STORAGE": "storage",
                "EVO_PROFILE": "profile", "EVO_MEM_EXP": "experiments"}
    for line in text.splitlines():
        parts = line.strip().split(" ", 1)
        if len(parts) != 2 or parts[0] not in prefixes or "=" not in parts[1]:
            continue
        key, value = parts[1].split("=", 1)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", key):
            continue
        target = result[prefixes[parts[0]]]
        if key in target:
            raise ValueError("duplicate probe key: " + key)
        if re.fullmatch(r"-?[0-9]+", value):
            target[key] = int(value)
        elif value == "None":
            target[key] = None
        else:
            target[key] = value
    return result


def compare(a, b):
    out = {}
    for group in sorted(set(a) | set(b)):
        left, right = a.get(group, {}), b.get(group, {})
        if not isinstance(left, dict) or not isinstance(right, dict):
            continue
        out[group] = {}
        for key in sorted(set(left) | set(right)):
            old, new = left.get(key), right.get(key)
            if old == new:
                continue
            change = {"before": old, "after": new}
            if type(old) in (int, float) and type(new) in (int, float):
                change["delta"] = new - old
            out[group][key] = change
    return out


def _jsonable(value):
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def directory_summary(entries):
    totals = {"ram": {"count": 0, "bytes": 0},
              "archive": {"count": 0, "bytes": 0}}
    types = {}
    for item in entries:
        place = "archive" if item.get("mem") else "ram"
        totals[place]["count"] += 1
        totals[place]["bytes"] += int(item.get("size", 0))
        kind = str(item.get("type", 0))
        types[kind] = types.get(kind, 0) + 1
    return {"by_location": totals, "by_type": types,
            "total_count": len(entries)}


def list_files_with_timeout(evo, timeout_ms=30000):
    """Allow the Evo's slow directory response more time than the 5 s default."""
    original = getattr(evo, "recv_pkt", None)
    if original is None:  # Simple fake devices in desktop tests.
        return evo.list_files()

    def receive(dev, session=None, timeout=None):
        return original(dev, session=session,
                        timeout=timeout_ms if timeout is None else timeout)

    evo.recv_pkt = receive
    try:
        return evo.list_files()
    finally:
        evo.recv_pkt = original


def device_snapshot(evo, lock):
    with lock(timeout=120):
        attrs = evo.get_device_info()
        dynamic = evo.get_dynamic_info()
        entries = list_files_with_timeout(evo)
        return {
            "attributes": _jsonable(attrs),
            "dynamic": _jsonable(dynamic),
            "directory": _jsonable(entries),
            "directory_summary": directory_summary(entries),
        }


def safe_send(evo, lock, path, name):
    if path.suffix.lower() != ".py" or not path.is_file():
        raise ValueError("send requires an existing .py source file")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,7}", name):
        raise ValueError("name must be 1-8 letters/digits, starting with a letter")
    with lock(timeout=120):
        names = {item["name"].upper() for item in list_files_with_timeout(evo)}
        if name.upper() in names:
            raise FileExistsError("calculator variable already exists: " + name)
        evo.send_file(str(path), name)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    usb = sub.add_parser("usb", help="read USB descriptors from sysfs only")
    usb.add_argument("--sysfs", type=Path, default=Path("/sys/bus/usb/devices"))
    usb.add_argument("--all", action="store_true", help="include non-Evo devices")
    sub.add_parser("device", help="read device attributes, memory counters and directory")
    send = sub.add_parser("send", help="preflight and transfer a new Python source program")
    send.add_argument("path", type=Path)
    send.add_argument("--name", help="calculator program name; defaults to filename stem")
    parse = sub.add_parser("parse", help="convert diagnostic transcript lines to JSON")
    parse.add_argument("path", type=Path)
    diff = sub.add_parser("compare", help="compare two parsed JSON runs")
    diff.add_argument("before", type=Path)
    diff.add_argument("after", type=Path)
    args = p.parse_args(argv)
    if args.command == "usb":
        data = scan_usb(args.sysfs)
        result = data if args.all else evo_only(data)
    elif args.command in ("device", "send"):
        sys.path.insert(0, str(ROOT))
        import evo_usb
        from usblock import usb_lock
        if args.command == "device":
            result = device_snapshot(evo_usb, usb_lock)
        else:
            name = args.name or args.path.stem.upper()
            safe_send(evo_usb, usb_lock, args.path, name)
            result = {"sent": str(args.path), "name": name}
    elif args.command == "parse":
        result = parse_probe(args.path.read_text())
    else:
        result = compare(json.loads(args.before.read_text()),
                         json.loads(args.after.read_text()))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
