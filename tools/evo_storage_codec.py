#!/usr/bin/env python3
"""Offline proof of concept for compressed Arch84 X-list payload blocks.

No calculator access. This is a candidate format, not an on-device migration.
Each list holds at most 100 numbers. New compressed blocks have a fourth
header number containing an Adler-32 checksum of decoded bytes. Raw fallback
uses the existing A84BL block layout; no calculator migration is performed.
"""
import argparse
import json
from pathlib import Path
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from A84BL import PER
from A84ST import adler, pack5, unpack5
from A84CY import lz_compress
from A84CZ import lz_decompress

COMPRESSED_MAGIC = 8487
RAW_MAGIC = 8486
RAW_CHUNK = 768
LENGTH_BASE = 1024
COMPRESSED_PER = 480


def checksum(data):
    a, b = adler(1, 0, data)
    return a + 65536 * b


def _block(magic, index, raw, payload):
    compressed = magic == COMPRESSED_MAGIC
    limit = COMPRESSED_PER if compressed else PER
    if len(payload) > limit or len(raw) > RAW_CHUNK:
        raise ValueError("block exceeds bounded format")
    padded = payload + bytes((-len(payload)) % 5)
    if compressed:
        header = [magic + 0.5, index + 0.5,
                  (len(raw) * LENGTH_BASE + len(payload)) + 0.5,
                  checksum(raw) + 0.5]
    else:
        header = [magic + 0.5, index + 0.5, len(raw) + 0.5]
    return header + pack5(padded)


def encode(data):
    """Return numbered, independently decodable list-value blocks."""
    blocks = []
    offset = 0
    while offset < len(data):
        raw = data[offset:offset + RAW_CHUNK]
        compressed = lz_compress(raw)
        if len(compressed) + 8 < len(raw) and len(compressed) <= COMPRESSED_PER:
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
        magic, found = (int(x) for x in block[:2])
        if found != index or magic not in (RAW_MAGIC, COMPRESSED_MAGIC):
            raise ValueError("invalid block header")
        if magic == COMPRESSED_MAGIC:
            if len(block) < 4:
                raise ValueError("missing checksum")
            raw_len, stored_len = divmod(int(block[2]), LENGTH_BASE)
            start = 4
            limit = COMPRESSED_PER
        else:
            raw_len = stored_len = int(block[2])
            start = 3
            limit = PER
        if not 0 < raw_len <= RAW_CHUNK or not 0 < stored_len <= limit:
            raise ValueError("invalid block size")
        if len(block) != start + (stored_len + 4) // 5:
            raise ValueError("invalid packed size")
        packed = bytes(unpack5(block[start:]))
        if any(packed[stored_len:]):
            raise ValueError("nonzero padding")
        payload = packed[:stored_len]
        if magic == COMPRESSED_MAGIC:
            part = lz_decompress(payload, raw_len)
            if checksum(part) != int(block[3]):
                raise ValueError("compressed block checksum mismatch")
        else:
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


def benchmark(data, repeats=3):
    """CPython codec timing and allocation peak; not an Evo measurement."""
    if repeats < 1 or repeats > 20:
        raise ValueError("repeats must be 1..20")
    rows = []
    for _ in range(repeats):
        tracemalloc.start()
        start = time.perf_counter()
        blocks = encode(data)
        encode_ms = (time.perf_counter() - start) * 1000
        _, encode_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        tracemalloc.start()
        start = time.perf_counter()
        if decode(blocks) != data:
            raise ValueError("roundtrip failed")
        decode_ms = (time.perf_counter() - start) * 1000
        _, decode_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rows.append({"encode_ms": round(encode_ms, 3),
                     "decode_ms": round(decode_ms, 3),
                     "encode_peak_bytes": encode_peak, "decode_peak_bytes": decode_peak})
    result = measure(data)
    result["platform"] = "CPython desktop"
    result["runs"] = rows
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--benchmark", action="store_true")
    args = parser.parse_args(argv)
    action = benchmark if args.benchmark else measure
    print(json.dumps({str(p): action(p.read_bytes()) for p in args.files}, indent=2))


if __name__ == "__main__":
    main()
