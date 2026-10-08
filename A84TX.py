# A84TX: selftest storage/codec checks (split from A84TS; loaded only by selftest)
from A84FS import SPLIT, VFS, dlen
from A84V1 import encode_fs
from A84CZ import (decode_stream, fs_measure, fs_stream, lz_compress,
    lz_decompress, same_tree)
from A84ST import ListStore, MemStorage, block_name, checksum1, pack5, unpack5
from A84KN import Kernel


# ---- storage / codec checks: run in memory, so they also exercise this
# firmware's str.encode, bytes.decode, bytearray, generators and big ints

def lcg(n, seed):
    out = bytearray()
    x = seed
    for i in range(n):
        x = (x * 75 + 74) % 65537
        out.append(x & 255)
    return bytes(out)


def sample_fs(big=130):
    # small on purpose: this runs on a calculator with ~20 KB of heap left;
    # big=130 -> a 2080-char file, enough to cross the 2048-byte frame boundary
    v = VFS()
    v.reset_default()
    v.mkdir("/home/evo/notes")
    for i in range(3):
        v.write("/home/evo/notes/n" + str(i) + ".txt",
                ("note " + str(i) + ": the quick brown fox\n") * (4 + i))
    v.write("/home/evo/u", "a\u00e9\u20ac\u6f22" * 12)
    v.write("/home/evo/e", "")
    v.write("/home/evo/big", "0123456789abcdef" * big)
    v.remove("/home/evo/.ashrc")
    v.write("/etc/hostname", "testbox\n")
    return v


def c_utf8():
    s = "a\u00e9\u20ac\u6f22"
    b = s.encode()
    return len(b) == 9 and b.decode() == s


def c_pack():
    for bs in (b"\xff" * 5, b"\x80\x00\x00\x00\x01", b"abcde", b"\x00" * 5):
        if bytes(unpack5(pack5(bs))) != bs:
            return False
    return True


def c_lz():
    for d in (b"", b"a", b"abcabc" * 50, lcg(300, 1), bytes(2048)):
        if lz_decompress(lz_compress(d), len(d)) != d:
            return False
    return len(lz_compress(b"abcabc" * 50)) < 100


def c_codec():
    v = sample_fs()
    return same_tree(decode_stream(fs_stream(v)), v)


def c_ratio():
    raw, stored = fs_measure(sample_fs())
    return stored < raw // 2


def c_store():
    ms = MemStorage()
    k = Kernel(ms)
    k.vfs = sample_fs()
    k.sync()
    k2 = Kernel(ms)
    return same_tree(k2.vfs, k.vfs) and k2.sync_ok


def c_corrupt():
    ms = MemStorage()
    k = Kernel(ms)
    k.vfs = sample_fs()
    k.sync()
    slot = int(ms.d["A84"][2])
    ms.d["S" + str(slot) + "000"][2] += 1.0
    return not Kernel(ms).sync_ok


def c_migrate():
    ms = MemStorage()
    v = sample_fs(8)
    v.write("/home/evo/u", "a\u00e9" * 12)     # v1 could only hold chars up to 255
    text = encode_fs(v)
    nums = []
    for i in range(0, len(text), 2):
        lo = 0
        if i + 1 < len(text):
            lo = ord(text[i + 1])
        nums.append(ord(text[i]) * 256 + lo)
    n = 0
    for i in range(0, len(nums), 99):
        ms.d[block_name(0, n)] = [8484] + nums[i:i + 99]
        n += 1
    ms.d["A84"] = [8484, 1, 0, n, len(text), checksum1(text)]
    k = Kernel(ms)
    ok = k.sync_ok and k.vfs.dirty and same_tree(k.vfs, v)
    k.sync()
    k2 = Kernel(ms)
    return ok and int(ms.d["A84"][1]) == 2 and same_tree(k2.vfs, k.vfs)


def c_big_codec():
    v = VFS()
    v.reset_default()
    v.write("/home/evo/big", "0123456789abcdef\n" * 200)       # 3400 chars -> pieces
    d = v.get("/home/evo/big").data
    if isinstance(d, str) or len(d) != (3400 + SPLIT - 1) // SPLIT or len(d[0]) != SPLIT or dlen(d) != 3400:
        return False
    back = decode_stream(fs_stream(v))
    return same_tree(back, v) and back.get("/home/evo/big").data == d


def c_big_share():
    v = VFS()
    v.reset_default()
    v.write("/tmp/a", "q" * 3000)
    v.copyfile("/tmp/a", "/tmp/b")
    v.append("/tmp/b", "x")
    a = v.get("/tmp/a").data
    return v.size("/tmp/a") == 3000 and v.size("/tmp/b") == 3001 and a[0] is v.get("/tmp/b").data[0]


CHECKS = [
    ("utf8 encode/decode", c_utf8), ("pack5 round trip", c_pack),
    ("lzss round trip", c_lz), ("fs codec round trip", c_codec),
    ("fs compresses >2x", c_ratio), ("store + reload", c_store),
    ("corruption detected", c_corrupt), ("v1 -> v2 migration", c_migrate),
    ("big file pieces", c_big_codec), ("big file cp shares", c_big_share),
]


def real_scratch_check(ti):
    # writes a sample filesystem through the REAL store_list/recall_list into
    # scratch lists ZTM / T0xxx (never the real A84 / S0xxx), twice to flip
    # slots, and verifies the read back. The caller deletes the lists after.
    st = ListStore(ti.store_list, ti.recall_list, "ti-lists", "ZTM", "T")
    v = sample_fs()
    for rnd in range(2):
        k = Kernel(MemStorage())
        k.storage = st
        k.vfs = v
        k.sync()
        got = st.read()
        back = decode_stream(got[1])
        if got[0] != 2 or not same_tree(back, v):
            return False
        v.write("/home/evo/round" + str(rnd), "x" * (100 * (rnd + 1)))
    return True
