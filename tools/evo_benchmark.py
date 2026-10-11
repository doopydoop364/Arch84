#!/usr/bin/env python3
"""Repeatable desktop/emulator memory and storage benchmark; no USB access."""
import argparse
import hashlib
import json
import platform
from pathlib import Path
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.evo_storage_codec import benchmark as codec_benchmark


def corpora():
    rng = random.Random(84)
    return {
        "small_text": b"hello Arch84\n",
        "repetitive_4k": b"Arch84 storage experiment\n" * 160,
        "random_4k": bytes(rng.randrange(256) for _ in range(4096)),
        "source_A84FS": (ROOT / "A84FS.py").read_bytes(),
        "source_A84SH": (ROOT / "A84SH.py").read_bytes(),
        "document_NETWORK": (ROOT / "docs/NETWORK.md").read_bytes(),
        "package_fortune": (ROOT / "repo/pkgs/fortune-1.0.ar84").read_bytes(),
    }


def emulator_run(heap=127800):
    from emu.emu import Emu
    emu = Emu(heap=heap)
    try:
        run = emu.run(["pwd", "ls", "echo hi > /tmp/phase4", "cat /tmp/phase4",
                       "pacman -Q", "fsck"], profile=True)
    finally:
        emu._tmp.cleanup()
    fields = ("rc", "error", "heap_total", "free_start", "free_loaded",
              "boot_free", "boot_ms", "min_free_gc", "min_free_nogc",
              "end_free", "stores", "recalls", "total_ms", "profile")
    return {"environment": "32-bit MicroPython unix emulator; not Evo hardware",
            "requested_heap": heap, "result": {k: run.get(k) for k in fields}}


def make_report(with_emulator=False, heap=127800):
    rev = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    sources = ("A84CD.py", "A84SH.py", "A84CP.py", "tools/evo_storage_codec.py")
    report = {"schema": 1, "revision": rev, "host": platform.platform(),
              "interpreter": platform.python_version(), "hardware_measurements": False,
              "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                for name in sources},
              "compression": {name: codec_benchmark(data) for name, data in corpora().items()},
              "emulator": None,
              "not_measured": ["Evo CPU timing", "Evo fragmented contiguous heap",
                               "physical list-write latency", "package-install peak heap"]}
    if with_emulator:
        report["emulator"] = emulator_run(heap)
    return report


def markdown(report):
    lines = ["# Evo phase 4 desktop benchmark", "",
             "Revision: `" + report["revision"] + "`. All compression numbers are CPython host results.", "",
             "| Corpus | Bytes | Current lists | Candidate lists | Saved | Elements saved |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for name, row in report["compression"].items():
        lines.append("| %s | %d | %d | %d | %d | %d |" %
                     (name, row["input_bytes"], row["current_lists"],
                      row["candidate_lists"], row["lists_saved"], row["elements_saved"]))
    if report["emulator"]:
        e = report["emulator"]["result"]
        lines += ["", "Emulator boot free: %s B; minimum after GC: %s B; boot time: %s ms; return code: %s." %
                  (e["boot_free"], e["min_free_gc"], e["boot_ms"], e["rc"])]
    lines += ["", "No physical Evo performance measurement is included.", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--emulator", action="store_true")
    parser.add_argument("--heap", type=int, default=127800)
    args = parser.parse_args(argv)
    report = make_report(args.emulator, args.heap)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
