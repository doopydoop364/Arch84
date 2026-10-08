"""Host-side helper for the MicroPython emulation harness.

Runs Arch84 under a real (32-bit) MicroPython unix port with a device-like
heap, driven by scripted key presses. See emu/README.md for fidelity notes.

    from emu import Emu
    e = Emu()
    r = e.run(["echo hi > a", "cat a"])    # r["screen"], r["min_free_gc"], ...
"""
import json
import os
import resource
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HEAP = 127800     # device-like free heap at start (device: 127,440 free)


def find_mp():
    p = os.environ.get("A84_MICROPYTHON")
    if p and os.access(p, os.X_OK):
        return p
    for c in ("/tmp/a84-micropython", os.path.join(HERE, "micropython")):
        if os.access(c, os.X_OK):
            return c
    return None


# --- key encoding (inverse of A84UI tables) ---------------------------------
LET = (41, 42, 43, 51, 52, 53, 54, 55, 61, 62, 63, 64, 65, 71, 72, 73, 74, 75,
       81, 82, 83, 84, 85, 91, 92, 93)
ENTER, TAB, BS, CLEAR, LEFT, RIGHT, UP, DOWN = 105, 22, 23, 45, 24, 26, 25, 34
SECOND, ALPHA = 21, 31
NORM = {'"': 11, "'": 12, "$": 13, ">": 14, "=": 15, "~": 33, "^": 51, "/": 55,
        ",": 62, "(": 63, ")": 64, "*": 65, "7": 72, "8": 73, "9": 74, "-": 75,
        "4": 82, "5": 83, "6": 84, "+": 85, "1": 92, "2": 93, "3": 94,
        " ": 95, "0": 102, ".": 103, "_": 104}
SEC = {"{": 63, "}": 64, "[": 75, "]": 85}      # 2nd + key


def keys_for_text(text):
    """Key codes that type `text` (no Enter). Letters use alpha (one-shot)."""
    out = []
    for ch in text:
        if "a" <= ch <= "z":
            out += [ALPHA, LET[ord(ch) - 97]]
        elif ch in NORM:
            out.append(NORM[ch])
        elif ch in SEC:
            out += [SECOND, SEC[ch]]
        elif ch == ":":
            out += [ALPHA, 103]
        elif ch == "?":
            out += [ALPHA, 104]
        else:
            raise ValueError("no key for " + repr(ch))
    return out


def keys_for_lines(lines):
    out = []
    for ln in lines:
        out += keys_for_text(ln) + [ENTER]
    return out


class Emu:
    def __init__(self, mp=None, heap=HEAP, cpu_s=600, as_mb=256):
        self.mp = mp or find_mp()
        if not self.mp:
            raise RuntimeError("set A84_MICROPYTHON to the 32-bit unix micropython")
        self.heap = heap
        self.cpu_s = cpu_s
        self.as_mb = as_mb
        self._tmp = tempfile.TemporaryDirectory()
        self.listdir = os.path.join(self._tmp.name, "lists")
        os.makedirs(self.listdir)

    def run(self, lines=None, keys=None, heap=None, fresh=False, shots=False,
            exit_at_end=True):
        """Boot Arch84 and type `lines` (+ `exit` unless exit_at_end False).
        Lists persist between calls on this Emu unless fresh=True."""
        ks = list(keys or [])
        if lines:
            ks += keys_for_lines(lines)
        if exit_at_end:
            ks += keys_for_lines(["exit"])
        with tempfile.TemporaryDirectory() as d:
            kf, rf = (os.path.join(d, n) for n in ("k", "r"))
            open(kf, "w").write("\n".join(map(str, ks)) + "\n")
            if fresh:
                for f in os.listdir(self.listdir):
                    os.remove(os.path.join(self.listdir, f))
            lf = self.listdir
            cmd = [self.mp, "-X", "heapsize=%d" % (heap or self.heap),
                   os.path.join(HERE, "run.py"), kf, lf, rf]
            if shots:
                cmd.append("shots")

            def lim():
                resource.setrlimit(resource.RLIMIT_CPU, (self.cpu_s, self.cpu_s))
                m = self.as_mb << 20
                resource.setrlimit(resource.RLIMIT_AS, (m, m))
            p = subprocess.run(cmd, cwd=ROOT, preexec_fn=lim, capture_output=True, stdin=subprocess.DEVNULL,
                               text=True, timeout=self.cpu_s * 2)
            rep = {}
            if os.path.exists(rf):
                rep = json.load(open(rf))
            else:
                rep["crash"] = True
            rep["stdout"] = p.stdout
            rep["stderr"] = p.stderr
            rep["rc"] = p.returncode
            return rep
