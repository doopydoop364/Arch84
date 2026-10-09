# A84BL: file data kept in calculator lists instead of the heap (Arch84 module, loaded on demand).
# This is the READING half (the Ext class, which stays resident once the filesystem holds such files);
# the code that allocates and writes lists is A84BM, loaded only while something is being stored.
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
from A84ST import unpack5

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
            e = st._recall(lname(i))        # (a MemoryError is not swallowed: it must not look like a damaged file)
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
        elif not isinstance(n.data, str) and not isinstance(n.data, list):
            for i in n.data.ids:        # (duck typed: an Ext of an older copy of this module counts too)
                out.add(i)
    return out


def mark_saved(vfs):
    # the tree that was just saved (or loaded) is the one a restart will come back to
    vfs.store.blob_saved = used_ids(vfs)
    vfs.blob_busy = None            # recomputed by the next make(): numbers freed since are usable again
