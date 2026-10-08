"""Regression tests added by the optimisation/bug-fix campaign
(docs/OPTIMIZATION_CAMPAIGN.md)."""
import random
import unittest

from testutil import *
import A84CZ
from A84CZ import lz_compress, lz_decompress, LZ_HASH


def colliding_trigrams():
    seen = {}
    for a in range(256):
        for b in range(0, 256, 7):
            for c in range(0, 256, 13):
                h = (a * 5 + b * 31 + c * 131) & (LZ_HASH - 1)
                if h in seen and seen[h] != (a, b, c):
                    return seen[h], (a, b, c)
                seen[h] = (a, b, c)


class LzHashTests(unittest.TestCase):
    def test_hash_collision_is_verified(self):
        t1, t2 = colliding_trigrams()
        d = bytes(t1) + b"xyz" + bytes(t2) + b"xyz" + bytes(t1) + bytes(t2)
        self.assertEqual(lz_decompress(lz_compress(d), len(d)), d)

    def test_roundtrip_boundaries(self):
        rng = random.Random(84)
        for n in list(range(0, 40)) + [255, 256, 1023, 1024, 1025, 2047, 2048, 2049, 4097]:
            for kind in range(4):
                if kind == 0:
                    d = bytes(rng.randrange(256) for _ in range(n))
                elif kind == 1:
                    d = bytes([rng.randrange(3)] * n)
                elif kind == 2:
                    d = (b"abcabcabd" * (n // 9 + 1))[:n]
                else:
                    d = bytes(rng.choice(b"ab\n ") for _ in range(n))
                c = lz_compress(d)
                self.assertEqual(lz_decompress(c, len(d)), d, (n, kind))

    def test_incompressible_overhead_bounded(self):
        rng = random.Random(1)
        d = bytes(rng.randrange(256) for _ in range(1024))
        self.assertLessEqual(len(lz_compress(d)), 1024 + 1024 // 8 + 2)

    def test_text_ratio_not_worse_than_pinned(self):
        d = open("A84SH.py", "rb").read()[:1024]
        self.assertLess(len(lz_compress(d)), 740)


if __name__ == "__main__":
    unittest.main()
