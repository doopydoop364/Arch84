#!/usr/bin/env python3
"""Power-cut sweep: kill the emulated calculator after k list stores during a
sync (k = 0..), reboot, and require the filesystem to be exactly the old save or
the new one - never corrupt, never a mix. Lists are the only persistent state.
   python3 emu/powercut.py [nfiles]"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from emu import Emu

def state(e):
    r = e.run(["cat f0 f7 g0", "du -s ~"], shots=True)
    scr = r["screen"]
    txt = r["stdout"]
    boot_bad = [w for w in ("FAILED", "Corrupt", "Saving off", "out of memory") if w in txt]
    return r, boot_bad

def main(n=40):
    base = [f"echo A{i} > f{i}" for i in range(n)] + ["sync"]
    change = [f"echo B{i} > f{i}" for i in range(0, n, 3)] + ["echo BB > g0", "sync"]
    e0 = Emu()
    e0.run(base, fresh=True)
    ref_old, _ = state(e0)
    # reference new state (no cut)
    import shutil
    snap = e0.listdir + ".snap"
    shutil.copytree(e0.listdir, snap)
    e0.run(change, exit_at_end=False)
    ref_new, _ = state(e0)
    old_sig = tuple(ref_old["screen"][:6]); new_sig = tuple(ref_new["screen"][:6])
    print("old:", old_sig)
    print("new:", new_sig)
    bad = 0
    k = 0
    while True:
        shutil.rmtree(e0.listdir); shutil.copytree(snap, e0.listdir)
        r = e0.run(change, exit_at_end=False, cut=k)
        cut_happened = r.get("error") and "SystemExit" in r["error"]
        r3, boot_bad = state(e0)
        sig = tuple(r3["screen"][:6])
        verdict = "OLD" if sig == old_sig else "NEW" if sig == new_sig else "MIXED/OTHER"
        if verdict == "MIXED/OTHER" or boot_bad:
            bad += 1
            print("k=%d cut=%s -> %s %s %s" % (k, bool(cut_happened), verdict, boot_bad, sig))
        if not cut_happened:
            print("no cut at k=%d (sync needs %d stores); final state %s" % (k, k, verdict))
            break
        k += 1
    shutil.rmtree(snap, ignore_errors=True)
    print("powercut: %d cut points tested, %d bad" % (k, bad))
    return bad

if __name__ == "__main__":
    sys.exit(1 if main(int(sys.argv[1]) if len(sys.argv) > 1 else 40) else 0)
