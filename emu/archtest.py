#!/usr/bin/env python3
"""archive on the emulated device: heap freed, survival across a fresh boot, and
extract after boot. Prints the heap numbers the command is for."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from emu import Emu

def mem(t):
    return [int(m) for m in re.findall(r"Mem:\s+\d+\s+(\d+)\s+(\d+)", t) for m in m][1::2] if False else \
           [(int(a), int(b)) for a, b in re.findall(r"Mem:\s+\d+\s+(\d+)\s+(\d+)", t)]

def used(t):
    m = re.findall(r"Mem:\s+\d+\s+(\d+)\s+(\d+)", t)
    return int(m[-1][0]) if m else None


def main():
    e = Emu()
    make = []
    for i in range(4):
        make += ["echo " + "x" * 90 + " > f%d" % i] + ["cat f%d f%d > t" % (i, i), "cat t t > f%d" % i] * 2
    make.append("rm t")
    rA = e.run(make + ["free"], fresh=True)
    u_before = used(rA["stdout"])
    rB = e.run(make + ["archive create big f0 f1 f2 f3", "free"], fresh=True)
    u_after = used(rB["stdout"])
    print("heap in use with 4 files of ~1.4 KB: %s B; after `archive create`: %s B -> freed %s B" % (
        u_before, u_after, (u_before - u_after) if u_before and u_after else "?"))
    ok = bool(u_before and u_after and u_before - u_after > 2000)
    r1 = e.run(["archive list", "archive check", "ls", "sync"])
    t1 = r1["stdout"]
    r2 = e.run(["archive extract big", "wc f0"])
    t2 = r2["stdout"]
    print("fresh boot, extract:", [l for l in t2.split("\n") if "restored" in l or " f0" in l])
    ok = ok and "restored 4 files" in t2 and "Traceback" not in t1 + t2
    r3 = e.run(["archive list", "fsck"])
    print("after extract:", [l for l in r3["stdout"].split("\n") if "problems" in l or "archive" in l and "list" not in l][-3:])
    ok = ok and "no problems found" in r3["stdout"]
    print("archive on device:", "ok" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
