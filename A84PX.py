# A84PX: the `pacman` and `makepkg` commands (Arch84 module, lazily loaded).
# Registers itself into COMMANDS.
#   pacman -U FILE...   install package files      pacman -R NAME...   remove
#   pacman -S NAME...   install from /var/cache/pacman/pkg (with dependencies)
#   pacman -Sy          rebuild the repository index   -Su  upgrade installed packages
#   pacman -Sl          list that repository   -Ss WORD  search   -Si NAME  info
#   pacman -Qu          list packages the repository has newer versions of
#   pacman -Q [NAME]    list installed    -Qi NAME info    -Ql [NAME] files
#   pacman -Qk [NAME]   verify files      -Qo PATH owner   -Qp FILE  inspect a file
#   makepkg [-d DEP]... DIR NAME VERSION [DESCRIPTION...]
import gc
import sys
from A84FS import VFSError
from A84CD import COMMANDS
from A84PM import HOMEDIR, LOCK, REPO, SYNCDB, PkgError, ok_name, split_dep
from A84PD import db_read, db_reason, mkdirs

USAGE = ("usage: pacman -U FILE | -R[s] NAME | -S[yu] [NAME] | -Sc[c] | -Sl|-Ss|-Si | -Q[ilkopuedt] [ARG]\n"
         "       makepkg [-d DEP]... DIR NAME VERSION [DESC]\n")


def show(sh, meta, old):
    if old is None:
        sh.out("installed " + meta["name"] + " " + meta["version"] + " ("
               + str(len(meta["files"])) + " files)\n")
    elif old == meta["version"]:
        sh.out("reinstalled " + meta["name"] + " " + old + "\n")
    else:
        sh.out("upgraded " + meta["name"] + " " + old + " -> " + meta["version"] + "\n")


def mod(name):
    # a lazily loaded helper module; collecting first gives the compiler a clean heap
    gc.collect()
    try:
        return __import__(name)
    except BaseException:
        # MicroPython keeps a module whose import failed (out of memory) half-built, and
        # the helpers it had pulled in with it: later uses would hit "no attribute"
        from A84CD import HELPERS
        for m in HELPERS:
            sys.modules.pop(m, None)
        sys.modules.pop(name, None)
        raise


def keep_in_lists(vfs, meta):
    # the package's files go into calculator lists (A84BL, its database entry already did): the heap
    # keeps only a reference to each, and the text is read back when something reads the file
    for p, size, s in meta["files"]:
        vfs.externalize(p)


def drop_net():
    # the network code is only needed while downloading: free it before the installer loads
    # (desktop Python keeps it: reloading would only slow the tests)
    if getattr(sys.implementation, "name", "") == "micropython":
        sys.modules.pop("A84PN", None)
        sys.modules.pop("A84NT", None)
    gc.collect()


def take_lock(vfs):
    if vfs.exists(LOCK):
        raise PkgError("unable to lock database (" + LOCK + " exists)\n"
                       "if no pacman is running, remove it: rm " + LOCK)
    mkdirs(vfs, LOCK[:LOCK.rfind("/")], [])
    vfs.write(LOCK, "pacman\n")


def search(sh, mods, rest):
    pb = mod("A84PB")
    newest = pb.newest
    rows = pb.repo(sh.vfs)
    rows.sort()
    if "l" in mods:
        for n, v, p, d, ds in rows:
            sh.out(n + " " + v + "\n")
        return 0
    if not rest:
        sh.err("error: no targets specified")
        return 1
    st = 0
    if "i" in mods:
        for t in rest:
            b = newest(sh.vfs, t)
            if b is None:
                sh.err("error: package '" + t + "' was not found")
                st = 1
            else:
                sh.out("Name        : " + t + "\nVersion     : " + b[0] + "\nDescription : " + b[3]
                       + "\nDepends On  : " + (" ".join(b[2]) or "None") + "\nRepository  : "
                       + (b[1].split(":")[1] if b[1][:4] == "mod:" else ("net" if b[1][:4] == "net:" else "local")) + "\n")
        return st
    w = rest[0].lower()
    for n, v, p, d, ds in rows:
        if w in n or w in ds.lower():
            sh.out(n + " " + v + "\n    " + ds + "\n")
    return 0


def clean(sh, everything):
    # the cache is the repository: -Sc drops every package file except the installed
    # versions, -Scc drops them all
    vfs = sh.vfs
    n = 0
    chars = 0
    if vfs.isdir(REPO):
        for f in list(vfs.listdir(REPO)):
            if not f.endswith(".ar84"):
                continue
            k = f.rfind("-")
            if not everything and k > 0 and ok_name(f[:k]):
                m = db_read(vfs, f[:k], False)
                if m is not None and m["version"] == f[k + 1:-5]:
                    continue
            p = REPO + "/" + f
            chars += sh.fsize(p)
            vfs.remove(p)
            n += 1
            sh.out("removed " + f + "\n")
    if vfs.isfile(SYNCDB):
        vfs.remove(SYNCDB)
    sh.out("cache cleaned: " + str(n) + " packages, " + str(chars) + " chars\n")
    return 0


def change(sh, op, mods, rest):
    vfs = sh.vfs
    if op == "R":
        pi = mod("A84PI")
        metas = pi.removal_set(vfs, rest, "s" in mods)
        for n in pi.remove_order(metas):
            m = pi.remove(vfs, n)
            sh.out("removed " + n + " " + m["version"] + "\n")
        return 0
    if op == "S" and "c" in mods:
        return clean(sh, "cc" in mods)
    pb = mod("A84PB")
    plan = pb.plan
    sync = pb.sync
    upgrades = pb.upgrades
    install = mod("A84PI").install
    pb = None
    files = []
    asdep = []
    if op == "U":
        for a in rest:
            files.append(sh.resolve(a))
    else:
        if "y" in mods:
            n, why = mod("A84PN").refresh(sh)
            drop_net()
            if n is None:
                if why is not None:
                    sh.err("warning: package index not downloaded: " + why + " (using the local repository)")
            else:
                sh.out("downloaded the package index (" + str(n) + " packages)\n")
            rows, bad = sync(vfs)
            sh.out("synchronized " + str(len(rows)) + " packages" + (" (" + str(bad) + " skipped)" if bad else "") + "\n")
        if "u" in mods:
            for n, o, v, p in upgrades(vfs):
                files.append(p)
        for n in rest:
            plan(vfs, n, files, [], 0, asdep)
    plan = sync = upgrades = None
    sys.modules.pop("A84PB", None)          # planning is done: its code is not needed while installing
    if files:
        sh.k.release_spare()                # the reserved block is the one contiguous piece of heap left
    try:
        # download first, while the network code is loaded, then drop it: the installer needs the room
        paths = []
        for f in files:
            if f[:4] == "net:":
                gc.collect()
                paths.append(mod("A84PN").fetch(sh, f[4:]))
            else:
                paths.append(f)
        drop_net()
        for k in range(len(files)):
            gc.collect()
            meta, old = install(vfs, paths[k], "dep" if files[k] in asdep else None)
            keep_in_lists(vfs, meta)
            if files[k][:4] == "net:":
                vfs.remove(paths[k])            # the mirror has it again: no cached copy needed
            show(sh, meta, old)
    finally:
        if files:
            sh.k.hold_spare()
    if op == "S":
        for n in rest:
            db_reason(vfs, split_dep(n)[0], "explicit")      # naming a package makes it explicit
    if not files and "y" not in mods:
        sh.out("nothing to do\n")
    return 0


def cmd_pacman(sh, args):
    HOMEDIR[0] = sh.k.env.get("HOME", "/home/evo")
    if not args or args[0][:1] != "-" or len(args[0]) < 2:
        sh.err(USAGE.rstrip())
        return 1
    op = args[0][1]
    mods = args[0][2:]
    rest = args[1:]
    vfs = sh.vfs
    try:
        if op == "Q":
            if "u" in mods:
                for n, o, v, p in mod("A84PB").upgrades(vfs):
                    sh.out(n + " " + o + " -> " + v + "\n")
                return 0
            return mod("A84PQ").query(sh, mods, rest)
        if op == "S" and ("l" in mods or "s" in mods or "i" in mods):
            return search(sh, mods, rest)
        if op == "U" or op == "S" or op == "R":
            if op == "S" and "y" not in mods and "u" not in mods and "c" not in mods and not rest:
                sh.err("error: no targets specified")
                return 1
            if op != "S" and not rest:
                sh.err("error: no targets specified")
                return 1
            take_lock(vfs)
            try:
                return change(sh, op, mods, rest)
            finally:
                pl = sys.modules.get("A84PL")
                if pl is not None and hasattr(pl, "free_modules"):    # (a module that failed to load is half-built)
                    pl.free_modules()
                if vfs.isfile(LOCK):
                    vfs.remove(LOCK)
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
        out, nf, nb = mod("A84PB").build(sh.vfs, sh.resolve(rest[0]), rest[1], rest[2], " ".join(rest[3:]), deps)
    except (PkgError, VFSError) as e:
        sh.err("makepkg: " + str(e))
        return 1
    sh.out("built " + out + " (" + str(nf) + " files, " + str(nb) + " chars)\n")
    return 0


COMMANDS["pacman"] = cmd_pacman
COMMANDS["makepkg"] = cmd_makepkg
