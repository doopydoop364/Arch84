# A84PL: packages stored in flash modules (library for pacman, lazily loaded, only
# when a flash repository or package is used). tools/ar84pack.py writes the modules:
#   R84REG.py   REPOS = ("core", ...)                          the repositories
#   QR<NAME>.py ROWS = ((name, version, "K123456", parts, "dep dep", "description"), ...)
#   K<6 hex><n>.py  LINES = ("AR84 1", ...)                    part n of one package
from A84PM import PkgError, ok_dep, ok_name, ok_ver

def is_part(n):
    # K + 6 hex digits + part number: a package part module on the flash
    if len(n) != 8 or n[0] != "K" or not ("0" <= n[7] <= "9"):
        return False
    for c in n[1:7]:
        if not ("0" <= c <= "9" or "A" <= c <= "F"):
            return False
    return True


def free_modules():
    # drop every package part module (and its compiled text) from memory
    import sys
    import gc
    for n in list(sys.modules.keys()):
        if is_part(n):
            del sys.modules[n]
    gc.collect()


def flash_lines(path):
    # path = "mod:<repo>:<K123456>:<parts>": the lines of a package stored in the
    # flash modules K1234560 .. K123456<parts-1> (LINES tuples), one part in memory at a time
    import sys
    import gc
    f = path.split(":")
    if len(f) != 4:
        raise PkgError("bad package source")
    try:
        parts = int(f[3])
    except ValueError:
        raise PkgError("bad package source")
    for i in range(parts):
        name = f[2] + str(i)
        if not is_part(name):
            raise PkgError("bad package source")
        gc.collect()                    # importing needs a contiguous read buffer
        try:
            m = __import__(name)
        except ImportError:
            raise PkgError("package module " + name + " is not on the calculator")
        try:
            lines = m.LINES
        except AttributeError:
            lines = ()
        m = None
        for line in lines:
            yield line
        lines = None
        sys.modules.pop(name, None)
        gc.collect()


def flash_rows():
    # packages stored in flash modules: the registry R84REG lists the repositories
    # (REPOS = ("core", ...)), each repository's index module QR<NAME> has
    # ROWS = ((name, version, "K123456", parts, "dep dep", "description"), ...).
    # -> (rows like repo(), number of bad entries)
    import sys
    import gc
    rows = []
    bad = 0
    try:
        reg = __import__("R84REG")
        repos = list(reg.REPOS)
    except (ImportError, AttributeError, TypeError):
        return rows, bad
    sys.modules.pop("R84REG", None)
    for r in repos:
        mod = "QR" + str(r).upper()
        gc.collect()
        try:
            m = __import__(mod)
            tab = list(m.ROWS)
        except (ImportError, AttributeError, TypeError):
            bad += 1
            sys.modules.pop(mod, None)
            continue
        sys.modules.pop(mod, None)
        for t in tab:
            try:
                n, v, mid, parts, deps, desc = t
                d = deps.split()
                ok = ok_name(n) and ok_ver(v) and is_part(mid + "0") and 0 < int(parts) < 10 and ok_name(str(r)) and len(str(r)) < 7
                for x in d:
                    ok = ok and ok_dep(x)
            except (ValueError, TypeError, AttributeError):
                ok = False
            if ok:
                rows.append((n, v, "mod:" + str(r) + ":" + mid + ":" + str(int(parts)), d, str(desc)))
            else:
                bad += 1
        tab = None
        gc.collect()
    return rows, bad


