# A84V1: writer for the OLD (version 1) text filesystem format. The device only
# READS v1 (A84FS.decode_fs, for migration); this writer is used by the tests
# and the on-device self test, so it is not loaded in normal operation.
from A84FS import FS_VERSION, dtext


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
