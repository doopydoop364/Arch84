#!/usr/bin/env python3
"""Flash repositories on the emulated device: packages that exist only as modules on the
import path (tools/ar84pack.py output), synced and installed by pacman on MicroPython."""
import os, re, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from emu import Emu
import ar84pack
from test_pacman import mk, run


def make_packages(d):
    sh, t = mk()
    v = sh.vfs
    out = []
    for name, ver, deps, size in (("lib", "1.0", [], 20), ("app", "2.0", ["lib>=1.0"], 8), ("bigone", "1", [], 150)):
        base = "/tmp/" + name
        for p in (base, base + "/usr", base + "/usr/bin"):
            if not v.exists(p):
                v.mkdir(p)
        v.write(base + "/usr/bin/" + name, ("echo %s %s\n" % (name, ver)) * size)
        flags = " ".join("-d '%s'" % x for x in deps)
        assert "built" in run(sh, t, "makepkg %s %s %s %s test" % (flags, base, name, ver))
        f = os.path.join(d, "%s-%s.ar84" % (name, ver))
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(v.read("/var/cache/pacman/pkg/%s-%s.ar84" % (name, ver)))
        out.append(f)
    return out


def main():
    with tempfile.TemporaryDirectory() as d:
        mods = os.path.join(d, "mods")
        os.makedirs(mods)
        pk = make_packages(d)
        allm = ar84pack.build_repo("core", pk[:1], mods)
        allm.update(ar84pack.build_repo("mine", pk[1:], mods, 1500))
        allm["R84REG.py"] = ar84pack.registry_source(["core", "mine"])
        for fn, text in allm.items():
            with open(os.path.join(mods, fn), "w", encoding="utf-8") as fh:
                fh.write(text)
        os.environ["MICROPYPATH"] = ".:" + mods
        e = Emu()
        steps = [("pacman -Sy", ["synchronized 3 packages"]),
                 ("pacman -Sl", ["app 2.0", "bigone 1", "lib 1.0"]),
                 ("pacman -Si app", ["Repository  : mine", "Depends On  : lib>=1.0"]),
                 ("pacman -S app", ["installed lib 1.0", "installed app 2.0"]),
                 ("pacman -S bigone", ["installed bigone 1"]),
                 ("pacman -Qk bigone", ["bigone: 1 total files, 0 altered"]),
                 ("pacman -Qk app", ["app: 1 total files, 0 altered"]),
                 ("app", ["app 2.0"]),
                 ("bigone | wc", ["150"]),
                 ("pacman -Qdt", []),
                 ("pacman -Rns app", ["removed app 2.0", "removed lib 1.0"]),
                 ("pacman -Q", ["bigone 1"])]
        ok = True
        first = True
        for cmd, want in steps:
            r = e.run([cmd, "free"], fresh=first, nodraw=True)
            first = False
            t = r["stdout"]
            used = re.findall(r"Mem:\s+\d+\s+(\d+)\s+(\d+)", t)
            good = r["rc"] == 0 and "Traceback" not in t and "out of memory" not in t and "rolled back" not in t
            flat = t.replace("\n", "")
            for w in want:
                good = good and w in flat
            print("%-22s %s  used/free %s" % (cmd, "ok  " if good else "FAIL", used[-1] if used else "?"))
            if not good:
                print("   ", repr(t[-400:]))
            ok = ok and good
        print("flash repositories on device:", "ok" if ok else "FAIL")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
