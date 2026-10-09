# A84TS: self test (Arch84 module 10/10, loaded only by the selftest command)
# Runs every command in a throwaway shell (MemStorage, fresh VFS per case);
# the real filesystem and saved storage are never touched.
from A84ST import MemStorage
from A84KN import Kernel
from A84SH import Shell
from A84CD import all_commands
from A84UI import strip

PARTS = 4
PARTMODS = ("A84T1", "A84T2", "A84T3", "A84T4")     # literal names: the BAK copies rename them
# test hooks (desktop tests): replace the checks / cases instead of loading the
# generated parts A84T1..A84T4
CHECKS = None
CASES = None


class Cap:
    def __init__(self):
        self.text = ""
        self.cleared = 0

    def write(self, t):
        self.text += strip(t)
        if t != "" and not t.endswith("\n"):
            self.text += "\n"

    def post(self, t, pending=False):
        pass

    def echo(self, t):
        pass

    def clear(self):
        self.cleared += 1

    def close(self):
        pass


def load_part(p):
    # (number of the first item, [(label, want or None, lines or check fn)]) of
    # quarter p; the module holding it is dropped again by drop_part
    if CASES is not None or CHECKS is not None:
        import A84TX
        checks = CHECKS if CHECKS is not None else A84TX.CHECKS
        cases = CASES
        if cases is None:
            cases = []
            for q in range(1, PARTS + 1):
                cases = cases + __import__(PARTMODS[q - 1]).CASES
        allx = [(l, None, f) for l, f in checks] + [(l, w, ln) for l, ln, w in cases]
        total = len(allx)
        got = []
        first = 0
        for i in range(total):
            if i * PARTS // total == p - 1:
                if not got:
                    first = i + 1
                got.append(allx[i])
        return first, got
    m = __import__(PARTMODS[p - 1])
    items = [(l, w, ln) for l, ln, w in m.CASES]
    first = m.START
    if p == 1:
        import A84TX
        items = [(l, None, f) for l, f in A84TX.CHECKS] + items
        first = 1
    return first, items


def drop_part(p):
    import sys
    for name in (PARTMODS[p - 1], "A84TX"):
        sys.modules.pop(name, None)
    settle()


def run_case(lines):
    cap = Cap()
    k = Kernel(MemStorage())
    sh = Shell(k, cap)
    out = ""
    for line in lines:
        cap.text = ""
        if line[:1] == "!":
            k.add_history(line[1:])
        else:
            sh.execute(line)
        out = cap.text
    return out, cap, sh


def matches(want, got, cap, sh):
    if want == "#clear":
        return cap.cleared == 1
    if want == "#exit":
        return not sh.running
    if want == "#reboot":
        return sh.reboot and not sh.running
    if want[:1] == "~":
        return want[1:] in got
    if want[:1] == "^":
        return got.startswith(want[1:])
    return got == want


def settle():
    try:
        import gc
        gc.collect()
    except ImportError:
        pass


def freek():
    # free heap in KB after a collect (" ?" where the interpreter cannot tell)
    try:
        import gc
        gc.collect()
        return " " + str(gc.mem_free() // 1000) + "k"
    except Exception:
        return ""


def attempt(fn):
    # fn() -> (ok, got). "ok" / "lowmem" / "fail"; one retry (after dropping the
    # lazy command modules) when the failure looks like a memory shortage
    got = ""
    for tries in range(2):
        settle()
        try:
            ok, got = fn()
        except Exception as e:
            ok = False
            got = "EXC " + repr(e)
        if ok:
            return "ok", ""
        if "emory" in got and tries == 0:
            try:
                from A84CD import evict
                evict()
            except ImportError:
                pass
            continue
        break
    if "emory" in got:
        return "lowmem", got
    return "fail", got


def case_fn(lines, want):
    def f():
        got, cap, s2 = run_case(lines)
        return matches(want, got, cap, s2), got
    return f


def check_fn(fn):
    def f():
        return fn(), "False"
    return f


def selftest(sh, args):
    # A MemoryError inside a check is a calculator-RAM shortage, not a bug:
    # it is reported as LOWMEM, counted separately, never as a failure.
    #   selftest [N] [name] [-v] [-r] [-p]
    # N (1..PARTS): only that quarter of the tests (a smaller, safer run on the
    # calculator; each quarter's data is loaded alone and dropped afterwards);
    # name: only the cases containing it; -r: one result line per test as it
    # finishes; -p: also name each test before it starts.
    verbose = "-v" in args
    res = "-r" in args
    prog = "-p" in args
    part = 0
    only = ""
    for a in args:
        if a[:1] != "-":
            if a.isdigit():
                part = int(a)
            else:
                only = a
    partial = part > 0 or only != ""
    fails = []
    lows = []
    used = ["selftest"]
    done = 0
    for p in range(1, PARTS + 1):
        if part > 0 and p != part:
            continue
        try:
            first, items = load_part(p)
        except ImportError:
            sh.err("selftest: module " + PARTMODS[p - 1] + " is not installed")
            return 1
        except MemoryError:
            sh.err("selftest: out of memory loading part " + str(p) + " (reboot first)")
            return 1
        n = first - 1
        for label, want, x in items:
            n += 1
            if only != "" and (want is None or only not in label):
                continue
            if want is not None:
                for line in x:
                    if line[:1] != "!":
                        w = line.split(" ")[0]
                        if w not in used:
                            used.append(w)
            done += 1
            if prog:
                sh.out(">" + str(n) + " " + label + "\n")
                sh.flush_out()
            if want is None:
                st, got = attempt(check_fn(x))
            else:
                st, got = attempt(case_fn(x, want))
            if st == "ok":
                if res:
                    sh.out("ok " + str(n) + " " + label + freek() + "\n")
                elif verbose:
                    sh.out("ok   " + label + "\n")
            elif st == "lowmem":
                lows.append(label)
                if res:
                    sh.out("LOWMEM " + str(n) + " " + label + freek() + "\n")
                    sh.out("  " + got[-60:] + "\n")     # what ran out (allocation size)
                else:
                    sh.out("LOWMEM " + label + "\n")
            else:
                fails.append(label)
                if want is None:
                    sh.out("FAIL " + label + ": " + got[:12] + "\n")
                else:
                    sh.out("FAIL " + label + "\n")
                    sh.out("  got " + repr(got)[:26] + "\n")
                    sh.out("  want " + repr(want)[:24] + "\n")
            if res:
                sh.flush_out()
        items = None
        drop_part(p)
    for label in fails:
        sh.out("FAILED " + label + "\n")
    untested = []
    if not partial:
        untested = [c for c in all_commands() if c not in used]
    for c in untested:
        sh.out("UNTESTED " + c + "\n")
    sh.out("selftest: " + str(done - len(fails) - len(lows)) + "/" + str(done)
           + " passed, " + str(len(lows)) + " lowmem, " + str(len(untested))
           + " untested\n")
    if fails or untested:
        return 1
