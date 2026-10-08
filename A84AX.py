# A84AX: the `archive` command: extract, delete, check and the command line
# (Arch84 module, lazily loaded). Library and `archive create` are in A84AR.
from A84FS import StorageError, VFSError
from A84CD import COMMANDS, unload
from A84AI import ArError, find, read_index, store_for, write_index


def delete(sh, name):
    e = find(sh.vfs, name)
    write_index(sh.vfs, [y for y in read_index(sh.vfs) if y["name"] != name])
    sh.vfs.dirty = True
    return e


def check(sh, e):
    st = store_for(sh)
    n = 0
    for chunk in st._stream(e["id"], e["blocks"], e["bytes"], e["sum"]):
        n += len(chunk)
    return n


def cmd_archive(sh, args):
    post = None
    try:
        status, post = run(sh, args)
    finally:
        # the packer / decoder are big: drop them before the filesystem is saved
        unload("archive", "A84AX", "A84AR", "A84AE", "A84AI")
    if post is None:
        sh.k.stop_spin()
        return status
    return status + commit(sh, post)


def commit(sh, post):
    # save the new state; only after that are the lists of a deleted/extracted archive cleared
    k = sh.k
    err = ""
    for attempt in (0, 1):
        try:
            import gc
            gc.collect()
            k.sync()
            err = ""
            break
        except (StorageError, MemoryError) as x:
            err = str(x)
    k.stop_spin()
    if err:
        # Not fatal: lists and catalogue exist, the saved copy still has the old state.
        # The next sync (or exit) commits; a power cut before that changes nothing.
        sh.err("archive: warning: not saved yet (" + err + "): run sync")
        return 0
    if post[0] == "shrink":
        from A84AI import shrink, store_for
        shrink(store_for(sh), post[1])
        unload("archive", "A84AI")
    return 0


def run(sh, args):
    # -> (status, what to save afterwards or None)
    if not args:
        sh.err("usage: archive create NAME PATH... | extract [-k] NAME | list | check [NAME] | delete NAME")
        return 1, None
    op = args[0]
    rest = args[1:]
    post = None
    try:
        if op in ("create", "c"):
            if len(rest) < 2:
                raise ArError("usage: archive create NAME PATH...")
            from A84AR import create            # only creating needs the packer
            e, stats = create(sh, rest[0], rest[1:])
            sh.out("archived " + str(e["files"]) + " files (" + str(e["raw"]) + " chars -> " + str(e["bytes"])
                   + " bytes in " + str(e["blocks"]) + " lists) as " + e["name"] + "\n")
            post = ("save",)
        elif op in ("extract", "x"):
            keep = "-k" in rest
            names = [a for a in rest if a != "-k"]
            if len(names) != 1:
                raise ArError("usage: archive extract [-k] NAME")
            from A84AE import extract           # only extracting needs the decoder
            e = extract(sh, names[0], keep)
            sh.out("restored " + str(e["files"]) + " files from " + e["name"] + "\n")
            post = ("save",)
            if not keep:
                post = ("shrink", e)
        elif op in ("list", "l"):
            for e in read_index(sh.vfs):
                sh.out(e["name"] + ": " + str(e["files"]) + " files, " + str(e["raw"]) + " chars, "
                       + str(e["bytes"]) + " bytes, lists Q" + str(e["id"]) + "xxx\n")
                for p in e["paths"]:
                    sh.out("  " + p + "\n")
        elif op in ("check", "t"):
            ents = read_index(sh.vfs)
            if rest:
                ents = [find(sh.vfs, rest[0])]
            bad = 0
            for e in ents:
                try:
                    check(sh, e)
                    sh.out(e["name"] + ": ok\n")
                except (StorageError, ValueError) as x:
                    bad += 1
                    sh.err(e["name"] + ": " + str(x))
            return (1 if bad else 0), None
        elif op in ("delete", "d"):
            if len(rest) != 1:
                raise ArError("usage: archive delete NAME")
            e = delete(sh, rest[0])
            sh.out("deleted " + rest[0] + "\n")
            post = ("shrink", e)
        else:
            raise ArError("unknown operation: " + op)
    except ArError as x:
        sh.err("archive: " + str(x))
        return 1, None
    except VFSError as x:
        sh.err("archive: " + str(x))
        return 1, None
    except MemoryError:
        sh.err("archive: out of memory")
        return 1, None
    return 0, post


COMMANDS["archive"] = cmd_archive
