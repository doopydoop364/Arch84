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
