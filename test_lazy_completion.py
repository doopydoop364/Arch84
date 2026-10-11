"""Completion remains available without loading its module at shell import."""
import subprocess
import sys
import unittest


class LazyCompletionTests(unittest.TestCase):
    def test_import_defers_completion_until_first_use(self):
        source = """import sys
import A84SH
assert 'A84CP' not in sys.modules
from A84KN import Kernel
from A84ST import MemStorage
from A84UI import PlainTerm
sh = A84SH.Shell(Kernel(MemStorage()), PlainTerm())
assert 'A84CP' not in sys.modules
assert sh.complete('mkd')[1] == ['mkdir']
assert 'A84CP' in sys.modules
assert sh.complete('cat ')[0] == 4
"""
        run = subprocess.run([sys.executable, "-c", source],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_low_memory_import_failure_preserves_input(self):
        source = """import builtins
import A84SH
from A84KN import Kernel
from A84ST import MemStorage
from A84UI import PlainTerm
sh = A84SH.Shell(Kernel(MemStorage()), PlainTerm())
original = builtins.__import__
def fail_completion(name, *args, **kwargs):
    if name == 'A84CP':
        raise MemoryError()
    return original(name, *args, **kwargs)
builtins.__import__ = fail_completion
assert sh.complete('cat file') == (8, [])
builtins.__import__ = original
assert sh.complete('mkd')[1] == ['mkdir']
"""
        run = subprocess.run([sys.executable, "-c", source],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_pressure_eviction_releases_and_reloads_completion(self):
        source = """import sys
import A84SH
from A84CD import evict
from A84KN import Kernel
from A84ST import MemStorage
from A84UI import PlainTerm
sh = A84SH.Shell(Kernel(MemStorage()), PlainTerm())
assert sh.complete('mkd')[1] == ['mkdir']
assert 'A84CP' in sys.modules
assert evict() >= 1
assert 'A84CP' not in sys.modules
assert sh.complete('mkd')[1] == ['mkdir']
"""
        run = subprocess.run([sys.executable, "-c", source],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_pressure_evict_needs_no_full_lazy_views(self):
        source = """import sys
import A84CD
import A84CP
def no_space():
    raise MemoryError('cannot allocate full lazy view')
A84CD.LAZY.keys = no_space
A84CD.LAZY.values = no_space
assert A84CD.evict() >= 1
assert 'A84CP' not in sys.modules
"""
        run = subprocess.run([sys.executable, "-c", source],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == "__main__":
    unittest.main()
