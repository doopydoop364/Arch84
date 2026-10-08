# A84PD: installed-package database for pacman (Arch84 module, lazily loaded).
# /var/lib/pacman/local/<name>/desc  (name, version, desc, depends)
#                              files (d<TAB>dir | f<TAB>path<TAB>size<TAB>sum)
from A84FS import VFSError, unesc
from A84PM import DBDIR, PkgError, esc, split_dep


def db_names(vfs):
    if not vfs.isdir(DBDIR):
        return []
    return vfs.listdir(DBDIR)


def db_read(vfs, name, full=True):
    # -> meta with dirs / files from /var/lib/pacman/local/<name>, or None
    # (full=False skips the file list: much cheaper)
    base = DBDIR + "/" + name
    if not vfs.isdir(base):
        return None
    meta = {"name": name, "version": "?", "desc": "", "depends": [], "dirs": [], "files": [], "reason": "explicit"}
    try:
        for line in vfs.lines(base + "/desc"):
            sp = line.find(" ")
            if sp > 0:
                k = line[:sp]
                v = line[sp + 1:]
                if k == "desc":
                    meta["desc"] = unesc(v)
                elif k == "depends":
                    meta["depends"] = v.split()
                elif k == "version":
                    meta["version"] = v
                elif k == "reason":
                    meta["reason"] = v
        if not full:
            return meta
        for line in vfs.lines(base + "/files"):
            f = line.split("\t")
            if f[0] == "d" and len(f) == 2:
                meta["dirs"].append(f[1])
            elif f[0] == "f" and len(f) == 4:
                meta["files"].append((f[1], int(f[2]), f[3]))
    except (VFSError, ValueError):
        pass
    return meta


def desc_text(meta):
    d = "name " + meta["name"] + "\nversion " + meta["version"] + "\n"
    if meta["desc"] != "":
        d += "desc " + esc(meta["desc"]) + "\n"
    if meta["depends"]:
        d += "depends " + " ".join(meta["depends"]) + "\n"
    if meta.get("reason") == "dep":
        d += "reason dep\n"
    return d


def db_reason(vfs, name, reason):
    m = db_read(vfs, name, False)
    if m is not None and m["reason"] != reason:
        m["reason"] = reason
        vfs.write(DBDIR + "/" + name + "/desc", desc_text(m))


def db_write(vfs, meta):
    base = DBDIR + "/" + meta["name"]
    mkdirs(vfs, base, [])
    vfs.write(base + "/desc", desc_text(meta))
    vfs.write(base + "/files", "")
    buf = ""
    for p in meta["dirs"]:
        buf += "d\t" + p + "\n"
    for p, size, s in meta["files"]:
        buf += "f\t" + p + "\t" + str(size) + "\t" + s + "\n"
        if len(buf) > 400:
            vfs.append(base + "/files", buf)
            buf = ""
    if buf != "":
        vfs.append(base + "/files", buf)


def db_remove(vfs, name):
    base = DBDIR + "/" + name
    for f in ("desc", "files"):
        if vfs.exists(base + "/" + f):
            vfs.remove(base + "/" + f)
    if vfs.isdir(base):
        vfs.remove(base)


def requirers(vfs, name, skip=()):
    # installed packages (not in skip) that depend on `name`
    out = []
    for other in db_names(vfs):
        if other == name or other in skip:
            continue
        o = db_read(vfs, other, False)
        if o is not None:
            for d in o["depends"]:
                if split_dep(d)[0] == name:
                    out.append(other)
                    break
    return out


def owner(vfs, path):
    # name of the installed package that owns path (file or directory), or None
    for name in db_names(vfs):
        base = DBDIR + "/" + name + "/files"
        if not vfs.isfile(base):
            continue
        for line in vfs.lines(base):
            f = line.split("\t")
            if len(f) > 1 and f[1] == path:
                return name
    return None


def mkdirs(vfs, path, created):
    # mkdir -p; appends every directory it had to create to `created`
    parts = [p for p in path.split("/") if p != ""]
    cur = ""
    for p in parts:
        cur += "/" + p
        if vfs.exists(cur):
            if not vfs.isdir(cur):
                raise PkgError("not a directory: " + cur)
        else:
            vfs.mkdir(cur)
            created.append(cur)
