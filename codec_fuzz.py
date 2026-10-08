"""Codec round-trip fuzzer for CPython and MicroPython (deterministic seeds).

    python3 codec_fuzz.py [first_seed [count]]
    micropython -X heapsize=N codec_fuzz.py [first_seed [count]]

Random trees (unicode, empty/boundary/big files, edits of factory paths) ->
fs_stream -> decode_stream -> same_tree, plus lz and pack5 round trips. Prints a
digest of every encoded stream: it must be identical on both interpreters
(the saved format must not depend on the runtime).
"""
import sys
sys.path.insert(0, ".")
from A84FS import VFS, dnew
from A84CZ import fs_stream, decode_stream, same_tree, lz_compress, lz_decompress
from A84ST import pack5, unpack5

ALPHA = "abcdefghij klmnop\n\tqrstuvwxyz0123456789é€漢\\\""
SIZES = (0, 1, 2, 5, 255, 256, 511, 512, 513, 1023, 1024, 1025, 1500, 2047, 2048, 2049, 3000)


class Rng:
    def __init__(self, seed):
        self.s = (seed * 2654435761 + 99) & 0x7fffffff

    def n(self, k):
        self.s = (self.s * 1103515245 + 12345) & 0x7fffffff
        return (self.s >> 8) % k


def text(r, n):
    mode = r.n(4)
    if mode == 0:
        return "".join(ALPHA[r.n(len(ALPHA))] for _ in range(n))
    if mode == 1:
        return "ab" * (n // 2) + "a" * (n % 2)
    if mode == 2:
        return ("hello world\n" * (n // 12 + 1))[:n]
    return "".join(chr(32 + r.n(90)) for _ in range(n))


def digest(b):
    x = 5381
    for c in b:
        x = (x * 33 + c) & 0xffffff
    return x


def tree(r):
    v = VFS()
    v.reset_default()
    dirs = ["/", "/tmp", "/home/evo", "/etc", "/usr/bin"]
    for _ in range(r.n(12)):
        d = dirs[r.n(len(dirs))]
        nm = "n" + str(r.n(30)) + ("é" if r.n(5) == 0 else "")
        p = d.rstrip("/") + "/" + nm
        try:
            if r.n(4) == 0:
                v.mkdir(p)
                dirs.append(p)
            else:
                v.write(p, text(r, SIZES[r.n(len(SIZES))]))
        except Exception:
            pass
    if r.n(4) == 0:
        v.write("/etc/hostname", text(r, r.n(20)))      # edit a factory file
    if r.n(5) == 0:
        try:
            v.remove("/etc/profile")                    # delete a factory file
        except Exception:
            pass
    return v


def main():
    a = [int(x) for x in sys.argv[1:]]
    first, count = (a + [1, 40][len(a):])[:2]
    bad = 0
    for seed in range(first, first + count):
        r = Rng(seed)
        v = tree(r)
        stream = bytearray()
        for fr in fs_stream(v, [0, 0]):
            stream.extend(fr)
        back = decode_stream([bytes(stream)])
        ok = same_tree(v, back)
        # lz + pack5 on the same bytes
        sb = bytes(stream[:2000])
        ok = ok and lz_decompress(lz_compress(sb), len(sb)) == sb
        pad = sb + bytes((-len(sb)) % 5)
        ok = ok and bytes(unpack5(pack5(pad))) == pad
        if not ok:
            bad += 1
        print(seed, len(stream), digest(stream), "ok" if ok else "BAD")
    print("codec_fuzz bad", bad)


main()
