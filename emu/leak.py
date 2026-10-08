#!/usr/bin/env python3
"""Leak check: heap free (after gc) at the idle prompt vs repetitions of a
workload that returns the filesystem to its starting state. Flat = no leak."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from emu import Emu

CYCLES = {
    "files": ["echo hello > f", "cp f g", "mv g h", "cat h", "rm f h", "ls"],
    "dirs": ["mkdir -p x", "mkdir y", "cd y", "touch z", "cd ..", "rm -r y", "rmdir x", "ls -a"],
    "text": ["echo a b c > t", "grep a t", "sort t", "wc t", "head t", "tail t", "find / -name t", "du -s /", "rm t"],
    "sync": ["echo q >> s", "sync", "rm s", "sync", "df"],
    "env": ["export v=1", "alias z=ls", "z", "unalias z", "history", "which ls", "env", "free"],
}

def reboot_cycles():
    e = Emu()
    e.run([f"echo {i} > f{i}" for i in range(20)] + ["sync"], fresh=True)
    r = e.run(["reboot"] * 25 + ["echo done"])
    re_ = r["run_entries"]
    print("reboot x25: free at each shell start: first %d, then %d..%d, last %d | drift after 2nd boot: %d B"
          % (re_[0], min(re_[1:]), max(re_[1:]), re_[-1], re_[-1] - re_[1]), flush=True)


if __name__ == "__main__":
    reboot_cycles()
    e = Emu()
    for name, cyc in CYCLES.items():
        res = []
        for reps in (1, 10, 40):
            r = e.run(cyc * reps, fresh=True)
            res.append((reps, r["last_free"], r["min_free_gc"]))
        print("%-6s" % name, " ".join("x%d: free %d (min %d)" % t for t in res),
              "| delta x40-x1 = %d B" % (res[2][1] - res[0][1]), flush=True)
