import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

from tools.evo_firmware_inspect import inspect, parse_image


class FirmwareInspectorTests(unittest.TestCase):
    def test_mcuboot_hash_and_signature_presence(self):
        body = b"sample" * 10
        head = struct.pack("<IIHHIIBBHII", 0x96F3B83D, 0, 32, 0,
                           len(body), 0, 7, 1, 0, 1, 0)
        digest = hashlib.sha256(head + body).digest()
        entries = struct.pack("<HH", 0x10, 32) + digest + struct.pack("<HH", 0x23, 4) + b"sign"
        image = head + body + struct.pack("<HH", 0x6907, len(entries) + 4) + entries
        parsed = parse_image(image, 0)
        self.assertTrue(parsed["sha256_matches_tlv"])
        self.assertTrue(parsed["signature_tlv_present"])
        damaged = bytearray(image)
        damaged[35] ^= 1
        self.assertFalse(parse_image(damaged, 0)["sha256_matches_tlv"])

    def test_invalid_header_rejected(self):
        self.assertIsNone(parse_image(b"short", 0))

    def test_vector_candidate_and_runtime_markers_are_only_static_hints(self):
        body = struct.pack("<II", 0x300007F8, 0x100B1ADD) + b"micropython\x00heap_lock"
        head = struct.pack("<IIHHIIBBHII", 0x96F3B83D, 0, 32, 0,
                           len(body), 0, 7, 1, 0, 1, 0)
        digest = hashlib.sha256(head + body).digest()
        entry = struct.pack("<HH", 0x10, 32) + digest
        image = head + body + struct.pack("<HH", 0x6907, len(entry) + 4) + entry
        parsed = parse_image(image, 0)
        self.assertEqual(parsed["vector_candidate"]["initial_stack_word"], "0x300007f8")
        self.assertEqual(parsed["body_markers"]["micropython"], [8])
        self.assertEqual(parsed["body_markers"]["heap_lock"], [20])

    def test_protected_dependency_and_security_counter(self):
        body = b"firmware"
        protected_entries = (struct.pack("<HH", 0x40, 12) +
                             bytes((2, 0, 0, 0)) + struct.pack("<BBHI", 7, 1, 3, 42) +
                             struct.pack("<HHI", 0x50, 4, 9))
        protected = struct.pack("<HH", 0x6908, len(protected_entries) + 4) + protected_entries
        head = struct.pack("<IIHHIIBBHII", 0x96F3B83D, 0, 32, len(protected),
                           len(body), 0, 7, 1, 0, 1, 0)
        signed_area = head + body + protected
        digest = hashlib.sha256(signed_area).digest()
        entries = (struct.pack("<HH", 0x10, 32) + digest +
                   struct.pack("<HH", 0x01, 32) + b"k" * 32)
        image = signed_area + struct.pack("<HH", 0x6907, len(entries) + 4) + entries
        parsed = parse_image(image, 0)
        self.assertTrue(parsed["sha256_matches_tlv"])
        self.assertEqual(parsed["dependencies"], [{"image_id": 2,
                                                    "minimum_version": "7.1.3.42"}])
        self.assertEqual(parsed["security_counters"], [9])
        self.assertEqual(parsed["keyhashes"], [b"k".hex() * 32])
        self.assertEqual(parsed["image_end"], len(image))

    def test_zip_inventory_without_extracting(self):
        body = b"example"
        head = struct.pack("<IIHHIIBBHII", 0x96F3B83D, 0, 32, 0,
                           len(body), 0, 7, 1, 0, 1, 0)
        digest = hashlib.sha256(head + body).digest()
        entry = struct.pack("<HH", 0x10, 32) + digest
        image = head + body + struct.pack("<HH", 0x6907, len(entry) + 4) + entry
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.84b2"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("METADATA", "bundle_target_prodid:23\n")
                archive.writestr("package.84pk2", image)
            result = inspect(path)
        self.assertEqual(result["metadata"]["bundle_target_prodid"], "23")
        self.assertEqual(len(result["images"]), 1)
        self.assertTrue(result["images"][0]["sha256_matches_tlv"])
        self.assertFalse(result["signature_verified"])


if __name__ == "__main__":
    unittest.main()
