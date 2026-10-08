# A84PM: .ar84 package format and install database (library for pacman/makepkg).
#
# A package is one text file (UTF-8, '\n' lines, \ \n \t \r escaped in data):
#   AR84 1
#   name <name>              lowercase letters, digits . _ + -   (<= 24 chars)
#   version <version>        letters, digits . _ +               (<= 16 chars, no '-')
#   desc <escaped text>      optional
#   depends <dep> ...        optional; dep = name or name>=ver (also <= = > <)
#   D<TAB><path>             a directory
#   F<TAB><path><TAB><size><TAB><sum>   a file, followed by its data lines:
#   +<TAB><escaped chunk>    <= 256 chars of the file (file = the chunks in order)
#   END<TAB><entries><TAB><sum>         <entries> = D and F records; <sum> covers every
#                                       line above it. File sums cover the file text.
# sum = "%x-%x" % (b, a) of an Adler-32 style checksum over the characters.
# Installed packages live in /var/lib/pacman/local/<name>/ (desc, files); desc also has
# "reason dep" when the package was only installed to satisfy a dependency.
# The repository index is /var/lib/pacman/sync/repo.db (one line per package:
# name, version, file, depends, desc; rebuilt by pacman -Sy and when stale).
# Changing operations hold /var/lib/pacman/pacman.lock while they run.
from A84FS import VFSError, dpieces, normalize, unesc

MAGIC = "AR84 1"
DBDIR = "/var/lib/pacman/local"
REPO = "/var/cache/pacman/pkg"
LOCK = "/var/lib/pacman/pacman.lock"
SYNCDB = "/var/lib/pacman/sync/repo.db"
CHUNK = 256
MAXENTRIES = 300
MAXFILE = 20000
ROOTS = ("usr", "opt", "etc", "home", "var")
HOMEDIR = ["/home/evo"]        # set from $HOME by the pacman command
DENY_TREES = ("/var/lib/pacman", "/var/cache/pacman")
DENY_FILES = ("/etc/version", "/etc/hostname", "/etc/profile", "/etc/clock",
              "/home/evo/.profile", "/home/evo/.ashrc", "/home/evo/.ash_history")


class PkgError(Exception):
    pass


class Sum:
    def __init__(self):
        self.a = 1
        self.b = 0

    def add(self, s):
        a = self.a
        b = self.b
        for c in s:
            a = (a + ord(c)) % 65521
            b = (b + a) % 65521
        self.a = a
        self.b = b

    def hex(self):
        return "%x-%x" % (self.b, self.a)


def esc(s):
    s = s.replace("\\", "\\\\")
    s = s.replace("\n", "\\n")
    s = s.replace("\t", "\\t")
    return s.replace("\r", "\\r")


def ok_name(n):
    if n == "" or len(n) > 24 or not ("a" <= n[0] <= "z" or "0" <= n[0] <= "9"):
        return False
    for c in n:
        if not ("a" <= c <= "z" or "0" <= c <= "9" or c in "._+-"):
            return False
    return True


def ok_ver(v):
    if v == "" or len(v) > 16:
        return False
    for c in v:
        if not ("a" <= c <= "z" or "A" <= c <= "Z" or "0" <= c <= "9" or c in "._+"):
            return False
    return True


def ok_path(p):
    # absolute, already normalized, under an allowed root, not a protected file
    if p == "" or p[0] != "/" or len(p) > 120 or normalize(p, "/", "/") != p:
        return False
    for c in p:
        if ord(c) < 32:
            return False
    if p.split("/")[1] not in ROOTS or "/" not in p[1:]:
        return False
    if p in DENY_FILES or (p.startswith(HOMEDIR[0] + "/.") and p[len(HOMEDIR[0]) + 2:] in ("profile", "ashrc", "ash_history")):
        return False
    for t in DENY_TREES:
        if p == t or p.startswith(t + "/"):
            return False
    return True


def split_dep(d):
    # "lib>=1.2" -> ("lib", ">=", "1.2"); "lib" -> ("lib", "", "")
    for i in range(len(d)):
        if d[i] in "<>=":
            op = d[i]
            if d[i] != "=" and d[i + 1:i + 2] == "=":
                op += "="
            return d[:i], op, d[i + len(op):]
    return d, "", ""


def ok_dep(d):
    n, op, v = split_dep(d)
    return ok_name(n) and (op == "" or ok_ver(v))


def dep_ok(d, have):
    # does installed version `have` satisfy the dependency token d?
    n, op, v = split_dep(d)
    if op == "":
        return True
    a = vkey(have)
    b = vkey(v)
    if op == ">=":
        return a >= b
    if op == "<=":
        return a <= b
    if op == ">":
        return a > b
    if op == "<":
        return a < b
    return a == b


def vkey(v):
    # sortable version key: numeric parts compare as numbers
    out = []
    for p in v.replace("_", ".").replace("+", ".").split("."):
        if p != "" and p.strip("0123456789") == "":
            out.append((1, int(p), ""))
        else:
            out.append((0, 0, p))
    return out


def records(vfs, path):
    # yields (kind, x, y, z) per line; checks the package sum when END is reached
    total = Sum()
    seen_end = False
    first = True
    for line in vfs.lines(path):
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
            yield "E", f[1], None, None
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
    for p in meta["files"]:
        paths[p[0]] = "F"
    for d in meta["depends"]:
        if not ok_dep(d):
            raise PkgError("bad dependency: " + d[:30])
    if meta["name"] is None:
        raise PkgError("missing name/version")
    return meta
