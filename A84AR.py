# A84AR: `archive create` (Arch84 module, lazily loaded by A84AX, which has the command line).
# Moves files out of the Python heap into compressed calculator lists.
#
#   archive create NAME PATH...   pack files/dirs into lists Qnxxx and remove them from RAM
#   archive extract [-k] NAME     bring them back (the archive is deleted unless -k)
#   archive list                  archives, sizes and paths
#   archive check [NAME]          verify the stored lists (checksum)
#   archive delete NAME           discard an archive
#
# Stream format (inside the usual frames/lists): b"Q1", then records  type(68 dir | 70 file)
# varint(pathlen) path [varint(datalen) data]  ... 69. Paths are absolute; no factory image is
# involved, so nothing but the archived files is built or kept while packing.
# The lists live in the calculator's list memory, not on the Python heap, which is what
# limits the filesystem; Python cannot reach the flash Archive itself. The catalogue is
# /var/lib/archive/index (persisted with the filesystem): id TAB name TAB blocks TAB
# bytes TAB sum TAB files TAB raw TAB path TAB path ... An archive is created only after
# its lists were written and read back; the files leave RAM in the same sync that saves
# the catalogue, so a power cut shows either the old state or the new one.
from A84FS import StorageError, VFSError, dpieces
from A84CZ import FACTORY1_DIRS, FACTORY1_FILES
from A84CY import Out, put_varint, slices
from A84SW import Writer
from A84AI import (ArError, DIR, MAXID, ok_name, read_index, store_for, write_index)

ROOTS = ("home", "usr", "opt", "var", "tmp", "root")


def check_path(vfs, p):
    if p == "/" or p.split("/")[1] not in ROOTS:
        raise ArError("not allowed: " + p + " (system area)")
    if p == DIR or p.startswith(DIR + "/"):
        raise ArError("not allowed: " + p)
    if p in FACTORY1_DIRS:
        raise ArError(p + " is a system directory: archive what is inside it")
    for f, t in FACTORY1_FILES:
        if f == p:
            raise ArError(p + " is a system file")
    if not vfs.exists(p):
        raise ArError("no such file or directory: " + p)


def rec_path(out, t, path):
    b = path.encode()
    out.buf.append(t)
    put_varint(out.buf, len(b))
    out.buf.extend(b)


def encode(vfs, paths, stats):
    # generator of frames for the files/dirs under `paths`
    out = Out(stats)
    out.chunk = 512         # half-size frames: smaller buffers fit a fragmented heap
    out.buf.extend(b"Q1")
    for p in paths:
        stack = [(p, vfs.get(p))]
        while stack:
            path, node = stack.pop()
            if node.is_dir:
                rec_path(out, 68, path)
                names = list(node.children)
                names.sort()
                for i in range(len(names) - 1, -1, -1):
                    stack.append((path + "/" + names[i], node.children[names[i]]))
            else:
                rec_path(out, 70, path)
                pieces = dpieces(node.data)
                total = 0
                for sl in slices(pieces):
                    total += len(sl.encode())
                put_varint(out.buf, total)
                for sl in slices(pieces):
                    out.buf.extend(sl.encode())
                    if len(out.buf) >= 512:
                        for fr in out.frames(False):
                            yield fr
            if len(out.buf) >= 512:
                for fr in out.frames(False):
                    yield fr
    out.buf.append(69)
    for fr in out.frames(True):
        yield fr


def count(node):
    # (files, chars) below node
    nf = 0
    nc = 0
    stack = [node]
    while stack:
        n = stack.pop()
        if n.is_dir:
            stack.extend(n.children.values())
        else:
            nf += 1
            d = n.data
            if isinstance(d, str):
                nc += len(d)
            else:
                for piece in d:
                    nc += len(piece)
    return nf, nc


def create(sh, name, args):
    vfs = sh.vfs
    k = sh.k
    if not ok_name(name):
        raise ArError("bad archive name (a-z 0-9 . _ -, up to 24)")
    if not k.sync_ok:
        raise ArError("saving is off (storage did not load cleanly)")
    ents = read_index(vfs)
    used = {}
    for e in ents:
        used[e["id"]] = 1
        if e["name"] == name:
            raise ArError("archive exists: " + name)
    aid = -1
    for i in range(MAXID):
        if i not in used:
            aid = i
            break
    if aid < 0:
        raise ArError("too many archives (limit " + str(MAXID) + ")")
    paths = []
    for a in args:
        p = sh.resolve(a)
        check_path(vfs, p)
        if p == sh.cwd or sh.cwd.startswith(p + "/"):
            raise ArError("cannot archive the current directory: " + p)
        for q in paths:
            if p == q or p.startswith(q + "/") or q.startswith(p + "/"):
                raise ArError("overlapping paths: " + p + " " + q)
        paths.append(p)
    if not paths:
        raise ArError("nothing to archive")
    nfiles = 0
    raw = 0
    for p in paths:
        a, b = count(vfs.get(p))
        nfiles += a
        raw += b
    st = store_for(sh)
    stats = [0, 0]
    k.spin("Archiving " + name)
    k.release_spare()           # the writer's buffers need the contiguous block the kernel keeps
    try:
        for attempt in (0, 1):
            try:
                stats[0] = 0
                stats[1] = 0
                w = Writer(st)
                w.slot = aid
                for fr in encode(vfs, paths, stats):
                    w.feed(fr)
                    k.tick()
                w.finish()
                for x in w.readback():          # read it all back: length and checksum
                    pass
                break
            except MemoryError:
                if attempt:
                    raise
                import gc
                gc.collect()
    except (StorageError, MemoryError) as e:
        k.hold_spare()
        k.stop_spin()
        raise ArError("could not write the lists: " + str(e))
    k.hold_spare()
    ent = {"id": aid, "name": name, "blocks": w.nblocks, "bytes": w.nbytes, "sum": w.checksum(),
           "files": nfiles, "raw": raw, "paths": paths}
    ents.append(ent)
    try:
        write_index(vfs, ents)      # first: if this runs out of memory nothing has been removed yet
    except (MemoryError, VFSError):
        raise ArError("out of memory while updating the catalogue; nothing was archived")
    for p in paths:
        i = p.rfind("/")
        vfs.get(p[:i] or "/").children.pop(p[i + 1:])       # the files leave RAM here
    vfs.dirty = True            # A84AX saves after this module is gone
    return ent, stats
