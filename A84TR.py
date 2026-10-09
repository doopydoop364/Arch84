# A84TR: bounded, in-memory VFS undo log for multi-file operations.
# Persistent atomicity still comes from A84ST's verified inactive-slot save.
from A84FS import Node, VFSError


class Transaction:
    def __init__(self, vfs, limit=600):
        if vfs._tx is not None:
            raise VFSError("transaction already active")
        self.vfs = vfs
        self.limit = limit
        self.undo = []
        self.seen = {}
        self.blobs = []
        self.dirty = vfs.dirty
        self.ext = vfs.ext
        vfs._tx = self

    def record(self, parent, name):
        key = (id(parent), name)
        if key in self.seen:
            return
        if len(self.undo) >= self.limit:
            raise VFSError("transaction too large")
        old = parent.children.get(name)
        if old is not None and not old.is_dir:
            data = old.data
            old = Node(False, list(data) if isinstance(data, list) else data)
        self.undo.append((parent, name, old))
        self.seen[key] = 1

    def commit(self):
        if self.vfs._tx is not self:
            raise VFSError("transaction inactive")
        self.vfs._tx = None
        self.undo = []
        self.seen = {}
        self.blobs = []

    def add_blob(self, ext):
        self.blobs.append(ext)

    def rollback(self):
        if self.vfs._tx is not self:
            raise VFSError("transaction inactive")
        for parent, name, old in reversed(self.undo):
            if old is None:
                parent.children.pop(name, None)
            else:
                parent.children[name] = old
        self.vfs.dirty = self.dirty
        self.vfs.ext = self.ext
        if self.blobs:
            from A84BL import MAGIC, lname
            for ext in self.blobs:
                for i in ext.ids:
                    try:
                        ext.store._put(lname(i), [MAGIC + 0.5])
                    except Exception:
                        pass  # orphan lists can be reused after reboot or the next save
                    else:
                        busy = getattr(self.vfs, "blob_busy", None)
                        if busy is not None:
                            busy.discard(i)
        self.vfs._tx = None
        self.undo = []
        self.seen = {}
        self.blobs = []
