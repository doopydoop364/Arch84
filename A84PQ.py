# A84PQ: pacman queries -Q[ilkopedt] (library for pacman, lazily loaded).
from A84FS import dpieces
from A84PM import Sum
from A84PD import db_names, db_read, owner, requirers
from A84PS import scan


def info(sh, m):
    sh.out("Name        : " + m["name"] + "\nVersion     : " + m["version"] + "\n")
    sh.out("Description : " + m["desc"] + "\n")
    sh.out("Depends On  : " + (" ".join(m["depends"]) or "None") + "\n")
    if "reason" in m:
        sh.out("Reason      : " + ("Installed as a dependency" if m["reason"] == "dep" else "Explicitly installed") + "\n")
        sh.out("Required By : " + (" ".join(requirers(sh.vfs, m["name"])) or "None") + "\n")
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
        if m is not None and (("e" in mods and m["reason"] == "dep") or ("d" in mods and m["reason"] != "dep")
                              or ("t" in mods and requirers(vfs, n))):
            continue
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
