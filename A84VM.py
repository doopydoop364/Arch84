# A84VM: application-level virtual memory (pager). Pages of PAGE bytes live in RAM (at most
# `window` of them) or in a backend (swap files, lists, ...). Page table: loc[pid] -> backend
# location or -1 (never stored); res[pid] -> bytearray; dirty/use dicts. LRU by linear scan
# (no sorted()). Only touches the backend when access leaves the resident window.
import gc

PAGE = 1024
SEG = 32768


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
    # log-structured swap files swap0.dat, swap1.dat ... of <= SEG bytes. loc = seg*1048576+off.
    # A page is appended to the current segment; a superseded copy only counts as garbage, and a
    # segment whose pages are all garbage is deleted. `opener`/`remover` are open and os.remove.
    def __init__(self, opener, remover, page=PAGE, seg=SEG, prefix="swap"):
        self.op = opener
        self.rm = remover
        self.page = page
        self.per = seg // page
        self.prefix = prefix
        self.cur = 0
        self.used = 0
        self.live = {}
        self.reads = 0
        self.writes = 0

    def name(self, s):
        return self.prefix + str(s) + ".dat"

    def put(self, data, old):
        if old >= 0:
            self.drop(old)
        if self.used >= self.per:
            self.cur += 1
            self.used = 0
        f = self.op(self.name(self.cur), "wb" if self.used == 0 else "ab")
        f.write(data)
        f.close()
        loc = self.cur * 1048576 + self.used * self.page
        self.used += 1
        self.live[self.cur] = self.live.get(self.cur, 0) + 1
        self.writes += 1
        return loc

    def get(self, loc, buf):
        f = self.op(self.name(loc >> 20), "rb")
        f.seek(loc & 1048575)
        f.readinto(buf)
        f.close()
        self.reads += 1

    def drop(self, loc):
        s = loc >> 20
        self.live[s] -= 1
        if self.live[s] == 0 and s != self.cur:
            del self.live[s]
            self.rm(self.name(s))


class ListBackend:
    # the only store that survives on the calculator: pages packed 5 bytes per list element
    # (A84ST.pack5). One list per page, named <prefix><n>.
    def __init__(self, put, get, prefix="V"):
        from A84ST import pack5, unpack5
        self.p = put
        self.g = get
        self.pack = pack5
        self.unpack = unpack5
        self.prefix = prefix
        self.n = 0
        self.reads = 0
        self.writes = 0

    def put(self, data, old):
        if old < 0:
            self.n += 1
            old = self.n
        pad = (-len(data)) % 5
        self.p(self.prefix + str(old), self.pack(bytes(data) + bytes(pad)))
        self.writes += 1
        return old

    def get(self, loc, buf):
        v = self.unpack(list(self.g(self.prefix + str(loc))))
        buf[:] = v[:len(buf)]
        self.reads += 1

    def drop(self, loc):
        pass


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
            if load and self.loc[pid] >= 0:
                self.be.get(self.loc[pid], b)
            self.res[pid] = b
        self._touch(pid)
        return b

    def read(self, pid, off, n):
        return bytes(memoryview(self.page_in(pid))[off:off + n])

    def write(self, pid, off, data):
        b = self.page_in(pid, off != 0 or len(data) < self.page)
        b[off:off + len(data)] = data
        self.dirty[pid] = 1

    def flush(self):
        for pid in list(self.dirty):
            self.loc[pid] = self.be.put(self.res[pid], self.loc[pid])
        self.dirty.clear()
