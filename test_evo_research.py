import contextlib
import io
import json
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

from research import EVOMEM, EVOSTO
from tools import evo_research as er


class MemoryProbeTests(unittest.TestCase):
    def test_file_manager_import_runs_probe(self):
        out = io.StringIO()
        with patch.object(sys.implementation, "name", "tipython"):
            with contextlib.redirect_stdout(out):
                runpy.run_path(str(Path(EVOMEM.__file__)), run_name="EVOMEM")
        self.assertIn("EVO_MEM runtime=tipython", out.getvalue())

    def test_bounded_allocation_and_failure_recovery(self):
        attempted = []
        def alloc(n):
            attempted.append(n)
            return n <= 1500
        with patch.object(EVOMEM, "alloc_ok", side_effect=alloc):
            lo, cap, reached = EVOMEM.allocation_bound(20000, cap=8192)
        self.assertLessEqual(max(attempted), 2500)
        self.assertEqual(cap, 2500)
        self.assertLessEqual(lo, 1500)
        self.assertGreater(lo, 1435)
        self.assertFalse(reached)

    def test_no_heap_api_still_reports(self):
        with patch.object(EVOMEM, "metric", return_value=None):
            rows = dict(EVOMEM.probe())
        self.assertEqual(rows["single_object_probe_cap"], "unavailable")
        self.assertEqual(rows["free_after_gc"], "None")
        self.assertEqual(rows["bytearray_256_delta"], "unavailable")

    def test_allocation_failure_is_reported(self):
        def fail():
            raise MemoryError()
        self.assertEqual(EVOMEM.delta(fail), "allocation_failed")


class StorageProbeTests(unittest.TestCase):
    def test_file_manager_import_runs_probe(self):
        out = io.StringIO()
        with patch.object(sys.implementation, "name", "tipython"):
            with contextlib.redirect_stdout(out):
                runpy.run_path(str(Path(EVOSTO.__file__)), run_name="EVOSTO")
        self.assertIn("EVO_STORAGE runtime=tipython", out.getvalue())

    def test_read_only_probe(self):
        class FakeTi:
            def store_list(self):
                raise AssertionError("must not call")
            def recall_list(self):
                raise AssertionError("must not call")
        rows = dict(EVOSTO.probe(FakeTi()))
        self.assertEqual(rows["store_list_api"], 1)
        self.assertEqual(rows["recall_list_api"], 1)
        self.assertEqual(rows["open_missing_read"], "FileNotFoundError")

    def test_ti_open_stub(self):
        with patch("builtins.open", return_value=None) as opened:
            self.assertEqual(EVOSTO.read_open_probe(), "returned_none")
        opened.assert_called_once_with(EVOSTO.MISSING, "rb")


class DesktopToolkitTests(unittest.TestCase):
    def test_usb_fixture(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dev = root / "3-2"
            dev.mkdir()
            (dev / "idVendor").write_text("0451\n")
            (dev / "idProduct").write_text("e018\n")
            (dev / "product").write_text("TI-84 Evo\n")
            iface = root / "3-2:1.0"
            iface.mkdir()
            (iface / "bInterfaceClass").write_text("02")
            (iface / "tty").mkdir()
            (iface / "tty" / "ttyACM0").touch()
            rows = er.evo_only(er.scan_usb(root))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["interfaces"][0]["tty"], ["ttyACM0"])

    def test_parse_and_compare(self):
        a = er.parse_probe("EVO_MEM free_after_gc=1200\nEVO_STORAGE open_missing_read=returned_none\n")
        b = er.parse_probe("EVO_MEM free_after_gc=1100\nEVO_STORAGE open_missing_read=returned_none\n")
        self.assertEqual(er.compare(a, b)["memory"]["free_after_gc"]["delta"], -100)
        self.assertEqual(er.compare(a, b)["storage"], {})
        self.assertEqual(json.loads(json.dumps(a))["memory"]["free_after_gc"], 1200)
        with self.assertRaises(ValueError):
            er.parse_probe("EVO_MEM x=1\nEVO_MEM x=2\n")

    def test_send_refuses_existing_name(self):
        class FakeEvo:
            def list_files(self):
                return [{"name": "Evomem"}]
            def send_file(self, path, name):
                raise AssertionError("must not transfer")
        @contextlib.contextmanager
        def lock(timeout):
            yield
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "EVOMEM.py"
            path.write_text("pass\n")
            with self.assertRaises(FileExistsError):
                er.safe_send(FakeEvo(), lock, path, "EVOMEM")

    def test_send_new_name_after_directory_check(self):
        events = []
        class FakeEvo:
            def list_files(self):
                events.append("list")
                return [{"name": "ARCH84"}]
            def send_file(self, path, name):
                events.append("send:" + name)
        @contextlib.contextmanager
        def lock(timeout):
            events.append("lock")
            yield
            events.append("unlock")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "EVOMEM.py"
            path.write_text("pass\n")
            er.safe_send(FakeEvo(), lock, path, "EVOMEM")
        self.assertEqual(events, ["lock", "list", "send:EVOMEM", "unlock"])

    def test_device_snapshot_uses_lock(self):
        events = []
        class FakeEvo:
            def get_device_info(self):
                events.append("info")
                return {"id": b"\x01\x02"}
            def get_dynamic_info(self):
                events.append("dynamic")
                return {"free": 123}
            def list_files(self):
                events.append("directory")
                return []
        @contextlib.contextmanager
        def lock(timeout):
            events.append("lock")
            yield
            events.append("unlock")
        result = er.device_snapshot(FakeEvo(), lock)
        self.assertEqual(events, ["lock", "info", "dynamic", "directory", "unlock"])
        self.assertEqual(result["attributes"]["id"], "0102")

    def test_directory_timeout_is_extended_and_restored(self):
        class FakeEvo:
            def recv_pkt(self, dev, session=None, timeout=5000):
                return timeout
            def list_files(self):
                self.observed = self.recv_pkt(None)
                return []
        evo = FakeEvo()
        original = evo.recv_pkt
        self.assertEqual(er.list_files_with_timeout(evo), [])
        self.assertEqual(evo.observed, 30000)
        self.assertEqual(evo.recv_pkt, original)

    def test_directory_summary(self):
        rows = [{"name": "A", "mem": False, "size": 12, "type": 15},
                {"name": "B", "mem": True, "size": 40, "type": 15}]
        summary = er.directory_summary(rows)
        self.assertEqual(summary["by_location"]["ram"], {"count": 1, "bytes": 12})
        self.assertEqual(summary["by_location"]["archive"], {"count": 1, "bytes": 40})
        self.assertEqual(summary["by_type"], {"15": 2})


if __name__ == "__main__":
    unittest.main()
