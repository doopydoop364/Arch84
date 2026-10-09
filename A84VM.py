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
        # Keep the old copy until the replacement is allocated and installed.
        value = bytes(data)
        self.n += 1
        self.d[self.n] = value
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
            return ZERO
        # Write to another slot so a short or failed write leaves `old` intact.
        if self.free:
            loc = min(self.free)
            self.free.remove(loc)
        else:
            loc = (self.top // self.per) * 1048576 + (self.top % self.per) * self.page
            self.top += 1
        s = loc >> 20
        self.live[s] = self.live.get(s, 0) + 1
        try:
            f = self.handle(s, True)
            f.seek(loc & 1048575)
            if f.write(data) != len(data):
                raise OSError("short swap write")
        except Exception:
            self.drop(loc)
            raise
        self.writes += 1
        return loc

    def get(self, loc, buf):
        if loc == ZERO:
            for i in range(len(buf)):
                buf[i] = 0
            return
        f = self.handle(loc >> 20, False)
        f.seek(loc & 1048575)
        if f.readinto(buf) != len(buf):
            raise OSError("short swap read")
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

    def _slot(self):
        # Never write a foreign V list. Freed slots are checked again because a
        # different calculator program may have claimed one since we dropped it.
        while True:
            if self.free:
                slot = self.free.pop()
                fresh = False
            else:
                slot = self.top
                self.top += 1
                fresh = True
            if (slot + 1) * self.k - 1 > self.maxid:
                raise MemoryError("swap lists full")
            foreign = False
            for c in range(self.k):
                try:
                    v = self.g(self.lname(slot * self.k + c))
                except (KeyError, NameError):
                    continue
                if v is not None and (fresh or not v or int(v[0]) // 4194304 != 8490):
                    foreign = True
                    break
            if not foreign:
                return slot

    def put(self, data, old):
        if len(data) != self.page:
            raise ValueError("wrong swap page size")
        if old == ZERO:
            old = -1
        if not any(data):
            return ZERO
        # Write a different slot first. A failed store_list can leave a partial
        # list; the old slot remains authoritative until all chunks succeed.
        slot = self._slot()
        mv = memoryview(data)
        written = 0
        try:
            for c in range(self.k):
                part = mv[c * self.CH:(c + 1) * self.CH]
                n = len(part)
                while n > 0 and part[n - 1] == 0:
                    n -= 1
                body = bytes(part[:n])
                mode = 0
                if self.comp is not None and n > 100:
                    z = self.comp(body)
                    if len(z) * 10 < n * 7:     # kept only when it saves 30%
                        body = z
                        mode = 1
                m = (len(body) + 4) // 5 * 5
                head = self.HEAD + mode * 1048576 + n * 1024 + len(body)
                self.p(self.lname(slot * self.k + c), [head + 0.5] + self.pack(body + bytes(m - len(body))))
                written += 1
        except Exception:
            # Never reuse a partially written slot until every written list
            # has been reclaimed. The caller still owns the old page copy.
            cleaned = True
            for c in range(written):
                try:
                    self.p(self.lname(slot * self.k + c), [self.HEAD + 0.5])
                except Exception:
                    cleaned = False
            if cleaned:
                self.free.append(slot)
            raise
        self.writes += 1
        return slot

    def get(self, loc, buf):
        if loc == ZERO:
            for i in range(len(buf)):
                buf[i] = 0
            return
        o = 0
        for c in range(self.k):
            try:
                v = list(self.g(self.lname(loc * self.k + c)))
            except (KeyError, NameError):
                raise ValueError("swap list missing")
            if not v or int(v[0]) // 4194304 != 8490:
                raise ValueError("swap list damaged")
            h = int(v[0] - self.HEAD)
            n = (h >> 10) & 1023
            z = h & 1023
            mode = h >> 20
            if h < 0 or mode > 1 or n > self.CH or z > self.CH or len(v) != 1 + (z + 4) // 5:
                raise ValueError("swap list damaged")
            body = self.unpack(v[1:])[:z]
            if mode:
                if self.decomp is None:
                    raise ValueError("swap compression unsupported")
                body = self.decomp(body, n)
            elif z != n:
                raise ValueError("swap list damaged")
            if len(body) != n:
                raise ValueError("swap list damaged")
            take = min(n, len(buf) - o)
            buf[o:o + take] = body[:take]
            o += self.CH
        self.reads += 1

    def drop(self, loc):
        if loc != ZERO:
            for c in range(self.k):      # lists live in RAM: shrink the stale ones to one element
                name = self.lname(loc * self.k + c)
                v = self.g(name)
                if not v or int(v[0]) // 4194304 != 8490:
                    raise ValueError("swap list is not ours")
                self.p(name, [self.HEAD + 0.5])
            self.free.append(loc)


def free_heap():
    try:
        return gc.mem_free()
    except AttributeError:
        return 1 << 30                  # not MicroPython: no heap to run out of


class Pager:
    # Memory pressure is handled here: when free heap falls under `low` bytes, or an allocation
    # raises MemoryError, the least recently used resident pages go to the backend until it fits.
    # guard(f, ...) gives any other code the same treatment, make_room(n) asks for n bytes up front.
    # Tables: loc[pid] backend location (-1 never stored, ZERO all-zero); res[pid] resident
    # bytearray; use[pid] = last-use tick * 2 + dirty bit (one dict for both).
    def __init__(self, backend, page=PAGE, window=10, low=3072,
                 elevated=None, release=None, unload=None):
        if page < 1 or window < 1:
            raise ValueError("page and window must be positive")
        self.be = backend
        self.page = page
        self.window = window
        self.low = low                  # reserve: evict while free heap < low (0: off)
        self.elevated = elevated if elevated is not None else low * 2
        if self.elevated < low:
            raise ValueError("elevated threshold below critical threshold")
        self.release = release          # optional cache release before swapping
        self.unload = unload            # optional module unload after swapping
        self.loc = {}
        self.res = {}
        self.use = {}
        self.pins = {}                 # only pinned resident pages have an entry
        self.recovering = False
        self.tick = 0
        self.nxt = 0
        self.faults = 0
        self.evicts = 0
        self.alloc_fails = 0
        self.cleanup_fails = 0

    def new_page(self):
        pid = self.nxt
        self._make_room()
        b = self._alloc()
        try:
            self.guard(self.loc.__setitem__, pid, -1)
            self._touch(pid, 1)
            self.guard(self.res.__setitem__, pid, b)
        except BaseException:
            self.loc.pop(pid, None)
            self.use.pop(pid, None)
            raise
        self.nxt += 1
        return pid

    def free_page(self, pid):
        if self.pins.get(pid, 0):
            raise ValueError("page is pinned")
        if self.loc[pid] >= 0:
            self.be.drop(self.loc[pid])
        del self.loc[pid]
        if pid in self.res:
            del self.res[pid]
            del self.use[pid]

    def pin_page(self, pid):
        self.page_in(pid)
        self.guard(self.pins.__setitem__, pid, self.pins.get(pid, 0) + 1)

    def unpin_page(self, pid):
        n = self.pins[pid]
        if n == 1:
            del self.pins[pid]
        else:
            self.pins[pid] = n - 1

    def _touch(self, pid, dirty=0):
        self.tick += 1
        d = self.use.get(pid, 0) & 1
        self.guard(self.use.__setitem__, pid, (self.tick << 1) | d | dirty)

    def _make_room(self):
        while len(self.res) >= self.window or (self.low and self.res and free_heap() < self.low):
            if not self.evict():
                if len(self.res) >= self.window:
                    raise MemoryError("all resident pages pinned")
                break

    def make_room(self, nbytes):
        # evict LRU pages until nbytes (plus the reserve) are free; False if swap is all that is left
        if self.recovering:
            return False
        self.recovering = True
        try:
            gc.collect()
            released = False
            unloaded = False
            while free_heap() < nbytes + self.low:
                if not released and self.release is not None:
                    released = True
                    self.release()
                    gc.collect()
                    continue
                if not self.evict():
                    if not unloaded and self.unload is not None:
                        unloaded = True
                        self.unload()
                        gc.collect()
                    else:
                        return False
            return True
        finally:
            self.recovering = False

    def pressure_level(self):
        free = free_heap()
        if free < self.low:
            return 2
        if free < self.elevated:
            return 1
        return 0

    def guard(self, f, *args):
        # f(*args), and on MemoryError one LRU page goes to swap and f is tried again
        released = False
        unloaded = False
        while True:
            try:
                return f(*args)
            except MemoryError:
                self.alloc_fails += 1
                if self.recovering:
                    raise
                self.recovering = True
                try:
                    gc.collect()
                    if not released and self.release is not None:
                        released = True
                        self.release()
                        continue
                    if self.evict():
                        continue
                    if not unloaded and self.unload is not None:
                        unloaded = True
                        self.unload()
                        continue
                    raise
                finally:
                    self.recovering = False

    def _alloc(self):
        return self.guard(bytearray, self.page)

    def evict(self):
        best = -1
        bt = 0
        for pid in self.res:
            if self.pins.get(pid, 0):
                continue
            t = self.use[pid]
            if best < 0 or t < bt:
                best = pid
                bt = t
        if best < 0:
            return False
        if bt & 1:
            self._store(best)
        del self.res[best]
        del self.use[best]
        gc.collect()
        self.evicts += 1
        return True

    def _store(self, pid):
        old = self.loc[pid]
        new = self.be.put(self.res[pid], old)
        self.loc[pid] = new
        if old >= 0 and old != new:
            try:
                self.be.drop(old)
            except Exception:
                # The new copy is authoritative; failure to reclaim old space
                # must not turn a successful write into a lost page.
                self.cleanup_fails += 1

    def page_in(self, pid, load=True):
        b = self.res.get(pid)
        if b is None:
            self.faults += 1
            self._make_room()
            b = self._alloc()
            if load and self.loc[pid] != -1 and self.loc[pid] != ZERO:
                self.be.get(self.loc[pid], b)
            try:
                self._touch(pid)
                self.guard(self.res.__setitem__, pid, b)
            except BaseException:
                self.use.pop(pid, None)
                raise
        else:
            self._touch(pid)
        return b

    def read(self, pid, off, n):
        if off < 0 or n < 0 or off + n > self.page:
            raise ValueError("page read out of range")
        b = self.page_in(pid)
        return bytes(memoryview(b)[off:off + n])

    def write(self, pid, off, data):
        if off < 0 or off + len(data) > self.page:
            raise ValueError("page write out of range")
        b = self.page_in(pid, off != 0 or len(data) < self.page)
        b[off:off + len(data)] = data
        self._touch(pid, 1)

    def flush(self):
        for pid in self.res:
            if self.use[pid] & 1:
                self._store(pid)
                self.use[pid] &= ~1

    def stats(self):
        dirty = 0
        for pid in self.use:
            if self.use[pid] & 1:
                dirty += 1
        return {"resident": len(self.res), "pages": len(self.loc), "dirty": dirty,
                "pinned": len(self.pins), "faults": self.faults, "evictions": self.evicts,
                "allocation_failures": self.alloc_fails,
                "cleanup_failures": self.cleanup_fails,
                "backend_reads": self.be.reads, "backend_writes": self.be.writes}
