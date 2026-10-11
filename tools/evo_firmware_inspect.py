#!/usr/bin/env python3
"""Read-only static inventory of a TI-84 Evo OS bundle.

Recognizes the ZIP outer wrapper and MCUboot image headers in its package.
Checks embedded SHA-256 TLVs, but does not verify signatures or attest trust.
Never extracts files, communicates with USB, or installs firmware.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile

MAGIC = b"\x3d\xb8\xf3\x96"
HEADER = struct.Struct("<IIHHIIBBHII")
MAX_PACKAGE = 32 * 1024 * 1024


def _tlv_entries(data, start, end):
    out = []
    at = start
    while at < end:
        if at + 4 > end:
            raise ValueError("truncated TLV entry")
        kind, size = struct.unpack_from("<HH", data, at)
        at += 4
        if at + size > end:
            raise ValueError("TLV exceeds area")
        out.append((kind, data[at:at + size]))
        at += size
    return out


def parse_image(data, offset):
    if offset + HEADER.size > len(data):
        return None
    magic, load_addr, header_size, protected_size, body_size, flags, major, minor, revision, build, pad = HEADER.unpack_from(data, offset)
    if magic != 0x96F3B83D or not 32 <= header_size <= 4096 or body_size < 1:
        return None
    protected = offset + header_size + body_size
    if protected + 4 > len(data):
        return None
    p_magic, p_total = struct.unpack_from("<HH", data, protected)
    if p_magic == 0x6908:
        if p_total != protected_size or p_total < 4:
            return None
        normal = protected + p_total
        try:
            protected_entries = _tlv_entries(data, protected + 4, normal)
        except ValueError:
            return None
    elif protected_size == 0:
        normal = protected
        protected_entries = []
    else:
        return None
    if normal + 4 > len(data):
        return None
    n_magic, n_total = struct.unpack_from("<HH", data, normal)
    if n_magic != 0x6907 or n_total < 4 or normal + n_total > len(data):
        return None
    try:
        entries = _tlv_entries(data, normal + 4, normal + n_total)
    except ValueError:
        return None
    digest = hashlib.sha256(data[offset:normal]).digest()
    embedded = [value for kind, value in entries if kind == 0x10]
    return {"offset": offset, "load_address": load_addr,
            "header_bytes": header_size, "body_bytes": body_size,
            "protected_tlv_bytes": protected_size, "tlv_bytes": n_total,
            "flags": flags, "version": "%d.%d.%d.%d" % (major, minor, revision, build),
            "sha256_matches_tlv": bool(embedded) and all(value == digest for value in embedded),
            "signature_tlv_present": any(kind in (0x20, 0x21, 0x22, 0x23, 0x24, 0x25) for kind, _ in entries),
            "rsa3072_pss_tlv_present": any(kind == 0x23 and len(value) == 384 for kind, value in entries),
            "protected_tlv_types": ["0x%02x" % kind for kind, _ in protected_entries],
            "tlv_types": ["0x%02x" % kind for kind, _ in entries]}


def inspect(path):
    path = Path(path)
    raw = path.read_bytes()
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        packages = [m for m in members if m.filename.endswith(".84pk2")]
        if len(packages) != 1 or packages[0].file_size > MAX_PACKAGE:
            raise ValueError("expected one bounded .84pk2 package")
        package = archive.read(packages[0])
        metadata = archive.read("METADATA").decode("ascii")
    images = []
    at = 0
    while True:
        at = package.find(MAGIC, at)
        if at < 0:
            break
        item = parse_image(package, at)
        if item is not None:
            images.append(item)
        at += 4
    return {"file": str(path), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "metadata": dict(line.split(":", 1) for line in metadata.splitlines() if ":" in line),
            "members": [{"name": m.filename, "bytes": m.file_size} for m in members],
            "package_sha256": hashlib.sha256(package).hexdigest(),
            "images": images,
            "signature_verified": False,
            "notice": "TLV hash matching is an integrity check, not signature or bootloader verification"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = json.dumps(inspect(args.bundle), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(result)
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
