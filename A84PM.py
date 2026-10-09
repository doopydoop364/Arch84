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
# name, version, file, depends, desc; rebuilt by pacman -Sy and when stale). Packages that
# only exist on the mirror have the file "net:<file>"; the mirror's own index is
# /var/lib/pacman/sync/remote.db ("ARCH84-REPO 1", then name, version, file, size, sum,
# depends, escaped desc per line, tab separated), see A84PN and docs/NETWORK.md.
# Changing operations hold /var/lib/pacman/pacman.lock while they run.
from A84FS import normalize

MAGIC = "AR84 1"
DBDIR = "/var/lib/pacman/local"
REPO = "/var/cache/pacman/pkg"
LOCK = "/var/lib/pacman/pacman.lock"
SYNCDB = "/var/lib/pacman/sync/repo.db"
REMOTEDB = "/var/lib/pacman/sync/remote.db"      # the mirror's index, downloaded by pacman -Sy (A84PN)
MIRRORCONF = "/etc/pacman.d/mirror"               # optional: one line, the mirror's base URL
MIRROR = "https://doopydoop364.github.io/arch84/pkgs"
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
