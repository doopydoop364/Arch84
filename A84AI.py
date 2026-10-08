# A84AI: shared helpers of the `archive` command: catalogue and list store
# (Arch84 module, lazily loaded).
from A84FS import StorageError
from A84ST import ListStore

DIR = "/var/lib/archive"
INDEX = DIR + "/index"
MAXID = 10


class ArError(Exception):
    pass


def store_for(sh):
    s = sh.k.storage
    st = ListStore(s.put, s.get, s.kind, "A84Q", "Q")
    st.progress = sh.k.tick
    return st


def read_index(vfs):
    out = []
    if vfs.isfile(INDEX):
        for line in vfs.lines(INDEX):
            f = line.split("\t")
            if len(f) >= 8:
                out.append({"id": int(f[0]), "name": f[1], "blocks": int(f[2]), "bytes": int(f[3]),
                            "sum": int(f[4]), "files": int(f[5]), "raw": int(f[6]), "paths": f[7:]})
    return out


def write_index(vfs, ents):
    if not vfs.isdir(DIR):
        vfs.mkdir(DIR)
    text = ""
    for e in ents:
        text += "\t".join([str(e["id"]), e["name"], str(e["blocks"]), str(e["bytes"]), str(e["sum"]),
                           str(e["files"]), str(e["raw"])] + e["paths"]) + "\n"
    vfs.write(INDEX, text)


def ok_name(n):
    if n == "" or len(n) > 24:
        return False
    for c in n:
        if not ("a" <= c <= "z" or "0" <= c <= "9" or c in "._-"):
            return False
    return True


def shrink(st, e):
    # best effort: leave 1-element lists behind instead of data
    for i in range(e["blocks"]):
        try:
            st._put(st.bname(e["id"], i), [8484.5])
        except StorageError:
            break




def find(vfs, name):
    for e in read_index(vfs):
        if e["name"] == name:
            return e
    raise ArError("no such archive: " + name)
