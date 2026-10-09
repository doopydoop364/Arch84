# A84PI: install / remove operations for pacman (Arch84
# module, lazily loaded). No output here: A84PX prints.
from A84FS import VFSError, unesc
from A84PM import PkgError, Sum, dep_ok, split_dep
from A84PS import records, scan
from A84PD import db_read, db_remove, db_write, mkdirs, owner, requirers


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


def deepest_first(dirs):
    out = list(dirs)
    out.sort(key=len)
    out.reverse()
    return out


def finish(vfs, cur):
    if cur is not None and (cur[4] != cur[1] or cur[3].hex() != cur[2]):
        raise PkgError("file changed while installing: " + cur[0])
    if cur is not None and cur[5] is not None:
        ext = cur[5].finish()
        vfs.put(cur[0], ext)
        vfs.ext = True


def apply(vfs, path, meta):
    created = []
    cur = None
    for kind, x, y, z in records(vfs, path):
        if kind == "D":
            mkdirs(vfs, x, created)
        elif kind == "F" or kind == "E":
            finish(vfs, cur)
            cur = None
            if kind == "E" and z != meta["_archive_sum"]:
                raise PkgError("package changed between validation and install")
            if kind == "F":
                mkdirs(vfs, x[:x.rfind("/")], created)
                vfs.write(x, "")
                writer = None
                if int(y) >= 1024 and vfs.store is not None:
                    from A84BM import BlobWriter
                    writer = BlobWriter(vfs)
                    vfs._tx.add_blob(writer.ext)
                cur = [x, int(y), z, Sum(), 0, writer]
        elif kind == "+":
            text = unesc(x)
            if cur[5] is None:
                vfs.append(cur[0], text)
            else:
                cur[5].feed(text)
            cur[3].add(text)
            cur[4] += len(text)
    return created


def install(vfs, path, reason=None):
    # -> (meta, old version or None); reason "dep" marks a package installed only as
    # a dependency (a reinstall keeps the old reason unless one is given)
    meta = scan(vfs, path)
    old = db_read(vfs, meta["name"])
    check(vfs, meta)
    meta["reason"] = reason or (old["reason"] if old is not None else "explicit")
    tx = vfs.begin_transaction()
    try:
        created = apply(vfs, path, meta)
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
        db_write(vfs, meta)
        tx.commit()
    except Exception as e:
        tx.rollback()
        raise PkgError(str(e) + " (rolled back)")
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
    tx = vfs.begin_transaction()
    try:
        for p, size, s in meta["files"]:
            if vfs.isfile(p):
                vfs.remove(p)
        for d in deepest_first(meta["dirs"]):
            if vfs.isdir(d) and vfs.listdir(d) == []:
                vfs.remove(d)
        db_remove(vfs, name)
        tx.commit()
    except Exception as e:
        tx.rollback()
        raise PkgError(str(e) + " (rolled back)")
    return meta
