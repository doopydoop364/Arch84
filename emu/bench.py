#!/usr/bin/env python3
"""Baseline/regression benchmark under the MicroPython harness.
   A84_MICROPYTHON=... python3 emu/bench.py [--json out.json]
Heap numbers are MicroPython gc readings (bytes); ms are HOST times (relative)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from emu import Emu

def lines_repeat(n, fmt):
    return [fmt.format(i=i) for i in range(n)]

WORK = {
    "boot+exit": [],
    "idle_ls_x100": ["ls"] * 100,
    "cmd_mix_x60": ["pwd", "ls -a /", "cat /etc/hostname", "echo hello world",
                    "env", "uname -a", "grep -n a /etc/profile", "find / -name hostname",
                    "wc /etc/profile", "history"] * 6,
    "files_create_delete_x40": sum(([f"echo data{i} > f{i}", f"cp f{i} g{i}", f"rm f{i}", f"rm g{i}"]
                                    for i in range(10)), []) * 4,
    "mkdir_tree": [f"mkdir -p d{i}/e{i}" for i in range(20)] + [f"rm -r d{i}" for i in range(20)],
    "bigfile_8k_sync": ["echo 0123456789abcdef > a"] + ["cat a >> a"] * 9 + ["df", "sync", "wc a"],
    "sync_x10": ["echo x >> s", "sync"] * 10,
}

def main():
    out = {}
    e = Emu()
    print("%-26s %8s %8s %8s %8s %6s %7s %6s" % ("workload", "boot", "minGC", "end", "lowest", "stack", "ms", "err"))
    for name, lines in WORK.items():
        r = e.run(lines, fresh=True)
        out[name] = {k: r.get(k) for k in ("boot_free", "min_free_gc", "min_free_nogc",
                     "end_free", "stack_peak", "total_ms", "draw_calls", "draw_pixels",
                     "stores", "recalls", "error", "crash", "free_loaded")}
        o = out[name]
        print("%-26s %8s %8s %8s %8s %6s %7s %6s" % (name, o["boot_free"], o["min_free_gc"],
              o["end_free"], o["min_free_nogc"], o["stack_peak"], o["total_ms"], o["error"] or o["crash"] or "-"))
    if "--json" in sys.argv:
        json.dump(out, open(sys.argv[sys.argv.index("--json") + 1], "w"), indent=1, sort_keys=True)

main()
