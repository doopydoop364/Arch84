# A84FK: fsck - check the saved filesystem, the archive lists and the packages
# (Arch84 module, lazily loaded). Registers itself into COMMANDS.
#   fsck       report problems (exit status 1 if there are any)
#   fsck -r    also repair what is safe: leftover archive lists, missing system files
from A84FS import DEFAULT_DIRS, StorageError, VFSError
from A84CD import COMMANDS, unload
from A84PD import DBDIR
from A84AI import read_index, store_for


def check_main(sh, out):
    st = sh.k.storage
    try:
        got = st.read()
        if got is None:
            out.append("filesystem: nothing saved yet")
            return 0
        n = 0
        for chunk in got[1]:
            n += len(chunk)
        out.append("filesystem: saved copy ok (" + str(n) + " bytes)")
        return 0
    except StorageError as e:
        out.append("filesystem: SAVED COPY DAMAGED: " + str(e))
        return 1
    except MemoryError:
        out.append("filesystem: not enough memory to verify the saved copy")
        return 0


def check_archives(sh, out, repair):
    bad = 0
    st = store_for(sh)
    ents = read_index(sh.vfs)
    known = {}
    for e in ents:
        known[e["id"]] = e
    for aid in range(10):
        first = st._recall(st.bname(aid, 0))
        e = known.get(aid)
        if e is not None:
            try:
                n = 0
                for chunk in st._stream(e["id"], e["blocks"], e["bytes"], e["sum"]):
                    n += len(chunk)
                out.append("archive " + e["name"] + ": ok (" + str(e["files"]) + " files)")
            except (StorageError, ValueError) as x:
                bad += 1
                out.append("archive " + e["name"] + ": DAMAGED: " + str(x))
        elif first is not None and len(first) > 1:
            bad += 1
            out.append("lists Q" + str(aid) + "xxx: leftover data of no archive")
            if repair:
                i = 0
                while st._recall(st.bname(aid, i)) is not None and i < 999:
                    st._put(st.bname(aid, i), [8484.5])
                    i += 1
                out.append("  cleared " + str(i) + " lists")
    return bad


def check_packages(sh, out):
    bad = 0
    vfs = sh.vfs
    if not vfs.isdir(DBDIR):
        return 0
    names = vfs.listdir(DBDIR)
    missing = 0
    for n in names:
        if not vfs.isfile(DBDIR + "/" + n + "/files"):
            bad += 1
            out.append("package " + n + ": database entry incomplete")
            continue
        for line in vfs.lines(DBDIR + "/" + n + "/files"):
            f = line.split("\t")
            if f[0] == "f" and len(f) == 4 and not vfs.isfile(f[1]):
                missing += 1
                out.append("package " + n + ": missing " + f[1])
    out.append("packages: " + str(len(names)) + " installed, " + str(missing) + " files missing")
    return bad + missing


def check_system(sh, out, repair):
    vfs = sh.vfs
    miss = [d for d in DEFAULT_DIRS if not vfs.isdir(d)]
    for f in ("/etc/hostname", "/etc/profile"):
        if not vfs.isfile(f):
            miss.append(f)
    if not miss:
        out.append("system files: ok")
        return 0
    out.append("system files missing: " + " ".join(miss))
    if repair:
        out.append("  repaired " + str(sh.k.fix_system_files()))
    return 1


def cmd_fsck(sh, args):
    try:
        return run(sh, args)
    finally:
        unload("fsck", "A84FK", "A84PD", "A84AI")


def run(sh, args):
    repair = "-r" in args
    for a in args:
        if a != "-r":
            sh.err("usage: fsck [-r]")
            return 2
    out = []
    bad = check_system(sh, out, repair)
    try:
        bad += check_main(sh, out)
        bad += check_archives(sh, out, repair)
        bad += check_packages(sh, out)
    except (VFSError, StorageError) as e:
        out.append("error: " + str(e))
        bad += 1
    try:
        import gc
        gc.collect()
        out.append("memory: " + str(gc.mem_free()) + " bytes free")
    except (ImportError, AttributeError):
        pass
    for line in out:
        sh.out(line + "\n")
    if bad:
        sh.out(str(bad) + " problem" + ("s" if bad != 1 else "") + (" remain\n" if repair else " found (fsck -r repairs what is safe)\n"))
        return 1
    sh.out("no problems found\n")
    return 0


COMMANDS["fsck"] = cmd_fsck
