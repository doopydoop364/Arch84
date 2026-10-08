# A84CA: sed rev (Arch84 module, lazily loaded). Registers itself into COMMANDS.
# sed [-n] 'COMMAND[;COMMAND...]' [FILE...]  (reads standard input without FILE)
#   address: N | N,M | N,$ | $ | /text/        commands: s/old/new/[g][p]  d  p
# "old" is plain text, not a regular expression; & in "new" is the matched text.
# Put the script in quotes: ; is also the shell's command separator.
from A84FS import VFSError
from A84CD import COMMANDS


class SedError(Exception):
    pass


def parse_addr(s, i):
    # -> (addr, next index); addr is None, ("n", lo, hi) or ("t", text)
    if i < len(s) and s[i] == "/":
        j = s.find("/", i + 1)
        if j < 0:
            raise SedError("unterminated address")
        return ("t", s[i + 1:j]), j + 1
    if i < len(s) and s[i] == "$":
        return ("n", -1, -1), i + 1             # -1 = the last line
    j = i
    while j < len(s) and "0" <= s[j] <= "9":
        j += 1
    if j == i:
        return None, i
    lo = int(s[i:j])
    hi = lo
    if j < len(s) and s[j] == ",":
        if j + 1 < len(s) and s[j + 1] == "$":
            return ("n", lo, -1), j + 2
        k = j + 1
        while k < len(s) and "0" <= s[k] <= "9":
            k += 1
        if k == j + 1:
            raise SedError("bad address")
        hi = int(s[j + 1:k])
        j = k
    return ("n", lo, hi), j


def split_arg(s, i, delim):
    # text up to the next unescaped delim -> (text, next index)
    out = ""
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            if s[i + 1] == delim:
                out += delim
            else:
                out += c + s[i + 1]
            i += 2
            continue
        if c == delim:
            return out, i + 1
        out += c
        i += 1
    raise SedError("unterminated s command")


def compile_script(script):
    cmds = []
    for part in script.split(";"):
        s = part.strip()
        if s == "":
            continue
        addr, i = parse_addr(s, 0)
        if i >= len(s):
            raise SedError("missing command")
        c = s[i]
        if c == "d" or c == "p":
            if s[i + 1:].strip() != "":
                raise SedError("extra characters after command")
            cmds.append((addr, c, None, None, ""))
        elif c == "s" and i + 1 < len(s):
            d = s[i + 1]
            old, j = split_arg(s, i + 2, d)
            new, j = split_arg(s, j, d)
            flags = s[j:].strip()
            for f in flags:
                if f != "g" and f != "p":
                    raise SedError("unknown flag: " + f)
            if old == "":
                raise SedError("empty pattern")
            cmds.append((addr, "s", old, new, flags))
        else:
            raise SedError("unknown command: " + c)
    return cmds


def matches(addr, n, line, last):
    if addr is None:
        return True
    if addr[0] == "n":
        if addr[1] < 0:
            return last
        return addr[1] <= n and (addr[2] < 0 or n <= addr[2])
    return addr[1] in line


def substitute(line, old, new, glob):
    out = ""
    i = 0
    done = False
    while True:
        k = line.find(old, i)
        if k < 0 or (done and not glob):
            break
        rep = ""
        j = 0
        while j < len(new):
            if new[j] == "\\" and j + 1 < len(new):
                rep += new[j + 1]
                j += 2
            elif new[j] == "&":
                rep += old
                j += 1
            else:
                rep += new[j]
                j += 1
        out += line[i:k] + rep
        i = k + len(old)
        done = True
    return out + line[i:], done


def edit(sh, cmds, quiet, n, line, last):
    dead = False
    for addr, c, old, new, flags in cmds:
        if dead or not matches(addr, n, line, last):
            continue
        if c == "d":
            dead = True
        elif c == "p":
            sh.out(line + "\n")
        else:
            line, hit = substitute(line, old, new, "g" in flags)
            if hit and "p" in flags:
                sh.out(line + "\n")
    if not quiet and not dead:
        sh.out(line + "\n")


def cmd_sed(sh, args):
    quiet = False
    rest = []
    for a in args:
        if a == "-n" and not rest:
            quiet = True
        else:
            rest.append(a)
    if not rest:
        sh.err("usage: sed [-n] 's/old/new/[g]' | 'Nd' | 'N,Mp' | '/text/d' [FILE...]")
        return 2
    try:
        cmds = compile_script(rest[0])
    except SedError as e:
        sh.err("sed: " + str(e))
        return 2
    files = rest[1:] or ["-"]
    st = 0
    for f in files:
        try:
            n = 0
            prev = None
            for line in sh.lines(f):
                if prev is not None:
                    n += 1
                    edit(sh, cmds, quiet, n, prev, False)
                prev = line
            if prev is not None:
                edit(sh, cmds, quiet, n + 1, prev, True)
        except VFSError as e:
            sh.err("sed: " + f + ": " + str(e))
            st = 1
    return st


def cmd_rev(sh, args):
    st = 0
    for f in args or ["-"]:
        try:
            for line in sh.lines(f):
                sh.out("".join([line[k] for k in range(len(line) - 1, -1, -1)]) + "\n")
        except VFSError as e:
            sh.err("rev: " + f + ": " + str(e))
            st = 1
    return st


COMMANDS.update({"sed": cmd_sed, "rev": cmd_rev})
