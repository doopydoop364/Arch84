#!/usr/bin/env python3
"""Editor on the emulated device: typing, saving, a big file, memory."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from emu import Emu, keys_for_text, keys_for_lines, ENTER, CLEAR

def edit_session(pre, typed, post, **kw):
    ks = keys_for_lines(pre) + keys_for_lines(["edit note"]) + typed + keys_for_lines(post)
    return ks

def main():
    e = Emu()
    ok = True
    # 1. create a file through the editor, save, cat it back
    typed = keys_for_text("hello") + [ENTER] + keys_for_text("world") + [CLEAR] + keys_for_text("wq") + [ENTER]
    r = e.run(keys=edit_session([], typed, ["cat note"]), fresh=True)
    good = "hello\nworld\n" in r["stdout"] and "Traceback" not in r["stderr"] + r["stdout"]
    print("create+save+cat:", "ok" if good else "FAIL"); ok &= good
    # 2. big file (about 10 KB) opens, one edit, saves, persists after exit/reboot
    pre = ["echo " + "x" * 70 + " > a"] + ["cat a a > b", "cat b b > a"] * 3
    typed = [CLEAR] + keys_for_text("200") + [ENTER] + keys_for_text("zz") + [CLEAR] + keys_for_text("wq") + [ENTER]
    r = e.run(keys=edit_session(pre, [], []) [:0] + keys_for_lines(pre) + keys_for_lines(["wc a", "edit a"]) + typed + keys_for_lines(["wc a", "sync"]), fresh=True)
    t = r["stdout"]
    print("big file:", [l for l in t.split("\n") if l.strip().endswith(" a")], "minfree", r["min_free_gc"],
          "errors:", [w for w in ("out of memory", "Traceback", "too large") if w in t])
    # 3. random key fuzz inside the editor
    import random
    bad = 0
    for seed in range(12):
        rng = random.Random(seed)
        codes = [105, 105, 24, 25, 26, 34, 23, 45, 21, 31, 41, 42, 55, 72, 95, 102]
        typed = [rng.choice(codes) for _ in range(800)]
        r = e.run(keys=keys_for_lines(["edit z"]) + typed, fresh=True)
        txt = r["stdout"] + r["stderr"]
        if any(w in txt for w in ("Traceback", "internal error", "terminal error")) or r.get("crash"):
            bad += 1
            print("editor key fuzz seed", seed, "FAIL", txt[-200:])
    print("editor key fuzz: 12 runs,", bad, "failures"); ok &= bad == 0
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
