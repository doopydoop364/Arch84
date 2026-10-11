#!/usr/bin/env python3
"""Repeatable Arch84 heap benchmark under the 32-bit MicroPython emulator.

The JSON is an emulator result, never a physical Evo measurement. Set
A84_MICROPYTHON to the compatible 32-bit unix port described in emu/README.md.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from emu.emu import Emu

SCENARIOS = {
    "boot_commands": ["pwd", "ls"],
    "file_cycle": ["echo phase2 > /tmp/phase2", "cat /tmp/phase2",
                   "rm /tmp/phase2"],
}
PACKAGE_LINES = ["mkdir -p /tmp/p/usr/bin", "echo hi > /tmp/p/usr/bin/p",
                 "makepkg /tmp/p p 1",
                 "pacman -U /var/cache/pacman/pkg/p-1.ar84", "pacman -Q p"]


def summarize(report):
    if report.get("rc") != 0 or report.get("error") is not None:
        raise RuntimeError("emulator failed: " + str(report.get("error") or report.get("stderr")))
    marks = report.get("profile", [])
    by_name = {row[0]: row for row in marks}
    imports = report.get("imports", [])
    previous = report["free_start"]
    ranked = []
    for name, free in imports:
        ranked.append({"module": name, "retained_delta": previous - free})
        previous = free
    ranked.sort(key=lambda item: item["retained_delta"], reverse=True)
    commands = []
    for row in marks:
        name = row[0]
        if not name.startswith("command_before:"):
            continue
        command = name[len("command_before:"):]
        after = by_name.get("command_after:" + command)
        if after is not None:
            commands.append({"command": command, "free_before_gc_cycle": row[1],
                             "free_after_gc_cycle": after[1],
                             "retained_delta": row[1] - after[1],
                             "bounded_contiguous_lower_bound": after[3]})
    fs_before = by_name.get("fs_before")
    fs_after = by_name.get("fs_after")
    return {
        "heap_total": report["heap_total"],
        "free_start": report["free_start"],
        "free_loaded": report["free_loaded"],
        "boot_free": report.get("boot_free"),
        "min_free_gc": report.get("min_free_gc"),
        "end_free": report.get("end_free"),
        "largest_boot_lower_bound": by_name.get("greeting_after", [None, None, None, None])[3],
        "largest_boot_cap": by_name.get("greeting_after", [None, None, None, None, None])[4],
        "filesystem_load_inclusive_delta": (fs_before[1] - fs_after[1]
                                            if fs_before and fs_after else None),
        "commands": commands,
        "ranked_imports": ranked,
    }


def run(heap=127800, mp=None):
    out = {"environment": "32-bit MicroPython unix emulator",
           "heap_request": heap, "scenarios": {},
           "not_measured": ["physical RAM", "device fragmentation",
                            "true in-command package allocation peak",
                            "flash write latency"]}
    for name, lines in SCENARIOS.items():
        emu = Emu(mp=mp, heap=heap)
        rep = emu.run(lines, profile=True)
        out["scenarios"][name] = {"commands": lines, "summary": summarize(rep),
                                   "imports": rep["imports"], "profile": rep["profile"],
                                   "stores": rep.get("stores"), "recalls": rep.get("recalls")}
    # A tiny real package can compile/install at this emulator heap. At the
    # default tighter heap it fails during makepkg, so use a separate,
    # explicitly labeled reference heap instead of reporting a false peak.
    package_heap = max(heap, 159000)
    rep = Emu(mp=mp, heap=package_heap).run(PACKAGE_LINES, profile=True)
    installed = "installed p 1 (1 files)" in rep["stdout"] and "p 1\n" in rep["stdout"]
    out["scenarios"]["package_install"] = {
        "commands": PACKAGE_LINES, "heap_request": package_heap,
        "installed": installed, "summary": summarize(rep),
        "imports": rep["imports"], "profile": rep["profile"],
        "stores": rep.get("stores"), "recalls": rep.get("recalls")}
    emu = Emu(mp=mp, heap=heap)
    first = emu.run(["pwd"], profile=True)
    second = emu.run(["pwd"], profile=True)
    out["relaunch"] = {"first": summarize(first), "second": summarize(second),
                       "boot_free_delta": second["boot_free"] - first["boot_free"]}
    return out


def compare(before, after):
    if before["environment"] != after["environment"] or before["heap_request"] != after["heap_request"]:
        raise ValueError("benchmarks use different environments or requested heaps")
    fields = ("boot_free", "min_free_gc", "largest_boot_lower_bound", "end_free")
    return {name: {key: after["scenarios"][name]["summary"][key] -
                   before["scenarios"][name]["summary"][key] for key in fields}
            for name in before["scenarios"] if name in after["scenarios"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--heap", type=int, default=127800)
    parser.add_argument("--mp", help="path to a compatible 32-bit MicroPython")
    parser.add_argument("--output", type=Path, help="write JSON here")
    parser.add_argument("--compare", type=Path, nargs=2, metavar=("BEFORE", "AFTER"),
                        help="compare two saved emulator benchmark JSON files")
    args = parser.parse_args(argv)
    if args.heap < 100000 or args.heap > 3000000:
        parser.error("heap must be between 100000 and 3000000 bytes")
    if args.compare:
        result = compare(*(json.loads(path.read_text()) for path in args.compare))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    result = run(args.heap, args.mp)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded, end="")
    for name, item in result["scenarios"].items():
        s = item["summary"]
        print("%s: boot %s B free, minimum %s B; largest tested %s/%s B" %
              (name, s["boot_free"], s["min_free_gc"],
               s["largest_boot_lower_bound"], s["largest_boot_cap"]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
