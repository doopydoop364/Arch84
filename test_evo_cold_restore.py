import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock
from contextlib import nullcontext
from types import SimpleNamespace
import hashlib
import shutil

import evo_usb
from tools.evo_cold_restore import inspect_container, restore, restore_from_backup
from tools.evo_backup import filename
import json


class ColdRestoreTests(unittest.TestCase):
    def fake_device(self, files=None):
        return SimpleNamespace(evo_checksum=evo_usb.evo_checksum,
                               cbor_loads=evo_usb.cbor_loads,
                               _decode_custom_name=evo_usb._decode_custom_name,
                               list_files=Mock(return_value=files or []),
                               send_var_file=Mock(), get_variable=Mock())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "X0002.8xl2"
        token = b"\x36\xe8\x17\xe8\x01\xe4\x01\xe4\x01\xe4\x03\xe4\x00\x00"
        body = (b"\xbf" + evo_usb.cbor_text("metaData") + b"\xbf" +
                evo_usb.cbor_text("type") + evo_usb.cbor_uint(1) +
                evo_usb.cbor_text("name") + evo_usb.cbor_bytes(token) + b"\xff" +
                evo_usb.cbor_text("size") + evo_usb.cbor_uint(3) +
                evo_usb.cbor_text("data") + evo_usb.cbor_bytes(b"abc") + b"\xff")
        check = evo_usb.evo_checksum(body)
        self.path.write_bytes(body + bytes((check >> 8, check & 255)))

    def test_dry_run_has_no_device_calls(self):
        device = self.fake_device()
        result = restore(device, Mock(), self.path)
        self.assertEqual(result["name"], "X0002")
        self.assertFalse(result["written"])
        device.send_var_file.assert_not_called()

    def test_collision_stops_transfer(self):
        device = self.fake_device([{"name": "X0002", "type": 1}])
        lock = lambda **kwargs: nullcontext()
        with self.assertRaises(FileExistsError):
            restore(device, lock, self.path, True,
                    hashlib.sha256(self.path.read_bytes()).hexdigest())
        device.send_var_file.assert_not_called()

    def test_unused_name_is_sent_to_ram(self):
        device = self.fake_device()
        device.get_variable.side_effect = lambda name, kind, output: shutil.copyfile(self.path, output)
        result = restore(device, lambda **kwargs: nullcontext(), self.path, True,
                         hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertTrue(result["written"])
        self.assertTrue(result["verified"])
        device.send_var_file.assert_called_once_with(str(self.path), "ram")

    def test_failed_send_is_indeterminate_and_not_retried(self):
        device = self.fake_device()
        device.send_var_file.side_effect = RuntimeError("USB disconnected")
        with self.assertRaisesRegex(RuntimeError, "outcome unknown"):
            restore(device, lambda **kwargs: nullcontext(), self.path, True,
                    hashlib.sha256(self.path.read_bytes()).hexdigest())
        device.send_var_file.assert_called_once()
        device.get_variable.assert_not_called()

    def test_failed_readback_does_not_claim_verified(self):
        device = self.fake_device()
        device.get_variable.side_effect = lambda name, kind, output: Path(output).write_bytes(b"wrong")
        with self.assertRaisesRegex(RuntimeError, "readback not verified"):
            restore(device, lambda **kwargs: nullcontext(), self.path, True,
                    hashlib.sha256(self.path.read_bytes()).hexdigest())
        device.send_var_file.assert_called_once()

    def test_write_requires_known_digest_before_device_calls(self):
        device = self.fake_device()
        with self.assertRaises(ValueError):
            restore(device, lambda **kwargs: nullcontext(), self.path, True)
        device.list_files.assert_not_called()

    def test_checksum_is_required(self):
        data = bytearray(self.path.read_bytes())
        data[-1] ^= 1
        self.path.write_bytes(data)
        with self.assertRaises(ValueError):
            inspect_container(evo_usb, self.path)

    def test_verified_backup_manifest_selects_exact_list(self):
        directory = Path(self.temp.name) / "backup"
        directory.mkdir()
        item = {"name": "X0002", "type": 1, "size": 3, "archive": False}
        target = directory / filename(item)
        target.write_bytes(self.path.read_bytes())
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        manifest = {"schema": 1, "inventory": [item],
                    "results": {"1:X0002": {"status": "exported", "file": target.name,
                                            "sha256": digest, "bytes": target.stat().st_size}}}
        (directory / "manifest.json").write_text(json.dumps(manifest))
        device = self.fake_device()
        result = restore_from_backup(device, Mock(), directory, "X0002")
        self.assertFalse(result["written"])
        device.send_var_file.assert_not_called()
        with self.assertRaises(FileExistsError):
            restore_from_backup(self.fake_device([{"name": "X0002", "type": 1}]),
                                lambda **kwargs: nullcontext(), directory, "X0002", True)


if __name__ == "__main__":
    unittest.main()
