# A84VM: application-level virtual memory (pager). Pages of PAGE bytes live in RAM (at most
# `window` of them) or in a backend (swap files, lists, ...). Page table: loc[pid] -> backend
# location or -1 (never stored); res[pid] -> bytearray; dirty/use dicts. LRU by linear scan
# (no sorted()). Only touches the backend when access leaves the resident window.
import gc

PAGE = 1024
SEG = 32768
ZERO = -2                         # loc of an all-zero page (nothing stored)


class MemBackend:
    def __init__(self):
        self.d = {}
        self.n = 0
        self.reads = 0
        self.writes = 0

    def put(self, data, old):
        if old >= 0:
            del self.d[old]
        self.n += 1
        self.d[self.n] = bytes(data)
        self.writes += 1
        return self.n

    def get(self, loc, buf):
        buf[:] = self.d[loc]
        self.reads += 1

    def drop(self, loc):
        if loc in self.d:
            del self.d[loc]


class FileBackend:
    # swap files swap0.dat, swap1.dat ... of <= SEG bytes, each a fixed array of page slots.
    # loc = seg*1048576 + slot*page. A freed slot is reused in place (r+b), so the files never
    # grow past the peak number of live pages and need no compaction; a segment file is created
    # when the first slot in it is used and deleted when its last live page goes. One handle is
    # kept open per call pattern (the last segment written / read) to avoid open+close per page.
    # An all-zero page is not stored at all (loc ZERO).
    def __init__(self, opener, remover, page=PAGE, seg=SEG, prefix="swap"):
        self.op = opener
        self.rm = remover
        self.page = page
        self.per = seg // page
        self.prefix = prefix
        self.top = 0                    # slots handed out so far (next fresh slot)
        self.free = []                  # freed locs, reused first
        self.live = {}                  # segment -> live page count
        self.made = {}                  # segment -> file exists
        self.h = None
        self.hs = -1
        self.reads = 0
        self.writes = 0

    def name(self, s):
        return self.prefix + str(s) + ".dat"

    def handle(self, s, create):
        if self.hs != s:
            self.close()
            if create and s not in self.made:
                f = self.op(self.name(s), "wb")
                f.close()
                self.made[s] = 1
            self.h = self.op(self.name(s), "r+b")
            self.hs = s
        return self.h

    def close(self):
        if self.h is not None:
            self.h.close()
            self.h = None
            self.hs = -1

    def put(self, data, old):
        if old == ZERO:
            old = -1
        if not any(data):
            if old >= 0:
                self.drop(old)
            return ZERO
        if old < 0:
            if self.free:
                old = min(self.free)        # lowest first: the high segments drain and go
                self.free.remove(old)
            else:
                old = (self.top // self.per) * 1048576 + (self.top % self.per) * self.page
                self.top += 1
            s = old >> 20
            self.live[s] = self.live.get(s, 0) + 1
        f = self.handle(old >> 20, True)
        f.seek(old & 1048575)
        f.write(data)
        self.writes += 1
        return old

    def get(self, loc, buf):
        if loc == ZERO:
            for i in range(len(buf)):
                buf[i] = 0
            return
        f = self.handle(loc >> 20, False)
        f.seek(loc & 1048575)
        f.readinto(buf)
        self.reads += 1

    def drop(self, loc):
        if loc == ZERO:
            return
        s = loc >> 20
        self.live[s] -= 1
        if self.live[s] == 0:
            del self.live[s]
            if self.hs == s:
                self.close()
            del self.made[s]
            self.rm(self.name(s))
            self.free = [x for x in self.free if x >> 20 != s]
        else:
            self.free.append(loc)


class ListBackend:
    # the store that exists on the calculator (measured, OS 7.0): real list elements, 40 bits =
    # 5 bytes each (exact; 43+ bits and complex elements are not), ~1.6 ms/element to write,
    # ~1.1 ms/element + 4 ms to read. Cost follows the ELEMENT count, so a chunk (<= 99 elements,
    # 495 bytes, one list) stores only up to its last non-zero byte: element 0 = HEAD + length.
    # A page is ceil(page/495) chunks; a free page slot is reused. Lists are named
    # <prefix><4 digits>; a list whose head is not ours is never overwritten.
    HEAD = 8490 * 4194304           # element 0 = HEAD + mode*2^20 + rawlen*2^10 + stored length
    CH = 495

    def __init__(self, put, get, page=PAGE, prefix="V", maxid=9999, comp=None, decomp=None):
        from A84ST import pack5, unpack5
        self.p = put
        self.g = get
        self.pack = pack5
        self.unpack = unpack5
        self.page = page
        self.k = (page + self.CH - 1) // self.CH
        self.prefix = prefix
        self.maxid = maxid
        self.comp = comp                # comp(bytes) -> bytes, decomp(bytes, rawlen) -> bytes: optional
        self.decomp = decomp
        self.top = 0
        self.free = []
        self.reads = 0
        self.writes = 0

    def lname(self, i):
        return self.prefix + ("0000" + str(i))[-4:]

    def put(self, data, old):
        if old == ZERO:
            old = -1
        if not any(data):
            if old >= 0:
                self.drop(old)
            return ZERO
        if old < 0:
            if self.free:
                old = min(self.free)
                self.free.remove(old)
            else:
                if (self.top + 1) * self.k > self.maxid:
                    raise MemoryError("swap lists full")
                old = self.top
                self.top += 1
        mv = memoryview(data)
        for c in range(self.k):
            part = mv[c * self.CH:(c + 1) * self.CH]
            n = len(part)
            while n > 0 and part[n - 1] == 0:
                n -= 1
            body = bytes(part[:n])
            mode = 0
            if self.comp is not None and n > 100:
                z = self.comp(body)
                if len(z) * 10 < n * 7:         # kept only when it saves 30%
                    body = z
                    mode = 1
            m = (len(body) + 4) // 5 * 5
            head = self.HEAD + mode * 1048576 + n * 1024 + len(body)
            self.p(self.lname(old * self.k + c), [head + 0.5] + self.pack(body + bytes(m - len(body))))
        self.writes += 1
        return old

    def get(self, loc, buf):
        if loc == ZERO:
            for i in range(len(buf)):
                buf[i] = 0
            return
        o = 0
        for c in range(self.k):
            v = list(self.g(self.lname(loc * self.k + c)))
            h = int(v[0] - self.HEAD)
            n = (h >> 10) & 1023
            z = h & 1023
            if h < 0 or n > self.CH or z > self.CH:
                raise ValueError("swap list damaged")
            body = self.unpack(v[1:])[:z]
            if h >> 20:
                body = self.decomp(body, n)
            take = min(n, len(buf) - o)
            buf[o:o + take] = body[:take]
            o += self.CH
        self.reads += 1

    def drop(self, loc):
        if loc != ZERO:
            self.free.append(loc)
            for c in range(self.k):      # lists live in RAM: shrink the stale ones to one element
                self.p(self.lname(loc * self.k + c), [self.HEAD + 0.5])


class Pager:
    def __init__(self, backend, page=PAGE, window=10, low=0):
        self.be = backend
        self.page = page
        self.window = window
        self.low = low                  # also evict while gc.mem_free() < low (0: off)
        self.loc = {}                   # pid -> backend location, -1 = not on disk
        self.res = {}                   # pid -> bytearray (resident pages)
        self.dirty = {}
        self.use = {}
        self.tick = 0
        self.nxt = 0
        self.faults = 0
        self.evicts = 0

    def new_page(self):
        pid = self.nxt
        self.nxt += 1
        self.loc[pid] = -1
        self._make_room()
        self.res[pid] = bytearray(self.page)
        self.dirty[pid] = 1
        self._touch(pid)
        return pid

    def free_page(self, pid):
        if self.loc[pid] >= 0:
            self.be.drop(self.loc[pid])
        del self.loc[pid]
        if pid in self.res:
            del self.res[pid]
        if pid in self.dirty:
            del self.dirty[pid]
        if pid in self.use:
            del self.use[pid]

    def _touch(self, pid):
        self.tick += 1
        self.use[pid] = self.tick

    def _make_room(self):
        while len(self.res) >= self.window or (self.low and len(self.res) > 1 and gc.mem_free() < self.low):
            self.evict()

    def evict(self):
        best = -1
        bt = 0
        for pid in self.res:
            t = self.use[pid]
            if best < 0 or t < bt:
                best = pid
                bt = t
        if best < 0:
            return False
        if best in self.dirty:
            self.loc[best] = self.be.put(self.res[best], self.loc[best])
            del self.dirty[best]
        del self.res[best]
        gc.collect()
        self.evicts += 1
        return True

    def page_in(self, pid, load=True):
        b = self.res.get(pid)
        if b is None:
            self.faults += 1
            self._make_room()
            b = bytearray(self.page)
            if load and self.loc[pid] != -1 and self.loc[pid] != ZERO:
                self.be.get(self.loc[pid], b)
            self.res[pid] = b
        self._touch(pid)
        return b

    def read(self, pid, off, n):
        b = self.page_in(pid)
        return bytes(memoryview(b)[off:off + n])

    def write(self, pid, off, data):
        b = self.page_in(pid, off != 0 or len(data) < self.page)
        b[off:off + len(data)] = data
        self.dirty[pid] = 1

    def flush(self):
        for pid in list(self.dirty):
            self.loc[pid] = self.be.put(self.res[pid], self.loc[pid])
        self.dirty.clear()
