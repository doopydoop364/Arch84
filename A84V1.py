# A84V1: writer for the OLD (version 1) text filesystem format. The device only
# READS v1 (decode_fs below, for migration, loaded only when a v1 save is found);
# the writer is used by the tests and the on-device self test.
from A84FS import FS_VERSION, VFS, VFSError, dtext, normalize, unesc


def esc(s):
    s = s.replace("\\", "\\\\")
    s = s.replace("\n", "\\n")
    s = s.replace("\t", "\\t")
    return s.replace("\r", "\\r")


def sanitize(text):
    # storage only keeps codes 0-255
    out = []
    for c in text:
        if ord(c) < 256:
            out.append(c)
        else:
            out.append("?")
    return "".join(out)


def encode_fs(vfs):
    lines = ["A84FS" + str(FS_VERSION)]
    _encode_dir(vfs.root, "", lines)
    lines.append("END")
    return sanitize("\n".join(lines) + "\n")


def _encode_dir(node, prefix, lines):
    names = list(node.children.keys())
    names.sort()
    for name in names:
        child = node.children[name]
        path = prefix + "/" + name
        if child.is_dir:
            lines.append("D\t" + esc(path))
            _encode_dir(child, path, lines)
        else:
            lines.append("F\t" + esc(path) + "\t" + esc(dtext(child.data)))


def decode_fs(text):
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines or not lines[0].startswith("A84FS"):
        raise ValueError("bad header")
    if lines[0] != "A84FS" + str(FS_VERSION):
        raise ValueError("unsupported fs version " + lines[0][5:])
    if lines[-1] != "END":
        raise ValueError("missing END (truncated)")
    vfs = VFS()
    for line in lines[1:-1]:
        f = line.split("\t")
        try:
            if f[0] == "D" and len(f) == 2:
                path = unesc(f[1])
                _check_path(path)
                vfs.mkdir(path)
            elif f[0] == "F" and len(f) == 3:
                path = unesc(f[1])
                _check_path(path)
                if vfs.exists(path):
                    raise ValueError("duplicate " + path)
                vfs.write(path, unesc(f[2]))
            else:
                raise ValueError("bad record")
        except VFSError as e:
            raise ValueError("bad tree: " + str(e))
    vfs.dirty = False
    return vfs


def _check_path(path):
    if path == "/" or normalize(path, "/", "/") != path:
        raise ValueError("bad path " + path)
