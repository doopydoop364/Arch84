"""Mock-only failure tests for the read-only Evo backup workflow."""
from contextlib import contextmanager
from pathlib import Path
import json
import tempfile
import unittest

import evo_usb
from tools.evo_backup import backup, validate_container, verify_backup
from tools.evo_research import long_read_timeout


@contextmanager
def fake_lock(timeout):
    yield


class FakeEvo:
    evo_checksum = staticmethod(evo_usb.evo_checksum)
    cbor_loads = staticmethod(evo_usb.cbor_loads)

    def __init__(self):
        self.entries = [{"name": "A84AA", "type": 15, "size": 40, "mem": True},
                        {"name": "A84AB", "type": 15, "size": 40, "mem": True}]
        self.fail = set()
        self.calls = []

    def list_files(self):
        self.calls.append("list")
        return self.entries

    def get_variable(self, name, kind, output):
        self.calls.append(name)
        if name in self.fail:
            raise TimeoutError("simulated disconnect")
        payload = evo_usb.build_payload(name, "print('" + name + "')\n")
        check = evo_usb.evo_checksum(payload)
        Path(output).write_bytes(payload + check.to_bytes(2, "big"))


class BackupTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.dest = Path(td.name) / "backup"
        self.evo = FakeEvo()

    def test_backup_and_offline_verify(self):
        result = backup(self.evo, fake_lock, self.dest)
        self.assertEqual(result["summary"], {"exported": 2, "failed": 0,
                                              "pending": 0, "restore_verified": False})
        self.assertEqual(verify_backup(self.evo, self.dest)["summary"]["exported"], 2)
        self.assertEqual(self.evo.calls, ["list", "A84AA", "A84AB"])

    def test_resume_retries_only_failed_variable(self):
        self.evo.fail.add("A84AB")
        result = backup(self.evo, fake_lock, self.dest)
        self.assertEqual(result["summary"]["failed"], 1)
        self.evo.fail.clear()
        again = backup(self.evo, fake_lock, self.dest, resume=True)
        self.assertEqual(again["summary"]["exported"], 2)
        self.assertEqual(self.evo.calls.count("A84AA"), 1)
        self.assertEqual(self.evo.calls.count("A84AB"), 2)

    def test_tampered_backup_blocks_resume(self):
        result = backup(self.evo, fake_lock, self.dest)
        path = self.dest / result["results"]["15:A84AA"]["file"]
        path.write_bytes(b"corrupted")
        with self.assertRaises(ValueError):
            backup(self.evo, fake_lock, self.dest, resume=True)
        self.assertEqual(self.evo.calls.count("A84AA"), 1)

    def test_changed_directory_blocks_resume(self):
        backup(self.evo, fake_lock, self.dest)
        self.evo.entries[0]["size"] += 1
        with self.assertRaisesRegex(RuntimeError, "directory changed"):
            backup(self.evo, fake_lock, self.dest, resume=True)

    def test_existing_destination_is_never_overwritten(self):
        backup(self.evo, fake_lock, self.dest)
        with self.assertRaises(FileExistsError):
            backup(self.evo, fake_lock, self.dest)

    def test_directory_timeout_leaves_no_partial_destination(self):
        self.evo.list_files = lambda: (_ for _ in ()).throw(TimeoutError("directory"))
        with self.assertRaises(TimeoutError):
            backup(self.evo, fake_lock, self.dest)
        self.assertFalse(self.dest.exists())

    def test_resume_adopts_verified_orphan_file_without_redownload(self):
        backup(self.evo, fake_lock, self.dest)
        manifest_path = self.dest / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["results"].pop("15:A84AA")
        manifest_path.write_text(json.dumps(manifest))
        result = backup(self.evo, fake_lock, self.dest, resume=True)
        self.assertEqual(result["summary"]["exported"], 2)
        self.assertEqual(self.evo.calls.count("A84AA"), 1)

    def test_timeout_override_applies_to_explicit_five_seconds(self):
        class Receiver:
            def recv_pkt(self, dev, session=None, timeout=5000):
                return timeout
        receiver = Receiver()
        original = receiver.recv_pkt
        with long_read_timeout(receiver):
            self.assertEqual(receiver.recv_pkt(None, timeout=5000), 30000)
        self.assertEqual(receiver.recv_pkt(None, timeout=5000), 5000)
        self.assertEqual(receiver.recv_pkt.__func__, original.__func__)

    def test_empty_builtin_list_and_settings_container_variants(self):
        def container(kind, fields):
            body = (b"\xbf" + evo_usb.cbor_text("metaData") + b"\xbf" +
                    evo_usb.cbor_text("type") + evo_usb.cbor_uint(kind) + b"\xff" +
                    fields + b"\xff")
            return body + evo_usb.evo_checksum(body).to_bytes(2, "big")
        empty = container(1, evo_usb.cbor_text("type") + evo_usb.cbor_uint(0) +
                          evo_usb.cbor_text("len") + evo_usb.cbor_uint(0))
        settings = container(12, evo_usb.cbor_text("data") + b"\x81\x01")
        self.assertIn("empty-list", validate_container(self.evo, empty, {"type": 1})["integrity"])
        self.assertIn("settings", validate_container(self.evo, settings, {"type": 12})["integrity"])

    def test_container_name_must_match_directory(self):
        payload = evo_usb.build_payload("A84AA", "print(1)\n")
        data = payload + evo_usb.evo_checksum(payload).to_bytes(2, "big")
        self.evo.directory_display_name = evo_usb.directory_display_name
        with self.assertRaisesRegex(ValueError, "name mismatch"):
            validate_container(self.evo, data, {"name": "A84AB", "type": 15})


if __name__ == "__main__":
    unittest.main()
