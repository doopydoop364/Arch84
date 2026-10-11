#!/usr/bin/env python3
"""Offline proof of concept for compressed Arch84 X-list payload blocks.

No calculator access. This is a candidate format, not an on-device migration.
Each list holds at most 100 numbers. The third header number packs the stored
and original byte counts; a new magic distinguishes compressed blocks.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from A84BL import PER
from A84ST import pack5, unpack5
from A84CY import lz_compress
from A84CZ import lz_decompress

COMPRESSED_MAGIC = 8487
RAW_MAGIC = 8488
RAW_CHUNK = 768
LENGTH_BASE = 1024


def _block(magic, index, raw, payload):
    if len(payload) > PER or len(raw) > RAW_CHUNK:
        raise ValueError("block exceeds bounded format")
    padded = payload + bytes((-len(payload)) % 5)
    return [magic + 0.5, index + 0.5,
            (len(raw) * LENGTH_BASE + len(payload)) + 0.5] + pack5(padded)


def encode(data):
    """Return numbered, independently decodable list-value blocks."""
    blocks = []
    offset = 0
    while offset < len(data):
        raw = data[offset:offset + RAW_CHUNK]
        compressed = lz_compress(raw)
        if len(compressed) + 8 < len(raw) and len(compressed) <= PER:
            blocks.append(_block(COMPRESSED_MAGIC, len(blocks), raw, compressed))
            offset += len(raw)
        else:
            raw = data[offset:offset + PER]
            blocks.append(_block(RAW_MAGIC, len(blocks), raw, raw))
            offset += len(raw)
    return blocks


def decode(blocks):
    out = bytearray()
    for index, block in enumerate(blocks):
        if len(block) < 3 or len(block) > 100:
            raise ValueError("invalid block length")
        magic, found, sizes = (int(x) for x in block[:3])
        raw_len, stored_len = divmod(sizes, LENGTH_BASE)
        if found != index or magic not in (RAW_MAGIC, COMPRESSED_MAGIC):
            raise ValueError("invalid block header")
        if not 0 < raw_len <= RAW_CHUNK or not 0 < stored_len <= PER:
            raise ValueError("invalid block size")
        if len(block) != 3 + (stored_len + 4) // 5:
            raise ValueError("invalid packed size")
        payload = bytes(unpack5(block[3:]))[:stored_len]
        if magic == COMPRESSED_MAGIC:
            part = lz_decompress(payload, raw_len)
        else:
            if raw_len != stored_len:
                raise ValueError("invalid raw size")
            part = payload
        out.extend(part)
    return bytes(out)


def measure(data):
    blocks = encode(data)
    if decode(blocks) != data:
        raise ValueError("roundtrip failed")
    old = (len(data) + PER - 1) // PER
    current_elements = 0
    for offset in range(0, len(data), PER):
        current_elements += 3 + (len(data[offset:offset + PER]) + 4) // 5
    candidate_elements = sum(map(len, blocks))
    return {"input_bytes": len(data), "current_lists": old,
            "candidate_lists": len(blocks), "lists_saved": old - len(blocks),
            "current_elements": current_elements,
            "candidate_elements": candidate_elements,
            "elements_saved": current_elements - candidate_elements,
            "format": "offline candidate; no device writes"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps({str(p): measure(p.read_bytes()) for p in args.files}, indent=2))


if __name__ == "__main__":
    main()
