# A84PB: building packages (makepkg) and the local repository (pacman -S) for
# pacman (Arch84 module, lazily loaded). No output here: A84PX prints.
from A84FS import dlen, dpieces
from A84PM import (CHUNK, DBDIR, MAGIC, REPO, PkgError, Sum, esc, ok_name, ok_path,
                   ok_ver, scan, vkey)
from A84PD import mkdirs


def build(vfs, src, name, version, desc, depends):
    # packs the tree under src (whose layout is the target filesystem) into
    # REPO/<name>-<version>.ar84; -> (path, files, bytes)
    if not ok_name(name) or not ok_ver(version):
        raise PkgError("bad package name or version")
    for d in depends:
        if not ok_name(d):
            raise PkgError("bad dependency name: " + d)
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
    return out, len(files), nbytes


def repo(vfs):
    # [(name, version, path)] for every NAME-VERSION.ar84 in the local repository
    out = []
    if vfs.isdir(REPO):
        for f in vfs.listdir(REPO):
            if f.endswith(".ar84") and "-" in f:
                n, v = f[:-5].rsplit("-", 1)
                if ok_name(n) and ok_ver(v):
                    out.append((n, v, REPO + "/" + f))
    return out


def plan(vfs, name, order, seen, depth=0):
    # package files to install for `name`, dependencies first
    if depth > 8 or name in seen:
        raise PkgError("dependency loop at " + name)
    if vfs.isdir(DBDIR + "/" + name):
        return
    best = None
    for n, v, p in repo(vfs):
        if n == name and (best is None or vkey(v) > vkey(best[0])):
            best = (v, p)
    if best is None:
        raise PkgError("target not found: " + name)
    seen.append(name)
    for dep in scan(vfs, best[1])["depends"]:
        plan(vfs, dep, order, seen, depth + 1)
    seen.pop()
    if best[1] not in order:
        order.append(best[1])
