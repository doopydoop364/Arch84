# A84PI: install / remove operations for pacman (Arch84
# module, lazily loaded). No output here: A84PX prints.
from A84FS import VFSError, unesc
from A84PM import DBDIR, PkgError, Sum, dep_ok, records, scan, split_dep
from A84PD import db_names, db_read, db_remove, db_write, mkdirs, owner, requirers


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
    bad = []
    for dep in meta["depends"]:
        n = split_dep(dep)[0]
        if n == name:
            continue
        have = db_read(vfs, n, False)
        if have is None:
            bad.append(dep)
        elif not dep_ok(dep, have["version"]):
            bad.append(dep + " (installed " + have["version"] + ")")
    if bad:
        raise PkgError("missing dependency: " + ", ".join(bad))


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


def install(vfs, path, reason=None):
    # -> (meta, old version or None); reason "dep" marks a package installed only as
    # a dependency (a reinstall keeps the old reason unless one is given)
    meta = scan(vfs, path)
    old = db_read(vfs, meta["name"])
    check(vfs, meta)
    meta["reason"] = reason or (old["reason"] if old is not None else "explicit")
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


def removal_set(vfs, names, recurse):
    # {name: meta} of everything `pacman -R[s]` would remove; raises if something
    # that stays still needs one of them
    out = {}
    for n in names:
        m = db_read(vfs, n)
        if m is None:
            raise PkgError("target not found: " + n)
        out[n] = m
    if recurse:
        more = True
        while more:
            more = False
            for n in list(out.keys()):
                for d in out[n]["depends"]:
                    dn = split_dep(d)[0]
                    if dn in out:
                        continue
                    m = db_read(vfs, dn)
                    if m is not None and m["reason"] == "dep" and not requirers(vfs, dn, out):
                        out[dn] = m
                        more = True
    for n in out:
        need = requirers(vfs, n, out)
        if need:
            raise PkgError(n + " is required by " + " ".join(need))
    return out


def remove_order(metas):
    # dependents first
    left = list(metas.keys())
    left.sort()
    order = []
    while left:
        for n in left:
            blocked = False
            for o in left:
                if o != n:
                    for d in metas[o]["depends"]:
                        if split_dep(d)[0] == n:
                            blocked = True
            if not blocked:
                order.append(n)
                left.remove(n)
                break
        else:
            order += left           # a dependency cycle: any order will do
            break
    return order


def remove(vfs, name):
    meta = db_read(vfs, name)
    if meta is None:
        raise PkgError("target not found: " + name)
    for p, size, s in meta["files"]:
        if vfs.isfile(p):
            vfs.remove(p)
    for d in deepest_first(meta["dirs"]):
        if vfs.isdir(d) and vfs.listdir(d) == []:
            vfs.remove(d)
    db_remove(vfs, name)
    return meta
