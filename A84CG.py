# A84CG: rm rmdir cp mv head tail (Arch84 module, lazily loaded; split from A84CD so the
# always-resident part stays small). Registers itself into COMMANDS.

from A84FS import Node, VFSError, basename
from A84CD import COMMANDS, fail, need


def vfs_copyfile(vfs, src, dst):
    # pieces are immutable strings, so a copy shares them: a 100 KB file
    # costs one small list, not another 100 KB
    d = vfs._file(src).data
    if isinstance(d, list):
        d = list(d)               # (a str or an external file's data is immutable and shared)
    parent, name = vfs._parent(dst)
    node = parent.children.get(name)
    if node is None:
        parent.children[name] = Node(False, d)
    elif node.is_dir:
        raise VFSError("Is a directory")
    else:
        node.data = d
    vfs.dirty = True


def vfs_rename(vfs, src, dst):
    if src == "/":
        raise VFSError("Device or resource busy")
    if src == dst:
        return
    if dst.startswith(src + "/"):
        raise VFSError("Invalid argument")
    sparent, sname = vfs._parent(src)
    node = sparent.children.get(sname)
    if node is None:
        raise VFSError("No such file or directory")
    dparent, dname = vfs._parent(dst)
    old = dparent.children.get(dname)
    if old is not None:
        if old.is_dir:
            if not node.is_dir:
                raise VFSError("Is a directory")
            if old.children:
                raise VFSError("Directory not empty")
        elif node.is_dir:
            raise VFSError("Not a directory")
    del sparent.children[sname]
    dparent.children[dname] = node
    vfs.dirty = True


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


def copy_tree(vfs, src, dst):
    # iterative; files share their (immutable) pieces
    stack = [(src, dst)]
    while stack:
        s, d = stack.pop()
        if vfs.isdir(s):
            if not vfs.exists(d):
                vfs.mkdir(d)
            elif not vfs.isdir(d):
                raise VFSError("Not a directory")
            for n in vfs.listdir(s):
                stack.append((s.rstrip("/") + "/" + n, d.rstrip("/") + "/" + n))
        else:
            vfs.copyfile(s, d)


def cmd_cp(sh, args):
    rec = False
    rest = []
    for a in args:
        if a == "-r" or a == "-R":
            rec = True
        else:
            rest.append(a)
    args = rest
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
            sp = sh.resolve(s)
            dp = dest_for(sh, s, dst)
            if sh.vfs.isdir(sp):
                if not rec:
                    raise VFSError("omitting directory")
                dp = sh.resolve(dp)
                if dp == sp or dp.startswith(sp.rstrip("/") + "/"):
                    raise VFSError("cannot copy a directory into itself")
                copy_tree(sh.vfs, sp, dp)
            else:
                sh.vfs.copyfile(sp, dp)   # shares the pieces
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
        elif len(a) > 1 and a[0] == "-" and a[1:].strip("0123456789") == "":
            n = int(a[1:])                  # head -5
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

COMMANDS.update({"rm": cmd_rm, "rmdir": cmd_rmdir, "cp": cmd_cp, "mv": cmd_mv,
                 "head": cmd_head, "tail": cmd_tail})
