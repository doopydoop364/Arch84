"""mkdir -p, cp -r, ls -l, cut, tr, nl, seq, test, [, expr."""
import unittest

from testutil import *
from A84SH import Shell
from A84KN import Kernel
from A84ST import MemStorage


class T:
    def __init__(self):
        self.text = ""

    def write(self, s):
        self.text += s.replace("\x01", "E:")

    def post(self, s, pending=False):
        pass

    def busy(self):
        pass

    def clear(self):
        pass


def mk():
    t = T()
    return Shell(Kernel(MemStorage()), t), t


class CmdTests(unittest.TestCase):
    def setUp(self):
        self.sh, self.t = mk()

    def r(self, line):
        self.t.text = ""
        self.sh.execute(line)
        return self.t.text

    # -- mkdir -p / cp -r / ls -l
    def test_mkdir_p(self):
        self.assertEqual(self.r("mkdir -p a/b/c"), "")
        self.assertTrue(self.sh.vfs.isdir("/home/evo/a/b/c"))
        self.assertEqual(self.r("mkdir -p a/b/c a/x"), "")                 # existing is fine
        self.assertIn("File exists", self.r("mkdir a"))
        self.r("echo 1 > f")
        self.assertIn("Not a directory", self.r("mkdir -p f/x"))
        self.assertEqual(self.r("mkdir -p /tmp/p/q /tmp/r"), "")
        self.assertIn("missing operand", self.r("mkdir -p"))

    def test_cp_r(self):
        self.r("mkdir -p a/b; echo hi > a/b/f; echo top > a/t")
        self.assertEqual(self.r("cp -r a a2"), "")
        self.assertEqual(self.r("cat a2/b/f a2/t"), "hi\ntop\n")
        self.r("echo changed > a/t")
        self.assertEqual(self.r("cat a2/t"), "top\n")                      # independent copies
        self.assertEqual(self.r("cp -r a /tmp"), "")
        self.assertEqual(self.r("cat /tmp/a/b/f"), "hi\n")
        self.assertIn("omitting directory", self.r("cp a a3"))
        self.assertIn("into itself", self.r("cp -r a a/b/in"))
        self.assertIn("into itself", self.r("cp -r a a"))
        self.r("mkdir sub")
        self.assertIn("into itself", self.r("cp -r / sub"))                # the root is inside everything
        self.assertIn("into itself", self.r("cp -r / /tmp"))
        self.assertIn("into itself", self.r("cp -r /home sub"))
        self.assertIn("into itself", self.r("cp -r ../.. ."))
        self.assertEqual(self.r("ls sub"), "")
        self.r("cp -R a2 a4")
        self.assertTrue(self.sh.vfs.isfile("/home/evo/a4/b/f"))
        self.assertEqual(self.r("cp -r a2/t a2/b"), "")                    # files still work with -r
        self.assertTrue(self.sh.vfs.isfile("/home/evo/a2/b/t"))

    def test_head_tail_dash_number(self):
        self.r("seq 5 > n")
        self.assertEqual(self.r("head -2 n"), "1\n2\n")
        self.assertEqual(self.r("tail -2 n"), "4\n5\n")
        self.assertEqual(self.r("cat n | head -1"), "1\n")
        self.assertIn("No such file", self.r("head -x n"))

    def test_ls_l(self):
        self.r("mkdir d; echo hello > f")
        out = self.r("ls -l")
        self.assertIn("     - d/\n", out)
        self.assertIn("     6 f\n", out)
        self.assertNotIn(".ashrc", out)
        self.assertIn(".ashrc", self.r("ls -la"))
        self.assertIn(".ashrc", self.r("ls -al"))
        self.assertEqual(self.r("ls"), "d/  f\n")

    # -- cut / tr / nl / seq
    def test_cut(self):
        self.r("echo a:b:c > f; echo d:e >> f; echo nocolon >> f")
        self.assertEqual(self.r("cut -d : -f 2 f"), "b\ne\nnocolon\n")
        self.assertEqual(self.r("cut -d: -f1,3 f"), "a:c\nd\nnocolon\n")
        self.assertEqual(self.r("cut -d : -f 2- f"), "b:c\ne\nnocolon\n")
        self.assertEqual(self.r("cat f | cut -c 1-3"), "a:b\nd:e\nnoc\n")
        self.assertEqual(self.r("cut -c2 f"), ":\n:\no\n")
        self.assertIn("must specify", self.r("cut f"))
        self.assertIn("single character", self.r("cut -d ab -f 1 f"))
        self.assertIn("must specify", self.r("cut -f 0 f"))
        self.assertIn("No such file", self.r("cut -f1 nosuch"))

    def test_tr(self):
        self.assertEqual(self.r("echo hello | tr a-z A-Z"), "HELLO\n")
        self.assertEqual(self.r("echo hello | tr el ip"), "hippo\n")
        self.assertEqual(self.r("echo hello | tr -d l"), "heo\n")
        self.assertEqual(self.r("echo a-b | tr - _"), "a_b\n")
        self.assertEqual(self.r("echo abc | tr abc x"), "xxx\n")                 # SET2 is padded
        self.r("echo a b > f")
        self.assertEqual(self.r("tr ' ' '\\n' < f"), "a\nb\n")
        self.assertIn("usage", self.r("tr a"))
        self.assertIn("usage", self.r("tr a b c"))

    def test_nl_and_seq(self):
        self.assertEqual(self.r("echo x | nl"), "     1\tx\n")
        self.assertEqual(self.r("seq 3"), "1\n2\n3\n")
        self.assertEqual(self.r("seq 2 4"), "2\n3\n4\n")
        self.assertEqual(self.r("seq 10 -3 1"), "10\n7\n4\n1\n")
        self.assertEqual(self.r("seq 5 1"), "")
        self.assertIn("zero increment", self.r("seq 1 0 5"))
        self.assertIn("invalid", self.r("seq a"))
        self.assertIn("too many", self.r("seq 100000"))
        self.assertEqual(self.r("seq 3 | nl | tail -n 1"), "     3\t3\n")

    # -- test / [ / expr
    def test_test_and_brackets(self):
        self.r("mkdir d; echo x > f")
        for line, want in (("test -f f", 0), ("test -f d", 1), ("test -d d", 0), ("test -e nosuch", 1),
                           ("test -e f", 0), ("[ -d d ]", 0), ("[ ! -d d ]", 1), ("test -z ''", 0),
                           ("test -n ''", 1), ("test -n abc", 0), ("test a = a", 0), ("test a = b", 1),
                           ("test a != b", 0), ("test 3 -lt 10", 0), ("test 10 -lt 3", 1), ("test 5 -ge 5", 0),
                           ("test 5 -ne 5", 1), ("[ 2 -eq 2 ]", 0), ("test", 1), ("test abc", 0), ("test ''", 1)):
            self.r(line)
            self.assertEqual(self.sh.status, want, line)
        self.assertIn("missing ]", self.r("[ -f f"))
        self.assertIn("integer expression expected", self.r("test a -lt 3"))
        self.assertEqual(self.sh.status, 2)
        self.assertIn("unknown operator", self.r("test -q f"))

    def test_expr(self):
        for line, out in (("expr 2 + 3", "5\n"), ("expr 10 - 4", "6\n"), ("expr 6 '*' 7", "42\n"),
                          ("expr 7 / 2", "3\n"), ("expr 7 % 4", "3\n"), ("expr abc", "abc\n")):
            self.assertEqual(self.r(line), out, line)
        self.assertEqual(self.r("expr 1 - 1"), "0\n")
        self.assertEqual(self.sh.status, 1)
        self.assertIn("division by zero", self.r("expr 1 / 0"))
        self.assertIn("integer expression", self.r("expr a + 1"))
        self.assertIn("usage", self.r("expr 1 2"))

    def test_scripting_with_lists(self):
        self.sh.vfs.write("/usr/bin/chk", "test -f $1 && echo yes $1 || echo no $1\n")
        self.r("echo x > here")
        self.assertEqual(self.r("chk here"), "yes here\n")
        self.assertEqual(self.r("chk gone"), "no gone\n")
        self.sh.vfs.write("/usr/bin/count", "seq $1 | wc -l\n")
        self.assertEqual(self.r("count 7"), "7\n")

    def test_registered_lazily(self):
        from A84CD import LAZY
        for c in "cut tr nl seq test [ expr".split():
            self.assertIn(c, LAZY)


class SedTests(unittest.TestCase):
    def setUp(self):
        self.sh, self.t = mk()
        self.sh.vfs.write("/home/evo/f", "one\ntwo\nthree two\nfour\n")

    def r(self, line):
        self.t.text = ""
        self.sh.execute(line)
        return self.t.text

    def test_substitute(self):
        self.assertEqual(self.r("sed 's/two/2/' f"), "one\n2\nthree 2\nfour\n")
        self.assertEqual(self.r("echo aaa | sed 's/a/b/'"), "baa\n")
        self.assertEqual(self.r("echo aaa | sed 's/a/b/g'"), "bbb\n")
        self.assertEqual(self.r("echo abc | sed 's/b/[&]/'"), "a[b]c\n")
        self.assertEqual(self.r("echo abc | sed 's/b/\\&/'"), "a&c\n")
        self.assertEqual(self.r("echo a/b | sed 's|/|-|'"), "a-b\n")
        self.assertEqual(self.r("echo a/b | sed 's/\\//-/'"), "a-b\n")
        self.assertEqual(self.r("echo abc | sed 's/x/y/'"), "abc\n")
        self.assertEqual(self.r("echo abc | sed 's/abc//'"), "\n")

    def test_addresses_and_commands(self):
        self.assertEqual(self.r("sed 2d f"), "one\nthree two\nfour\n")
        self.assertEqual(self.r("sed 2,3d f"), "one\nfour\n")
        self.assertEqual(self.r("sed '/two/d' f"), "one\nfour\n")
        self.assertEqual(self.r("sed -n 2p f"), "two\n")
        self.assertEqual(self.r("sed -n '/o/p' f"), "one\ntwo\nthree two\nfour\n")
        self.assertEqual(self.r("sed 2p f").count("two"), 3)             # printed twice + the other line
        self.assertEqual(self.r("sed -n 's/two/2/p' f"), "2\nthree 2\n")
        self.assertEqual(self.r("sed '2,3s/e/E/g' f"), "one\ntwo\nthrEE two\nfour\n")
        self.assertIn("unknown command", self.r("sed '$d' f"))              # "last line" is not supported
        self.assertEqual(self.r("sed '/one/s/o/0/;3d' f"), "0ne\ntwo\nfour\n")

    def test_errors(self):
        for bad, msg in (("sed", "usage"), ("sed 'x' f", "unknown command"), ("sed 's/a/b' f", "unterminated"),
                         ("sed 's//b/' f", "empty pattern"), ("sed 's/a/b/q' f", "unknown flag"),
                         ("sed '2,d' f", "bad address"), ("sed 'd d' f", "extra characters"), ("sed 2 f", "missing command"),
                         ("sed d nosuch", "No such file")):
            self.assertIn(msg, self.r(bad), bad)

    def test_rev_and_pipes(self):
        self.assertEqual(self.r("echo abc | rev"), "cba\n")
        self.assertEqual(self.r("rev f").split("\n")[0], "eno")
        self.assertEqual(self.r("cat f | sed 's/o/0/g' | rev | head -n 1"), "en0\n")
        self.assertEqual(self.r("echo 5 | sed 's/5/&&/'"), "55\n")


if __name__ == "__main__":
    unittest.main()

