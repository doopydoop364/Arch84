# A84C3: sort wc basename dirname (Arch84 module, split from A84C2 so each lazily loaded piece
# has a small compile-time memory peak). Registers itself into COMMANDS.

from A84FS import VFSError
from A84CD import COMMANDS, pad


def numkey(s):
    s = s.strip()
    i = 0
    neg = False
    if s[:1] == "-":
        neg = True
        i = 1
    j = i
    while j < len(s) and "0" <= s[j] <= "9":
        j += 1
    if j == i:
        return 0
    v = int(s[i:j])
    if neg:
        return -v
    return v


def cmd_sort(sh, args):
    rev = False
    num = False
    uniq = False
    files = []
    for a in args:
        if a[:1] == "-" and len(a) > 1:
            for c in a[1:]:
                if c == "r":
                    rev = True
                elif c == "n":
                    num = True
                elif c == "u":
                    uniq = True
                else:
                    sh.err("sort: invalid option -- '" + c + "'")
                    return 2
        else:
            files.append(a)
    if not files and sh.stdin is not None:
        files = ["-"]
    if not files:
        sh.err("usage: sort [-rnu] [FILE...]")
        return 2
    lines = []
    st = 0
    for f in files:
        try:
            for line in sh.lines(f):
                lines.append(line)
        except VFSError as e:
            sh.err("sort: " + f + ": " + str(e))
            st = 2
    if num:
        # ties fall back to the whole line (like sort(1)); MicroPython's list
        # sort is not stable, so equal keys alone gave an arbitrary order
        lines.sort(key=lambda l: (numkey(l), l))
    else:
        lines.sort()
    if rev:
        lines.reverse()
    out = []
    for l in lines:
        if not (uniq and out and out[-1] == l):
            out.append(l)
    if out:
        sh.out("\n".join(out) + "\n")
    return st


def cmd_wc(sh, args):
    flags = ""
    files = []
    for a in args:
        if a[:1] == "-" and len(a) > 1:
            for c in a[1:]:
                if c in "lwc":
                    flags += c
                else:
                    sh.err("wc: invalid option -- '" + c + "'")
                    return 2
        else:
            files.append(a)
    implicit = False
    if not files and sh.stdin is not None:
        files = ["-"]
        implicit = True
    if not files:
        sh.err("usage: wc [-lwc] [FILE...]")
        return 2
    one = len(flags) == 1
    if flags == "":
        flags = "lwc"
    tot = [0, 0, 0]
    st = 0
    for f in files:
        try:
            it = sh.lines(f)
            nchars = sh.fsize(f)
        except VFSError as e:
            sh.err("wc: " + f + ": " + str(e))
            st = 1
            continue
        nl = 0
        nw = 0
        for line in it:
            nl += 1
            nw += len(line.split())
        v = [nl, nw, nchars]
        row = ""
        for k in range(3):
            tot[k] += v[k]
            if "lwc"[k] in flags:
                if one:
                    row += str(v[k])
                else:
                    row += pad(v[k], 7)
        if implicit:
            sh.out(row + "\n")         # standard input has no name
        else:
            sh.out(row + " " + f + "\n")
    if len(files) > 1:
        row = ""
        for k in range(3):
            if "lwc"[k] in flags:
                if one:
                    row += str(tot[k])
                else:
                    row += pad(tot[k], 7)
        sh.out(row + " total\n")
    return st


def cmd_basename(sh, args):
    if not args:
        sh.err("basename: missing operand")
        return 1
    p = args[0]
    q = p.rstrip("/")
    if q == "":
        if p == "":
            sh.out("\n")
        else:
            sh.out("/\n")
        return
    n = q[q.rfind("/") + 1:]
    if len(args) > 1 and n != args[1] and n.endswith(args[1]):
        n = n[:len(n) - len(args[1])]
    sh.out(n + "\n")


def cmd_dirname(sh, args):
    if not args:
        sh.err("dirname: missing operand")
        return 1
    p = args[0]
    q = p.rstrip("/")
    if p == "":
        sh.out(".\n")
    elif q == "":
        sh.out("/\n")
    else:
        i = q.rfind("/")
        if i < 0:
            sh.out(".\n")
        else:
            d = q[:i].rstrip("/")
            if d == "":
                d = "/"
            sh.out(d + "\n")

COMMANDS.update({
    "sort": cmd_sort, "wc": cmd_wc, "basename": cmd_basename, "dirname":
    cmd_dirname,
})
