# A84CZ: filesystem codec v2 (Arch84 module 2/10)
#
# VFS -> records (tree + only what differs from the frozen factory image)
#     -> frames of <= 2048 raw bytes, each LZSS-compressed when that is smaller
#     -> a byte stream that A84ST packs into calculator lists.
# Everything works in small pieces: the calculator heap fails on single
# allocations of about 8 KB, so nothing here builds a whole-filesystem
# string or list.
#
# Record stream (before framing):  b"R2" <factory version>, then records
#   D <parent dir idx> <name>               new directory (gets the next index)
#   F <parent dir idx> <name> <data>        file created or overwritten
#   X <parent dir idx> <name>               child removed (file or directory)
#   E <record count>                        end marker
# varint = LEB128; name/data are UTF-8 with a varint byte length.
# Only directories have indexes: 0 = root, 1..18 = FACTORY1_DIRS in order,
# then new directories in record order. Files are never referenced.
#
# FACTORY1_* is FROZEN. Saves made with factory 1 rebuild their defaults from
# it, so editing it would silently corrupt old saves. To change the shipped
# defaults, add FACTORY2 and keep FACTORY1; test_arch84.py pins the hash.
from A84FS import *

CHUNK = 2048
FRAME_HDR = 5
MAXNAME = 255
MAXDATA = 1048576
FACTORY_VER = 1

FACTORY1_DIRS = ("/bin", "/boot", "/dev", "/etc", "/home", "/home/evo",
                 "/proc", "/root", "/run", "/tmp", "/usr", "/usr/bin",
                 "/usr/lib", "/usr/share", "/var", "/var/cache",
                 "/var/lib", "/var/log")
FACTORY1_FILES = (
    ("/etc/hostname", "arch84\n"),
    ("/etc/profile", "# /etc/profile\nexport PATH=/usr/local/bin:/usr/bin:/bin\n"
                     "export SHELL=/bin/ash\n"),
    ("/home/evo/.profile", "# ~/.profile\n"),
    ("/home/evo/.ashrc", "# ~/.ashrc\nalias ll='ls -a'\n"),
)
# /etc/version is not part of the diff: it always holds the running VERSION.
VERSION_FILE = "/etc/version"


def factory_vfs(ver):
    if ver != 1:
        raise ValueError("unknown factory version " + str(ver))
    v = VFS()
    for d in FACTORY1_DIRS:
        v.mkdir(d)
    for p, data in FACTORY1_FILES:
        v.write(p, data)
    v.write(VERSION_FILE, VERSION + "\n")
    v.dirty = False
    return v


# ------------------------------------------------------------------ LZSS
# groups of 8 items behind a control byte (bit set = literal byte, clear =
# 2-byte match: 12-bit distance-1, 4-bit length-3)

def lz_compress(d):
    n = len(d)
    out = bytearray()
    idx = {}
    i = 0
    pos = 0
    ctl = 0
    nbit = 0
    while i < n:
        if nbit == 0:
            pos = len(out)
            out.append(0)
            ctl = 0
        ln = 0
        off = 0
        if i + 2 < n:
            j = idx.get((d[i] << 16) | (d[i + 1] << 8) | d[i + 2], -1)
            if j >= 0 and i - j <= 4096:
                ln = 3
                while ln < 18 and i + ln < n and d[j + ln] == d[i + ln]:
                    ln += 1
                off = i - j
        if ln >= 3:
            v = off - 1
            out.append(v & 255)
            out.append(((v >> 8) << 4) | (ln - 3))
            step = ln
        else:
            ctl |= 1 << nbit
            out.append(d[i])
            step = 1
        for p in range(i, i + step):
            if p + 2 < n:
                idx[(d[p] << 16) | (d[p + 1] << 8) | d[p + 2]] = p
        i += step
        nbit += 1
        if nbit == 8:
            out[pos] = ctl
            nbit = 0
    if nbit:
        out[pos] = ctl
    return bytes(out)


def lz_decompress(c, rawlen):
    out = bytearray(rawlen)     # pre-sized: no growth/realloc churn on a fragmented heap
    o = 0
    i = 0
    n = len(c)
    while o < rawlen:
        if i >= n:
            raise ValueError("lz: truncated")
        ctl = c[i]
        i += 1
        for b in range(8):
            if o >= rawlen:
                break
            if ctl & (1 << b):
                if i >= n:
                    raise ValueError("lz: truncated")
                out[o] = c[i]
                o += 1
                i += 1
            else:
                if i + 1 >= n:
                    raise ValueError("lz: truncated")
                v = c[i] | ((c[i + 1] >> 4) << 8)
                ln = (c[i + 1] & 15) + 3
                i += 2
                s = o - (v + 1)
                if s < 0:
                    raise ValueError("lz: bad offset")
                if o + ln > rawlen:
                    raise ValueError("lz: length mismatch")
                for k in range(ln):
                    out[o + k] = out[s + k]
                o += ln
    return bytes(out)


def make_frame(raw, stats):
    # frame = mode(1) rawlen(2) paylen(2) payload; mode 1 = LZSS, 0 = raw
    payload = raw
    mode = 0
    try:
        c = lz_compress(raw)
        if len(c) < len(raw):
            payload = c
            mode = 1
    except MemoryError:
        pass            # a sync must not fail just because the hash dict did not fit
    n = len(raw)
    m = len(payload)
    fr = bytes([mode, n >> 8, n & 255, m >> 8, m & 255]) + payload
    if stats is not None:
        stats[0] += n
        stats[1] += len(fr)
    return fr


# ---------------------------------------------------------------- writer

def put_varint(buf, n):
    while n >= 128:
        buf.append((n & 127) | 128)
        n >>= 7
    buf.append(n)


class Out:
    def __init__(self, stats):
        self.buf = bytearray()
        self.stats = stats
        self.count = 0

    def frames(self, final):
        buf = self.buf
        n = len(buf)
        off = 0
        out = []
        while n - off >= CHUNK or (final and n - off > 0):
            take = n - off
            if take > CHUNK:
                take = CHUNK
            out.append(make_frame(bytes(buf[off:off + take]), self.stats))
            off += take
        if off:
            self.buf = buf[off:]
        return out


def rec_head(out, t, parent, name):
    nb = name.encode()
    out.buf.append(t)
    put_varint(out.buf, parent)
    put_varint(out.buf, len(nb))
    out.buf.extend(nb)
    out.count += 1


def slices(pieces):
    # <= 1 KB slices of characters (never splits a UTF-8 character)
    for p in pieces:
        if len(p) <= 1024:
            yield p
        else:
            for i in range(0, len(p), 1024):
                yield p[i:i + 1024]


def rec_file(out, parent, name, data):
    # data is a str or a list of pieces (A84FS); it is encoded slice by slice,
    # never joined. The byte length precedes the data, so it is summed first.
    rec_head(out, 70, parent, name)
    pieces = dpieces(data)
    total = 0
    for sl in slices(pieces):
        total += len(sl.encode())
    put_varint(out.buf, total)
    for sl in slices(pieces):
        out.buf.extend(sl.encode())
        if len(out.buf) >= CHUNK:
            for fr in out.frames(False):
                yield fr


def fs_stream(vfs, stats=None):
    # generator of frames (bytes). stats, if given, becomes [raw, stored].
    fac = factory_vfs(FACTORY_VER)
    fidx = {"/": 0}
    for k in range(len(FACTORY1_DIRS)):
        fidx[FACTORY1_DIRS[k]] = k + 1
    nxt = len(FACTORY1_DIRS) + 1
    out = Out(stats)
    out.buf.extend(b"R2")
    out.buf.append(FACTORY_VER)
    stack = [("/", vfs.root, 0)]
    while stack:
        path, node, ix = stack.pop()
        fnode = fac.get(path)
        if fnode is not None and not fnode.is_dir:
            fnode = None
        if fnode is not None:
            fnames = list(fnode.children.keys())
            fnames.sort()
            for name in fnames:
                ac = node.children.get(name)
                if ac is None or ac.is_dir != fnode.children[name].is_dir:
                    rec_head(out, 88, ix, name)
        names = list(node.children.keys())
        names.sort()
        subs = []
        for name in names:
            ch = node.children[name]
            if path == "/":
                cpath = "/" + name
            else:
                cpath = path + "/" + name
            fc = None
            if fnode is not None:
                fc = fnode.children.get(name)
            if ch.is_dir:
                if fc is not None and fc.is_dir:
                    cix = fidx[cpath]
                else:
                    rec_head(out, 68, ix, name)
                    cix = nxt
                    nxt += 1
                subs.append((cpath, ch, cix))
            elif cpath == VERSION_FILE:
                pass
            elif fc is not None and not fc.is_dir and fc.data == ch.data:
                pass
            else:
                for fr in rec_file(out, ix, name, ch.data):
                    yield fr
            if len(out.buf) >= CHUNK:
                for fr in out.frames(False):
                    yield fr
        for k in range(len(subs) - 1, -1, -1):
            stack.append(subs[k])
    out.buf.append(69)
    put_varint(out.buf, out.count)
    for fr in out.frames(True):
        yield fr


def fs_measure(vfs):
    # (raw bytes, stored bytes) of what a sync would write
    stats = [0, 0]
    for fr in fs_stream(vfs, stats):
        pass
    return stats[0], stats[1]


# ---------------------------------------------------------------- reader

def utf8_cut(b):
    # largest index <= len(b) that does not split a UTF-8 character
    n = len(b)
    j = n - 1
    k = 0
    while j >= 0 and k < 3 and (b[j] & 192) == 128:
        j -= 1
        k += 1
    if j < 0:
        return n            # only continuation bytes: decode() will reject them
    lead = b[j]
    if lead < 128:
        need = 1
    elif lead >> 5 == 6:
        need = 2
    elif lead >> 4 == 14:
        need = 3
    elif lead >> 3 == 30:
        need = 4
    else:
        return n            # invalid lead byte: decode() will reject it
    if n - j < need:
        return j
    return n


class Rd:
    def __init__(self, chunks):
        self.src = iter(chunks)
        self.sb = b""
        self.sp = 0
        self.raw = b""
        self.rp = 0

    def _stored(self, n):
        out = bytearray()
        while len(out) < n:
            if self.sp >= len(self.sb):
                try:
                    self.sb = next(self.src)
                except StopIteration:
                    raise ValueError("stream truncated")
                self.sp = 0
                continue
            k = n - len(out)
            if k > len(self.sb) - self.sp:
                k = len(self.sb) - self.sp
            out.extend(self.sb[self.sp:self.sp + k])
            self.sp += k
        return out

    def _frame(self):
        h = self._stored(FRAME_HDR)
        mode = h[0]
        rawlen = (h[1] << 8) | h[2]
        paylen = (h[3] << 8) | h[4]
        if rawlen == 0 or rawlen > 2 * CHUNK:
            raise ValueError("bad frame length")
        p = bytes(self._stored(paylen))
        if mode == 0:
            if paylen != rawlen:
                raise ValueError("bad raw frame")
            self.raw = p
        elif mode == 1:
            self.raw = lz_decompress(p, rawlen)
        else:
            raise ValueError("bad frame mode")
        self.rp = 0

    def byte(self):
        while self.rp >= len(self.raw):
            self._frame()
        b = self.raw[self.rp]
        self.rp += 1
        return b

    def varint(self):
        n = 0
        shift = 0
        while True:
            b = self.byte()
            n |= (b & 127) << shift
            if b < 128:
                return n
            shift += 7
            if shift > 35:
                raise ValueError("bad varint")

    def text_pieces(self, n):
        # n bytes of UTF-8 as decoded str pieces (<= one frame each); a
        # character split across frames is carried over
        carry = b""
        left = n
        while left > 0:
            if self.rp >= len(self.raw):
                self._frame()
            k = left
            if k > len(self.raw) - self.rp:
                k = len(self.raw) - self.rp
            piece = carry + self.raw[self.rp:self.rp + k]
            self.rp += k
            left -= k
            cut = len(piece)
            if left > 0:
                cut = utf8_cut(piece)
            yield piece[:cut].decode()
            carry = piece[cut:]

    def take_text(self, n):
        return "".join(self.text_pieces(n))

    def take_data(self, n):
        # canonical file data (A84FS): small -> str, big -> list of 1 KB
        # pieces. A big file is never joined into one string.
        return dchunks(self.text_pieces(n))

    def take(self, n):
        out = bytearray()
        while len(out) < n:
            if self.rp >= len(self.raw):
                self._frame()
            k = n - len(out)
            if k > len(self.raw) - self.rp:
                k = len(self.raw) - self.rp
            out.extend(self.raw[self.rp:self.rp + k])
            self.rp += k
        return out


def _name(rd):
    ln = rd.varint()
    if ln == 0 or ln > MAXNAME:
        raise ValueError("bad name length")
    name = bytes(rd.take(ln)).decode()
    if name == "." or name == ".." or "/" in name:
        raise ValueError("bad name")
    return name


def _decode(chunks):
    rd = Rd(chunks)
    h = rd.take(3)
    if h[0] != 82 or h[1] != 50:
        raise ValueError("bad stream header")
    vfs = factory_vfs(h[2])
    dirs = [vfs.root]
    for d in FACTORY1_DIRS:
        dirs.append(vfs.get(d))
    seen = 0
    while True:
        t = rd.byte()
        if t == 69:
            if rd.varint() != seen:
                raise ValueError("record count mismatch")
            break
        parent = rd.varint()
        if parent >= len(dirs):
            raise ValueError("bad parent")
        p = dirs[parent]
        if not p.is_dir:
            raise ValueError("parent is not a directory")
        name = _name(rd)
        seen += 1
        if t == 68:
            if name in p.children:
                raise ValueError("duplicate " + name)
            nd = Node(True)
            p.children[name] = nd
            dirs.append(nd)
        elif t == 70:
            ln = rd.varint()
            if ln > MAXDATA:
                raise ValueError("file too large")
            data = rd.take_data(ln)
            old = p.children.get(name)
            if old is None:
                p.children[name] = Node(False, data)
            elif old.is_dir:
                raise ValueError("file over directory")
            else:
                old.data = data
        elif t == 88:
            if name in p.children:
                del p.children[name]
        else:
            raise ValueError("bad record type")
    vfs.dirty = False
    return vfs


def decode_stream(chunks):
    # chunks: iterable of bytes. Raises ValueError (corrupt) or StorageError
    # (from the storage layer, e.g. checksum); never anything else.
    try:
        return _decode(chunks)
    except (ValueError, StorageError):
        raise
    except Exception as e:
        raise ValueError("fs stream: " + repr(e))


def same_tree(a, b):
    # iterative structural equality of two VFS trees
    stack = [(a.root, b.root)]
    while stack:
        x, y = stack.pop()
        if x.is_dir != y.is_dir:
            return False
        if not x.is_dir:
            if x.data != y.data:
                return False
            continue
        if len(x.children) != len(y.children):
            return False
        for name in x.children:
            if name not in y.children:
                return False
            stack.append((x.children[name], y.children[name]))
    return True
