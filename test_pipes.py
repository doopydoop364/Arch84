"""Pipes and standard input (A84PE parser, A84SH executor, text commands)."""
import random
import unittest

from testutil import *
from A84PE import ParseError, parse
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
    sh = Shell(Kernel(MemStorage()), t)
    return sh, t


def run(sh, t, line):
    t.text = ""
    sh.execute(line)
    return t.text


ENV = {"USER": "evo", "?": "0", "1": "one"}


class ParseTests(unittest.TestCase):
    def p(self, s):
        return parse(s, ENV, "/home/evo", True)

    def test_stages(self):
        self.assertEqual(self.p("a | b c > f"), [(["a"], None, None), (["b", "c"], (">", "f"), None)])
        self.assertEqual(self.p("cat < f | sort"), [(["cat"], None, "f"), (["sort"], None, None)])
        self.assertEqual(self.p("a|b|c"), [(["a"], None, None), (["b"], None, None), (["c"], None, None)])
        self.assertEqual(self.p(""), [([], None, None)])
        self.assertEqual(self.p("# comment"), [([], None, None)])

    def test_quoted_operators_are_text(self):
        self.assertEqual(self.p("echo '|' \"<\" a\\|b"), [(["echo", "|", "<", "a|b"], None, None)])

    def test_errors(self):
        for bad in ["a |", "| a", "a || b", "a | | b", "a < b < c", "a <", "a; b", "a & b", "x <<< y"]:
            with self.assertRaises(ParseError, msg=bad):
                self.p(bad)

    def test_legacy_mode_unchanged(self):
        for bad in ["a | b", "a < b"]:
            with self.assertRaises(ParseError):
                parse(bad, ENV, "/h")
        self.assertEqual(parse("echo hi > f", ENV, "/h"), (["echo", "hi"], (">", "f")))

    def test_digit_variables(self):
        self.assertEqual(self.p("echo $1 $2 ${1}x")[0][0], ["echo", "one", "", "onex"])


class PipeTests(unittest.TestCase):
    def setUp(self):
        self.sh, self.t = mk()

    def r(self, line):
        return run(self.sh, self.t, line)

    def test_basic_chain(self):
        self.r("echo b > f"); self.r("echo a >> f"); self.r("echo c >> f")
        self.assertEqual(self.r("cat f | sort"), "a\nb\nc\n")
        self.assertEqual(self.r("cat f | sort -r | head -n 1"), "c\n")
        self.assertEqual(self.r("cat f | grep -v b | wc -l"), "2\n")
        self.assertEqual(self.r("echo hello | cat"), "hello\n")

    def test_stdin_redirect_and_dash(self):
        self.r("echo xyz > f")
        self.assertEqual(self.r("grep y < f"), "xyz\n")
        self.assertEqual(self.r("cat < f"), "xyz\n")
        self.assertEqual(self.r("cat f | cat -"), "xyz\n")
        self.assertEqual(self.r("sort < f | wc -c"), "4\n")

    def test_output_redirect_on_last_stage(self):
        self.r("echo b > f"); self.r("echo a >> f")
        self.assertEqual(self.r("sort < f | head -n 1 > g"), "")
        self.assertEqual(self.r("cat g"), "a\n")
        self.assertEqual(self.r("cat f | sort >> g"), "")
        self.assertEqual(self.r("cat g"), "a\na\nb\n")

    def test_empty_pipe_is_input_not_missing_input(self):
        self.assertEqual(self.r("echo -n | wc -c"), "0\n")
        self.assertEqual(self.r("echo -n | grep x"), "")
        self.assertEqual(self.sh.status, 1)
        self.assertIn("usage", self.r("grep x"))

    def test_status_is_the_last_stage(self):
        self.r("echo a | grep zzz")
        self.assertEqual(self.sh.status, 1)
        self.r("nosuchcmd | cat")
        self.assertEqual(self.sh.status, 0)
        self.r("echo a | nosuchcmd")
        self.assertEqual(self.sh.status, 127)

    def test_errors_do_not_travel_down_the_pipe(self):
        out = self.r("cat /nope | wc -l")
        self.assertIn("E:cat: /nope: No such file or directory", out)
        self.assertIn("0\n", out)

    def test_missing_input_file(self):
        self.assertIn("No such file", self.r("cat < /nope"))
        self.assertEqual(self.sh.status, 1)

    def test_parse_errors_leave_no_state(self):
        self.assertIn("syntax error", self.r("cat |"))
        self.assertEqual(self.sh.status, 2)
        self.assertIsNone(self.sh.stdin)
        self.assertIsNone(self.sh._cap)

    def test_state_cleared_after_a_pipeline(self):
        self.r("echo a | cat")
        self.assertIsNone(self.sh.stdin)
        self.assertIsNone(self.sh._cap)
        self.assertIn("usage", self.r("sort"))

    def test_big_data_through_pipes_stays_in_pieces(self):
        for _ in range(3):
            self.r("echo " + "x" * 90 + " >> big")
        for _ in range(7):
            self.r("cat big big > t")
            self.r("cat t > big")
        n = self.sh.vfs.size("/home/evo/big")
        self.assertGreater(n, 5000)
        self.assertEqual(self.r("cat big | wc -c").strip(), str(n))
        self.assertEqual(self.r("cat big | cat | cat | wc -l").strip(), self.r("wc -l big").split()[0])

    def test_tail_head_stdin(self):
        for i in range(30):
            self.r("echo %d >> n" % i)
        self.assertEqual(self.r("cat n | tail -n 2"), "28\n29\n")
        self.assertEqual(self.r("cat n | head -n 2"), "0\n1\n")

    def test_wc_names(self):
        self.r("echo a b > f")
        self.assertEqual(self.r("cat f | wc").split(), ["1", "2", "4"])
        self.assertEqual(self.r("wc f").split(), ["1", "2", "4", "f"])
        self.assertEqual(self.r("cat f | wc - f").count("\n"), 3)     # "-" , f, total

    def test_uniq_and_tee(self):
        for w in "a a b a".split():
            self.r("echo " + w + " >> f")
        self.assertEqual(self.r("uniq f"), "a\nb\na\n")
        self.assertEqual(self.r("cat f | uniq -c"), "      2 a\n      1 b\n      1 a\n")
        self.assertEqual(self.r("cat f | uniq -d"), "a\n")
        self.assertEqual(self.r("cat f | sort | uniq"), "a\nb\n")
        self.assertEqual(self.r("echo q | tee x y"), "q\n")
        self.assertEqual(self.r("cat x y"), "q\nq\n")
        self.r("echo r | tee -a x")
        self.assertEqual(self.r("cat x"), "q\nr\n")

    def test_tee_onto_its_own_input_terminates(self):
        self.r("echo a > f")
        self.r("tee -a f < f")
        self.assertEqual(self.r("cat f"), "a\na\n")

    def test_random_pipelines_match_python(self):
        rng = random.Random(4)
        for _ in range(60):
            lines = [rng.choice("abc") * rng.randrange(1, 4) for _ in range(rng.randrange(0, 12))]
            self.r("echo -n > f")
            for l in lines:
                self.r("echo " + l + " >> f")
            self.assertEqual(self.r("cat f | sort | uniq"), "".join(x + "\n" for x in sorted(set(lines))))
            self.assertEqual(self.r("cat f | grep -c a").strip(), str(sum(1 for x in lines if "a" in x)))


class KeyTests(unittest.TestCase):
    def test_pipe_keys_are_typeable(self):
        from A84UI import TiTerm
        term = TiTerm(None)
        self.assertEqual(term.translate(52), "|")
        self.assertEqual(term.translate(53), "<")
        self.assertEqual(term.translate(61), "\\")
        term.translate(31)                  # alpha: letters, not symbols
        self.assertEqual(term.translate(52), "e")



class ScriptTests(unittest.TestCase):
    def setUp(self):
        self.sh, self.t = mk()
        self.sh.vfs.write("/usr/bin/hello", "# greet\necho hello $1 $#\necho second\n")

    def r(self, line):
        return run(self.sh, self.t, line)

    def test_runs_from_path_with_arguments(self):
        self.assertEqual(self.r("hello world"), "hello world 1\nsecond\n")
        self.assertEqual(self.r("hello"), "hello  0\nsecond\n")
        self.assertEqual(self.r("/usr/bin/hello a b"), "hello a 2\nsecond\n")

    def test_output_goes_through_pipes_and_redirects(self):
        self.assertEqual(self.r("hello x | wc -l"), "2\n")
        self.assertEqual(self.r("hello x | grep sec"), "second\n")
        self.assertEqual(self.r("hello q > /tmp/o"), "")
        self.assertEqual(self.sh.vfs.read("/tmp/o"), "hello q 1\nsecond\n")
        self.assertEqual(self.r("hello q >> /tmp/o"), "")
        self.assertEqual(self.sh.vfs.read("/tmp/o").count("second"), 2)

    def test_arguments_do_not_leak(self):
        self.r("hello a")
        self.assertNotIn("1", self.sh.k.env)
        self.assertNotIn("#", self.sh.k.env)
        self.assertEqual(self.r("echo $1 end"), " end\n")

    def test_nested_scripts_and_depth_limit(self):
        self.sh.vfs.write("/usr/bin/outer", "hello inner\n")
        self.assertEqual(self.r("outer"), "hello inner 1\nsecond\n")
        self.sh.vfs.write("/usr/bin/rec", "rec\n")
        self.assertIn("nested too deeply", self.r("rec"))

    def test_exit_is_refused_inside_scripts(self):
        self.sh.vfs.write("/usr/bin/bad", "exit\necho after\n")
        out = self.r("bad")
        self.assertIn("not allowed in scripts", out)
        self.assertIn("after\n", out)
        self.assertTrue(self.sh.running)

    def test_status_of_last_command(self):
        self.sh.vfs.write("/usr/bin/f", "false\n")
        self.r("f")
        self.assertEqual(self.sh.status, 1)

    def test_directory_and_missing_are_not_scripts(self):
        self.assertIn("command not found", self.r("nosuch"))
        self.assertIn("command not found", self.r("./nosuch"))
        self.sh.vfs.mkdir("/usr/bin/adir")
        self.assertIn("command not found", self.r("adir"))

if __name__ == "__main__":
    unittest.main()
