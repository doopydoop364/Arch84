#!/usr/bin/env python3
"""Conservative capacity estimates from an Evo read-only device snapshot.

This model does not prove that Archive lists can be read or written by Python.
It treats a measured full 100-element list size as an input, not a constant of
the hardware. Keep a substantial user-RAM reserve for the Python heap.
"""
import argparse
import json
from pathlib import Path

PAYLOAD_PER_X_LIST = 485
MAX_X_LISTS = 10000


def estimate(snapshot, full_list_bytes=1314, reserves=(0, 150000, 300000)):
    if full_list_bytes < PAYLOAD_PER_X_LIST or full_list_bytes > 10000:
        raise ValueError("implausible full-list directory size")
    dynamic = snapshot["dynamic"]
    free_ram = int(dynamic["ram"])
    free_archive = int(dynamic["archive"])
    used_x = sum(1 for row in snapshot["directory"]
                 if row.get("type") == 1 and row.get("name", "").startswith("X")
                 and row["name"][1:].isdigit() and len(row["name"]) == 5)
    names_left = max(0, MAX_X_LISTS - used_x)

    def capacity(free, reserve):
        count = min(names_left, max(0, free - reserve) // full_list_bytes)
        return {"lists": count, "payload_bytes": count * PAYLOAD_PER_X_LIST}

    return {
        "status": "Inferred capacity bounds from observed counters",
        "firmware_reported": {
            "total_ram_bytes": snapshot["attributes"].get("total-ram"),
            "total_flash_bytes": snapshot["attributes"].get("total-flash"),
            "free_user_ram_bytes": free_ram,
            "free_archive_bytes": free_archive,
        },
        "assumptions": {
            "full_list_variable_bytes": full_list_bytes,
            "payload_per_x_list_bytes": PAYLOAD_PER_X_LIST,
            "existing_x_lists": used_x,
            "remaining_x_names": names_left,
            "physical_ram_bytes": None,
            "python_archive_write_supported": False,
            "python_archive_read_verified": False,
        },
        "ram_scenarios": {str(reserve): capacity(free_ram, reserve)
                          for reserve in reserves},
        "archive_hypothetical_if_readable": capacity(free_archive, 0),
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("snapshot", type=Path, help="JSON from tools/evo_research.py device")
    p.add_argument("--full-list-bytes", type=int, default=1314)
    p.add_argument("--reserve", type=int, action="append", help="user RAM kept free (repeatable)")
    p.add_argument("--output", type=Path)
    args = p.parse_args(argv)
    reserves = tuple(args.reserve) if args.reserve else (0, 150000, 300000)
    if any(v < 0 for v in reserves):
        p.error("RAM reserve cannot be negative")
    result = estimate(json.loads(args.snapshot.read_text()), args.full_list_bytes, reserves)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
