import os
import unittest

from tools.evo_storage_codec import COMPRESSED_MAGIC, decode, encode, measure


class CodecTests(unittest.TestCase):
    def test_repetitive_text_saves_lists(self):
        data = (b"Arch84 storage experiment\n" * 100)
        blocks = encode(data)
        self.assertEqual(decode(blocks), data)
        self.assertTrue(any(int(b[0]) == COMPRESSED_MAGIC for b in blocks))
        self.assertGreater(measure(data)["lists_saved"], 0)
        self.assertTrue(all(len(b) <= 100 for b in blocks))

    def test_uncompressible_falls_back_without_loss(self):
        data = os.urandom(2000)
        self.assertEqual(decode(encode(data)), data)
        self.assertLessEqual(len(encode(data)), (len(data) + 484) // 485)

    def test_corrupt_header_is_rejected(self):
        blocks = encode(b"hello" * 200)
        blocks[0][1] = 99.5
        with self.assertRaises(ValueError):
            decode(blocks)


if __name__ == "__main__":
    unittest.main()
