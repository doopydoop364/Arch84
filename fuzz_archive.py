"""Archive fuzzer for CPython and MicroPython: random files, archive create/extract/
delete/check in random order with save+reload in between. The two interpreters must
print identical lines; the tree must always equal the model (files archived are absent,
extracted files identical).

    python3 fuzz_archive.py [first_seed [count]]
"""
import sys
sys.path.insert(0, ".")
from A84ST import MemStorage
from A84KN import Kernel
from A84SH import Shell


class Rng:
    def __init__(self, s):
        self.s = (s * 2654435761 + 11) & 0x7fffffff

    def n(self, k):
        self.s = (self.s * 1103515245 + 12345) & 0x7fffffff
        return (self.s >> 8) % k


class T:
    def __init__(self):
        self.text = ""
    def write(self, s): self.text += s.replace("\x01", "E:")
    def post(self, s, p=False): pass
    def busy(self): pass
    def clear(self): pass


def h(s):
    x = 5381
    for c in s:
        x = (x * 33 + ord(c)) & 0xffffff
    return x


def dump(vfs, under):
    out = []
    st = [(under, vfs.get(under))]
    while st:
        p, n = st.pop()
        if n is None:
            continue
        if n.is_dir:
            out.append(p + "/")
            for c in n.children:
                st.append((p + "/" + c, n.children[c]))
        else:
            d = n.data
            out.append(p + "=" + (d if isinstance(d, str) else "".join(d)))
    out.sort()
    return "\n".join(out)


TEXT = ["a", "", "hello\n" * 30, "é€漢\t\\", "z" * 700, "line\n" * 200]


def main():
    a = [int(x) for x in sys.argv[1:]]
    first, count = (a + [1, 25][len(a):])[:2]
    bad = 0
    for seed in range(first, first + count):
        r = Rng(seed)
        ms = MemStorage()
        sh = Shell(Kernel(ms), T())
        t = sh.term
        v = sh.vfs
        v.mkdir("/home/evo/w")
        names = []
        for i in range(8):
            if r.n(3) == 0:
                v.mkdir("/home/evo/w/d%d" % i)
                v.write("/home/evo/w/d%d/in" % i, TEXT[r.n(len(TEXT))])
            else:
                v.write("/home/evo/w/f%d" % i, TEXT[r.n(len(TEXT))])
            names.append(i)
        orig = dump(sh.vfs, "/home/evo/w")
        archived = {}
        for step in range(14):
            op = r.n(5)
            t.text = ""
            before = dump(sh.vfs, "/home/evo/w")
            line = ""
            if op < 2:
                pick = []
                for i in names:
                    if r.n(3) == 0:
                        for p in ("/home/evo/w/f%d" % i, "/home/evo/w/d%d" % i):
                            if sh.vfs.exists(p):
                                pick.append(p)
                if pick and len(archived) < 4:
                    nm = "z%d" % r.n(4)
                    line = "archive create %s %s" % (nm, " ".join(pick))
                    sh.execute(line)
                    if "archived" in t.text:
                        archived[nm] = before
            elif op == 2 and archived:
                nm = sorted(archived)[r.n(len(archived))]
                sh.execute("archive extract " + nm)
                line = "x " + nm
                if "restored" in t.text:
                    del archived[nm]
            elif op == 3:
                sh.execute("archive check")
                line = "check"
                if "DAMAGED" in t.text or "damaged" in t.text:
                    bad += 1
            else:
                sh.k.sync()
                sh = Shell(Kernel(ms), T())      # save + reload
                t = sh.term
                line = "reload"
            print(seed, step, h(line), h(t.text), h(dump(sh.vfs, "/home/evo/w")), sorted(archived))
        for nm in sorted(archived):
            sh.execute("archive extract " + nm)
        # everything archived is back: the original content is the union we started with
        same = dump(sh.vfs, "/home/evo/w") == orig
        if not same:
            bad += 1
        print(seed, "final", h(dump(sh.vfs, "/home/evo/w")), len(archived), "SAME" if same else "DIFFERENT")
    print("fuzz_archive bad", bad)


main()
