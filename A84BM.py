# A84BM: the writing half of A84BL (Arch84 module, loaded only while files are moved into lists, then
# dropped again): allocation of list numbers and writing the lists. See A84BL for the layout and rules.
from A84FS import StorageError, VFSError
from A84ST import pack5
from A84CZ import utf8_cut
from A84BL import MAGIC, PER, MAXID, Ext, lname, used_ids


def saved_ids(store):
    s = getattr(store, "blob_saved", None)
    if s is None:
        return set()
    return s


def free_id(st, busy, i):
    # the first usable list number >= i: not in use, and not a foreign list that happens to be called that
    while i <= MAXID:
        if i not in busy:
            e = st._recall(lname(i))
            if e is None or int(e[0]) == MAGIC:
                return i
        i += 1
    raise VFSError("No space left on device")


def write_list(st, busy, ids, data, i):
    i = free_id(st, busy, i)
    pad = (5 - len(data) % 5) % 5
    st._put(lname(i), [MAGIC + 0.5, i + 0.5, len(data) + 0.5] + pack5(data + bytes(pad)))
    busy.add(i)
    ids.append(i)
    return i + 1


class BlobWriter:
    # Incremental file writer: package extraction can feed each + record without
    # assembling the whole file in the Python heap.
    def __init__(self, vfs):
        self.st = vfs.store
        if self.st is None:
            raise VFSError("no list storage")
        self.busy = getattr(vfs, "blob_busy", None)
        if self.busy is None:
            self.busy = used_ids(vfs)
            for i in saved_ids(self.st):
                self.busy.add(i)
            vfs.blob_busy = self.busy
        self.ids = []
        self.n = 0
        self.nxt = 0
        self.buf = bytearray()
        self.ext = Ext(self.st, self.ids, 0)

    def feed(self, text):
        self.n += len(text)
        self.buf.extend(text.encode())
        while len(self.buf) >= PER:
            cut = utf8_cut(bytes(self.buf[:PER]))
            if cut <= 0:
                cut = PER
            self.nxt = write_list(self.st, self.busy, self.ids, bytes(self.buf[:cut]), self.nxt)
            self.buf = self.buf[cut:]

    def finish(self):
        if self.buf:
            self.nxt = write_list(self.st, self.busy, self.ids, bytes(self.buf), self.nxt)
            self.buf = bytearray()
        self.ext.n = self.n
        return self.ext


def make(vfs, pieces):
    # writes the text (an iterable of str pieces) into lists -> Ext, or None when that is not possible
    # (no store, lists full, memory): the file then simply stays in the heap
    st = vfs.store
    if st is None:
        return None
    writer = BlobWriter(vfs)
    try:
        for p in pieces:
            writer.feed(p)
        return writer.finish()
    except (StorageError, VFSError, MemoryError, ValueError):
        return None
