# A84PS: reading .ar84 packages - record parser and validator (library for pacman,
# lazily loaded). Format: see A84PM.
from A84FS import dpieces, unesc
from A84PM import (MAGIC, MAXENTRIES, MAXFILE, PkgError, Sum, ok_dep, ok_name, ok_path, ok_ver)

MAX_RECORD = 1024


def bounded_lines(pieces):
    # Avoid assembling an unbounded line before the package parser can reject it.
    carry = ""
    for piece in pieces:
        pos = 0
        while pos < len(piece):
            end = piece.find("\n", pos)
            if end < 0:
                if len(carry) + len(piece) - pos > MAX_RECORD:
                    raise PkgError("package record too long")
                carry += piece[pos:]
                break
            if len(carry) + end - pos > MAX_RECORD:
                raise PkgError("package record too long")
            yield carry + piece[pos:end]
            carry = ""
            pos = end + 1
    if carry:
        yield carry


def records(vfs, path):
    # yields (kind, x, y, z) per line; checks the package sum when END is reached
    total = Sum()
    seen_end = False
    first = True
    if path[:4] == "mod:":
        from A84PL import flash_lines
        src = flash_lines(path)
    elif hasattr(vfs, "_file"):
        src = bounded_lines(dpieces(vfs._file(path).data))
    else:
        src = vfs.lines(path)       # desktop repository builders supply a text view
    for line in src:
        if len(line) > MAX_RECORD:
            raise PkgError("package record too long")
        if seen_end:
            raise PkgError("data after END")
        if first:
            if line != MAGIC:
                raise PkgError("not an .ar84 package")
            first = False
            total.add(line + "\n")
            continue
        f = line.split("\t")
        k = f[0]
        if k == "END":
            if len(f) != 3:
                raise PkgError("bad END record")
            if f[2] != total.hex():
                raise PkgError("checksum mismatch (damaged package)")
            seen_end = True
            yield "E", f[1], None, f[2]
            continue
        total.add(line + "\n")
        if k == "D" and len(f) == 2:
            yield "D", f[1], None, None
        elif k == "F" and len(f) == 4:
            yield "F", f[1], f[2], f[3]
        elif k == "+" and len(f) == 2:
            yield "+", f[1], None, None
        else:
            sp = line.find(" ")
            if sp < 0 or line[:sp] not in ("name", "version", "desc", "depends"):
                raise PkgError("bad record: " + line[:20])
            yield "H", line[:sp], line[sp + 1:], None
    if first:
        raise PkgError("empty package file")
    if not seen_end:
        raise PkgError("truncated package (no END)")


def scan(vfs, path):
    # validates the whole package; returns meta
    meta = {"name": None, "version": None, "desc": "", "depends": [], "dirs": [], "files": []}
    paths = {}
    cur = None          # [path, size, sum, Sum, got]
    entries = 0
    for kind, x, y, z in records(vfs, path):
        if kind == "H":
            if entries:
                raise PkgError("header after entries")
            if x == "desc":
                meta["desc"] = unesc(y)
            elif x == "depends":
                meta["depends"] = y.split()
            else:
                meta[x] = y
            continue
        if kind in "DF" or kind == "E":
            if cur is not None:
                if cur[4] != cur[1]:
                    raise PkgError("size mismatch: " + cur[0])
                if cur[3].hex() != cur[2]:
                    raise PkgError("file checksum mismatch: " + cur[0])
                meta["files"].append((cur[0], cur[1], cur[2]))
                cur = None
        if kind == "D" or kind == "F":
            if meta["name"] is None or meta["version"] is None:
                raise PkgError("missing name/version")
            if not ok_name(meta["name"]):
                raise PkgError("bad package name")
            if not ok_ver(meta["version"]):
                raise PkgError("bad package version")
            entries += 1
            if entries > MAXENTRIES:
                raise PkgError("too many entries")
            if not ok_path(x):
                raise PkgError("path not allowed: " + x[:40])
            if x in paths:
                raise PkgError("duplicate path: " + x[:40])
            if x == path:
                raise PkgError("package contains itself")
            paths[x] = kind
            par = x[:x.rfind("/")]
            while par != "":
                if paths.get(par) == "F":
                    raise PkgError("file used as directory: " + par[:40])
                par = par[:par.rfind("/")]
            if kind == "D":
                meta["dirs"].append(x)
            else:
                try:
                    size = int(y)
                except ValueError:
                    raise PkgError("bad size for " + x[:40])
                if size < 0 or size > MAXFILE:
                    raise PkgError("file too large: " + x[:40])
                cur = [x, size, z, Sum(), 0]
        elif kind == "+":
            if cur is None:
                raise PkgError("data without a file")
            try:
                text = unesc(x)
            except ValueError:
                raise PkgError("bad escape in data")
            cur[3].add(text)
            cur[4] += len(text)
            if cur[4] > cur[1]:
                raise PkgError("size mismatch: " + cur[0])
        elif kind == "E":
            try:
                n = int(x)
            except ValueError:
                raise PkgError("bad END record")
            if n != entries:
                raise PkgError("entry count mismatch")
            meta["_archive_sum"] = z
    for p in meta["files"]:
        paths[p[0]] = "F"
    for d in meta["depends"]:
        if not ok_dep(d):
            raise PkgError("bad dependency: " + d[:30])
    if meta["name"] is None:
        raise PkgError("missing name/version")
    return meta
