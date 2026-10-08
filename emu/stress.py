#!/usr/bin/env python3
"""Capacity stress under the device-like heap: how big can the filesystem get
before a save/reload fails, and does failure stay graceful (no data loss,
shell keeps running)? Prints one row per scenario."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from emu import Emu

def verdict(r):
    txt = r["stdout"] + "\n".join(r.get("screen", []))
    flags = [w for w in ("out of memory", "low memory", "internal error", "FAILED", "Traceback", "NOT synced", "Saving off", "MemoryError") if w in txt]
    return (r.get("error") or r.get("crash") or "") , flags

def big(k):
    return ["echo 0123456789abcdef > a"] + ["cat a >> a"] * k + ["sync", "wc -c a"]

def many(n):
    return [f"echo {i} > f{i}" for i in range(n)] + ["sync", "ls"]

def bigdir_ls(n):
    return [f"touch f{i}" for i in range(n)] + ["ls", "find / -name f1", "sync"]

if __name__ == "__main__":
    e = Emu()
    for k in (8, 9, 10, 11, 12, 13):
        e2 = Emu()
        r = e2.run(big(k), fresh=True)
        r2 = e2.run(["wc -c a", "cat a > b", "rm b", "ls"])         # reload in a new boot
        print("bigfile %6d B: run1 %s | reload %s" % (16 * 2**k + 2**k - 1 if False else 17 * 2**k, verdict(r), verdict(r2)), "free", r["last_free"], r2["boot_free"], flush=True)
    for n in (10, 25, 50, 100):
        e2 = Emu()
        r = e2.run(many(n), fresh=True)
        r2 = e2.run(["ls"])
        print("files %4d: run1 %s | reload %s" % (n, verdict(r), verdict(r2)), "free", r["last_free"], r2["boot_free"], flush=True)
