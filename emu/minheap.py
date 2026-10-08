#!/usr/bin/env python3
"""Smallest heap (bytes, MicroPython -X heapsize) on which each workload runs
cleanly = true peak requirement incl. fragmentation. Lower = better.
   python3 emu/minheap.py [name ...]"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from emu import Emu
from bench import WORK

BAD = ("out of memory", "low memory", "internal error", "MemoryError", "FAILED",
       "Traceback", "terminal error", "NOT synced", "Saving off")

SOFT = ("low memory",)       # a save that skipped only its tree-compare check


def ok(r, strict=True):
    if r.get("crash") or r.get("error"):
        return False
    txt = r["stdout"] + r["stderr"] + "\n".join(r.get("screen", []))
    bad = [b for b in BAD if strict or b not in SOFT]
    return not any(b in txt for b in bad)

def minheap(e, lines, lo=60000, hi=200000):
    if not ok(e.run(lines, fresh=True, heap=hi)):
        return None
    while hi - lo > 256:
        mid = (lo + hi) // 2
        if ok(e.run(lines, fresh=True, heap=mid)):
            hi = mid
        else:
            lo = mid
    return hi

if __name__ == "__main__":
    e = Emu()
    for name, lines in WORK.items():
        if len(sys.argv) > 1 and name not in sys.argv[1:]:
            continue
        print("%-28s %s" % (name, minheap(e, lines)), flush=True)
