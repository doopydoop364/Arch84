# A84CB: printenv setenv unsetenv (Arch84 module, lazily loaded). Registers into COMMANDS.
# The system-wide variables live in /etc/environment (NAME=value lines, read at startup);
# setenv/unsetenv change that file and the running session. `export`/`unset` change only
# the session.
from A84FS import VFSError
from A84CD import COMMANDS

PATH = "/etc/environment"


def valid(name):
    if name == "" or "0" <= name[0] <= "9":
        return False
    for c in name:
        if not (c == "_" or "a" <= c <= "z" or "A" <= c <= "Z" or "0" <= c <= "9"):
            return False
    return True


def cmd_printenv(sh, args):
    if not args:
        names = list(sh.k.env.keys())
        names.sort()
        for n in names:
            sh.out(n + "=" + sh.k.env[n] + "\n")
        return 0
    st = 0
    for a in args:
        if a in sh.k.env:
            sh.out(sh.k.env[a] + "\n")
        else:
            st = 1
    return st


def rewrite(sh, changes):
    # changes: name -> value, or None to delete; keeps comments and other lines
    out = []
    left = dict(changes)
    if sh.vfs.isfile(PATH):
        for line in sh.vfs.lines(PATH):
            i = line.find("=")
            n = line[:i].strip() if i > 0 else ""
            if n in left:
                v = left.pop(n)
                if v is not None:
                    out.append(n + "=" + v)
            else:
                out.append(line)
    for n in left:
        if left[n] is not None:
            out.append(n + "=" + left[n])
    sh.vfs.write(PATH, "\n".join(out) + "\n")


def cmd_setenv(sh, args):
    if not args:
        sh.err("usage: setenv NAME=VALUE...")
        return 1
    changes = {}
    for a in args:
        i = a.find("=")
        if i < 1 or not valid(a[:i]):
            sh.err("setenv: '" + a + "': not a valid NAME=VALUE")
            return 1
        v = a[i + 1:]
        if a[:i] == "HOME" and v[:1] != "/":
            sh.err("setenv: HOME must be an absolute path")
            return 1
        changes[a[:i]] = v
    try:
        rewrite(sh, changes)
    except VFSError as e:
        sh.err("setenv: " + str(e))
        return 1
    for n in changes:
        sh.k.env[n] = changes[n]
    return 0


def cmd_unsetenv(sh, args):
    if not args:
        sh.err("usage: unsetenv NAME...")
        return 1
    changes = {}
    for a in args:
        if not valid(a):
            sh.err("unsetenv: '" + a + "': not a valid name")
            return 1
        changes[a] = None
    try:
        rewrite(sh, changes)
    except VFSError as e:
        sh.err("unsetenv: " + str(e))
        return 1
    for n in changes:
        sh.k.env.pop(n, None)
    return 0


COMMANDS.update({"printenv": cmd_printenv, "setenv": cmd_setenv, "unsetenv": cmd_unsetenv})
