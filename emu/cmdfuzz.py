#!/usr/bin/env python3
"""Random command sessions typed on the emulated device, including the heavy lazy
commands (edit, pacman, makepkg, archive, fsck, man, sed ...). Fails on a crash, a
Traceback, an internal error or a degraded terminal.
   python3 emu/cmdfuzz.py [first_seed [count [lines_per_run [--heap=N]]]]"""
import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from emu import Emu

NAMES = ["a", "b", "c", "d", "d/e", "f1", "f2", "x.txt", "../a", ".", "/tmp", "/tmp/t", "~", "/usr/bin/q", "/proc/version"]
WORDS = ["hello", "x y", "1", "2", "abc", "a-b", "-n", "-r", "0", "9"]
CMDS = ["echo", "cat", "ls", "ls -l", "cd", "mkdir -p", "touch", "rm", "rm -rf", "cp", "cp -r", "mv", "head -n 2",
        "tail -n 2", "grep -n", "sort", "sort -r", "uniq -c", "wc", "du", "find", "tr a-c x", "cut -d a -f 1", "nl",
        "seq 4", "sed s/a/b/", "rev", "test -f", "expr 1 + 2", "man ls", "help cp", "man -k file", "fsck", "fsck -r",
        "archive create z1", "archive create z2", "archive extract z1", "archive extract z2", "archive list",
        "archive check", "archive delete z1", "makepkg -d a /tmp/s pk 1", "makepkg /tmp/s pk 2", "pacman -Q",
        "pacman -Qi pk", "pacman -Ql pk", "pacman -Qk", "pacman -U /var/cache/pacman/pkg/pk-1.ar84",
        "pacman -U /var/cache/pacman/pkg/pk-2.ar84", "pacman -R pk", "pacman -S pk", "pacman -Sl", "edit a", "edit f1",
        "df", "free", "uname -a", "which ls", "env", "history", "date", "uptime", "sync", "keys", "alias zz=ls", "zz",
        "mkdir /tmp/s", "mkdir -p /tmp/s/usr/bin", "echo hi > /tmp/s/usr/bin/q", "chmod"]


def lines_for(seed, n):
    r = random.Random(seed)
    out = []
    for _ in range(n):
        c = r.choice(CMDS)
        parts = [c] + [r.choice(NAMES) if r.random() < 0.7 else r.choice(WORDS) for _ in range(r.randrange(0, 3))]
        line = " ".join(parts)
        k = r.random()
        if k < 0.12:
            line += " | " + r.choice(["sort", "wc -l", "head -n 1", "cat", "uniq", "tr a b"])
        elif k < 0.2:
            line += r.choice([" ; ", " && ", " || "]) + r.choice(CMDS) + " " + r.choice(NAMES)
        elif k < 0.26:
            line += " > " + r.choice(NAMES)
        out.append(line)
    return out


BAD = ("Traceback", "internal error", "terminal error", "falling back")


def one(seed, n, heap, nodraw):
    lines = [l for l in lines_for(seed, n) if all(ch in "abcdefghijklmnopqrstuvwxyz0123456789 \"'$>=~^/*,()-+.<_|;&:?\\[]" for ch in l)]
    e = Emu()
    r = e.run(lines, fresh=True, heap=heap, nodraw=nodraw)
    txt = r["stdout"] + r["stderr"]
    bad = [b for b in BAD if b in txt]
    if r.get("crash") or r.get("error") or bad or r["rc"] != 0:
        return seed, r.get("error"), bad, txt[-300:]
    return None


if __name__ == "__main__":
    heap = None
    nodraw = "--nodraw" in sys.argv
    for x in sys.argv:
        if x.startswith("--heap="):
            heap = int(x[7:])
    a = [int(x) for x in sys.argv[1:] if not x.startswith("--")]
    first, count, n = (a + [1, 10, 120][len(a):])[:3]
    fails = 0
    for s in range(first, first + count):
        f = one(s, n, heap, nodraw)
        if f:
            fails += 1
            print("FAIL", f)
    print("cmdfuzz: %d runs, %d failures" % (count, fails))
    sys.exit(1 if fails else 0)
