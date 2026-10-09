# A84PD: installed-package database for pacman (Arch84 module, lazily loaded).
# One file per package, /var/lib/pacman/local/<name> (one tree node; it is kept in calculator
# lists, see A84BL, so the heap holds only a reference):
#   name .. / version .. / desc .. / depends .. / reason dep     (the description lines)
#   %files
#   d<TAB>dir  |  f<TAB>path<TAB>size<TAB>sum                    (what the package installed)
# Older installs have a DIRECTORY /var/lib/pacman/local/<name>/ with the files desc and files;
# those are still read, removed and replaced (a directory node costs far more than a file).
from A84FS import VFSError, unesc
from A84PM import DBDIR, REMOTEDB, PkgError, esc, ok_dep, ok_name, ok_ver, split_dep


def db_names(vfs):
    if not vfs.isdir(DBDIR):
        return []
    return vfs.listdir(DBDIR)


def remote_rows(vfs):
    # yields (name, version, file, size, sum, depends list, desc) of the downloaded mirror index, one
    # row at a time (the index can be large and lives in lists: nothing holds all the rows);
    # lines that do not check out are skipped
    if not vfs.isfile(REMOTEDB):
        return
    first = True
    for line in vfs.lines(REMOTEDB):
        if first:
            first = False
            if line != "ARCH84-REPO 1":
                return
            continue
        f = line.split("\t")
        if len(f) != 7 or not ok_name(f[0]) or not ok_ver(f[1]) or f[2] != f[0] + "-" + f[1] + ".ar84":
            continue
        try:
            size = int(f[3])
        except ValueError:
            continue
        deps = f[5].split()
        ok = True
        for x in deps:
            if not ok_dep(x):
                ok = False
        if ok:
            yield (f[0], f[1], f[2], size, f[4], deps, unesc(f[6]))


def db_lines(vfs, name):
    # the lines of the package's database entry, whichever layout it has (a directory: desc,
    # then "%files", then files); None when there is no such package
    base = DBDIR + "/" + name
    if vfs.isfile(base):
        return vfs.lines(base)
    if vfs.isdir(base):
        return old_lines(vfs, base)
    return None


def old_lines(vfs, base):
    if vfs.isfile(base + "/desc"):
        for line in vfs.lines(base + "/desc"):
            yield line
    yield "%files"
    if vfs.isfile(base + "/files"):
        for line in vfs.lines(base + "/files"):
            yield line


def db_read(vfs, name, full=True):
    # -> meta with dirs / files of the installed package, or None
    # (full=False stops at the file list: much cheaper)
    lines = db_lines(vfs, name)
    if lines is None:
        return None
    meta = {"name": name, "version": "?", "desc": "", "depends": [], "dirs": [], "files": [], "reason": "explicit"}
    files = False
    try:
        for line in lines:
            if files:
                f = line.split("\t")
                if f[0] == "d" and len(f) == 2:
                    meta["dirs"].append(f[1])
                elif f[0] == "f" and len(f) == 4:
                    meta["files"].append((f[1], int(f[2]), f[3]))
                continue
            if line == "%files":
                if not full:
                    return meta
                files = True
                continue
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
    m = db_read(vfs, name)
    if m is not None and m["reason"] != reason:
        m["reason"] = reason
        db_write(vfs, m)


def db_write(vfs, meta):
    # writes (or replaces) the package's entry as one file
    base = DBDIR + "/" + meta["name"]
    mkdirs(vfs, DBDIR, [])
    if vfs.isdir(base):
        db_remove(vfs, meta["name"])                        # the older directory layout goes away first
    vfs.write(base, desc_text(meta) + "%files\n")
    buf = ""
    for p in meta["dirs"]:
        buf += "d\t" + p + "\n"
    for p, size, s in meta["files"]:
        buf += "f\t" + p + "\t" + str(size) + "\t" + s + "\n"
        if len(buf) > 400:
            vfs.append(base, buf)
            buf = ""
    if buf != "":
        vfs.append(base, buf)
    vfs.externalize(base, 120)                              # the entry lives in lists, not the heap


def db_remove(vfs, name):
    base = DBDIR + "/" + name
    if vfs.isdir(base):
        for f in ("desc", "files"):
            if vfs.exists(base + "/" + f):
                vfs.remove(base + "/" + f)
    if vfs.exists(base):
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
        lines = db_lines(vfs, name)
        files = False
        for line in lines:
            if line == "%files":
                files = True
                continue
            if files:
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
