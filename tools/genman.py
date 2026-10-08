#!/usr/bin/env python3
"""Regenerate A84MN.py (the on-device manual) from docs/manpages.txt.
   python3 tools/genman.py          write A84MN.py
   python3 tools/genman.py --check  exit 1 if A84MN.py is out of date"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEAD = """# A84MN: `man` - the manual pages (Arch84 module, lazily loaded; unloads itself after use).
# GENERATED from docs/manpages.txt by tools/genman.py - edit that file, not this one.
# One line per page: name TAB usage TAB description.
from A84CD import COMMANDS, all_commands, unload

"""
TAIL = """

def find(name):
    for chunk in PAGES:
        i = chunk.find(name + "\\t")
        while i >= 0:
            if i == 0 or chunk[i - 1] == "\\n":
                j = chunk.find("\\n", i)
                return chunk[i:j].split("\\t")
            i = chunk.find(name + "\\t", i + 1)
    return None


def cmd_man(sh, args):
    try:
        return run(sh, args)
    finally:
        unload("man", "A84MN")


def run(sh, args):
    if not args or args[0][:1] == "-" and args[0] != "-k" or args[0] == "-k" and len(args) != 2:
        sh.err("usage: man COMMAND | man -k WORD")
        return 1
    if args[0] == "-k":
        word = args[1]
        hit = False
        for chunk in PAGES:
            for line in chunk.split("\\n"):
                if line != "" and word in line:
                    f = line.split("\\t")
                    sh.out(f[0] + " - " + f[2][:40] + "\\n")
                    hit = True
        if not hit:
            sh.err("man: nothing appropriate: " + word)
            return 1
        return 0
    st = 0
    for name in args:
        page = find(name)
        if page is None:
            if name in all_commands():
                sh.err("man: no manual page for " + name)
            else:
                sh.err("man: no such command: " + name)
            st = 1
            continue
        sh.out(page[0] + " - " + page[2] + "\\nusage: " + page[1] + "\\n")
    return st


COMMANDS["man"] = cmd_man
"""


def build():
    rows = [l.rstrip("\n") for l in open(os.path.join(ROOT, "docs", "manpages.txt")) if l.strip()]
    rows.sort(key=lambda l: l.split("\t")[0])
    names = [r.split("\t")[0] for r in rows]
    assert len(set(names)) == len(names), "duplicate page"
    for r in rows:
        assert len(r.split("\t")) == 3, r
    chunks = []
    cur = []
    n = 0
    for r in rows:
        cur.append(r)
        n += len(r)
        if n > 700:
            chunks.append(cur)
            cur = []
            n = 0
    if cur:
        chunks.append(cur)
    body = "PAGES = (\n"
    for ch in chunks:
        body += "    (\n"
        for r in ch:
            body += "        " + repr(r + "\n") + "\n"
        body += "    ),\n"
    return HEAD + body + ")\n" + TAIL


if __name__ == "__main__":
    text = build()
    path = os.path.join(ROOT, "A84MN.py")
    if "--check" in sys.argv:
        sys.exit(0 if open(path).read() == text else 1)
    open(path, "w").write(text)
