# A84CD: commands (Arch84 module 7/10)

from A84FS import VERSION, VFSError


def fail(sh, cmd, arg, e):
    sh.err(cmd + ": " + arg + ": " + str(e))
    return 1


def cmd_help(sh, args):
    if args:
        return load_command("man")(sh, args)         # help COMMAND = man COMMAND
    names = all_commands()
    names.sort()
    sh.out("Arch84 " + VERSION + " commands:\n" + " ".join(names) + "\n")


def cmd_clear(sh, args):
    sh.term.clear()


def cmd_pwd(sh, args):
    sh.out(sh.cwd + "\n")


def cmd_ls(sh, args):
    show_all = False
    long = False
    paths = []
    for a in args:
        if a == "-a" or a == "-l" or a == "-la" or a == "-al":
            if a != "-l":
                show_all = True
            if a != "-a":
                long = True
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
            q = path.rstrip("/") + "/" + n
            if sh.vfs.isdir(q):
                n += "/"
                if long:
                    n = "     - " + n
            elif long:
                n = pad(sh.vfs.size(q), 6) + " " + n
            names.append(n)
        if names:
            if long:
                sh.out("\n".join(names) + "\n")
            else:
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
    parents = "-p" in args
    args = [a for a in args if a != "-p"]
    if not need(sh, "mkdir", args):
        return 1
    st = 0
    for a in args:
        try:
            p = sh.resolve(a)
            if parents:
                cur = ""
                for part in p.split("/")[1:]:
                    cur += "/" + part
                    if not sh.vfs.exists(cur):
                        sh.vfs.mkdir(cur)
                    elif not sh.vfs.isdir(cur):
                        raise VFSError("Not a directory")
            else:
                sh.vfs.mkdir(p)
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
    "echo": cmd_echo,
}


# Commands that live in lazily loaded modules: known by name only, loaded on first use,
# so they cost nothing until you run one. One string per module instead of a dict entry
# (and an interned name) per command.
MODS = (("A84C2", "true false grep find"), ("A84C3", "sort wc basename dirname"),
        ("A84C4", "du df free mount umount uptime"), ("A84C5", "date reboot poweroff"),
        ("A84C6", "uniq tee"), ("A84EV", "edit"), ("A84PX", "pacman makepkg"),
        ("A84AX", "archive"), ("A84FK", "fsck"),
        ("A84C7", "uname whoami hostname which keys selftest"),
        ("A84C8", "cut tr nl seq"), ("A84C9", "test [ expr"), ("A84MN", "man"), ("A84CA", "sed rev"),
        ("A84CB", "printenv setenv unsetenv"),
        ("A84CG", "rm rmdir cp mv head tail"))


class Lazy:
    # dict-like view of MODS: name -> module
    def __getitem__(self, name):
        for m, names in MODS:
            if (" " + names + " ").find(" " + name + " ") >= 0:
                return m
        raise KeyError(name)

    def __contains__(self, name):
        for m, names in MODS:
            if (" " + names + " ").find(" " + name + " ") >= 0:
                return True
        return False

    def __iter__(self):
        return iter(self.keys())

    def keys(self):
        out = []
        for m, names in MODS:
            out.extend(names.split(" "))
        return out

    def values(self):
        return [m for m, names in MODS]


LAZY = Lazy()


def all_commands():
    names = list(COMMANDS.keys())
    for n in LAZY.keys():
        if n not in COMMANDS:
            names.append(n)
    return names


# library modules the lazy commands import; evicted together with them
HELPERS = ("A84CY", "A84SW", "A84PM", "A84PS", "A84PQ", "A84PD", "A84PI", "A84PB", "A84PL", "A84AI", "A84AR", "A84AE", "A84ED")


def unload(command, *mods):
    # a rarely used command drops its own modules when it finishes, so the RAM it
    # freed (archive) is not immediately spent on its code
    import sys
    import gc
    COMMANDS.pop(command, None)
    for m in mods:
        sys.modules.pop(m, None)
    gc.collect()


def evict():
    # Lazy command modules stay resident once loaded. When the heap is too full to
    # compile the next one, drop them all (they reload on demand) and collect.
    import sys
    import gc
    gone = 0
    for n in LAZY.keys():
        COMMANDS.pop(n, None)
    for m in list(LAZY.values()) + list(HELPERS):
        if m != "A84SC" and m in sys.modules:
            del sys.modules[m]
            gone += 1
    gc.collect()
    return gone


def load_command(name):
    # the command function, importing its module first if needed (None if unknown)
    if name not in COMMANDS and name in LAZY:
        try:
            __import__(LAZY[name])
        except MemoryError:
            # MicroPython keeps a module that ran out of memory half-built in sys.modules:
            # evict() drops those too, so the retry starts clean (and so does a later try)
            evict()
            try:
                __import__(LAZY[name])
            except MemoryError:
                evict()
                raise
    return COMMANDS.get(name)
