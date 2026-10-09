# A84SW: the list writer of the block store (Arch84 module, lazily loaded).
# A84ST keeps what boot needs (reading); only a save (`sync`, archive create) writes,
# so this is imported then and dropped again (see Kernel.sync).
from A84FS import StorageError
from A84ST import BLOCK_ELEMS, ELEM_BYTES, MAXNBLOCKS, STORE_MAGIC, STORE_VER, adler


class Writer:
    def __init__(self, store):
        self.st = store
        old = store._meta()
        self.old = old
        self.slot = 0
        if old is not None and old[2] == 0:
            self.slot = 1
        self.a = 1
        self.b = 0
        self.nbytes = 0
        self.carry = bytearray()
        self.elems = [STORE_MAGIC + 0.5]    # the block being filled (magic first)
        self.nblocks = 0
        self.done = False

    def _flush(self):
        if self.nblocks >= MAXNBLOCKS:
            raise StorageError("filesystem too large")
        name = self.st.bname(self.slot, self.nblocks)
        cur = self.st._recall(name)
        if cur is not None and int(cur[0]) != STORE_MAGIC:
            raise StorageError("list " + name + " is not ours")
        cur = None
        self.st._put(name, self.elems)
        self.elems = [STORE_MAGIC + 0.5]
        self.nblocks += 1
        if self.st.progress is not None:
            self.st.progress()

    def _pack(self, buf, n):
        # buf[:n] (a multiple of 5 bytes) -> elements, flushing full blocks as
        # they fill; no intermediate element lists
        el = self.elems
        for i in range(0, n, ELEM_BYTES):
            hi = (buf[i] << 12) | (buf[i + 1] << 4) | (buf[i + 2] >> 4)
            lo = ((buf[i + 2] & 15) << 16) | (buf[i + 3] << 8) | buf[i + 4]
            el.append(hi * 1048576.0 + lo + 0.5)
            if len(el) == BLOCK_ELEMS:
                self._flush()
                el = self.elems

    def feed(self, data):
        self.a, self.b = adler(self.a, self.b, data)
        self.nbytes += len(data)
        buf = self.carry
        buf.extend(data)
        n = len(buf) // ELEM_BYTES * ELEM_BYTES
        if n:
            self._pack(buf, n)
            self.carry = buf[n:]

    def finish(self):
        if self.carry:
            while len(self.carry) < ELEM_BYTES:
                self.carry.append(0)
            self._pack(self.carry, len(self.carry))
            self.carry = bytearray()
        if len(self.elems) > 1 or self.nblocks == 0:
            self._flush()
        self.done = True

    def checksum(self):
        return (self.b << 16) | self.a

    def readback(self):
        # generator over what was just written (slot not yet live)
        return self.st._stream(self.slot, self.nblocks, self.nbytes,
                               self.checksum())

    def commit(self):
        st = self.st
        st._put(st.meta, [STORE_MAGIC + 0.5, STORE_VER + 0.5, self.slot + 0.5,
                            self.nblocks + 0.5, self.nbytes + 0.5,
                            self.checksum() + 0.5])
        warnings = []
        old = self.old
        if old is not None:
            # shrink the previous slot's lists (best effort)
            for i in range(old[3]):
                try:
                    st._put(st.bname(old[2], i), [STORE_MAGIC + 0.5])
                except StorageError as e:
                    warnings.append("could not shrink old block: " + str(e))
                    break
        return self.nblocks, warnings
