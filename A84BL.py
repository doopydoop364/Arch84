# A84BL: file data kept in calculator lists instead of the heap (Arch84 module, loaded on demand).
#
# The filesystem tree lives in the Python heap, a few tens of KB. A file's text can instead sit in
# lists (user RAM, hundreds of KB, not the heap): the tree node then holds an Ext, a small object
# with the list numbers, and the text is read back one list at a time when the file is read.
#   list X<nnnn>: [8486, id, nbytes, data packed 5 bytes per element]   (all stored as v + 0.5)
# VFS.externalize(path) moves a file; writing to a file brings its text back into the heap (the old
# lists are simply no longer referenced). The saved filesystem records the list numbers (record
# type "B" in A84CY/A84CZ), not the text.
#
# A list number is only reused when the current tree does not use it AND the last SAVED tree
# did not either (mark_saved after every sync): a crash before the next sync reloads the old
# save, whose files must still find their text.
from A84FS import StorageError, VFSError
from A84ST import pack5, unpack5
from A84CZ import utf8_cut

MAGIC = 8486
PER = 485               # bytes of text per list: 97 elements of 5 bytes after a 3 element header
MAXID = 9999


def lname(i):
    return "X" + ("0000" + str(i))[-4:]


class Pieces:
    # re-iterable view of an Ext's text pieces (a generator could only be read once)
    def __init__(self, ext):
        self.ext = ext

    def __iter__(self):
        return self.ext.read()


class Ext:
    def __init__(self, store, ids, n):
        self.store = store
        self.ids = ids          # list numbers, in order
        self.n = n              # characters in all

    def pieces(self):
        return Pieces(self)

    def read(self):
        st = self.store
        for i in self.ids:
            e = st._recall(lname(i))
            if e is None or len(e) < 3 or int(e[0]) != MAGIC or int(e[1]) != i:
                raise VFSError("Input/output error")
            try:
                raw = bytes(unpack5(e[3:]))[:int(e[2])]
                yield raw.decode()
            except (StorageError, ValueError):
                raise VFSError("Input/output error")


def used_ids(vfs):
    # the list numbers the tree refers to
    out = set()
    stack = [vfs.root]
    while stack:
        n = stack.pop()
        if n.is_dir:
            stack.extend(n.children.values())
        elif isinstance(n.data, Ext):
            for i in n.data.ids:
                out.add(i)
    return out


def saved_ids(store):
    s = getattr(store, "blob_saved", None)
    if s is None:
        return set()
    return s


def mark_saved(vfs):
    # the tree that was just saved (or loaded) is the one a restart will come back to
    vfs.store.blob_saved = used_ids(vfs)
    vfs.blob_busy = None            # recomputed by the next make(): numbers freed since are usable again


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


def make(vfs, pieces):
    # writes the text (an iterable of str pieces) into lists -> Ext, or None when that is not possible
    # (no store, lists full, memory): the file then simply stays in the heap
    st = vfs.store
    busy = getattr(vfs, "blob_busy", None)      # numbers not to hand out: in the tree now, or in the saved tree
    if busy is None:                            # (kept between calls: walking the tree for every file is slow)
        busy = used_ids(vfs)
        for i in saved_ids(st):
            busy.add(i)
        vfs.blob_busy = busy
    ids = []
    n = 0
    nxt = 0
    buf = bytearray()
    try:
        for p in pieces:
            n += len(p)
            buf.extend(p.encode())
            while len(buf) >= PER:
                cut = utf8_cut(bytes(buf[:PER]))
                if cut <= 0:
                    cut = PER
                nxt = write_list(st, busy, ids, bytes(buf[:cut]), nxt)
                buf = buf[cut:]
        if len(buf) > 0:
            write_list(st, busy, ids, bytes(buf), nxt)
    except (StorageError, VFSError, MemoryError, ValueError):
        return None
    return Ext(st, ids, n)
