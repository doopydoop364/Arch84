# A84C2: text commands: true false grep find (Arch84 module, split from A84C2 so each lazily loaded piece
# has a small compile-time memory peak). Registers itself into COMMANDS.

from A84FS import VFSError, basename
from A84CD import COMMANDS, join


def cmd_true(sh, args):
    return 0


def cmd_false(sh, args):
    return 1


def cmd_grep(sh, args):
    ci = False
    num = False
    inv = False
    cnt = False
    rest = []
    for a in args:
        if a[:1] == "-" and len(a) > 1 and not rest:
            for c in a[1:]:
                if c == "i":
                    ci = True
                elif c == "n":
                    num = True
                elif c == "v":
                    inv = True
                elif c == "c":
                    cnt = True
                else:
                    sh.err("grep: invalid option -- '" + c + "'")
                    return 2
        else:
            rest.append(a)
    if len(rest) == 1 and sh.stdin is not None:
        rest.append("-")
    if len(rest) < 2:
        sh.err("usage: grep [-ivnc] PATTERN [FILE...]")
        return 2
    pat = rest[0]
    if ci:
        pat = pat.lower()
    files = rest[1:]
    st = 1
    for f in files:
        try:
            it = sh.lines(f)
        except VFSError as e:
            sh.err("grep: " + f + ": " + str(e))
            st = 2
            continue
        n = 0
        i = 0
        for line in it:
            i += 1
            hay = line
            if ci:
                hay = line.lower()
            if (pat in hay) != inv:
                n += 1
                if not cnt:
                    pre = ""
                    if len(files) > 1:
                        pre = f + ":"
                    if num:
                        pre += str(i) + ":"
                    sh.out(pre + line + "\n")
        if cnt:
            pre = ""
            if len(files) > 1:
                pre = f + ":"
            sh.out(pre + str(n) + "\n")
        if n and st != 2:
            st = 0
    return st


def glob_match(pat, s):
    # * and ? only; iterative
    p = 0
    i = 0
    star = -1
    mark = 0
    while i < len(s):
        if p < len(pat) and pat[p] == "*":
            star = p
            mark = i
            p += 1
        elif p < len(pat) and (pat[p] == "?" or pat[p] == s[i]):
            p += 1
            i += 1
        elif star >= 0:
            p = star + 1
            mark += 1
            i = mark
        else:
            return False
    while p < len(pat) and pat[p] == "*":
        p += 1
    return p == len(pat)


def cmd_find(sh, args):
    start = "."
    name = None
    typ = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-name" and i + 1 < len(args):
            name = args[i + 1]
            i += 2
        elif a == "-type" and i + 1 < len(args):
            typ = args[i + 1]
            i += 2
        elif a[:1] == "-":
            sh.err("find: unknown predicate '" + a + "'")
            return 1
        else:
            start = a
            i += 1
    root = sh.resolve(start)
    if not sh.vfs.exists(root):
        sh.err("find: '" + start + "': No such file or directory")
        return 1
    stack = [(start, root)]
    while stack:
        disp, ab = stack.pop()
        node = sh.vfs.get(ab)
        ok = name is None or glob_match(name, basename(ab))
        if typ == "d" and not node.is_dir:
            ok = False
        if typ == "f" and node.is_dir:
            ok = False
        if ok:
            sh.out(disp + "\n")
        if node.is_dir:
            names = sh.vfs.listdir(ab)
            for j in range(len(names) - 1, -1, -1):
                stack.append((join(disp, names[j]), join(ab, names[j])))

COMMANDS.update({
    "true": cmd_true, "false": cmd_false, "grep": cmd_grep, "find": cmd_find,
})
