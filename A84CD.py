# A84CD: commands (Arch84 module 7/10)

from A84FS import VERSION, VFSError, basename


def fail(sh, cmd, arg, e):
    sh.err(cmd + ": " + arg + ": " + str(e))
    return 1


def cmd_help(sh, args):
    names = all_commands()
    names.sort()
    sh.out("Arch84 " + VERSION + " commands:\n" + " ".join(names) + "\n")


def cmd_clear(sh, args):
    sh.term.clear()


def cmd_pwd(sh, args):
    sh.out(sh.cwd + "\n")


def cmd_ls(sh, args):
    show_all = False
    paths = []
    for a in args:
        if a == "-a":
            show_all = True
        elif a.startswith("-") and len(a) > 1:
            sh.err("ls: invalid option -- '" + a[1:] + "'")
            return 2
        else:
            paths.append(a)
    if not paths:
        paths = ["."]
    st = 0
    for p in paths:
        path = sh.resolve(p)
        node = sh.vfs.get(path)
        if node is None:
            sh.err("ls: cannot access '" + p + "': No such file or directory")
            st = 2
            continue
        if not node.is_dir:
            sh.out(p + "\n")
            continue
        if len(paths) > 1:
            sh.out(p + ":\n")
        names = []
        for n in sh.vfs.listdir(path):
            if n.startswith(".") and not show_all:
                continue
            if node.children[n].is_dir:
                n += "/"
            names.append(n)
        if names:
            sh.out("  ".join(names) + "\n")
    return st


def cmd_cd(sh, args):
    if args:
        target = args[0]
    else:
        target = "~"
    path = sh.resolve(target)
    node = sh.vfs.get(path)
    if node is None:
        sh.err("cd: " + target + ": No such file or directory")
        return 1
    if not node.is_dir:
        sh.err("cd: " + target + ": Not a directory")
        return 1
    sh.cwd = path


def need(sh, cmd, args):
    if not args:
        sh.err(cmd + ": missing operand")
        return False
    return True


def cmd_mkdir(sh, args):
    if not need(sh, "mkdir", args):
        return 1
    st = 0
    for a in args:
        try:
            sh.vfs.mkdir(sh.resolve(a))
        except VFSError as e:
            st = fail(sh, "mkdir", "cannot create directory '" + a + "'", e)
    return st


def cmd_touch(sh, args):
    if not need(sh, "touch", args):
        return 1
    st = 0
    for a in args:
        try:
            sh.vfs.touch(sh.resolve(a))
        except VFSError as e:
            st = fail(sh, "touch", "cannot touch '" + a + "'", e)
    return st


def cmd_cat(sh, args):
    if not args and sh.stdin is not None:
        args = ["-"]
    if not need(sh, "cat", args):
        return 1
    st = 0
    for a in args:
        try:
            for line in sh.lines(a):    # streamed: never the whole file
                sh.out(line + "\n")
        except VFSError as e:
            st = fail(sh, "cat", a, e)
    return st


def cmd_echo(sh, args):
    nl = "\n"
    if args and args[0] == "-n":
        nl = ""
        args = args[1:]
    sh.out(" ".join(args) + nl)


def rm_tree(vfs, path):
    # iterative: no recursion limit to hit on a deep tree
    stack = [path]
    order = []
    while stack:
        p = stack.pop()
        order.append(p)
        if vfs.isdir(p):
            for n in vfs.listdir(p):
                stack.append(p.rstrip("/") + "/" + n)
    while order:
        vfs.remove(order.pop())


def cmd_rm(sh, args):
    rec = False
    force = False
    files = []
    opts = True
    for a in args:
        if opts and a == "--":
            opts = False
        elif opts and len(a) > 1 and a[0] == "-" and a.strip("rRf-") == "" and a.strip("-") != "":
            for c in a:
                if c == "r" or c == "R":
                    rec = True
                elif c == "f":
                    force = True
        else:
            files.append(a)
    if not files:
        if not force:
            sh.err("rm: missing operand")
            return 1
        return 0
    st = 0
    for a in files:
        path = sh.resolve(a)
        try:
            if sh.vfs.isdir(path):
                if not rec:
                    raise VFSError("Is a directory")
                if path == "/" or path == sh.cwd or sh.cwd.startswith(path + "/"):
                    raise VFSError("refusing to remove cwd or /")
                rm_tree(sh.vfs, path)
            elif force and not sh.vfs.exists(path):
                continue
            else:
                sh.vfs.remove(path)
        except VFSError as e:
            st = fail(sh, "rm", "cannot remove '" + a + "'", e)
    return st


def cmd_rmdir(sh, args):
    if not need(sh, "rmdir", args):
        return 1
    st = 0
    for a in args:
        path = sh.resolve(a)
        try:
            if not sh.vfs.isdir(path):
                if sh.vfs.exists(path):
                    raise VFSError("Not a directory")
                raise VFSError("No such file or directory")
            if path == sh.cwd or sh.cwd.startswith(path + "/"):
                raise VFSError("is the current directory")
            sh.vfs.remove(path)
        except VFSError as e:
            st = fail(sh, "rmdir", "failed to remove '" + a + "'", e)
    return st


def dest_for(sh, src, dst):
    d = sh.resolve(dst)
    if sh.vfs.isdir(d):
        return d.rstrip("/") + "/" + basename(sh.resolve(src))
    return d


def cmd_cp(sh, args):
    if len(args) < 2:
        sh.err("cp: missing file operand")
        return 1
    srcs = args[:-1]
    dst = args[-1]
    if len(srcs) > 1 and not sh.vfs.isdir(sh.resolve(dst)):
        sh.err("cp: target '" + dst + "' is not a directory")
        return 1
    st = 0
    for s in srcs:
        try:
            if sh.vfs.isdir(sh.resolve(s)):
                raise VFSError("omitting directory")
            sh.vfs.copyfile(sh.resolve(s), dest_for(sh, s, dst))   # shares the pieces
        except VFSError as e:
            st = fail(sh, "cp", "cannot copy '" + s + "'", e)
    return st


def cmd_mv(sh, args):
    if len(args) < 2:
        sh.err("mv: missing file operand")
        return 1
    srcs = args[:-1]
    dst = args[-1]
    if len(srcs) > 1 and not sh.vfs.isdir(sh.resolve(dst)):
        sh.err("mv: target '" + dst + "' is not a directory")
        return 1
    st = 0
    for s in srcs:
        try:
            sp = sh.resolve(s)
            if sp == sh.cwd or sh.cwd.startswith(sp + "/"):
                raise VFSError("is the current directory")
            sh.vfs.rename(sp, dest_for(sh, s, dst))
        except VFSError as e:
            st = fail(sh, "mv", "cannot move '" + s + "'", e)
    return st


def head_tail(sh, name, args):
    n = 10
    files = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-n" and i + 1 < len(args):
            try:
                n = int(args[i + 1])
            except ValueError:
                sh.err(name + ": invalid number of lines: " + args[i + 1])
                return 1
            i += 1
        else:
            files.append(a)
        i += 1
    if not files and sh.stdin is not None:
        files = ["-"]
    if not need(sh, name, files):
        return 1
    st = 0
    if n < 0:
        n = 0
    for a in files:
        try:
            it = sh.lines(a)
        except VFSError as e:
            st = fail(sh, name, a, e)
            continue
        lines = []
        if n > 0:
            for line in it:
                lines.append(line)
                if name == "head":
                    if len(lines) >= n:
                        break
                elif len(lines) > 2 * n + 32:
                    lines = lines[-n:]       # rolling window: tail never holds the file
        if name == "tail":
            lines = lines[-n:] if n > 0 else []
        if len(files) > 1:
            if a == "-":
                a = "standard input"
            sh.out("==> " + a + " <==\n")
        for line in lines:
            sh.out(line + "\n")
    return st


def cmd_head(sh, args):
    return head_tail(sh, "head", args)


def cmd_tail(sh, args):
    return head_tail(sh, "tail", args)


def pad(v, w):
    s = str(v)
    return " " * (w - len(s)) + s


def join(a, b):
    if a.endswith("/"):
        return a + b
    return a + "/" + b


COMMANDS = {
    "help": cmd_help, "clear": cmd_clear, "pwd": cmd_pwd, "ls": cmd_ls,
    "cd": cmd_cd, "mkdir": cmd_mkdir, "touch": cmd_touch, "cat": cmd_cat,
    "echo": cmd_echo, "rm": cmd_rm, "rmdir": cmd_rmdir, "cp": cmd_cp,
    "mv": cmd_mv, "head": cmd_head, "tail": cmd_tail,
}


# Commands that live in A84C2..C5 (13 KB of heap in all): registered by name only and
# loaded on first use, so they cost nothing until you run one.
LAZY = {}
for _m, _names in (("A84C2", "true false grep find"), ("A84C3", "sort wc basename dirname"),
                   ("A84C4", "du df free mount umount uptime"),
                   ("A84C5", "date reboot poweroff"), ("A84C6", "uniq tee")):
    for _n in _names.split():
        LAZY[_n] = _m


def all_commands():
    names = list(COMMANDS.keys())
    for n in LAZY:
        if n not in COMMANDS:
            names.append(n)
    return names


def load_command(name):
    # the command function, importing its module first if needed (None if unknown)
    if name not in COMMANDS and name in LAZY:
        __import__(LAZY[name])
    return COMMANDS.get(name)
