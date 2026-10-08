# A84PI: install / remove operations for pacman (Arch84
# module, lazily loaded). No output here: A84PX prints.
from A84FS import VFSError, unesc
from A84PM import DBDIR, PkgError, Sum, records, scan
from A84PD import db_names, db_read, db_remove, db_write, mkdirs, owner


def check(vfs, meta):
    name = meta["name"]
    for p, size, s in meta["files"]:
        node = vfs.get(p)
        if node is not None:
            if node.is_dir:
                raise PkgError("directory in the way: " + p)
            ow = owner(vfs, p)
            if ow is None:
                raise PkgError("exists in filesystem: " + p)
            if ow != name:
                raise PkgError(p + " is owned by " + ow)
    for d in meta["dirs"]:
        if vfs.exists(d) and not vfs.isdir(d):
            raise PkgError("file in the way: " + d)
    for dep in meta["depends"]:
        if dep != name and not vfs.isdir(DBDIR + "/" + dep):
            raise PkgError("missing dependency: " + dep)


def rollback(vfs, undo, created):
    for i in range(len(undo) - 1, -1, -1):
        u = undo[i]
        try:
            if u[0] == "n":
                vfs.remove(u[1])
            else:
                vfs.put(u[1], u[2])
        except VFSError:
            pass
    for i in range(len(created) - 1, -1, -1):
        try:
            vfs.remove(created[i])
        except VFSError:
            pass


def deepest_first(dirs):
    out = list(dirs)
    out.sort(key=len)
    out.reverse()
    return out


def finish(cur):
    if cur is not None and (cur[4] != cur[1] or cur[3].hex() != cur[2]):
        raise PkgError("file changed while installing: " + cur[0])


def apply(vfs, path):
    undo = []
    created = []
    cur = None
    try:
        for kind, x, y, z in records(vfs, path):
            if kind == "D":
                mkdirs(vfs, x, created)
            elif kind == "F" or kind == "E":
                finish(cur)
                cur = None
                if kind == "F":
                    mkdirs(vfs, x[:x.rfind("/")], created)
                    node = vfs.get(x)
                    if node is None:
                        undo.append(("n", x))
                    else:
                        undo.append(("f", x, node.data))
                    vfs.write(x, "")
                    cur = [x, int(y), z, Sum(), 0]
            elif kind == "+":
                text = unesc(x)
                vfs.append(cur[0], text)
                cur[3].add(text)
                cur[4] += len(text)
    except Exception as e:
        rollback(vfs, undo, created)
        raise PkgError(str(e) + " (rolled back)")
    return undo, created


def install(vfs, path):
    # -> (meta, old version or None)
    meta = scan(vfs, path)
    old = db_read(vfs, meta["name"])
    check(vfs, meta)
    undo, created = apply(vfs, path)
    keep = []
    if old is not None:
        new = {}
        for p, size, s in meta["files"]:
            new[p] = 1
        for p, size, s in old["files"]:
            if p not in new and vfs.isfile(p):
                vfs.remove(p)
        for d in deepest_first(old["dirs"]):
            if vfs.isdir(d):
                if vfs.listdir(d) == [] and d not in meta["dirs"]:
                    vfs.remove(d)
                else:
                    keep.append(d)
    meta["dirs"] = keep + created
    try:
        db_write(vfs, meta)
    except Exception as e:
        rollback(vfs, undo, created)
        db_remove(vfs, meta["name"])
        raise PkgError("cannot write the package database: " + str(e))
    if old is None:
        return meta, None
    return meta, old["version"]


def remove(vfs, name):
    meta = db_read(vfs, name)
    if meta is None:
        raise PkgError("target not found: " + name)
    for other in db_names(vfs):
        if other != name:
            o = db_read(vfs, other)
            if o is not None and name in o["depends"]:
                raise PkgError(name + " is required by " + other)
    for p, size, s in meta["files"]:
        if vfs.isfile(p):
            vfs.remove(p)
    for d in deepest_first(meta["dirs"]):
        if vfs.isdir(d) and vfs.listdir(d) == []:
            vfs.remove(d)
    db_remove(vfs, name)
    return meta
