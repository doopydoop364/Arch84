#!/usr/bin/env python3
"""Capacity at the device-like heap. For N small files: create+sync (session 1),
then a fresh boot that edits one file and syncs (session 2), then `reboot`
inside one session. Prints the largest N that is clean in each.
   python3 emu/cap.py [heap]"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from emu import Emu
from minheap import ok

def scenario(n, heap, reboot=False, strict=True):
    e = Emu(heap=heap)
    r1 = e.run([f"echo {i} > f{i}" for i in range(n)] + ["sync"], fresh=True)
    if not ok(r1, strict):
        return "save"
    if reboot:
        r2 = e.run(["reboot"], exit_at_end=True)
        r2 = e.run(["echo z >> f0", "sync", "wc f0"])
    else:
        r2 = e.run(["echo z >> f0", "sync", "wc f0"])
    if not ok(r2, strict):
        return "load/resync"
    return "ok"

if __name__ == "__main__":
    heap = int(sys.argv[1]) if len(sys.argv) > 1 else 127800
    for strict in (True, False):
        lo, hi = 10, 500
        while hi - lo > 4:
            mid = (lo + hi) // 2
            if scenario(mid, heap, False, strict) == "ok":
                lo = mid
            else:
                hi = mid
        print("heap %d: largest N saved+reloaded+re-saved %s: %d (first failure: %s)" % (
            heap, "with full verification" if strict else "allowing skipped verify", lo,
            scenario(hi, heap, False, strict)), flush=True)
