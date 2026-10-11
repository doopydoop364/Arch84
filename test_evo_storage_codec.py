import os
import unittest

from tools.evo_storage_codec import COMPRESSED_MAGIC, RAW_MAGIC, decode, encode, measure


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

    def test_compressed_payload_corruption_is_detected(self):
        blocks = encode(b"compressible payload\n" * 60)
        self.assertEqual(int(blocks[0][0]), COMPRESSED_MAGIC)
        blocks[0][4] += 1
        with self.assertRaises((ValueError, OverflowError)):
            decode(blocks)

    def test_compressed_checksum_and_size_limit(self):
        blocks = encode(b"x" * 700)
        blocks[0][3] += 1
        with self.assertRaisesRegex(ValueError, "checksum"):
            decode(blocks)
        blocks = encode(b"x" * 700)
        blocks[0][2] = 900 * 1024 + 10.5
        with self.assertRaisesRegex(ValueError, "size"):
            decode(blocks)

    def test_raw_fallback_is_existing_list_format(self):
        data = os.urandom(485)
        block = encode(data)[0]
        self.assertEqual(int(block[0]), RAW_MAGIC)
        self.assertEqual(len(block), 100)
        self.assertEqual(decode([block]), data)

    def test_tampered_padding_is_rejected(self):
        block = encode(b"a")[0]
        block[-1] += 1
        with self.assertRaisesRegex(ValueError, "padding"):
            decode([block])


if __name__ == "__main__":
    unittest.main()
