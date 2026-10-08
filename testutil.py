"""Shared helpers for the desktop tests (not a test module)."""
import sys

sys.path.insert(0, ".")
from A84FS import *
from A84V1 import decode_fs, encode_fs, esc, sanitize
from A84CZ import *
from A84ST import *
from A84KN import *


class FakeTI:
    """Behaves like the probed calculator:
       * a list holds at most 100 elements;
       * plain ints come back as int, but ints above 2**29 sometimes come back
         exactly 1 too low (flaky=True reproduces ~0.1% of them);
       * half values (v + 0.5) come back as float and are exact up to ~46 bits;
       * recall of a missing list raises."""

    def __init__(self, cap=100, flaky=True):
        self.lists = {}
        self.cap = cap
        self.flaky = flaky
        self.big_ints = 0      # plain ints >= 2**29 ever stored (the v2 writer must never)
        self.stores = []       # names, in order
        self.fail_after = None  # raise on the Nth store_list call (counting from 0)
        self.hook = None       # hook(name, data) -> data, to inject corruption

    def store_list(self, name, data):
        if len(data) > self.cap:
            raise ValueError("List length > 100.")
        if self.fail_after is not None and len(self.stores) >= self.fail_after:
            raise ValueError("simulated calculator failure")
        if self.hook is not None:
            data = self.hook(name, list(data))
        out = []
        for x in data:
            if isinstance(x, float) and x != int(x):
                if abs(x) >= 2 ** 46:
                    x = float("%.14g" % x)
                out.append(x)
            else:
                v = int(x)
                if v >= 2 ** 29:
                    self.big_ints += 1
                    if self.flaky and (v * 2654435761) % 997 == 0:
                        v -= 1
                out.append(v)
        self.stores.append(name)
        self.lists[name] = out

    def recall_list(self, name):
        if name not in self.lists:
            raise NameError(name)
        return list(self.lists[name])


def ti_store(ti):
    return ListStore(ti.store_list, ti.recall_list, "ti-lists")


def save_vfs(store, vfs):
    """Run the real write path (stream -> writer -> verify -> commit)."""
    k = Kernel(MemStorage())
    k.storage = store
    store.progress = k.tick
    k.vfs = vfs
    return k.sync()


def put_v1(put, text, slot=0, flaky_checksum=0):
    """Write `text` the way the OLD (version 1) storage did: 2 chars per int
    element, 99 data elements per list, meta of plain ints."""
    nums = []
    i = 0
    while i < len(text):
        hi = ord(text[i])
        lo = ord(text[i + 1]) if i + 1 < len(text) else 0
        nums.append(hi * 256 + lo)
        i += 2
    blocks = []
    j = 0
    while j < len(nums):
        blocks.append([8484] + nums[j:j + 99])
        j += 99
    if not blocks:
        blocks.append([8484])
    for n, b in enumerate(blocks):
        put(block_name(slot, n), b)
    put("A84", [8484, 1, slot, len(blocks), len(text), checksum1(text) + flaky_checksum])
    return len(blocks)


def bad_version(ms):
    ms.d["A84"] = [8484.5, 7.5, 0.5, 1.5, 10.5, 1.5]
    ms.d["S0000"] = [8484.5, 0.5]


def walk(vfs):
    out = {}
    st = [("/", vfs.root)]
    while st:
        p, n = st.pop()
        if n.is_dir:
            out[p] = None
            for c in n.children:
                st.append((p.rstrip("/") + "/" + c, n.children[c]))
        else:
            out[p] = dtext(n.data)
    return out


def rnd_text(rng, n, alphabet=None):
    alphabet = alphabet or "abcdefghij klmnop\n\tqrstuvwxyz0123456789é€漢\\\""
    return "".join(rng.choice(alphabet) for _ in range(n))
