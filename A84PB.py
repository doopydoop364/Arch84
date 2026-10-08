# A84PB: building packages (makepkg) and the local repository (pacman -S) for
# pacman (Arch84 module, lazily loaded). No output here: A84PX prints.
from A84FS import VFSError, dlen, dpieces, unesc
from A84PM import (CHUNK, MAGIC, REPO, SYNCDB, PkgError, Sum, esc, dep_ok, ok_dep, ok_name, ok_path,
                   ok_ver, split_dep, vkey)
from A84PS import scan
from A84PD import db_names, db_read, mkdirs


def build(vfs, src, name, version, desc, depends):
    # packs the tree under src (whose layout is the target filesystem) into
    # REPO/<name>-<version>.ar84; -> (path, files, bytes)
    if not ok_name(name) or not ok_ver(version):
        raise PkgError("bad package name or version")
    for d in depends:
        if not ok_dep(d):
            raise PkgError("bad dependency: " + d)
    dirs = []
    files = []
    stack = [src]
    base = len(src.rstrip("/"))
    while stack:
        p = stack.pop()
        for n in vfs.listdir(p):
            q = p.rstrip("/") + "/" + n
            rel = q[base:]
            top = rel.count("/") == 1 and vfs.isdir(q)     # /usr, /etc ...: system dirs
            if not ok_path(rel + "/x" if top else rel):
                raise PkgError("path not allowed in a package: " + rel[:40])
            if vfs.isdir(q):
                if not top:
                    dirs.append(rel)
                stack.append(q)
            else:
                files.append((rel, q))
    dirs.sort()
    files.sort()
    if len(dirs) + len(files) > 300:
        raise PkgError("too many entries (limit 300)")
    mkdirs(vfs, REPO, [])
    out = REPO + "/" + name + "-" + version + ".ar84"
    vfs.write(out, "")
    tot = Sum()
    buf = ""
    head = [MAGIC, "name " + name, "version " + version]
    if desc != "":
        head.append("desc " + esc(desc))
    if depends:
        head.append("depends " + " ".join(depends))
    lines = head + ["D\t" + d for d in dirs]
    nbytes = 0
    for line in lines:
        tot.add(line + "\n")
        buf += line + "\n"
        if len(buf) > 400:
            vfs.append(out, buf)
            buf = ""
    for rel, q in files:
        data = vfs._file(q).data
        fs = Sum()
        for piece in dpieces(data):
            fs.add(piece)
        size = dlen(data)
        if size > 20000:
            raise PkgError("file too large (limit 20000 chars): " + rel)
        nbytes += size
        line = "F\t" + rel + "\t" + str(size) + "\t" + fs.hex()
        tot.add(line + "\n")
        buf += line + "\n"
        for piece in dpieces(data):
            for i in range(0, len(piece), CHUNK):
                line = "+\t" + esc(piece[i:i + CHUNK])
                tot.add(line + "\n")
                buf += line + "\n"
                if len(buf) > 400:
                    vfs.append(out, buf)
                    buf = ""
    buf += "END\t" + str(len(dirs) + len(files)) + "\t" + tot.hex() + "\n"
    vfs.append(out, buf)
    if vfs.isfile(SYNCDB):
        vfs.remove(SYNCDB)
    return out, len(files), nbytes


def repo(vfs):
    # [(name, version, path, depends, desc)] for every package of the local repository
    # (NAME-VERSION.ar84 files) and of the flash repositories, from the index when it
    # still matches the directory
    if not vfs.isfile(SYNCDB):
        return sync(vfs)[0]
    files = []
    if vfs.isdir(REPO):
        for f in vfs.listdir(REPO):
            if f.endswith(".ar84"):
                files.append(f)
    rows = []
    nloc = 0
    for line in vfs.lines(SYNCDB):
        f = line.split("\t")
        if len(f) == 5:
            if f[2][:4] == "mod:":
                rows.append((f[0], f[1], f[2], f[3].split(), unesc(f[4])))
            else:
                if f[2] not in files:
                    return sync(vfs)[0]
                nloc += 1
                rows.append((f[0], f[1], REPO + "/" + f[2], f[3].split(), unesc(f[4])))
    if nloc != len(files):
        return sync(vfs)[0]
    return rows


def sync(vfs):
    # rescans the local repository, re-reads the flash repositories and rewrites the
    # index -> (rows, number skipped)
    rows = []
    bad = 0
    if vfs.isdir(REPO):
        for f in vfs.listdir(REPO):
            if not f.endswith(".ar84"):
                continue
            try:
                m = scan(vfs, REPO + "/" + f)
            except (PkgError, VFSError):
                bad += 1
                continue
            if f != m["name"] + "-" + m["version"] + ".ar84":
                bad += 1
                continue
            rows.append((m["name"], m["version"], REPO + "/" + f, m["depends"], m["desc"]))
    frows = []
    import gc
    gc.collect()                             # importing needs a contiguous read buffer
    try:
        __import__("R84REG")                 # the registry exists: read the flash repositories
        import sys
        sys.modules.pop("R84REG", None)
        from A84PL import flash_rows
        frows, fbad = flash_rows()
        bad += fbad
    except ImportError:
        pass
    if not rows and not frows and not vfs.isfile(SYNCDB):
        return rows, bad
    rows += frows
    mkdirs(vfs, SYNCDB[:SYNCDB.rfind("/")], [])
    vfs.write(SYNCDB, "")
    buf = ""
    for n, v, p, d, ds in rows:
        buf += n + "\t" + v + "\t" + (p if p[:4] == "mod:" else p[len(REPO) + 1:]) + "\t" + " ".join(d) + "\t" + esc(ds) + "\n"
        if len(buf) > 400:
            vfs.append(SYNCDB, buf)
            buf = ""
    if buf != "":
        vfs.append(SYNCDB, buf)
    return rows, bad


def newest(vfs, name):
    # (version, path, depends, desc) of the newest repository version, or None
    best = None
    for n, v, p, d, ds in repo(vfs):
        if n == name and (best is None or vkey(v) > vkey(best[0])):
            best = (v, p, d, ds)
    return best


def upgrades(vfs):
    # [(name, installed version, new version, path)] for installed packages
    out = []
    for n in db_names(vfs):
        m = db_read(vfs, n)
        b = newest(vfs, n)
        if m is not None and b is not None and vkey(b[0]) > vkey(m["version"]):
            out.append((n, m["version"], b[0], b[1]))
    return out


def plan(vfs, token, order, seen, depth=0, deps=None):
    # package files to install for `token` (name or name>=ver), dependencies first;
    # paths added only as dependencies are also appended to `deps`
    if deps is None:
        deps = []
    name = split_dep(token)[0]
    if depth > 8 or name in seen:
        raise PkgError("dependency loop at " + name)
    have = db_read(vfs, name, False)
    if have is not None and dep_ok(token, have["version"]):
        return
    best = newest(vfs, name)
    if best is None:
        raise PkgError("target not found: " + name)
    if not dep_ok(token, best[0]):
        raise PkgError("cannot satisfy " + token + " (repository has " + best[0] + ")")
    seen.append(name)
    for dep in best[2]:
        plan(vfs, dep, order, seen, depth + 1, deps)
    seen.pop()
    if best[1] not in order:
        order.append(best[1])
        if depth > 0 and have is None:
            deps.append(best[1])
