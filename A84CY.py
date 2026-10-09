# A84CY: the writing half of the filesystem codec (Arch84 module, lazily loaded).
# A84CZ keeps what boot needs (decoding); only `sync`, `df` and the archive packer compress,
# so this module is imported then and not kept resident while idle.
# See A84CZ for the record stream format.
from A84FS import SPLIT, dpieces
from A84CZ import CHUNK, FACTORY1_DIRS, VERSION_FILE, factory_vfs

FACTORY_VER = 1

LZ_HASH = 1024      # match table entries (2 bytes each)


def lz_compress(d):
    # Fixed memory: a 2 KB hash table (last position of each 3-byte hash,
    # pos+1 in 2 bytes, 0 = empty; candidates are verified) and a pre-sized
    # output. The earlier dict-per-position version grew to >10 KB of
    # fragmenting reallocations on incompressible frames.
    n = len(d)
    out = bytearray(n + (n >> 3) + 2)
    hb = 64                     # table sized to the input: tiny frames stay tiny
    while hb < n and hb < LZ_HASH:
        hb <<= 1
    tab = bytearray(hb * 2)
    mask = hb - 1
    o = 0
    i = 0
    pos = 0
    ctl = 0
    nbit = 0
    while i < n:
        if nbit == 0:
            pos = o
            o += 1
            ctl = 0
        ln = 0
        if i + 2 < n:
            h = ((d[i] * 5 + d[i + 1] * 31 + d[i + 2] * 131) & mask) * 2
            j = (tab[h] | (tab[h + 1] << 8)) - 1
            if j >= 0 and i - j <= 4096 and d[j] == d[i] and d[j + 1] == d[i + 1] \
                    and d[j + 2] == d[i + 2]:
                ln = 3
                while ln < 18 and i + ln < n and d[j + ln] == d[i + ln]:
                    ln += 1
        if ln:
            v = i - j - 1
            out[o] = v & 255
            out[o + 1] = ((v >> 8) << 4) | (ln - 3)
            o += 2
            step = ln
        else:
            ctl |= 1 << nbit
            out[o] = d[i]
            o += 1
            step = 1
        p = i
        e = i + step
        if e > n - 2:
            e = n - 2
        while p < e:
            h = ((d[p] * 5 + d[p + 1] * 31 + d[p + 2] * 131) & mask) * 2
            tab[h] = (p + 1) & 255
            tab[h + 1] = (p + 1) >> 8
            p += 1
        i += step
        nbit += 1
        if nbit == 8:
            out[pos] = ctl
            nbit = 0
    if nbit:
        out[pos] = ctl
    return bytes(out[:o])


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
        self.chunk = CHUNK      # raw bytes per frame (the archive packer uses smaller ones)

    def frames(self, final):
        buf = self.buf
        n = len(buf)
        off = 0
        out = []
        ch = self.chunk
        while n - off >= ch or (final and n - off > 0):
            take = n - off
            if take > ch:
                take = ch
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
    # <= SPLIT-char slices (never splits a UTF-8 character)
    for p in pieces:
        if len(p) <= SPLIT:
            yield p
        else:
            for i in range(0, len(p), SPLIT):
                yield p[i:i + SPLIT]


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
            elif not isinstance(ch.data, str) and not isinstance(ch.data, list):
                # external data (A84BL): the list numbers, not the text
                rec_head(out, 66, ix, name)
                put_varint(out.buf, ch.data.n)
                put_varint(out.buf, len(ch.data.ids))
                for i in ch.data.ids:
                    put_varint(out.buf, i)
            elif isinstance(ch.data, str) and len(ch.data) <= 256:
                # small file (the common case): no generators, one encode
                rec_head(out, 70, ix, name)
                b = ch.data.encode()
                put_varint(out.buf, len(b))
                out.buf.extend(b)
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


def same_data(x, y):
    if isinstance(x, str) or isinstance(x, list):
        return (isinstance(y, str) or isinstance(y, list)) and x == y
    if isinstance(y, str) or isinstance(y, list):
        return False
    return x.ids == y.ids and x.n == y.n      # external data (A84BL)


def same_tree(a, b):
    # iterative structural equality of two VFS trees. Files are compared in
    # place; only directories are queued (a wide directory used to queue one
    # tuple per file, which is what ran out of memory at the end of a save).
    stack = [(a.root, b.root)]
    while stack:
        x, y = stack.pop()
        if not x.is_dir or not y.is_dir:
            return False
        xc = x.children
        yc = y.children
        if len(xc) != len(yc):
            return False
        for name in xc:
            if name not in yc:
                return False
            cx = xc[name]
            cy = yc[name]
            if cx.is_dir != cy.is_dir:
                return False
            if cx.is_dir:
                stack.append((cx, cy))
            elif not same_data(cx.data, cy.data):
                return False
    return True
