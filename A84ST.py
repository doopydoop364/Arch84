# A84ST: block storage in calculator lists (Arch84 module 3/10)
#
# Stores a byte stream (the frames from A84CZ) in lists. Each element holds
# 5 bytes = 40 bits, stored as v + 0.5: measured on the calculator, plain
# integers above ~2^29 sometimes come back exactly 1 too low, while half
# values were exact in ~18,000 samples up to 46 bits. 99 data elements per
# list (a list holds at most 100; element 0 is the magic).
#
# Two slots (S0xxx / S1xxx). A save writes the INACTIVE slot, reads it back
# and verifies it, and only then writes the meta list `A84`, so any failure
# leaves the previous save live. Lists whose first element is not our magic
# are never overwritten. Only this module touches store_list/recall_list.
#
# meta list (all v+0.5): [magic, version, slot, nblocks, nbytes, checksum]
# version 2 = this format; version 1 = the old 2-chars-per-element text
# format, still READ here so existing saves migrate (the first sync after
# loading one writes version 2).
from A84FS import StorageError

try:
    import ti_system as _ti
except ImportError:
    _ti = None

STORE_MAGIC = 8484
STORE_VER = 2
BLOCK_ELEMS = 100        # TI lists hold at most 100 elements
DATA_ELEMS = BLOCK_ELEMS - 1
META_NAME = "A84"
ELEM_BYTES = 5
MAXNBLOCKS = 999


def adler(a, b, data):
    for c in data:
        a = (a + c) % 65521
        b = (b + a) % 65521
    return a, b


def pack5(bs):
    # bytes (length a multiple of 5) -> list of 40-bit values + 0.5.
    # Built from two 20-bit halves with float arithmetic (exact below 2^46):
    # a 40-bit int is a big integer on a 32-bit MicroPython, and the old
    # shift/multiply loop allocated dozens of them per element.
    out = []
    for i in range(0, len(bs), ELEM_BYTES):
        hi = (bs[i] << 12) | (bs[i + 1] << 4) | (bs[i + 2] >> 4)
        lo = ((bs[i + 2] & 15) << 16) | (bs[i + 3] << 8) | bs[i + 4]
        out.append(hi * 1048576.0 + lo + 0.5)
    return out


def unpack5(nums):
    # presized output; the 40-bit value is split with float arithmetic into
    # two 20-bit small ints (no big-integer temporaries, see pack5)
    out = bytearray(len(nums) * ELEM_BYTES)
    i = 0
    for x in nums:
        if x < 0 or x >= 1099511627776.0:
            raise StorageError("element out of range")
        hi = int(x * 9.5367431640625e-07)       # x / 2^20, exact
        lo = int(x - hi * 1048576.0)
        out[i] = hi >> 12
        out[i + 1] = (hi >> 4) & 255
        out[i + 2] = ((hi & 15) << 4) | (lo >> 16)
        out[i + 3] = (lo >> 8) & 255
        out[i + 4] = lo & 255
        i += ELEM_BYTES
    return out


def block_name(slot, idx, prefix="S"):
    return prefix + str(slot) + ("000" + str(idx))[-3:]


# ---- version 1 (old) helpers, read only

def checksum1(text):
    a = 1
    b = 0
    for c in text:
        a = (a + ord(c)) % 65521
        b = (b + a) % 65521
    return b * 65536 + a


def unpack_text1(nums, nchars):
    out = []
    for v in nums:
        v = int(v)
        out.append(chr(v // 256))
        out.append(chr(v % 256))
    return "".join(out)[:nchars]


class ListStore:
    # put(name, list) / get(name) -> list are the only calculator calls
    def __init__(self, put, get, kind, meta=META_NAME, prefix="S"):
        # meta/prefix name the lists: other values give a scratch store that
        # cannot touch the real filesystem (used by the on-device checks)
        self.put = put
        self.get = get
        self.kind = kind
        self.meta = meta
        self.prefix = prefix
        self.progress = None     # set by the kernel: called after each list read/written

    def bname(self, slot, idx):
        return block_name(slot, idx, self.prefix)

    def _put(self, name, elems):
        try:
            self.put(name, elems)
        except StorageError:
            raise
        except Exception as e:
            raise StorageError("store_list failed: " + repr(e))

    def _recall(self, name):
        try:
            v = self.get(name)
        except MemoryError:
            raise         # not "no such list": callers report out of memory, never damage
        except Exception:
            return None   # a missing list raises on some firmwares
        if v is None:
            return None
        v = list(v)
        if len(v) == 0:
            return None
        return v

    def _meta(self):
        m = self._recall(self.meta)
        if m is None:
            return None
        if len(m) != 6 or int(m[0]) != STORE_MAGIC:
            raise StorageError("list " + self.meta + " is not ours")
        return [int(x) for x in m]

    def writer(self):
        from A84SW import Writer        # only saving needs it: loaded then, not kept at idle
        return Writer(self)

    def _stream(self, slot, nblocks, nbytes, cs):
        a = 1
        b = 0
        got = 0
        for i in range(nblocks):
            blk = self._recall(self.bname(slot, i))
            if blk is None or int(blk[0]) != STORE_MAGIC:
                raise StorageError("block " + str(i) + " missing/bad")
            data = unpack5(blk[1:])
            if len(data) > nbytes - got:
                data = data[:nbytes - got]
            got += len(data)
            a, b = adler(a, b, data)
            if self.progress is not None:
                self.progress()
            yield data
        if got != nbytes:
            raise StorageError("length mismatch")
        if ((b << 16) | a) != cs:
            raise StorageError("checksum mismatch")

    def _read1(self, m):
        slot = m[2]
        nblocks = m[3]
        nchars = m[4]
        nums = []
        for i in range(nblocks):
            blk = self._recall(self.bname(slot, i))
            if blk is None or int(blk[0]) != STORE_MAGIC:
                raise StorageError("block " + str(i) + " missing/bad")
            nums.extend(blk[1:])
        text = unpack_text1(nums, nchars)
        if len(text) != nchars:
            raise StorageError("length mismatch")
        c = checksum1(text)
        # old saves stored this large integer as a plain int, and plain ints
        # can read back exactly 1 too low
        if m[5] != c and m[5] != c - 1:
            raise StorageError("checksum mismatch")
        return [text.encode()]

    def read(self):
        # None (nothing saved) or (version, iterable of bytes)
        m = self._meta()
        if m is None:
            return None
        if m[1] == 1:
            return 1, self._read1(m)
        if m[1] != STORE_VER:
            raise StorageError("store version " + str(m[1]))
        if m[3] < 1 or m[3] > MAXNBLOCKS:
            raise StorageError("bad block count")
        return 2, self._stream(m[2], m[3], m[4], m[5])


class MemStorage(ListStore):
    # same packing/meta code, but the lists live in a dict: used off the
    # calculator, in tests and by the on-device self test
    def __init__(self):
        self.d = {}
        ListStore.__init__(self, self._mput, self._mget, "memory")

    def _mput(self, name, elems):
        if len(elems) > BLOCK_ELEMS:
            raise ValueError("List length > 100.")
        self.d[name] = list(elems)

    def _mget(self, name):
        return list(self.d[name])


def make_storage():
    if _ti is not None and hasattr(_ti, "store_list") and hasattr(_ti, "recall_list"):
        return ListStore(_ti.store_list, _ti.recall_list, "ti-lists")
    return MemStorage()
