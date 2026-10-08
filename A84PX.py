# A84PX: the `pacman` and `makepkg` commands (Arch84 module, lazily loaded).
# Registers itself into COMMANDS.
#   pacman -U FILE...   install package files      pacman -R NAME...   remove
#   pacman -S NAME...   install from /var/cache/pacman/pkg (with dependencies)
#   pacman -Sl          list that repository
#   pacman -Q [NAME]    list installed    -Qi NAME info    -Ql [NAME] files
#   pacman -Qk [NAME]   verify files      -Qo PATH owner   -Qp FILE  inspect a file
#   makepkg [-d DEP]... DIR NAME VERSION [DESCRIPTION...]
from A84FS import VFSError, dpieces
from A84CD import COMMANDS
from A84PM import DBDIR, PkgError, Sum, scan
from A84PD import db_names, db_read, owner
from A84PI import install, remove
from A84PB import build, plan, repo

USAGE = ("usage: pacman -U FILE | -R NAME | -S NAME | -Sl | -Q[ilkop] [ARG]\n"
         "       makepkg [-d DEP]... DIR NAME VERSION [DESC]\n")


def show(sh, meta, old):
    if old is None:
        sh.out("installed " + meta["name"] + " " + meta["version"] + " ("
               + str(len(meta["files"])) + " files)\n")
    elif old == meta["version"]:
        sh.out("reinstalled " + meta["name"] + " " + old + "\n")
    else:
        sh.out("upgraded " + meta["name"] + " " + old + " -> " + meta["version"] + "\n")


def info(sh, m):
    sh.out("Name        : " + m["name"] + "\nVersion     : " + m["version"] + "\n")
    sh.out("Description : " + m["desc"] + "\n")
    sh.out("Depends On  : " + (" ".join(m["depends"]) or "None") + "\n")
    n = 0
    for p, size, s in m["files"]:
        n += size
    sh.out("Size        : " + str(n) + " chars in " + str(len(m["files"])) + " files\n")


def altered(sh, m):
    bad = 0
    for p, size, s in m["files"]:
        node = sh.vfs.get(p)
        why = None
        if node is None or node.is_dir:
            why = "missing"
        else:
            t = Sum()
            n = 0
            for piece in dpieces(node.data):
                t.add(piece)
                n += len(piece)
            if n != size:
                why = "size changed"
            elif t.hex() != s:
                why = "modified"
        if why:
            bad += 1
            sh.out(m["name"] + ": " + p + " (" + why + ")\n")
    return bad


def query(sh, mods, args):
    vfs = sh.vfs
    if "o" in mods:
        if not args:
            sh.err("pacman: no path given")
            return 1
        st = 0
        for a in args:
            p = sh.resolve(a)
            o = owner(vfs, p)
            if o is None:
                sh.err("error: No package owns " + a)
                st = 1
            else:
                sh.out(p + " is owned by " + o + " " + db_read(vfs, o)["version"] + "\n")
        return st
    if "p" in mods:
        if not args:
            sh.err("pacman: no file given")
            return 1
        meta = scan(vfs, sh.resolve(args[0]))
        info(sh, meta)
        for p, size, s in meta["files"]:
            sh.out(p + "\n")
        return 0
    names = args
    if not names:
        names = db_names(vfs)
        if not names and ("i" in mods or "l" in mods or "k" in mods):
            return 0
    st = 0
    for n in names:
        m = db_read(vfs, n)
        if m is None:
            sh.err("error: package '" + n + "' was not found")
            st = 1
        elif "i" in mods:
            info(sh, m)
        elif "l" in mods:
            for p, size, s in m["files"]:
                sh.out(n + " " + p + "\n")
        elif "k" in mods:
            bad = altered(sh, m)
            sh.out(n + ": " + str(len(m["files"])) + " total files, " + str(bad) + " altered files\n")
            if bad:
                st = 1
        else:
            sh.out(n + " " + m["version"] + "\n")
    return st


def cmd_pacman(sh, args):
    if not args or args[0][:1] != "-" or len(args[0]) < 2:
        sh.err(USAGE.rstrip())
        return 1
    op = args[0][1]
    mods = args[0][2:]
    rest = args[1:]
    vfs = sh.vfs
    try:
        if op == "Q":
            return query(sh, mods, rest)
        if op == "S" and "l" in mods:
            rows = repo(vfs)
            rows.sort()
            for n, v, p in rows:
                sh.out(n + " " + v + "\n")
            return 0
        if op == "U" or op == "S" or op == "R":
            if not rest:
                sh.err("error: no targets specified")
                return 1
            if op == "R":
                for n in rest:
                    m = remove(vfs, n)
                    sh.out("removed " + n + " " + m["version"] + "\n")
                return 0
            files = []
            if op == "U":
                for a in rest:
                    files.append(sh.resolve(a))
            else:
                for n in rest:
                    plan(vfs, n, files, [])
            for f in files:
                meta, old = install(vfs, f)
                show(sh, meta, old)
            if not files:
                sh.out("nothing to do\n")
            return 0
    except PkgError as e:
        sh.err("error: " + str(e))
        return 1
    except VFSError as e:
        sh.err("error: " + str(e))
        return 1
    sh.err(USAGE.rstrip())
    return 1


def cmd_makepkg(sh, args):
    deps = []
    rest = []
    i = 0
    while i < len(args):
        if args[i] == "-d" and i + 1 < len(args):
            deps.append(args[i + 1])
            i += 2
        else:
            rest.append(args[i])
            i += 1
    if len(rest) < 3:
        sh.err("usage: makepkg [-d DEP]... DIR NAME VERSION [DESCRIPTION...]")
        return 1
    try:
        out, nf, nb = build(sh.vfs, sh.resolve(rest[0]), rest[1], rest[2], " ".join(rest[3:]), deps)
    except (PkgError, VFSError) as e:
        sh.err("makepkg: " + str(e))
        return 1
    sh.out("built " + out + " (" + str(nf) + " files, " + str(nb) + " chars)\n")
    return 0


COMMANDS["pacman"] = cmd_pacman
COMMANDS["makepkg"] = cmd_makepkg
