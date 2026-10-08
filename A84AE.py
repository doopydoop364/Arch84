# A84AE: `archive extract` (Arch84 module, lazily loaded by A84AX).
from A84FS import Node, StorageError, VFSError
from A84CZ import Rd
from A84AI import ArError, DIR, find, read_index, store_for, write_index


def decode(chunks):
    # -> a scratch tree (root Node) holding the archived paths
    rd = Rd(chunks)
    if bytes(rd.take(2)) != b"Q1":
        raise ValueError("not an archive stream")
    root = Node(True)
    while True:
        t = rd.byte()
        if t == 69:
            return root
        path = bytes(rd.take(rd.varint())).decode()
        if t == 68:
            node = Node(True)
        elif t == 70:
            node = Node(False, rd.take_data(rd.varint()))
        else:
            raise ValueError("bad record")
        parts = path.split("/")[1:]
        cur = root
        for part in parts[:-1]:
            nxt = cur.children.get(part)
            if nxt is None or not nxt.is_dir:
                nxt = Node(True)
                cur.children[part] = nxt
            cur = nxt
        old = cur.children.get(parts[-1])
        if old is not None and node.is_dir and old.is_dir:
            continue                    # the directory record of a path already created
        cur.children[parts[-1]] = node


def find_node(root, path):
    cur = root
    for part in path.split("/")[1:]:
        if not cur.is_dir or part not in cur.children:
            return None
        cur = cur.children[part]
    return cur


def extract(sh, name, keep):
    vfs = sh.vfs
    k = sh.k
    e = find(vfs, name)
    for p in e["paths"]:
        if vfs.exists(p):
            raise ArError("already exists: " + p)
    st = store_for(sh)
    k.spin("Extracting " + name)
    try:
        tree = decode(st._stream(e["id"], e["blocks"], e["bytes"], e["sum"]))
    except MemoryError:
        k.stop_spin()
        raise ArError("not enough free RAM (needs about " + str(e["raw"]) + " chars plus the tree)")
    except (ValueError, StorageError) as x:
        k.stop_spin()
        raise ArError("archive damaged: " + str(x))
    added = []
    try:
        for p in e["paths"]:
            node = find_node(tree, p)
            if node is None:
                raise ArError("archive is missing " + p)
            i = p.rfind("/")
            parent = vfs.get(p[:i] or "/")
            if parent is None:
                mk = ""
                for part in p[:i].split("/")[1:]:
                    mk += "/" + part
                    if not vfs.exists(mk):
                        vfs.mkdir(mk)
                parent = vfs.get(p[:i])
            if not parent.is_dir:
                raise ArError("not a directory: " + p[:i])
            parent.children[p[i + 1:]] = node
            added.append((parent, p[i + 1:]))
        if not keep:
            ents = read_index(vfs)
            write_index(vfs, [x for x in ents if x["name"] != name])
        vfs.dirty = True
    except (ArError, StorageError, MemoryError, VFSError) as x:
        for parent, nm in added:
            parent.children.pop(nm, None)
        if not keep and vfs.isdir(DIR):
            ents = read_index(vfs)
            gone = True
            for y in ents:
                if y["name"] == name:
                    gone = False
            if gone:
                ents.append(e)
                write_index(vfs, ents)
        k.stop_spin()
        raise ArError(str(x) if isinstance(x, ArError) else "failed, nothing changed: " + str(x))
    return e
