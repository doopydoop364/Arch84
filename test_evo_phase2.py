import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from research import EVOMEM, EVOPROF, EVOSCR
from tools import evo_bench, evo_storage_model
from tools import evo_cold_export
from tools import evo_research


class ProfileTests(unittest.TestCase):
    def test_configured_fragmentation_probe_is_bounded(self):
        with self.assertRaises(ValueError):
            EVOMEM.experiment(max_probe=100000)
        with mock.patch.object(EVOMEM, "allocation_bound", return_value=(1000, 2000, False)) as bound:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                EVOMEM.experiment(max_probe=2000, rounds=2)
        self.assertEqual(bound.call_count, 2)
        self.assertIn("EVO_MEM_EXP round_1=", output.getvalue())

    def test_bounded_block_caps_allocation(self):
        with mock.patch.object(EVOPROF, "metric", return_value=16000):
            lower, cap = (int(n) for n in EVOPROF.bounded_block().split("/"))
        self.assertEqual(cap, 2000)
        self.assertGreaterEqual(lower, 1936)

    def test_profile_parser_preserves_readings(self):
        result = evo_research.parse_probe(
            "EVO_PROFILE runtime=tipython\n"
            "EVO_PROFILE A84FS=1234/1400/50000\n"
            "EVO_MEM_EXP round_0=100/50/75/64/128/0\n")
        self.assertEqual(result["profile"]["runtime"], "tipython")
        self.assertEqual(result["profile"]["A84FS"], "1234/1400/50000")
        self.assertEqual(result["experiments"]["round_0"], "100/50/75/64/128/0")

    def test_benchmark_summary_import_deltas(self):
        rep = {"rc": 0, "error": None, "profile": [["greeting_after", 500, 100,
                1200, 1600, 10]], "imports": [["A84FS", 850], ["A84KN", 600]],
               "free_start": 1000, "heap_total": 1200, "free_loaded": 600,
               "boot_free": 500, "min_free_gc": 400, "end_free": 450}
        result = evo_bench.summarize(rep)
        self.assertEqual(result["ranked_imports"][0],
                         {"module": "A84KN", "retained_delta": 250})
        self.assertEqual(result["largest_boot_lower_bound"], 1200)

    def test_benchmark_comparison_rejects_different_heaps(self):
        before = {"environment": "emulator", "heap_request": 100000,
                  "scenarios": {"one": {"summary": {"boot_free": 10,
                      "min_free_gc": 5, "largest_boot_lower_bound": 2,
                      "end_free": 9}}}}
        after = {"environment": "emulator", "heap_request": 100000,
                 "scenarios": {"one": {"summary": {"boot_free": 13,
                     "min_free_gc": 7, "largest_boot_lower_bound": 3,
                     "end_free": 10}}}}
        self.assertEqual(evo_bench.compare(before, after)["one"]["boot_free"], 3)
        after["heap_request"] = 120000
        with self.assertRaises(ValueError):
            evo_bench.compare(before, after)


class ScratchTests(unittest.TestCase):
    class FakeTi:
        def __init__(self, present=None, error=False, missing_raises=False):
            self.value = present
            self.error = error
            self.missing_raises = missing_raises
            self.writes = []

        def recall_list(self, name):
            if self.error:
                raise OSError("unknown read failure")
            if self.missing_raises and self.value is None:
                raise NameError(name)
            return self.value

        def store_list(self, name, value):
            self.writes.append((name, value))
            self.value = value

    def test_default_and_collision_never_write(self):
        for present in (None, [1.5]):
            ti = self.FakeTi(present)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertFalse(EVOSCR.run(ti=ti))
                if present is not None:
                    self.assertFalse(EVOSCR.run(EVOSCR.TOKEN, ti))
            self.assertEqual(ti.writes, [])

    def test_uncertain_preflight_fails_closed(self):
        ti = self.FakeTi(error=True)
        with self.assertRaises(RuntimeError):
            EVOSCR.run(EVOSCR.TOKEN, ti)
        self.assertEqual(ti.writes, [])

    def test_opted_in_small_list_verified(self):
        ti = self.FakeTi(missing_raises=True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(EVOSCR.run(EVOSCR.TOKEN, ti))
        self.assertEqual(len(ti.writes), 1)
        self.assertEqual(ti.writes[0][0], "Z84P")
        self.assertEqual(len(ti.writes[0][1]), 16)


class CapacityTests(unittest.TestCase):
    def test_model_reserve_and_namespace(self):
        snapshot = {"dynamic": {"ram": 10000, "archive": 20000},
                    "attributes": {"total-ram": 30000, "total-flash": 40000},
                    "directory": [{"type": 1, "name": "X0000"},
                                  {"type": 2, "name": "X0001"}]}
        result = evo_storage_model.estimate(snapshot, full_list_bytes=1000,
                                            reserves=(0, 5000))
        self.assertEqual(result["assumptions"]["existing_x_lists"], 1)
        self.assertEqual(result["ram_scenarios"]["5000"]["payload_bytes"], 2425)
        self.assertFalse(result["assumptions"]["python_archive_read_verified"])

    def test_invalid_size_refused(self):
        with self.assertRaises(ValueError):
            evo_storage_model.estimate({}, full_list_bytes=100)

    def test_cold_export_read_only_and_no_overwrite(self):
        class FakeEvo:
            def list_files(self):
                return [{"name": "X0002", "type": 1}]

            def get_variable(self, name, type_id, output):
                self.request = (name, type_id)
                Path(output).write_bytes(b"sample-list")

        @contextlib.contextmanager
        def lock(timeout):
            yield

        with tempfile.TemporaryDirectory() as td:
            destination = Path(td) / "X0002.evo"
            fake = FakeEvo()
            result = evo_cold_export.export(fake, lock, "X0002", destination)
            self.assertEqual(fake.request, ("X0002", 1))
            self.assertEqual(destination.read_bytes(), b"sample-list")
            self.assertFalse(result["calculator_changed"])
            with self.assertRaises(FileExistsError):
                evo_cold_export.export(fake, lock, "X0002", destination)
            with self.assertRaises(ValueError):
                evo_cold_export.export(fake, lock, "A84", Path(td) / "other")


if __name__ == "__main__":
    unittest.main()
