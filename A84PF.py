# A84PF: generated /proc and /dev files (Arch84 module, loaded on first access).
# Nothing here is ever stored: VFS.get() asks node() for paths the saved tree does not have.
from A84FS import Node, VERSION

PROC = ("dmesg", "meminfo", "modules", "mounts", "uptime", "version")


def node(k, path):
    # path "/proc" or "/dev" -> list of names; a file path -> Node or None
    if path == "/proc":
        return list(PROC)
    if path == "/dev":
        return ["null"]
    if path == "/dev/null":
        return Node(False, "")
    if path[:6] != "/proc/" or path[6:] not in PROC:
        return None
    return Node(False, text(k, path[6:]))


def text(k, name):
    if name == "dmesg":
        return "\n".join(k.boot_msgs) + "\n"        # the lines printed while this session booted
    if name == "version":
        return "Arch84 " + VERSION + " (MicroPython) " + k.hostname() + "\n"
    if name == "uptime":
        from A84FS import ms_since, now_ms
        up = ms_since(k.t0)
        now = now_ms()
        if up is None or now is None:
            return "unavailable\n"
        return "%d.%02d %d.%02d\n" % (up // 1000, up % 1000 // 10, now // 1000, now % 1000 // 10)
    if name == "mounts":
        s = "rootfs / vfs rw 0 0\n"
        s += "storage " + k.storage.kind + "\n"
        return s
    if name == "modules":
        import sys
        names = [m for m in sys.modules if m[:3] == "A84" or m == "ARCH84"]
        names.sort()
        return "\n".join(names) + "\n"
    # meminfo
    try:
        import gc
        free = gc.mem_free()
        used = gc.mem_alloc()
    except (ImportError, AttributeError):
        return "unavailable\n"
    return ("MemTotal: %d\nMemFree: %d\nMemUsed: %d\nNodes: %d\n" % (free + used, free, used, k.vfs.count()))
