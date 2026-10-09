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
from A84FS import MAXNAME, Node, StorageError, VERSION, VFS, dchunks, dnew

CHUNK = 1024    # raw bytes per frame (readers accept up to 2 * CHUNK: older saves used 2048)
FRAME_HDR = 5
MAXDATA = 1048576

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


def lz_decompress(c, rawlen, i=0, n=None):
    # c[i:n] is the payload (offsets let a caller decompress straight out of a
    # larger buffer without slicing a copy)
    out = bytearray(rawlen)     # pre-sized: no growth/realloc churn on a fragmented heap
    o = 0
    if n is None:
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


# ---------------------------------------------------------------- writer


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
        sb = self.sb
        sp = self.sp
        if sp + n <= len(sb):
            self.sp = sp + n
            return sb[sp:sp + n]
        out = bytearray()           # extend, not slice assignment: older ports lack it
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
        sb = self.sb
        sp = self.sp
        if sp + paylen <= len(sb):
            self.sp = sp + paylen       # payload lies in the current block: no copy
        else:
            sb = self._stored(paylen)
            sp = 0
        if mode == 0:
            if paylen != rawlen:
                raise ValueError("bad raw frame")
            self.raw = bytes(sb[sp:sp + paylen])
        elif mode == 1:
            self.raw = lz_decompress(sb, rawlen, sp, sp + paylen)
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
        raw = self.raw
        rp = self.rp
        if rp + n <= len(raw):      # all inside this frame: one decode, no generator
            self.rp = rp + n
            return dnew(raw[rp:rp + n].decode())
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
    raw = rd.raw
    rp = rd.rp
    if rp + ln <= len(raw):
        rd.rp = rp + ln
        name = raw[rp:rp + ln].decode()
    else:
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


