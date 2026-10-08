# A84FS: paths, VFS, old v1 text codec (Arch84 module 1/10)

# Only storage code here touches ti_system (store_list/recall_list).

VERSION = "0.0.6-dev"
FS_VERSION = 1
HOME = "/home/evo"
ERR = "\x01"   # prefix of error lines sent to the terminal (drawn red)

try:
    import ti_system as _ti
except ImportError:
    _ti = None
try:
    import time as _time
except ImportError:
    _time = None


def mono_s():
    # whole seconds from a monotonic counter (calculator start), or None
    if _time is None:
        return None
    if hasattr(_time, "monotonic"):
        return int(_time.monotonic())
    n = now_ms()
    if n is None:
        return None
    return n // 1000


def ms_since(t0):
    n = now_ms()
    if n is None or t0 is None:
        return None
    if hasattr(_time, "ticks_diff"):
        return _time.ticks_diff(n, t0)
    return n - t0


def now_ms():
    # milliseconds from the best clock available, or None if there is none
    if _time is None:
        return None
    if hasattr(_time, "ticks_ms"):
        return _time.ticks_ms()
    if hasattr(_time, "time"):
        return int(_time.time() * 1000)
    return None


# ---------------------------------------------------------------- paths

def normalize(path, cwd="/", home=HOME):
    if path == "":
        return cwd
    if path == "~" or path.startswith("~/"):
        path = home + path[1:]
    if not path.startswith("/"):
        if cwd == "/":
            path = "/" + path
        else:
            path = cwd + "/" + path
    parts = []
    for part in path.split("/"):
        if part == "" or part == ".":
            continue
        if part == "..":
            if parts:
                parts.pop()
        else:
            parts.append(part)
    return "/" + "/".join(parts)


def basename(path):
    i = path.rfind("/")
    return path[i + 1:]


# ------------------------------------------------------------------ VFS

class VFSError(Exception):
    pass


# ---- file data
# A file's `data` is a str when it has <= BIGMIN chars, otherwise a list of
# str pieces of exactly SPLIT chars (the last one 1..SPLIT). The shape is
# canonical (equal text -> equal representation, so == works on data) and
# nothing on the load/save/copy/append/stream paths ever joins a big file into
# one string: the calculator heap fragments, and a single 5 KB string failed.
MAXNAME = 255   # bytes of UTF-8 per path component (the saved format's limit)
SPLIT = 512     # small, uniform pieces: they fit the holes a fragmented heap has
BIGMIN = 1024


def dnew(s):
    # canonical data for the text s
    if len(s) <= BIGMIN:
        return s
    out = []
    for i in range(0, len(s), SPLIT):
        out.append(s[i:i + SPLIT])
    return out


def dlen(d):
    if isinstance(d, str):
        return len(d)
    n = 0
    for p in d:
        n += len(p)
    return n


def dtext(d):
    # the whole text as one str (needs one contiguous block: avoid for big files)
    if isinstance(d, str):
        return d
    return "".join(d)


def dpieces(d):
    # snapshot of the pieces: safe to iterate while the file is being appended to
    if isinstance(d, str):
        if d == "":
            return []
        return [d]
    return list(d)


def dappend(d, s):
    if s == "":
        return d
    if isinstance(d, str):
        if len(d) + len(s) <= BIGMIN:
            return d + s
        return dnew(d + s)
    last = d[-1]
    room = SPLIT - len(last)
    if room > 0:
        d[-1] = last + s[:room]
        s = s[room:]
    while s != "":
        d.append(s[:SPLIT])
        s = s[SPLIT:]
    return d


def dchunks(text_iter):
    # canonical data from an iterable of str pieces (any sizes), never
    # holding more than about one SPLIT plus the finished pieces
    out = []
    buf = ""
    total = 0
    for p in text_iter:
        total += len(p)
        buf += p
        while len(buf) >= SPLIT:
            out.append(buf[:SPLIT])
            buf = buf[SPLIT:]
    if total <= BIGMIN:
        return "".join(out) + buf
    if buf != "":
        out.append(buf)
    return out


def iter_lines(d):
    # lines without their newline; a missing final newline still gives a line
    # and a trailing newline gives no empty extra line. Works piece by piece.
    carry = ""
    for ch in dpieces(d):
        parts = (carry + ch).split("\n")
        carry = parts.pop()
        for p in parts:
            yield p
    if carry != "":
        yield carry


class Node:
    def __init__(self, is_dir, data=""):
        self.is_dir = is_dir
        self.data = data
        if is_dir:
            self.children = {}
        else:
            self.children = None


DEFAULT_DIRS = ["/bin", "/boot", "/dev", "/etc", "/home", "/home/evo",
                "/proc", "/root", "/run", "/tmp", "/usr", "/usr/bin",
                "/usr/lib", "/usr/share", "/var", "/var/cache",
                "/var/lib", "/var/log"]
# /dev and /proc stay empty until they become generated (never persisted
# content); the startup files below are seeded only on a brand-new filesystem
PROFILE = ("# /etc/profile\n"
           "export PATH=/usr/local/bin:/usr/bin:/bin\n"
           "export SHELL=/bin/ash\n")
USER_PROFILE = "# ~/.profile\n"
ASHRC = "# ~/.ashrc\nalias ll='ls -a'\n"


class VFS:
    def __init__(self):
        self.root = Node(True)
        self.dirty = False

    # paths passed in must already be normalized and absolute

    def get(self, path):
        node = self.root
        for part in path.split("/"):
            if part == "":
                continue
            if not node.is_dir or part not in node.children:
                return None
            node = node.children[part]
        return node

    def exists(self, path):
        return self.get(path) is not None

    def isdir(self, path):
        node = self.get(path)
        return node is not None and node.is_dir

    def isfile(self, path):
        node = self.get(path)
        return node is not None and not node.is_dir

    def _parent(self, path):
        parts = [p for p in path.split("/") if p != ""]
        if not parts:
            raise VFSError("Invalid argument")
        node = self.root
        for part in parts[:-1]:
            if part not in node.children:
                raise VFSError("No such file or directory")
            node = node.children[part]
            if not node.is_dir:
                raise VFSError("Not a directory")
        name = parts[-1]
        if len(name) > 63 and len(name.encode()) > MAXNAME:
            # the saved format limits a name to 255 UTF-8 bytes; accepting a
            # longer one made every later sync fail
            raise VFSError("File name too long")
        return node, name

    def mkdir(self, path):
        if path == "/":
            raise VFSError("File exists")
        parent, name = self._parent(path)
        if name in parent.children:
            raise VFSError("File exists")
        parent.children[name] = Node(True)
        self.dirty = True

    def touch(self, path):
        parent, name = self._parent(path)
        if name not in parent.children:
            parent.children[name] = Node(False)
            self.dirty = True

    def write(self, path, data):
        parent, name = self._parent(path)
        node = parent.children.get(name)
        if node is None:
            parent.children[name] = Node(False, dnew(data))
        elif node.is_dir:
            raise VFSError("Is a directory")
        else:
            node.data = dnew(data)
        self.dirty = True

    def put(self, path, data):
        # replace a file's contents with data that is already canonical (dnew/dchunks)
        parent, name = self._parent(path)
        node = parent.children.get(name)
        if node is None:
            parent.children[name] = Node(False, data)
        elif node.is_dir:
            raise VFSError("Is a directory")
        else:
            node.data = data
        self.dirty = True

    def append(self, path, data):
        node = self.get(path)
        if node is None:
            self.write(path, data)
        elif node.is_dir:
            raise VFSError("Is a directory")
        else:
            node.data = dappend(node.data, data)
            self.dirty = True

    def _file(self, path):
        node = self.get(path)
        if node is None:
            raise VFSError("No such file or directory")
        if node.is_dir:
            raise VFSError("Is a directory")
        return node

    def read(self, path):
        return dtext(self._file(path).data)

    def size(self, path):
        return dlen(self._file(path).data)

    def lines(self, path):
        # generator of lines; errors are raised now, not at the first next()
        return iter_lines(self._file(path).data)

    def copyfile(self, src, dst):
        # pieces are immutable strings, so a copy shares them: a 100 KB file
        # costs one small list, not another 100 KB
        d = self._file(src).data
        if not isinstance(d, str):
            d = list(d)
        parent, name = self._parent(dst)
        node = parent.children.get(name)
        if node is None:
            parent.children[name] = Node(False, d)
        elif node.is_dir:
            raise VFSError("Is a directory")
        else:
            node.data = d
        self.dirty = True

    def listdir(self, path):
        node = self.get(path)
        if node is None:
            raise VFSError("No such file or directory")
        if not node.is_dir:
            raise VFSError("Not a directory")
        names = list(node.children.keys())
        names.sort()
        return names

    def remove(self, path):
        if path == "/":
            raise VFSError("Device or resource busy")
        parent, name = self._parent(path)
        node = parent.children.get(name)
        if node is None:
            raise VFSError("No such file or directory")
        if node.is_dir and node.children:
            raise VFSError("Directory not empty")
        del parent.children[name]
        self.dirty = True

    def rename(self, src, dst):
        if src == "/":
            raise VFSError("Device or resource busy")
        if src == dst:
            return
        if dst.startswith(src + "/"):
            raise VFSError("Invalid argument")
        sparent, sname = self._parent(src)
        node = sparent.children.get(sname)
        if node is None:
            raise VFSError("No such file or directory")
        dparent, dname = self._parent(dst)
        old = dparent.children.get(dname)
        if old is not None:
            if old.is_dir:
                if not node.is_dir:
                    raise VFSError("Is a directory")
                if old.children:
                    raise VFSError("Directory not empty")
            elif node.is_dir:
                raise VFSError("Not a directory")
        del sparent.children[sname]
        dparent.children[dname] = node
        self.dirty = True

    def reset_default(self):
        self.root = Node(True)
        for d in DEFAULT_DIRS:
            self.mkdir(d)
        self.write("/etc/hostname", "arch84\n")
        self.write("/etc/version", VERSION + "\n")
        self.write("/etc/profile", PROFILE)
        self.write(HOME + "/.profile", USER_PROFILE)
        self.write(HOME + "/.ashrc", ASHRC)
        self.dirty = True

    def count(self):
        n = 0
        stack = [self.root]
        while stack:
            node = stack.pop()
            n += 1
            if node.is_dir:
                stack.extend(node.children.values())
        return n


# ------------------------------------------------------------- fs codec
# Text format (one record per line, fields separated by TAB):
#   A84FS<version>
#   D<TAB>/path
#   F<TAB>/path<TAB>escaped-data      (escapes: \\ \n \t \r)
#   END

def unesc(s):
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            i += 1
            if i >= n:
                raise ValueError("bad escape at end")
            d = s[i]
            if d == "n":
                out.append("\n")
            elif d == "t":
                out.append("\t")
            elif d == "r":
                out.append("\r")
            elif d == "\\":
                out.append("\\")
            else:
                raise ValueError("bad escape")
        else:
            out.append(c)
        i += 1
    return "".join(out)


def decode_fs(text):
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines or not lines[0].startswith("A84FS"):
        raise ValueError("bad header")
    if lines[0] != "A84FS" + str(FS_VERSION):
        raise ValueError("unsupported fs version " + lines[0][5:])
    if lines[-1] != "END":
        raise ValueError("missing END (truncated)")
    vfs = VFS()
    for line in lines[1:-1]:
        f = line.split("\t")
        try:
            if f[0] == "D" and len(f) == 2:
                path = unesc(f[1])
                _check_path(path)
                vfs.mkdir(path)
            elif f[0] == "F" and len(f) == 3:
                path = unesc(f[1])
                _check_path(path)
                if vfs.exists(path):
                    raise ValueError("duplicate " + path)
                vfs.write(path, unesc(f[2]))
            else:
                raise ValueError("bad record")
        except VFSError as e:
            raise ValueError("bad tree: " + str(e))
    vfs.dirty = False
    return vfs


def _check_path(path):
    if path == "/" or normalize(path, "/", "/") != path:
        raise ValueError("bad path " + path)


# ------------------------------------------------------ storage backends

class StorageError(Exception):
    pass
