# A84C8: cut tr nl seq (Arch84 module, lazily loaded). Registers itself into COMMANDS.
from A84FS import VFSError
from A84CD import COMMANDS, pad


def ranges(spec):
    # "1,3-5,7-" -> [(lo, hi)]  (hi None = to the end); None if malformed
    out = []
    for part in spec.split(","):
        a, sep, b = part.partition("-")
        try:
            lo = int(a) if a != "" else 1
            hi = int(b) if sep and b != "" else (None if sep else lo)
        except ValueError:
            return None
        if lo < 1 or (hi is not None and hi < lo):
            return None
        out.append((lo, hi))
    return out


def picked(rs, i):
    for lo, hi in rs:
        if i >= lo and (hi is None or i <= hi):
            return True
    return False


def cmd_cut(sh, args):
    delim = "\t"
    mode = ""
    spec = ""
    files = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-d" and i + 1 < len(args):
            delim = args[i + 1]
            i += 2
        elif a == "-f" or a == "-c":
            if i + 1 >= len(args):
                sh.err("cut: option requires an argument -- '" + a[1] + "'")
                return 2
            mode = a[1]
            spec = args[i + 1]
            i += 2
        elif a[:2] == "-d" and len(a) > 2:
            delim = a[2:]
            i += 1
        elif a[:2] in ("-f", "-c") and len(a) > 2:
            mode = a[1]
            spec = a[2:]
            i += 1
        else:
            files.append(a)
            i += 1
    rs = ranges(spec) if mode else None
    if rs is None:
        sh.err("cut: you must specify a list of fields (-f) or characters (-c)")
        return 2
    if len(delim) != 1:
        sh.err("cut: the delimiter must be a single character")
        return 2
    if not files:
        files = ["-"]
    st = 0
    for f in files:
        try:
            for line in sh.lines(f):
                if mode == "c":
                    sh.out("".join([line[k] for k in range(len(line)) if picked(rs, k + 1)]) + "\n")
                elif delim not in line:
                    sh.out(line + "\n")
                else:
                    parts = line.split(delim)
                    sh.out(delim.join([parts[k] for k in range(len(parts)) if picked(rs, k + 1)]) + "\n")
        except VFSError as e:
            sh.err("cut: " + f + ": " + str(e))
            st = 1
    return st


def expand(s):
    # tr set: ranges a-z and the escapes \n \t \\
    out = ""
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            c = {"n": "\n", "t": "\t"}.get(s[i + 1], s[i + 1])
            i += 1
        if i + 2 < len(s) and s[i + 1] == "-":
            hi = s[i + 2]
            for k in range(ord(c), ord(hi) + 1):
                out += chr(k)
            i += 3
            continue
        out += c
        i += 1
    return out


def cmd_tr(sh, args):
    delete = False
    sets = []
    for a in args:
        if a == "-d" and not sets:
            delete = True
        else:
            sets.append(a)
    if len(sets) != (1 if delete else 2):
        sh.err("usage: tr SET1 SET2 | tr -d SET   (reads standard input)")
        return 2
    a = expand(sets[0])
    b = ""
    if not delete:
        b = expand(sets[1])
        if b == "":
            sh.err("tr: SET2 is empty")
            return 2
    for line in sh.lines("-"):
        out = ""
        for c in line + "\n":
            k = a.find(c)
            if k < 0:
                out += c
            elif not delete:
                out += b[k] if k < len(b) else b[-1]
        sh.out(out)
    return 0


def cmd_nl(sh, args):
    files = args or ["-"]
    n = 0
    st = 0
    for f in files:
        try:
            for line in sh.lines(f):
                n += 1
                sh.out(pad(n, 6) + "\t" + line + "\n")
        except VFSError as e:
            sh.err("nl: " + f + ": " + str(e))
            st = 1
    return st


def cmd_seq(sh, args):
    try:
        nums = [int(a) for a in args]
    except ValueError:
        sh.err("seq: invalid number")
        return 1
    if len(nums) == 1:
        first, step, last = 1, 1, nums[0]
    elif len(nums) == 2:
        first, step, last = nums[0], 1, nums[1]
    elif len(nums) == 3:
        first, step, last = nums
    else:
        sh.err("usage: seq [FIRST [INCREMENT]] LAST")
        return 1
    if step == 0:
        sh.err("seq: zero increment")
        return 1
    if abs(last - first) > 2000:
        sh.err("seq: too many numbers (limit 2000)")
        return 1
    k = first
    while (step > 0 and k <= last) or (step < 0 and k >= last):
        sh.out(str(k) + "\n")
        k += step
    return 0


COMMANDS.update({"cut": cmd_cut, "tr": cmd_tr, "nl": cmd_nl, "seq": cmd_seq})
