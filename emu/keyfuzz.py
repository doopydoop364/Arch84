#!/usr/bin/env python3
"""Random raw key presses (all 49 key codes incl. 2nd/alpha/arrows/tab/enter)
through the real terminal + editor + shell on the emulated device. Fails on a
degraded terminal, a Traceback, an internal error or a crash.
   python3 emu/keyfuzz.py [first_seed [count [keys_per_run]]]"""
import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from emu import Emu

CODES = [11, 12, 13, 14, 15, 21, 22, 23, 24, 25, 26, 31, 33, 34, 41, 42, 43, 45, 51, 52, 53, 54, 55,
         61, 62, 63, 64, 65, 71, 72, 73, 74, 75, 81, 82, 83, 84, 85, 91, 92, 93, 94, 95, 102, 103, 104, 105,
         99, 1, 0]       # last three: unknown codes

BAD = ("terminal error", "falling back", "Traceback", "internal error", "ash: low memory")

def one(seed, n):
    rng = random.Random(seed)
    ks = []
    for _ in range(n):
        r = rng.random()
        ks.append(105 if r < 0.08 else rng.choice(CODES))
    e = Emu()
    r = e.run(keys=ks, shots=False)
    txt = r["stdout"] + r["stderr"]
    bad = [b for b in BAD if b in txt]
    if r.get("crash") or r.get("error") or bad or r["rc"] != 0:
        return seed, r.get("error"), r.get("crash"), bad, r["rc"], txt[-300:]
    return None

if __name__ == "__main__":
    a = [int(x) for x in sys.argv[1:]]
    first, count, n = (a + [1, 20, 1500][len(a):])[:3]
    fails = 0
    for s in range(first, first + count):
        f = one(s, n)
        if f:
            fails += 1
            print("FAIL", f)
    print("keyfuzz: %d runs, %d failures" % (count, fails))
