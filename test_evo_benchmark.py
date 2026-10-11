import unittest
from unittest.mock import patch

from tools.evo_benchmark import corpora, make_report, markdown


class BenchmarkTests(unittest.TestCase):
    def test_corpora_and_report_are_offline(self):
        self.assertEqual(corpora()["random_4k"], corpora()["random_4k"])
        with patch("tools.evo_benchmark.emulator_run", side_effect=AssertionError("no emulator")):
            report = make_report(with_emulator=False)
        self.assertFalse(report["hardware_measurements"])
        self.assertIsNone(report["emulator"])
        self.assertGreater(report["compression"]["repetitive_4k"]["lists_saved"], 0)
        self.assertEqual(report["compression"]["random_4k"]["lists_saved"], 0)
        self.assertIn("No physical Evo", markdown(report))


if __name__ == "__main__":
    unittest.main()
