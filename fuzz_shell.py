"""Deterministic shell fuzzer that runs on BOTH CPython and MicroPython.

    python3 fuzz_shell.py SEED [NCMDS]            (desktop)
    micropython -X heapsize=N fuzz_shell.py SEED  (emulation harness)

Prints one line per command (status + output hash) and a final "tree" hash
after a sync + reload. Differences between the two interpreters, an
"internal error", or a changed tree after reload are bugs. Uses its own LCG
so both runtimes see identical input.
"""
import sys
sys.path.insert(0, ".")
from A84FS import ERR
from A84ST import MemStorage
from A84KN import Kernel
from A84SH import Shell

NAMES = ["a", "b", "c", "d/e", "d", "d/f", "g.txt", ".h", "x y", "é", "/tmp/t", "~/n", "../a", ".", "..", "/", "a/b/c", "/proc/version", "/proc/mounts", "/dev/null", "/proc/nope", "/dev"]
WORDS = ["a b", "*", "?", "-n", "--", "$USER", "${HOME}/x", "~", "~/q", "\"'", "\\", ">", ">>", "#c", "hello", "foo bar", "x", "", "é€", "a\\nb", "'q q'", '"$HOME"', "$?", "tab\\tx", "0123456789" * 8]
CMDS = ["echo", "cat", "ls", "ls -a", "cd", "mkdir", "touch", "rm", "rm -r", "rmdir", "cp", "mv",
        "head", "tail -n 2", "grep", "grep -n", "grep -c", "grep -i", "sort", "sort -n", "sort -u", "wc",
        "du", "du -s", "find", "basename", "dirname", "pwd", "df", "history", "env", "export V=1",
        "alias z=ls", "which ls", "uname -a", "sort -r", "sort -nr", "tail -n 0", "head -n 1", "head -n x",
        "wc -l", "wc -c", "wc -w", "grep -v", "cat -", "ls -l", "mkdir -p", "date", "unalias z", "which z",
        "cp -r", "rm -f", "echo -n", "export", "alias", "history -c", "find / -type d -name", "find . -type f",
        "du /tmp", "cd ~", "cd -", "mv -f", "z"]


class T:
    def __init__(self):
        self.t = ""

    def write(self, s):
        self.t += s.replace(ERR, "E:")

    def echo(self, s): pass
    def safe_key(self, tick=None): return False
    def post(self, s, pending=False):
        if not pending:
            self.write(s)
    def busy(self): pass
    def clear(self): pass
    def close(self): pass


class Rng:
    def __init__(self, seed):
        self.s = (seed * 2654435761 + 12345) & 0x7fffffff

    def n(self, k):
        self.s = (self.s * 1103515245 + 12345) & 0x7fffffff
        return (self.s >> 8) % k

    def pick(self, seq):
        return seq[self.n(len(seq))]


def h(s):
    x = 5381
    for c in s:
        x = (x * 33 + ord(c)) & 0xffffff
    return x


def mkline(r):
    cmd = r.pick(CMDS)
    args = []
    for _ in range(r.n(4)):
        args.append(r.pick(NAMES) if r.n(3) else r.pick(WORDS))
    line = cmd + " " + " ".join(args)
    p = r.n(6)
    if p == 0:
        line += " | " + r.pick(["sort", "wc -l", "head -n 2", "grep a", "uniq -c", "tail -n 1", "cat", "tee " + r.pick(NAMES), "sort -r | uniq"])
    elif p == 1:
        line += " < " + r.pick(NAMES)
    elif p == 2:
        line += r.pick([" ; ", " && ", " || "]) + r.pick(CMDS) + " " + r.pick(NAMES)
    k = r.n(8)
    if k == 0:
        line += " > " + r.pick(NAMES)
    elif k == 1:
        line += " >> " + r.pick(NAMES)
    return line


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
            out.append(p + "=" + (d if isinstance(d, str) else "".join(d)))
    out.sort()
    return "\n".join(out)


def fake_proc(path):
    from A84FS import Node
    if path == "/proc":
        return ["meminfo", "version"]
    if path == "/dev":
        return ["null"]
    if path == "/dev/null":
        return Node(False, "")
    if path in ("/proc/meminfo", "/proc/version"):
        return Node(False, "fixed " + path + "\n")
    return None


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    ncmd = int(sys.argv[2]) if len(sys.argv) > 2 else 80
    r = Rng(seed)
    ms = MemStorage()
    k = Kernel(ms)
    t = T()
    sh = Shell(k, t)
    k.vfs.proc = fake_proc          # the real files differ between interpreters (heap, uptime)
    bad = 0
    for i in range(ncmd):
        line = mkline(r)
        t.t = ""
        try:
            sh.execute(line)
        except Exception as e:
            t.t += "EXC " + repr(e)
        if "internal error" in t.t or t.t.startswith("EXC"):
            bad += 1
        if len(sys.argv) > 3 and int(sys.argv[3]) == i:
            print("LINE", line, "\nOUT", t.t)
        print(i, h(line), sh.status, h(t.t), len(t.t), t.t[:60].replace("\n", "|") if "internal" in t.t or "EXC" in t.t else "")
    k.fix_system_files()        # what the next boot repairs anyway
    k.sync()
    before = dump(k.vfs)
    k = sh = t = r = None       # one kernel at a time, like the device
    try:
        import gc
        gc.collect()
    except ImportError:
        pass
    k2 = Kernel(ms)
    if "-v" in sys.argv:
        print("BOOT", k2.boot_msgs)
    after = dump(k2.vfs)
    if before != after:
        a = before.split("\n")
        b = after.split("\n")
        for x in a:
            if x not in b:
                print("ONLY-LIVE", x[:100])
        for x in b:
            if x not in a:
                print("ONLY-RELOADED", x[:100])
    print("tree", h(before), len(before), "reload", "SAME" if before == after else "DIFFERENT", "bad", bad)


main()
