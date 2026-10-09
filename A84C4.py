# A84C4: du df free mount umount uptime (Arch84 module, split from A84C2 so each lazily loaded piece
# has a small compile-time memory peak). Registers itself into COMMANDS.

from A84FS import dlen, ms_since, now_ms
from A84ST import DATA_ELEMS, ELEM_BYTES
from A84CD import COMMANDS, join, pad


def show_path(arg, root, p):
    if root == "/":
        return p
    return arg.rstrip("/") + p[len(root):]


def cmd_du(sh, args):
    summary = False
    paths = []
    for a in args:
        if a == "-s":
            summary = True
        else:
            paths.append(a)
    if not paths:
        paths = ["."]
    st = 0
    for arg in paths:
        root = sh.resolve(arg)
        node = sh.vfs.get(root)
        if node is None:
            sh.err("du: cannot access '" + arg + "': No such file or directory")
            st = 1
            continue
        order = []
        stack = [root]
        while stack:
            p = stack.pop()
            order.append(p)
            if sh.vfs.isdir(p):
                for n in sh.vfs.listdir(p):
                    stack.append(join(p, n))
        sizes = {}
        for k in range(len(order) - 1, -1, -1):
            p = order[k]
            nd = sh.vfs.get(p)
            own = 0
            if not nd.is_dir:
                own = dlen(nd.data)
            sizes[p] = sizes.get(p, 0) + own
            if p != root:
                par = p[:p.rfind("/")]
                if par == "":
                    par = "/"
                sizes[par] = sizes.get(par, 0) + sizes[p]
        if summary or not node.is_dir:
            sh.out(pad(sizes[root], 6) + " " + arg + "\n")
        else:
            for k in range(len(order) - 1, -1, -1):
                p = order[k]
                if sh.vfs.isdir(p):
                    sh.out(pad(sizes[p], 6) + " " + show_path(arg, root, p) + "\n")
    return st


def cmd_df(sh, args):
    sh.k.release_spare()        # same buffers as a save: use the reserved block
    try:
        from A84CY import fs_measure
        raw, stored = fs_measure(sh.vfs)
    finally:
        sh.k.hold_spare()
    per = DATA_ELEMS * ELEM_BYTES
    sh.out("Filesystem  " + pad("Raw", 6) + " " + pad("Stored", 6) + " "
           + pad("Blk", 3) + "\n")
    sh.out("rootfs      " + pad(raw, 6) + " " + pad(stored, 6) + " "
           + pad((stored + per - 1) // per, 3) + "\n")


def cmd_free(sh, args):
    try:
        import gc
        gc.collect()
        f = gc.mem_free()
        a = gc.mem_alloc()
    except (ImportError, AttributeError):
        sh.err("free: no memory information available")
        return 1
    sh.out("    " + pad("total", 8) + pad("used", 8) + pad("free", 8) + "\n")
    sh.out("Mem:" + pad(f + a, 8) + pad(a, 8) + pad(f, 8) + "\n")
    if "-l" in args:
        sh.out("largest block: " + str(largest_block(f)) + "\n")


def largest_block(top):
    # biggest bytearray the heap can give right now (fragmentation shows as a small number
    # next to a large free count); found by bisection, nothing is kept
    import gc
    lo = 0
    hi = top
    while hi - lo > 64:
        mid = (lo + hi) // 2
        try:
            b = bytearray(mid)
            b = None
            lo = mid
        except MemoryError:
            hi = mid
        gc.collect()
    return lo


def cmd_mount(sh, args):
    if args:
        sh.err("mount: only listing is supported")
        return 1
    sh.out("rootfs on / type vfs (rw)\n")
    if sh.k.storage.kind == "ti-lists":
        sh.out("storage: ti-lists (A84, S0/S1)\n")
    else:
        sh.out("storage: memory (not saved)\n")


def cmd_umount(sh, args):
    if not args:
        sh.err("umount: missing operand")
        return 1
    if args[0] == "/":
        sh.err("umount: /: target is busy")
    else:
        sh.err("umount: " + args[0] + ": not mounted")
    return 1


def hms(ms):
    s = ms // 1000
    return str(s // 3600) + ":" + ("0" + str(s // 60 % 60))[-2:] + ":" + ("0" + str(s % 60))[-2:]


def cmd_uptime(sh, args):
    up = ms_since(sh.k.t0)
    now = now_ms()
    if up is None or now is None:
        sh.err("uptime: no clock available")
        return 1
    sh.out("up " + hms(up) + "\n")
    sh.out("calculator ticks " + hms(now) + "\n")

COMMANDS.update({
    "du": cmd_du, "df": cmd_df, "free": cmd_free, "mount": cmd_mount,
    "umount": cmd_umount, "uptime": cmd_uptime,
})
