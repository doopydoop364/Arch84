"""No USB access: failure cases for scratch variable ownership."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import evo_usb

from tools import evo_scratch as scratch


class FakeEvo:
    build_appvar = staticmethod(evo_usb.build_appvar)
    cbor_loads = staticmethod(evo_usb.cbor_loads)
    def __init__(self):
        self.entries = []
        self.fail_send = False
        self.deleted = []

    def get_dynamic_info(self):
        return {"ram": 480000, "archive": 2100000}

    def send_ascii_data(self, kind, name, values, location, overwrite):
        assert not overwrite
        if self.fail_send:
            self.entries.append({"name": name, "type": 1, "archive": False, "size": 80})
            raise TimeoutError("partial response")
        self.entries.append({"name": name, "type": 1,
                             "archive": location == "archive", "size": 80})

    def delete_variable(self, name, kind):
        self.deleted.append((name, kind))
        self.entries = [row for row in self.entries if row["name"] != name]


class ScratchTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.journal = Path(directory.name) / "scratch.jsonl"
        self.evo = FakeEvo()
        self.snapshot = patch.object(scratch, "snapshot", side_effect=lambda evo: (evo.entries, {scratch.key(e): e for e in evo.entries}))
        self.read = patch.object(scratch, "read_one", return_value=b"verified-list")
        self.snapshot.start()
        self.read.start()
        self.addCleanup(self.snapshot.stop)
        self.addCleanup(self.read.stop)

    def test_create_and_verified_cleanup(self):
        result = scratch.create(self.evo, self.journal, "archive")
        self.assertEqual(result["name"], "Z84A")
        self.assertTrue(scratch.cleanup(self.evo, self.journal)["deleted"])
        self.assertEqual(self.evo.deleted, [("Z84A", 1)])
        self.assertEqual(scratch.read_journal(self.journal)[-1]["event"], "deleted")

    def test_name_collision_across_types(self):
        self.evo.entries.append({"name": "Z84R", "type": 15})
        with self.assertRaises(FileExistsError):
            scratch.create(self.evo, self.journal, "ram")
        self.assertFalse(self.journal.exists())

    def test_low_memory_stops_before_journal_and_write(self):
        with self.assertRaisesRegex(RuntimeError, "reserve"):
            scratch.create(self.evo, self.journal, "ram", min_ram=500000)
        self.assertFalse(self.evo.entries)

    def test_failed_send_is_indeterminate_and_not_cleaned(self):
        self.evo.fail_send = True
        with self.assertRaisesRegex(RuntimeError, "unknown"):
            scratch.create(self.evo, self.journal, "ram")
        self.assertEqual(scratch.read_journal(self.journal)[-1]["event"], "indeterminate_transfer")
        with self.assertRaisesRegex(RuntimeError, "ownership"):
            scratch.cleanup(self.evo, self.journal)
        self.assertFalse(self.evo.deleted)

    def test_changed_content_blocks_delete(self):
        scratch.create(self.evo, self.journal, "ram")
        with patch.object(scratch, "read_one", return_value=b"changed"):
            with self.assertRaisesRegex(RuntimeError, "content changed"):
                scratch.cleanup(self.evo, self.journal)
        self.assertFalse(self.evo.deleted)

    def test_changed_location_blocks_delete(self):
        scratch.create(self.evo, self.journal, "ram")
        self.evo.entries[0]["archive"] = True
        with self.assertRaisesRegex(RuntimeError, "location changed"):
            scratch.cleanup(self.evo, self.journal)
        self.assertFalse(self.evo.deleted)

    def test_probe_cleanup_requires_exact_source_and_readback(self):
        source = self.journal.parent / "EVOCOLD.py"
        source.write_text("print('probe')\n")
        self.evo.entries.append({"name": "EVOCOLD", "type": 15,
                                 "archive": False, "size": 40})
        payload = evo_usb.build_payload("EVOCOLD", source.read_text())
        container = payload + evo_usb.evo_checksum(payload).to_bytes(2, "big")
        with patch.object(scratch, "fetch_variable", side_effect=lambda evo, item, raw, output: output.write_bytes(container)), \
             patch.object(scratch, "validate_container"):
            result = scratch.cleanup_probe(self.evo, self.journal, source)
        self.assertTrue(result["deleted"])
        self.assertEqual(self.evo.deleted, [("EVOCOLD", 15)])

    def test_probe_cleanup_refuses_changed_program(self):
        source = self.journal.parent / "EVOCOLD.py"
        source.write_text("print('probe')\n")
        self.evo.entries.append({"name": "EVOCOLD", "type": 15,
                                 "archive": False, "size": 40})
        payload = evo_usb.build_payload("EVOCOLD", "print('other')\n")
        container = payload + evo_usb.evo_checksum(payload).to_bytes(2, "big")
        with patch.object(scratch, "fetch_variable", side_effect=lambda evo, item, raw, output: output.write_bytes(container)), \
             patch.object(scratch, "validate_container"):
            with self.assertRaisesRegex(RuntimeError, "differs"):
                scratch.cleanup_probe(self.evo, self.journal, source)
        self.assertFalse(self.evo.deleted)


if __name__ == "__main__":
    unittest.main()
