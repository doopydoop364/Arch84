#!/usr/bin/env python3
"""Smallest heap on which a saved filesystem of N small files (a) is written
by one sync and (b) loads in a fresh boot. Lower = better. Host MicroPython
runs of emu/mp/sync_probe.py and emu/mp/load_probe.py."""
import os, subprocess, sys, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MP = os.environ.get("A84_MICROPYTHON") or "/tmp/a84-micropython"
LD = "/tmp/ld2"

def run(script, heap, *args):
    return subprocess.run([MP, "-X", "heapsize=%d" % heap, os.path.join(HERE, "mp", script), *args],
                          cwd=ROOT, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=300)

def ok_save(n, heap):
    shutil.rmtree(LD, ignore_errors=True); os.makedirs(LD)
    r = run("sync_probe.py", heap, str(n), "stop")
    return r.returncode == 0 and "after sync" in r.stdout

def ok_load(heap):
    r = run("load_probe.py", heap)
    return r.returncode == 0 and "loaded" in r.stdout

def scan(f, lo=80000, hi=180000, step=1000):
    """(highest failing heap, success fraction below 127800): robust to the
    non-monotonic behaviour fragmentation causes"""
    worst = None
    okc = tot = 0
    for h in range(lo, hi + 1, step):
        r = f(h)
        if not r:
            worst = h
        if h <= 127800:
            tot += 1
            okc += 1 if r else 0
    return worst, "%d/%d ok <=127800" % (okc, tot)


def bisect(f, lo=70000, hi=400000):
    if not f(hi):
        return None
    while hi - lo > 512:
        mid = (lo + hi) // 2
        if f(mid):
            hi = mid
        else:
            lo = mid
    return hi

if __name__ == "__main__":
    for n in [int(a) for a in sys.argv[1:]] or [50, 100, 200]:
        save = scan(lambda h: ok_save(n, h))
        ok_save(n, 400000)       # make the lists with plenty of room
        load = scan(ok_load)
        print("files %4d: save: highest failing heap %s (%s) | load: %s (%s)" % ((n,) + save + load), flush=True)
