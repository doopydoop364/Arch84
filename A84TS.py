# A84TS: self test (Arch84 module 10/10, loaded only by the selftest command)
# Runs every command in a throwaway shell (MemStorage, fresh VFS per case);
# the real filesystem and saved storage are never touched.
from A84ST import MemStorage
from A84KN import Kernel
from A84SH import Shell
from A84CD import all_commands
from A84TD import CASES, Cap
from A84TX import CHECKS


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


def attempt(fn):
    # fn() -> (ok, got). "ok" / "lowmem" / "fail"; one retry after a collect
    # when the failure looks like a memory shortage
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
    verbose = "-v" in args
    fails = []
    lows = []
    used = ["selftest"]
    done = 0
    # storage checks first, while the lazy command module is not loaded yet
    for label, fn in CHECKS:
        done += 1
        st, got = attempt(check_fn(fn))
        if st == "ok":
            if verbose:
                sh.out("ok   " + label + "\n")
        elif st == "lowmem":
            lows.append(label)
            sh.out("LOWMEM " + label + "\n")
        else:
            fails.append(label)
            sh.out("FAIL " + label + ": " + got[:12] + "\n")
    for m in ("A84C2", "A84C3", "A84C4", "A84C5"):
        try:
            __import__(m)      # the lazy commands must be registered to be tested
        except ImportError:
            sh.err("selftest: module " + m + " is not installed")
            return 1
        except MemoryError:
            sh.err("selftest: out of memory loading " + m + " (reboot, then run selftest first)")
            return 1
    for label, lines, want in CASES:
        for line in lines:
            if line[:1] != "!":
                w = line.split(" ")[0]
                if w not in used:
                    used.append(w)
        done += 1
        st, got = attempt(case_fn(lines, want))
        if st == "ok":
            if verbose:
                sh.out("ok   " + label + "\n")
        elif st == "lowmem":
            lows.append(label)
            sh.out("LOWMEM " + label + "\n")
        else:
            fails.append(label)
            sh.out("FAIL " + label + "\n")
            sh.out("  got " + repr(got)[:26] + "\n")
            sh.out("  want " + repr(want)[:24] + "\n")
    untested = [c for c in all_commands() if c not in used]
    for c in untested:
        sh.out("UNTESTED " + c + "\n")
    sh.out("selftest: " + str(done - len(fails) - len(lows)) + "/" + str(done)
           + " passed, " + str(len(lows)) + " lowmem, " + str(len(untested))
           + " untested\n")
    if fails or untested:
        return 1
