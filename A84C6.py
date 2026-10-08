# A84C6: uniq tee (Arch84 module, lazily loaded; small so it compiles within the heap).
# Registers itself into COMMANDS.

from A84FS import VFSError
from A84CD import COMMANDS, pad


def cmd_uniq(sh, args):
    count = False
    dup = False
    files = []
    for a in args:
        if a[:1] == "-" and len(a) > 1:
            for c in a[1:]:
                if c == "c":
                    count = True
                elif c == "d":
                    dup = True
                else:
                    sh.err("uniq: invalid option -- '" + c + "'")
                    return 2
        else:
            files.append(a)
    if not files:
        files = ["-"]
    if len(files) > 1:
        sh.err("uniq: extra operand '" + files[1] + "'")
        return 2
    try:
        it = sh.lines(files[0])
        prev = None
        n = 0
        for line in it:
            if prev is not None and line == prev:
                n += 1
                continue
            if prev is not None:
                emit(sh, prev, n, count, dup)
            prev = line
            n = 1
        if prev is not None:
            emit(sh, prev, n, count, dup)
    except VFSError as e:
        sh.err("uniq: " + files[0] + ": " + str(e))
        return 1


def emit(sh, line, n, count, dup):
    if dup and n < 2:
        return
    if count:
        sh.out(pad(n, 7) + " " + line + "\n")
    else:
        sh.out(line + "\n")


def cmd_tee(sh, args):
    # copies standard input to standard output and to each FILE
    app = False
    files = []
    for a in args:
        if a == "-a":
            app = True
        else:
            files.append(a)
    st = 0
    paths = []
    for f in files:
        p = sh.resolve(f)
        try:
            if app:
                sh.vfs.append(p, "")
            else:
                sh.vfs.write(p, "")
            paths.append((f, p))
        except VFSError as e:
            sh.err("tee: " + f + ": " + str(e))
            st = 1
    for line in sh.lines("-"):
        text = line + "\n"
        sh.out(text)
        for f, p in paths:
            try:
                sh.vfs.append(p, text)
            except VFSError as e:
                sh.err("tee: " + f + ": " + str(e))
                st = 1
    return st


COMMANDS.update({"uniq": cmd_uniq, "tee": cmd_tee})
