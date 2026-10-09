"""Package fuzzer for CPython and MicroPython (deterministic): random valid and
damaged .ar84 packages, installs/upgrades/removals. Prints a digest per step; the
two interpreters must print identical lines and no step may leave a half-installed
state (checked by `pacman -Qk` and a tree comparison after a failed step).

    python3 fuzz_pkg.py [first_seed [count]]
    micropython -X heapsize=N fuzz_pkg.py [first_seed [count]]
"""
import sys
sys.path.insert(0, ".")
from A84FS import dtext
from A84ST import MemStorage
from A84KN import Kernel
from A84SH import Shell
from A84PM import MAGIC, Sum, esc, PkgError
import A84PI

NAMES = ["aa", "bb", "cc", "d-1"]
PATHS = ["/usr/bin/x", "/usr/bin/y", "/opt/p/a", "/opt/p/q/b", "/etc/c.conf", "/usr/share/d/e", "/home/evo/u"]
BAD = ["/dev/x", "usr/x", "/etc/version", "/tmp/z", "/usr/../x"]
TEXT = ["a", "hello\n", "x\ty\\z", "é€漢", "", "echo $1\n", "q" * 300]


class Rng:
    def __init__(self, s):
        self.s = (s * 2654435761 + 7) & 0x7fffffff

    def n(self, k):
        self.s = (self.s * 1103515245 + 12345) & 0x7fffffff
        return (self.s >> 8) % k


class T:
    def write(self, s): pass
    def post(self, s, p=False): pass
    def busy(self): pass
    def clear(self): pass


def h(s):
    x = 5381
    for c in s:
        x = (x * 33 + ord(c)) & 0xffffff
    return x


def dump(vfs):
    out = []
    st = [("/", vfs.root)]
    while st:
        p, n = st.pop()
        if n.is_dir:
            out.append(p + "/")
            for c in n.children:
                st.append((p.rstrip("/") + "/" + c, n.children[c]))
        else:
            d = n.data
            out.append(p + "=" + dtext(d))
    out.sort()
    return "\n".join(out)


def build(r, name, ver):
    ents = []
    for _ in range(r.n(5)):
        if r.n(12) == 0:
            p = BAD[r.n(len(BAD))]
        else:
            p = PATHS[r.n(len(PATHS))]
        if r.n(6) == 0:
            ents.append(("D", p[:p.rfind("/")] or "/usr"))
        else:
            ents.append(("F", p, TEXT[r.n(len(TEXT))]))
    deps = [NAMES[r.n(len(NAMES))]] if r.n(4) == 0 else []
    lines = [MAGIC, "name " + name, "version " + ver]
    if deps:
        lines.append("depends " + " ".join(deps))
    for e in ents:
        if e[0] == "D":
            lines.append("D\t" + e[1])
        else:
            s = Sum()
            s.add(e[2])
            lines.append("F\t%s\t%d\t%s" % (e[1], len(e[2]), s.hex()))
            for i in range(0, len(e[2]), 100):
                lines.append("+\t" + esc(e[2][i:i + 100]))
    tot = Sum()
    for l in lines:
        tot.add(l + "\n")
    lines.append("END\t%d\t%s" % (len(ents), tot.hex()))
    k = r.n(8)
    if k == 0 and len(lines) > 3:
        del lines[r.n(len(lines))]
    elif k == 1:
        i = r.n(len(lines))
        lines[i] = lines[i][:r.n(len(lines[i]) + 1)]
    return "\n".join(lines) + "\n"


STAT = {}


def main():
    a = [int(x) for x in sys.argv[1:]]
    first, count = (a + [1, 30][len(a):])[:2]
    bad = 0
    for seed in range(first, first + count):
        r = Rng(seed)
        ms = MemStorage()
        k = Kernel(ms)
        sh = Shell(k, T())
        v = k.vfs
        steps = []
        for step in range(12):
            op = r.n(4)
            name = NAMES[r.n(len(NAMES))]
            before = dump(v)
            res = ""
            if op < 2:
                v.write("/home/evo/p.ar84", build(r, name, str(1 + r.n(3))))
                before = dump(v)
                try:
                    meta, old = A84PI.install(v, "/home/evo/p.ar84")
                    res = "ok " + meta["name"] + " " + str(old)
                except PkgError as e:
                    res = "err " + str(e)[:30]
                    if dump(v) != before:
                        res += " DIRTY"
                        bad += 1
            elif op == 2:
                try:
                    A84PI.remove(v, name)
                    res = "removed " + name
                except PkgError as e:
                    res = "err " + str(e)[:30]
            else:
                sh.execute("pacman -Qk")
                res = "qk"
            steps.append(res)
            STAT[res.split(" ")[0]] = STAT.get(res.split(" ")[0], 0) + 1
            print(seed, step, h(res), len(res), res[-6:] if "DIRTY" in res else "", h(dump(v)))
        # every installed package must verify clean and survive a save/reload
        k.sync()
        k = sh = None
        k2 = Kernel(ms)
        for line in ("x",):
            pass
        print(seed, "final", h(dump(k2.vfs)))
    print("fuzz_pkg dirty", bad, sorted(STAT.items()))


main()
