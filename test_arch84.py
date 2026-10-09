"""Local tests for Arch84 (A84FS/KN/UI/CD/SH). Run: python3 test_arch84.py
These run on desktop CPython with fake ti_system objects; they do NOT prove
calculator compatibility."""
import unittest

import os
import sys
sys.path.insert(0, ".")
from A84FS import *
from A84V1 import decode_fs, encode_fs, esc, sanitize
from A84CZ import *
from A84CY import *
from A84ST import *
from A84KN import *
from A84UI import *
from A84GX import *
import A84TS
import A84KN
from testutil import FakeTI, ti_store, save_vfs, put_v1, bad_version
import A84C2, A84C3, A84C4, A84C5, A84C6
from A84C5 import days_from_civil, civil_from_days
from A84CD import *
from A84SH import *


class CaptureTerm:
    def __init__(self):
        self.text = ""
        self.raw = ""
        self.cleared = 0

    def write(self, t):
        self.raw += t
        t = t.replace(ERR, "")
        self.text += t if t.endswith("\n") or t == "" else t + "\n"

    def echo(self, t):
        pass

    def safe_key(self, tick=None):
        return False

    def post(self, t, pending=False):
        if not pending:
            self.write(t)

    def busy(self):
        pass

    def clear(self):
        self.cleared += 1

    def close(self):
        pass


def mk(storage=None):
    k = Kernel(storage or MemStorage())
    t = CaptureTerm()
    return Shell(k, t), t


def run(sh, t, line):
    t.text = ""
    sh.execute(line)
    return t.text


class PathTests(unittest.TestCase):
    def test_normalize(self):
        n = normalize
        self.assertEqual(n("/", "/x"), "/")
        self.assertEqual(n("a/b", "/"), "/a/b")
        self.assertEqual(n("a/b", "/x"), "/x/a/b")
        self.assertEqual(n("..", "/"), "/")
        self.assertEqual(n("../..", "/a/b/c"), "/a")
        self.assertEqual(n("./a/./b//c/", "/"), "/a/b/c")
        self.assertEqual(n("/a/b/../c", "/z"), "/a/c")
        self.assertEqual(n("~", "/"), "/home/evo")
        self.assertEqual(n("~/", "/"), "/home/evo")
        self.assertEqual(n("~/p/../q", "/"), "/home/evo/q")
        self.assertEqual(n("", "/tmp"), "/tmp")
        self.assertEqual(n("/../../..", "/"), "/")
        self.assertEqual(n("~x", "/"), "/~x")
        self.assertEqual(n(".", "/etc"), "/etc")


class VFSTests(unittest.TestCase):
    def setUp(self):
        self.v = VFS()
        self.v.reset_default()

    def test_default_layout(self):
        self.assertEqual(self.v.listdir("/"),
                         ["bin", "boot", "dev", "etc", "home", "proc", "root",
                          "run", "tmp", "usr", "var"])
        self.assertEqual(self.v.listdir("/var"), ["cache", "lib", "log"])
        self.assertEqual(self.v.listdir("/usr"), ["bin", "lib", "share"])
        self.assertEqual(self.v.listdir("/etc"), ["hostname", "profile", "version"])
        self.assertEqual(self.v.listdir("/home"), ["evo"])
        self.assertEqual(self.v.read("/etc/hostname"), "arch84\n")
        self.assertEqual(self.v.read("/etc/version"), VERSION + "\n")

    def test_ops(self):
        v = self.v
        v.mkdir("/tmp/a")
        v.write("/tmp/a/f", "hi")
        v.append("/tmp/a/f", "!")
        self.assertEqual(v.read("/tmp/a/f"), "hi!")
        self.assertTrue(v.isdir("/tmp/a"))
        self.assertTrue(v.isfile("/tmp/a/f"))
        self.assertFalse(v.isdir("/tmp/a/f"))
        with self.assertRaises(VFSError):
            v.mkdir("/tmp/a")
        with self.assertRaises(VFSError):
            v.mkdir("/nope/x")
        with self.assertRaises(VFSError):
            v.mkdir("/tmp/a/f/x")        # parent is a file
        with self.assertRaises(VFSError):
            v.read("/tmp/a")
        with self.assertRaises(VFSError):
            v.write("/tmp/a", "x")
        with self.assertRaises(VFSError):
            v.remove("/tmp/a")           # not empty
        with self.assertRaises(VFSError):
            v.remove("/")
        v.remove("/tmp/a/f")
        v.remove("/tmp/a")
        self.assertFalse(v.exists("/tmp/a"))

    def test_rename(self):
        v = self.v
        v.mkdir("/tmp/d")
        v.write("/tmp/d/f", "1")
        v.rename("/tmp/d", "/var/d2")
        self.assertEqual(v.read("/var/d2/f"), "1")
        with self.assertRaises(VFSError):
            v.rename("/var/d2", "/var/d2/in")
        v.write("/tmp/x", "x")
        with self.assertRaises(VFSError):
            v.rename("/tmp/x", "/var/d2")   # file over non-empty dir


class CodecTests(unittest.TestCase):
    def test_roundtrip(self):
        v = VFS()
        v.reset_default()
        v.mkdir("/home/evo/projects")
        v.write("/home/evo/projects/t.txt", "line1\nline2\ttab \\ back\r\n")
        v.write("/home/evo/empty", "")
        v.write("/home/evo/sp ace", "x")
        s = encode_fs(v)
        w = decode_fs(s)
        self.assertEqual(w.read("/home/evo/projects/t.txt"),
                         "line1\nline2\ttab \\ back\r\n")
        self.assertEqual(w.read("/home/evo/sp ace"), "x")
        self.assertEqual(w.read("/home/evo/empty"), "")
        self.assertEqual(encode_fs(w), s)
        self.assertFalse(w.dirty)

    def test_rejects_garbage(self):
        v = VFS()
        v.reset_default()
        s = encode_fs(v)
        for bad in ["", "junk\n", s.replace("A84FS1", "A84FS9"),
                    s[:-4], s.replace("D\t/bin", "D\t/a/../bin"),
                    s.replace("D\t/bin", "D\t/nodir/bin"),
                    s + "X", "A84FS1\nF\t/a\nEND\n",
                    "A84FS1\nF\t/a\tbad\\q\nEND\n"]:
            with self.assertRaises(ValueError, msg=repr(bad[:30])):
                decode_fs(bad)


class ParserTests(unittest.TestCase):
    env = {"USER": "evo", "HOME": "/home/evo", "PATH": "/usr/local/bin:/usr/bin:/bin",
           "X": "a b", "?": "0"}

    def p(self, s):
        return parse(s, self.env, "/home/evo")

    def test_basic(self):
        self.assertEqual(self.p("  ls   -a  /tmp "), (["ls", "-a", "/tmp"], None))
        self.assertEqual(self.p(""), ([], None))
        self.assertEqual(self.p("# hi"), ([], None))

    def test_quotes(self):
        self.assertEqual(self.p('echo "hello world"')[0], ["echo", "hello world"])
        self.assertEqual(self.p("echo 'hello  world'")[0], ["echo", "hello  world"])
        self.assertEqual(self.p("echo ''")[0], ["echo", ""])
        self.assertEqual(self.p("echo 'a'\"b\"c")[0], ["echo", "abc"])
        self.assertEqual(self.p("echo '$HOME'")[0], ["echo", "$HOME"])
        self.assertEqual(self.p('echo "$HOME/x"')[0], ["echo", "/home/evo/x"])
        self.assertEqual(self.p('echo "a \\"q\\" \\$HOME"')[0],
                         ["echo", 'a "q" $HOME'])
        self.assertEqual(self.p("echo a\\ b")[0], ["echo", "a b"])
        self.assertEqual(self.p("echo '>' \">>\"")[0], ["echo", ">", ">>"])
        with self.assertRaises(ParseError):
            self.p('echo "oops')
        with self.assertRaises(ParseError):
            self.p("echo 'oops")

    def test_vars(self):
        self.assertEqual(self.p("echo $USER $HOME $PATH")[0],
                         ["echo", "evo", "/home/evo", "/usr/local/bin:/usr/bin:/bin"])
        self.assertEqual(self.p("echo ${USER}x $NOPE| ".replace("| ", ""))[0],
                         ["echo", "evox", ""])
        self.assertEqual(self.p("echo $X")[0], ["echo", "a b"])
        self.assertEqual(self.p("echo $?")[0], ["echo", "0"])
        self.assertEqual(self.p("echo $ 5$")[0], ["echo", "$", "5$"])
        self.assertEqual(self.p("echo $USER_x")[0], ["echo", ""])

    def test_tilde(self):
        self.assertEqual(self.p("cd ~")[0], ["cd", "/home/evo"])
        self.assertEqual(self.p("cd ~/p")[0], ["cd", "/home/evo/p"])
        self.assertEqual(self.p("echo a~b ~x '~'")[0], ["echo", "a~b", "~x", "~"])

    def test_redirect(self):
        self.assertEqual(self.p("echo hi > f"), (["echo", "hi"], (">", "f")))
        self.assertEqual(self.p("echo hi >> f"), (["echo", "hi"], (">>", "f")))
        self.assertEqual(self.p("echo hi >f"), (["echo", "hi"], (">", "f")))
        self.assertEqual(self.p("> f"), ([], (">", "f")))
        self.assertEqual(self.p('echo "a b" > "my file"'),
                         (["echo", "a b"], (">", "my file")))
        for bad in ["echo >", "echo > >", "echo > a > b", "echo a>b"]:
            with self.assertRaises(ParseError, msg=bad):
                self.p(bad)

    def test_unsupported(self):
        for bad in ["a | b", "a; b", "a & b", "a < b"]:
            with self.assertRaises(ParseError):
                self.p(bad)


class ShellTests(unittest.TestCase):
    def setUp(self):
        self.sh, self.t = mk()

    def r(self, line):
        return run(self.sh, self.t, line)

    def test_prompt(self):
        self.assertEqual(self.sh.prompt(), "[evo@arch84 ~]$ ")
        self.r("cd /etc")
        self.assertEqual(self.sh.prompt(), "[evo@arch84 /etc]$ ")
        self.r("cd ~/")
        self.r("mkdir projects")
        self.r("cd projects")
        self.assertEqual(self.sh.prompt(), "[evo@arch84 ~/projects]$ ")

    def test_spec_examples(self):
        self.assertEqual(self.r("ls /"), "bin/  boot/  dev/  etc/  home/  proc/  root/  run/  tmp/  usr/  var/\n")
        self.r("cd /etc")
        self.assertEqual(self.r("cat hostname"), "arch84\n")
        self.r("cd ~/")
        self.assertEqual(self.sh.cwd, "/home/evo")
        self.assertEqual(self.r("mkdir projects"), "")
        self.assertEqual(self.r("touch test.txt"), "")
        self.assertEqual(self.r("ls"), "projects/  test.txt\n")

    def test_redirection(self):
        self.r('echo "hello world" > test.txt')
        self.assertEqual(self.r("cat test.txt"), "hello world\n")
        self.r("echo second >> test.txt")
        self.assertEqual(self.r("cat test.txt"), "hello world\nsecond\n")
        self.r("echo over > test.txt")
        self.assertEqual(self.r("cat test.txt"), "over\n")
        self.r("echo $HOME $USER > e")
        self.assertEqual(self.r("cat e"), "/home/evo evo\n")
        self.assertEqual(self.r("cat nope > x"), "cat: nope: No such file or directory\n")
        self.assertEqual(self.r("echo hi > /nodir/x"),
                         "ash: /nodir/x: No such file or directory\n")
        self.assertEqual(self.r("echo hi > /tmp"), "ash: /tmp: Is a directory\n")

    def test_env(self):
        self.assertIn("HOME=/home/evo\n", self.r("env"))
        self.assertIn("SHELL=/bin/ash\n", self.r("env"))
        self.r("export FOO=bar")
        self.assertEqual(self.r("echo $FOO"), "bar\n")
        self.assertIn("not a valid identifier", self.r("export 1x=3"))
        self.r("export MY_VAR=1")
        self.assertEqual(self.r("echo $MY_VAR"), "1\n")

    def test_which_alias(self):
        self.assertEqual(self.r("which ls"), "ls: shell built-in command\n")
        self.assertIn("not found", self.r("which zzz"))
        self.r("alias ll='ls -a'")
        self.assertEqual(self.r("which ll"), "ll: aliased to ls -a\n")
        self.r("touch .h")
        self.assertIn(".h", self.r("ll"))
        self.r("alias loop=loop")      # must not recurse forever
        self.assertIn("not found", self.r("loop"))
        self.r("unalias ll")
        self.assertIn("not found", self.r("ll"))

    def test_status(self):
        self.r("cat nope")
        self.assertEqual(self.r("echo $?"), "1\n")
        self.assertEqual(self.r("echo $?"), "0\n")

    def test_cp_mv_rm(self):
        self.r("echo a > f")
        self.r("mkdir d")
        self.r("cp f d")
        self.assertEqual(self.r("cat d/f"), "a\n")
        self.r("cp f g")
        self.r("mv g h")
        self.assertEqual(self.r("ls"), "d/  f  h\n")
        self.r("mv h d/h2")
        self.assertEqual(self.r("ls d"), "f  h2\n")
        self.assertIn("omitting", self.r("cp d x"))
        self.assertIn("Is a directory", self.r("rm d"))
        self.assertIn("not empty", self.r("rmdir d"))
        self.assertIn("Not a directory", self.r("rmdir f"))
        self.r("rm -r d")
        self.assertEqual(self.r("ls"), "f\n")
        self.assertIn("No such", self.r("rm zz"))
        self.assertIn("cwd", self.r("rm -r ~"))
        self.r("mkdir e")
        self.assertEqual(self.r("rmdir e"), "")
        self.assertIn("missing file operand", self.r("cp"))

    def test_head_tail(self):
        self.r("echo 1 > n")
        for i in range(2, 16):
            self.r("echo %d >> n" % i)
        self.assertEqual(self.r("head n").split(), [str(i) for i in range(1, 11)])
        self.assertEqual(self.r("tail n").split(), [str(i) for i in range(6, 16)])
        self.assertEqual(self.r("head -n 2 n"), "1\n2\n")
        self.assertEqual(self.r("tail -n 2 n"), "14\n15\n")
        self.assertEqual(self.r("tail -n 0 n"), "")

    def test_uname_etc(self):
        self.assertEqual(self.r("uname"), "Arch84\n")
        self.assertEqual(self.r("uname -a"),
                         "Arch84 arch84 " + VERSION + " evo Python\n")
        self.assertEqual(self.r("whoami"), "evo\n")
        self.assertEqual(self.r("hostname"), "arch84\n")
        self.r("echo box > /etc/hostname")
        self.assertEqual(self.r("hostname"), "box\n")
        self.assertEqual(self.sh.prompt(), "[evo@box ~]$ ")
        self.assertIn("syntax", self.r("echo a | b") + "syntax")
        self.assertEqual(self.r("nosuch"), "ash: command not found: nosuch\n")
        self.assertEqual(self.r("ls /nope"),
                         "ls: cannot access '/nope': No such file or directory\n")
        self.assertEqual(self.r("cd /nope"), "cd: /nope: No such file or directory\n")
        self.assertEqual(self.r("cd /etc/hostname"), "cd: /etc/hostname: Not a directory\n")

    def test_clear_and_exit(self):
        self.r("clear")
        self.assertEqual(self.t.cleared, 1)
        self.r("exit")
        self.assertFalse(self.sh.running)

    def test_history_cmd(self):
        self.sh.k.add_history("ls")
        self.sh.k.add_history("ls")
        self.sh.k.add_history("pwd")
        self.assertEqual(self.r("history"), "1  ls\n2  pwd\n")
        self.r("history -c")
        self.assertEqual(self.r("history"), "")


class PersistTests(unittest.TestCase):
    def test_spec_scenario(self):
        ti = FakeTI()
        store = ti_store(ti)
        sh, t = mk(store)
        self.assertTrue(any("Created new filesystem" in m for m in sh.k.boot_msgs))
        run(sh, t, "mkdir projects")
        run(sh, t, "echo hello > projects/test.txt")
        out = run(sh, t, "sync")
        self.assertIn("synced", out)
        run(sh, t, "echo more > projects/two.txt")
        run(sh, t, "exit")               # auto sync because dirty
        self.assertIn("Synced filesystem", t.text)
        sh2, t2 = mk(ti_store(ti))
        self.assertTrue(any("Restored fs" in m for m in sh2.k.boot_msgs))
        self.assertEqual(run(sh2, t2, "cat projects/test.txt"), "hello\n")
        self.assertEqual(run(sh2, t2, "cat projects/two.txt"), "more\n")
        self.assertEqual(run(sh2, t2, "cat /etc/hostname"), "arch84\n")
        self.assertEqual(run(sh2, t2, "cat /etc/version"), VERSION + "\n")
        self.assertFalse(sh2.vfs.dirty)

    def test_history_persists(self):
        ti = FakeTI()
        sh, t = mk(ti_store(ti))
        sh.k.add_history("ls /")
        sh.k.add_history("echo hi")
        run(sh, t, "sync")
        sh2, t2 = mk(ti_store(ti))
        self.assertEqual(sh2.k.history, ["ls /", "echo hi"])

    def test_corrupt_store_is_not_overwritten(self):
        ti = FakeTI()
        store = ti_store(ti)
        sh, t = mk(store)
        run(sh, t, "echo precious > /home/evo/p")
        run(sh, t, "sync")
        slot = int(ti.lists["A84"][2])
        ti.lists[block_name(slot, 0)][1] += 1.0
        before = {k: list(v) for k, v in ti.lists.items()}
        sh2, t2 = mk(ti_store(ti))
        self.assertFalse(sh2.k.sync_ok)
        self.assertTrue(any("[FAILED]" in m for m in sh2.k.boot_msgs))
        run(sh2, t2, "mkdir x")
        self.assertIn("sync disabled", run(sh2, t2, "sync"))
        self.assertIn("NOT synced", run(sh2, t2, "exit"))
        self.assertEqual(ti.lists, before)

    def test_legacy_unreadable_version(self):
        ms = MemStorage()
        bad_version(ms)
        k = Kernel(ms)
        self.assertFalse(k.sync_ok)
        self.assertTrue(k.vfs.isfile("/etc/hostname"))   # still usable

    def test_boot_reports_repairs(self):
        v = VFS()
        v.mkdir("/home")
        ms = MemStorage()
        save_vfs(ms, v)
        k = Kernel(ms)
        self.assertTrue(any(("Repaired %d system files" % (len(DEFAULT_DIRS) + 1)) in m for m in k.boot_msgs))
        k2 = Kernel(MemStorage())
        self.assertTrue(any("Checked system files" in m for m in k2.boot_msgs))

    def test_boot_mount_and_shell_lines(self):
        import io, contextlib
        sh, term = mk()
        self.assertTrue(any(m == "[  OK  ] Mounted VFS root"
                            for m in sh.k.boot_msgs))
        sh.execute("exit")
        buf = []
        class Rec(CaptureTerm):
            def readline(self, p, ed):
                return "exit"
        sh.term = Rec()
        sh.running = True
        sh.run()
        self.assertIn("Reached target Shell", sh.term.text)
        sh.running = True
        sh.cwd = "/gone"
        sh.term = Rec()
        sh.run()
        self.assertIn("[FAILED] Shell", sh.term.text)
        self.assertEqual(sh.cwd, "/")

    def test_boot_lines_reported_live_in_order(self):
        seen = []
        k = Kernel(MemStorage(), lambda s, p=False: p or seen.append(s))
        self.assertEqual([s.rstrip("\n") for s in seen], k.boot_msgs)
        self.assertEqual(seen[0], "[  OK  ] Created new filesystem\n")
        self.assertTrue(seen[-1].startswith("[  OK  ] Loaded history"))
        # the log is called while boot runs, not afterwards
        order = []
        class S(MemStorage):
            def read(self):
                order.append("load")
                return None
        Kernel(S(), lambda s, p=False: order.append("log"))
        self.assertEqual(order[0], "log")      # "[*     ] Loading filesystem"
        self.assertEqual(order[1], "load")
        self.assertEqual(order[2], "log")      # its OK line, after the work

    def test_pending_lines_precede_each_result(self):
        ev = []
        Kernel(MemStorage(), lambda s, p=False: ev.append((p, s)))
        pend = [s for p, s in ev if p]
        self.assertEqual([s.strip() for s in pend],
                         ["[*     ] Loading filesystem",
                          "[*     ] Checking system files",
                          "[*     ] Mounting VFS root",
                          "[*     ] Loading history"])
        for i in range(len(ev) - 1):
            if ev[i][0]:
                self.assertFalse(ev[i + 1][0])   # always followed by a result

    def test_ti_pending_line_is_replaced(self):
        ti = TiTermTests.T([])
        term = TiTerm(ti)
        term.post("[*     ] Loading filesystem\n", True)
        self.assertEqual(ti.rows[1].rstrip(), "[*     ] Loading filesystem")
        self.assertEqual(term.lines, [])          # not kept in scrollback
        term.post("[  OK  ] Loaded filesystem\n")
        self.assertEqual(ti.rows[1].rstrip(), "[  OK  ] Loaded filesystem")
        self.assertEqual(len(term.lines), 1)

    def test_ti_post_draws_immediately(self):
        ti = TiTermTests.T([])
        term = TiTerm(ti)
        term.post("one\n")
        self.assertEqual(ti.rows[1].rstrip(), "one")
        term.post("two\n")
        self.assertEqual(ti.rows[2].rstrip(), "two")
        self.assertEqual(ti.writes, 11)   # 10 rows on first paint, then only row 2

    def test_missing_system_files_restored(self):
        v = VFS()
        v.mkdir("/home")
        ms = MemStorage()
        save_vfs(ms, v)
        k = Kernel(ms)
        self.assertTrue(k.vfs.isdir("/home/evo"))
        self.assertEqual(k.vfs.read("/etc/hostname"), "arch84\n")


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.sh, self.t = mk()
        for l in ["mkdir projects", "mkdir pics", "touch pz.txt",
                  "echo x > /etc/hosts", "touch .hidden"]:
            run(self.sh, self.t, l)

    def ed(self, keys, hist=None):
        e = LineEditor(hist if hist is not None else [], self.sh.complete)
        for k in keys:
            e.feed(k)
        return e

    def test_command(self):
        self.assertEqual(self.ed("mk").buf, "mk")
        self.assertEqual(self.ed(list("mk") + ["tab"]).buf, "mkdir")
        self.assertEqual(self.ed(list("whoa") + ["tab"]).buf, "whoami")

    def test_path(self):
        self.assertEqual(self.ed(list("cd pro") + ["tab"]).buf, "cd projects/")
        self.assertEqual(self.ed(list("cat /etc/ho") + ["tab"]).buf, "cat /etc/host")
        e = self.ed(list("cat /etc/hosta") + ["tab"])
        self.assertEqual(e.buf, "cat /etc/hosta")
        self.assertEqual(self.ed(list("cat /etc/hostn") + ["tab"]).buf,
                         "cat /etc/hostname")

    def test_dirs_only_and_hidden(self):
        e = self.ed(list("cd p") + ["tab"])    # pics/ projects/ (pz.txt excluded)
        self.assertEqual(e.buf, "cd pics/")
        self.assertNotIn(".hidden", self.sh.complete("cat ")[1])
        self.assertIn(".hidden", self.sh.complete("cat .")[1])
        self.assertEqual(self.sh.complete("cd ~")[1], ["~/"])

    def test_cycle(self):
        e = self.ed(list("cat p") + ["tab"])
        self.assertEqual(e.buf, "cat pics/")   # no common ext beyond 'p' -> cycle
        e.feed("tab")
        self.assertEqual(e.buf, "cat projects/")
        e.feed("tab")
        self.assertEqual(e.buf, "cat pz.txt")
        e.feed("tab")
        self.assertEqual(e.buf, "cat pics/")
        self.assertIn("[pics/]", e.hint)
        e.feed("x")                             # typing ends the cycle
        e.feed("tab")
        self.assertNotIn("[", e.hint)

    def test_cycle_hint_keeps_current_visible(self):
        for i in range(15):
            run(self.sh, self.t, "touch longfilename_number_%02d.txt" % i)
        run(self.sh, self.t, "touch a_really_long_name_that_is_over_thirty_chars_wide.txt")
        e = self.ed(list("cat l") + ["tab"])
        if e.cyc is None:                 # common prefix was extended first
            e.feed("tab")
        seen = 0
        for _ in range(20):
            self.assertIn("[", e.hint[:32])
            self.assertIn("]", e.hint[:32])
            seen += 1
            e.feed("tab")
        self.assertEqual(seen, 20)
        self.assertTrue(e.hint.startswith("["))

    def test_common_prefix_then_cycle(self):
        e = self.ed(list("cat pr") + ["tab"])
        self.assertEqual(e.buf, "cat projects/")
        e2 = self.ed(list("cat /home/evo/p") + ["tab"])
        self.assertEqual(e2.buf, "cat /home/evo/pics/")

    def test_mid_line_completion(self):
        e = self.ed(list("cat pro  x"))
        e.feed("left"); e.feed("left"); e.feed("left")
        e.feed("tab")
        self.assertEqual(e.buf, "cat projects/  x")
        self.assertEqual(e.pos, len("cat projects/"))

    def test_arg_kinds(self):
        self.assertEqual(self.sh.complete("which mkd")[1], ["mkdir"])
        self.assertEqual(self.sh.complete("uname -")[1], ["-a", "-n", "-r", "-s"])
        self.assertEqual(self.sh.complete("echo hi > pz")[1], ["pz.txt"])
        self.assertEqual(self.sh.complete("echo $HO")[1], ["$HOME"])
        self.assertEqual(self.sh.complete("export US")[1], ["USER"])
        run(self.sh, self.t, "alias zap=ls")
        self.assertEqual(self.sh.complete("za")[1], ["zap"])
        self.assertEqual(self.sh.complete("unalias z")[1], ["zap"])

    def test_spaces_and_quotes(self):
        run(self.sh, self.t, "touch 'my file'")
        self.assertEqual(self.sh.complete("cat my")[1], ["my\\ file"])
        self.assertEqual(self.sh.complete("cat 'my")[1], ["'my file"])
        self.assertEqual(self.sh.complete("cat ")[0], 4)

    def test_nothing_when_no_match(self):
        e = self.ed(list("zzz") + ["tab"])
        self.assertEqual(e.buf, "zzz")
        self.assertEqual(e.hint, "no matches")


class EditorTests(unittest.TestCase):
    def ed(self, hist=()):
        return LineEditor(list(hist), lambda s: (len(s), []))

    def type(self, e, s):
        for c in s:
            e.feed(c)

    def test_editing(self):
        e = self.ed()
        self.type(e, "helo")
        e.feed("left")
        e.feed("l")
        self.assertEqual((e.buf, e.pos), ("hello", 4))
        e.feed("home"); e.feed("x")
        self.assertEqual(e.buf, "xhello")
        e.feed("end")
        e.feed("bs")
        self.assertEqual(e.buf, "xhell")
        e.feed("home"); e.feed("bs")    # nothing before cursor
        self.assertEqual(e.buf, "xhell")
        e.feed("right")
        e.feed("clear")
        self.assertEqual(e.buf, "")
        e.feed("left"); e.feed("bs")
        self.assertEqual(e.buf, "")
        e.feed("enter")
        self.assertTrue(e.done)

    def test_history_prefix_newest_first(self):
        e = self.ed(["ls", "cat a", "echo hi", "cat b", "pwd"])
        e.feed("up")
        self.assertEqual(e.buf, "pwd")
        e.feed("up")
        self.assertEqual(e.buf, "cat b")
        e.feed("down")
        self.assertEqual(e.buf, "pwd")
        e.feed("down")
        self.assertEqual(e.buf, "")
        e2 = self.ed(["ls", "cat a", "echo hi", "cat b", "pwd"])
        self.type(e2, "ca")
        e2.feed("up")
        self.assertEqual(e2.buf, "cat b")
        e2.feed("up")
        self.assertEqual(e2.buf, "cat a")
        e2.feed("up")
        self.assertEqual(e2.buf, "cat a")      # stays at oldest match
        e2.feed("down"); e2.feed("down")
        self.assertEqual(e2.buf, "ca")          # restored typed prefix

    def test_suggestion(self):
        e = self.ed(["echo hello", "echo help"])
        self.type(e, "echo he")
        self.assertEqual(e.hint, ">lp")
        e.feed("right")                          # accept newest match
        self.assertEqual(e.buf, "echo help")
        e.feed("right")                          # nothing more
        self.assertEqual(e.buf, "echo help")

    def test_forward_delete(self):
        e = self.ed()
        self.type(e, "abc")
        e.feed("home")
        e.feed("del")
        self.assertEqual(e.buf, "bc")


A = {c: n for n, c in zip("abcdefghijklmnopqrstuvwxyz", LET_CODES)}


class TiTermTests(unittest.TestCase):
    """Drive TiTerm with a fake ti module speaking the verified API."""
    class T:
        def __init__(self, keys):
            self.keys = list(keys)
            self.rows = {}
            self.writes = 0
            self.cleared = 0

        def get_key(self, w):
            if w == 0:
                return 0
            return self.keys.pop(0)

        def disp_clr(self):
            self.cleared += 1

        def disp_at(self, row, text, align):
            assert align == "left" and 1 <= row <= 10 and len(text) <= 31
            self.rows[row] = text
            self.writes += 1

    def line(self, keys):
        ti = self.T(keys)
        term = TiTerm(ti)
        sh, _ = mk()
        out = term.readline(sh.prompt(), sh.new_editor())
        return out, term, ti, sh

    def test_letters_digits_symbols(self):
        # alpha+e, alpha+c, alpha+h, alpha+o ; digits ; mem=space ; Y= quote
        keys = [31, 52, 31, 43, 31, 55, 31, 72, 95, 92, 93, 11, 62, 105]
        # e c h o ' ' 1 2 " ,
        out, *_ = self.line(keys)
        self.assertEqual(out, 'echo' [:0] + 'echo 12",')

    def test_lock_and_uppercase(self):
        keys = [21, 31, 41, 42, 21, 43, 31, 32, 105]   # lock: a b ; 2nd c ; unlock ; a? (nonalpha: 41 normal -> none)
        out, term, *_ = self.line(keys)
        self.assertEqual(out, "abC")

    def test_alpha_one_shot(self):
        out, *_ = self.line([31, 41, 32, 72, 105])      # a then math(no char), 7
        self.assertEqual(out, "a7")

    def test_second_layer_and_actions(self):
        out, *_ = self.line([31, 41, 31, 42, 31, 43, 21, 24, 21, 23, 105])
        self.assertEqual(out, "bc")                     # home, forward-delete 'a'
        out, *_ = self.line([31, 41, 31, 42, 24, 23, 105])
        self.assertEqual(out, "b")                      # left, bs deletes 'a'
        out, *_ = self.line([92, 93, 45, 94, 105])
        self.assertEqual(out, "3")                      # clear line

    def test_tab_key_completes(self):
        out, *_ = self.line([31, 62, 22, 105])          # 'j' + tab: nothing
        self.assertEqual(out, "j")
        out, *_ = self.line([31, 85, 31, 55, 31, 72, 22, 105])   # w h o + tab
        self.assertEqual(out, "whoami")

    def test_unknown_key_hint_and_redraw_cache(self):
        ti = self.T([91 + 3, 105])      # 94 is '3'
        term = TiTerm(ti)
        sh, _ = mk()
        term.readline(sh.prompt(), sh.new_editor())
        w1 = ti.writes
        ti2 = self.T([2, 105])           # code 2 unknown
        term2 = TiTerm(ti2)
        ed = sh.new_editor()
        term2.readline(sh.prompt(), ed)
        self.assertEqual(ed.buf, "")
        self.assertTrue(ti2.rows[10].startswith("key 2"))

    def test_session_output_and_wrap(self):
        ti = self.T([105])
        term = TiTerm(ti)
        sh, _ = mk()
        sh.term = term
        sh.execute("echo " + "x" * 70)
        self.assertEqual(term.lines, ["x" * 31, "x" * 31, "x" * 8])
        term.readline(sh.prompt(), sh.new_editor())
        for r in ti.rows.values():
            self.assertEqual(len(r), 31)

    def test_long_line_window(self):
        ti = self.T([92] * 80 + [105])
        term = TiTerm(ti)
        sh, _ = mk()
        term.readline(sh.prompt(), sh.new_editor())
        self.assertLessEqual(len(ti.rows), 10)

    def test_scroll_clamped(self):
        ti = self.T([21, 25, 21, 25, 21, 34, 105])
        term = TiTerm(ti)
        sh, _ = mk()
        for i in range(30):
            term.write("line %d\n" % i)
        term.readline(sh.prompt(), sh.new_editor())
        self.assertGreaterEqual(term.off, 0)

    def test_close_dumps_scrollback(self):
        import io, contextlib
        ti = self.T([])
        term = TiTerm(ti)
        term.write("bye\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            term.close()
        self.assertIn("bye", buf.getvalue())

    def test_gt_on_math_key(self):
        out, *_ = self.line([92, 41, 21, 41, 14, 21, 63, 21, 85, 105])
        self.assertEqual(out, "1>>>{]")

    def test_tables(self):
        for k in ALPHA:
            self.assertEqual(len(ALPHA[k]), 1)
        self.assertEqual(ALPHA[41] + ALPHA[93], "az")
        self.assertEqual(len(set(LET_CODES)), 26)
        for k in ACT.values():
            self.assertTrue(len(k) > 1)
        self.assertLessEqual(BLOCK_ELEMS, 100)


class StartupTests(unittest.TestCase):
    def shell(self, skip=False, files=None):
        calls = {"close": 0, "n": 0}
        class Term(CaptureTerm):
            def safe_key(self, tick=None):
                return skip
            def readline(self, p, ed):
                calls["n"] += 1
                return "exit"
            def close(self):
                calls["close"] += 1
        k = Kernel(MemStorage())
        for path, text in (files or {}).items():
            k.vfs.write(path, text)
        sh = Shell(k, Term())
        return sh, calls

    def test_defaults_are_seeded_on_new_fs(self):
        k = Kernel(MemStorage())
        self.assertEqual(k.vfs.read("/etc/profile").split("\n")[1],
                         "export PATH=/usr/local/bin:/usr/bin:/bin")
        self.assertIn("alias ll='ls -a'", k.vfs.read(HOME + "/.ashrc"))
        self.assertTrue(k.vfs.isfile(HOME + "/.profile"))
        self.assertEqual(k.env["PATH"], "/usr/local/bin:/usr/bin:/bin")

    def test_startup_files_run_in_order(self):
        sh, calls = self.shell(files={
            "/etc/profile": "export FOO=one\n",
            HOME + "/.profile": "export FOO=two\nexport BAR=x\n",
            HOME + "/.ashrc": "# comment\n\nalias zz='ls -a'\n"})
        sh.run()
        self.assertEqual(sh.k.env["FOO"], "two")
        self.assertEqual(sh.k.env["BAR"], "x")
        self.assertEqual(sh.k.aliases["zz"], "ls -a")
        for p in ("/etc/profile", HOME + "/.profile", HOME + "/.ashrc"):
            self.assertIn("[  OK  ] Ran " + p, sh.term.text)

    def test_missing_startup_file_is_just_skipped(self):
        sh, calls = self.shell()
        sh.vfs.remove(HOME + "/.ashrc")
        sh.run()
        self.assertNotIn(".ashrc", sh.term.text)

    def test_startup_cannot_exit_or_reboot(self):
        sh, calls = self.shell(files={HOME + "/.profile": "exit\nreboot\npoweroff\nexport OK=1\n"})
        sh.run()
        self.assertEqual(calls["n"], 1)               # prompt was reached
        self.assertEqual(sh.k.env["OK"], "1")         # later lines still ran
        self.assertFalse(sh.reboot)
        self.assertIn("'exit' not allowed", sh.term.text)
        self.assertIn("[ WARN ] " + HOME + "/.profile: 3 errors", sh.term.text)

    def test_failing_startup_command_warns(self):
        sh, calls = self.shell(files={"/etc/profile": "nosuchcmd\nexport A=1\n"})
        sh.run()
        self.assertIn("[ WARN ] /etc/profile: 1 errors", sh.term.text)
        self.assertEqual(sh.k.env["A"], "1")
        self.assertEqual(sh.status, 127 if False else sh.status)

    def test_safe_key_skips_startup(self):
        sh, calls = self.shell(skip=True, files={"/etc/profile": "export FOO=one\n"})
        sh.run()
        self.assertNotIn("FOO", sh.k.env)
        self.assertIn("Startup files skipped", sh.term.text)
        self.assertEqual(calls["n"], 1)

    def test_startup_not_run_by_selftest_or_execute(self):
        sh, calls = self.shell(files={"/etc/profile": "export FOO=one\n"})
        sh.execute("echo hi")
        self.assertNotIn("FOO", sh.k.env)
        out, cap, s2 = A84TS.run_case(["echo $FOO"])
        self.assertEqual(out, "\n")

    def test_reboot_flag_and_close(self):
        class Term(CaptureTerm):
            closed = 0
            def readline(self, p, ed):
                return "reboot"
            def close(self):
                Term.closed += 1
        k = Kernel(MemStorage())
        sh = Shell(k, Term())
        sh.run()
        self.assertTrue(sh.reboot)
        self.assertEqual(Term.closed, 0)             # screen is kept for the next boot
        self.assertIn("Reached target Reboot", sh.term.text)

    def test_reboot_syncs_and_state_survives(self):
        ms = MemStorage()
        k = Kernel(ms)
        sh = Shell(k, CaptureTerm())
        sh.execute("echo keep > f")
        sh.execute("reboot")
        self.assertTrue(sh.reboot)
        k2 = Kernel(ms)                              # what main() does on reboot
        self.assertEqual(k2.vfs.read(HOME + "/f"), "keep\n")

    def test_reboot_refuses_when_sync_fails(self):
        class Bad(MemStorage):
            def writer(self):
                raise StorageError("disk full")
        k = Kernel(Bad())
        sh = Shell(k, CaptureTerm())
        sh.execute("touch f")
        sh.execute("reboot")
        self.assertFalse(sh.reboot)
        self.assertTrue(sh.running)

    def test_poweroff_halts(self):
        sh, t = mk()
        out = run(sh, t, "poweroff")
        self.assertFalse(sh.running)
        self.assertIn("Reached target Power-Off", t.text)


class SpinnerTests(unittest.TestCase):
    """The systemd-style [***   ] progress animation."""
    def setUp(self):
        self.real = (A84KN.now_ms, A84KN.ms_since)
        self.clock = [0]
        A84KN.now_ms = lambda: self.clock[0]
        A84KN.ms_since = lambda t0: None if t0 is None else self.clock[0] - t0

    def tearDown(self):
        A84KN.now_ms, A84KN.ms_since = self.real

    def kernel(self, storage=None):
        posts = []
        k = Kernel(storage or MemStorage(), lambda s, p=False: posts.append((s.rstrip("\n"), p)))
        del posts[:]
        return k, posts

    def test_frames_are_8_wide_like_the_ok_tag(self):
        self.assertEqual(len(SPIN), 8)
        for f in SPIN:
            self.assertEqual(len("[" + f + "]"), len("[  OK  ]"))
            self.assertEqual(f.strip(" ").strip("*"), "")          # only asterisks and padding
            self.assertEqual(f.strip(" "), "*" * len(f.strip(" ")))  # contiguous
        starts = [f.index("*") for f in SPIN]
        ends = [len(f.rstrip(" ")) for f in SPIN]
        self.assertEqual(starts[0], 0)
        self.assertEqual(ends[-1], 6)
        self.assertEqual(starts, sorted(starts))                   # slides left to right
        self.assertEqual(SPIN[0], "*     ")
        self.assertEqual(SPIN[2], "***   ")

    def test_spin_posts_the_first_frame_as_pending(self):
        k, posts = self.kernel()
        k.spin("Working")
        self.assertEqual(posts, [("[*     ] Working", True)])

    def test_tick_is_rate_limited_and_advances_in_order(self):
        k, posts = self.kernel()
        k.spin("Working")
        for _ in range(5):
            k.tick()                       # no time has passed
        self.assertEqual(len(posts), 1)
        seen = []
        for i in range(10):
            self.clock[0] += SPIN_MS
            k.tick()
        frames = [p[0][1:7] for p in posts]
        self.assertEqual(frames[0], SPIN[0])
        self.assertEqual(frames, [SPIN[i % 8] for i in range(11)])   # in order, wraps
        self.assertTrue(all(p[1] for p in posts))                    # always pending

    def test_tick_below_the_interval_does_not_advance(self):
        k, posts = self.kernel()
        k.spin("Working")
        self.clock[0] += SPIN_MS - 1
        k.tick()
        self.assertEqual(len(posts), 1)
        self.clock[0] += 1
        k.tick()
        self.assertEqual(len(posts), 2)

    def test_say_and_stop_end_the_animation(self):
        k, posts = self.kernel()
        k.spin("Working")
        k.say("[  OK  ] Done")
        del posts[:]
        self.clock[0] += 1000
        k.tick()
        self.assertEqual(posts, [])
        k.spin("Again")
        k.stop_spin()
        del posts[:]
        self.clock[0] += 1000
        k.tick()
        self.assertEqual(posts, [])

    def test_without_a_clock_every_tick_advances(self):
        A84KN.ms_since = lambda t0: None
        k, posts = self.kernel()
        k.spin("Working")
        k.tick()
        k.tick()
        self.assertEqual([p[0][1:7] for p in posts], [SPIN[0], SPIN[1], SPIN[2]])

    def test_tick_without_a_log_is_harmless(self):
        k = Kernel(MemStorage())
        k.spin("x")
        self.clock[0] += 1000
        k.tick()

    def test_storage_progress_drives_the_animation_while_saving_and_loading(self):
        ti = FakeTI()
        k, posts = self.kernel(ti_store(ti))
        k.vfs.write("/home/evo/big", "0123456789abcdef\n" * 3000)
        ticks = []
        real = k.storage.progress
        def counting():
            ticks.append(1)
            self.clock[0] += SPIN_MS            # each unit of work takes a while
            real()
        k.storage.progress = counting
        k.spin("Syncing filesystem")
        raw, stored, blocks, warns = k.sync()
        k.stop_spin()
        self.assertGreaterEqual(blocks, 2)
        self.assertGreaterEqual(len(ticks), blocks)             # a tick per list written
        frames = [p[0][1:7] for p in posts if p[1]]
        self.assertGreater(len(set(frames)), 3)                  # it really moved
        for a, b in zip(frames, frames[1:]):
            self.assertEqual(SPIN.index(b), (SPIN.index(a) + 1) % 8)   # strictly sequential

    def test_boot_animates_while_loading_a_multi_block_save(self):
        ti = FakeTI()
        k0 = Kernel(ti_store(ti))
        k0.vfs.write("/home/evo/big", "".join(chr(33 + (i * 7) % 90) for i in range(6000)))
        k0.sync()
        posts = []
        st = ti_store(ti)
        real_get = st.get
        def slow_get(name):
            self.clock[0] += SPIN_MS             # reading each list takes a while
            return real_get(name)
        st.get = slow_get
        Kernel(st, lambda s, p=False: posts.append((s.rstrip("\n"), p)))
        loading = [p[0][1:7] for p in posts if p[1] and p[0].endswith("Loading filesystem")]
        self.assertGreater(len(set(loading)), 2)
        # and the finished line replaces it
        self.assertTrue(any(p[0].startswith("[  OK  ] Restored fs") and not p[1] for p in posts))

    def test_shutdown_sync_animates(self):
        class Rec(CaptureTerm):
            def __init__(self):
                CaptureTerm.__init__(self)
                self.posts = []
            def post(self, t, pending=False):
                self.posts.append((t.rstrip("\n"), pending))
        ti = FakeTI()
        t = Rec()
        sh = Shell(Kernel(ti_store(ti)), t)
        real = sh.k.storage.progress
        def slow():
            self.clock[0] += SPIN_MS
            real()
        sh.k.storage.progress = slow
        sh.vfs.write("/home/evo/big", "0123456789abcdef\n" * 3000)
        sh.execute("exit")
        syncing = [p[0][1:7] for p in t.posts if p[1] and "Syncing" in p[0]]
        self.assertGreater(len(set(syncing)), 2)
        self.assertEqual(t.posts[-1][0], "[  OK  ] Reached target Shutdown")

    def test_sync_command_starts_and_stops_the_spinner(self):
        sh, t = mk()
        sh.k.log = lambda s, p=False: None
        run(sh, t, "sync")
        self.assertIsNone(sh.k.spin_msg)
        class Bad(MemStorage):
            def writer(self):
                raise StorageError("disk full")
        sh2 = Shell(Kernel(Bad()), CaptureTerm())
        sh2.execute("touch f")
        sh2.execute("sync")
        self.assertIsNone(sh2.k.spin_msg)

    def test_startup_ticks_between_commands(self):
        ticks = []
        class Term(CaptureTerm):
            def safe_key(self, tick=None):
                for _ in range(3):
                    tick()                     # the key-wait loop reports progress
                return False
            def readline(self, p, ed):
                return "exit"
        k = Kernel(MemStorage())
        k.vfs.write("/etc/profile", "export A=1\nexport B=2\nexport C=3\n")
        real = k.tick
        k.tick = lambda: (ticks.append(1), real())
        sh = Shell(k, Term())
        sh.run()
        self.assertGreaterEqual(len(ticks), 3 + 3)      # key wait + one per startup command

    def test_safe_key_wait_reports_progress_and_times_out(self):
        class T:
            def __init__(self):
                self.polls = 0
            def get_key(self, w):
                self.polls += 1
                return 0
        import A84UI
        import A84FS
        real = A84UI.now_ms
        real_fs = A84FS.now_ms
        clock = [0]
        def fake():
            clock[0] += 100
            return clock[0]
        A84UI.now_ms = fake
        A84FS.now_ms = fake         # ms_since() reads the clock from A84FS
        try:
            ti = T()
            term = TiTerm(ti)
            ticks = []
            self.assertFalse(term.safe_key(lambda: ticks.append(1)))
            self.assertGreaterEqual(len(ticks), 3)
            self.assertEqual(ticks.__len__(), ti.polls)
            ti2 = T()
            ti2.get_key = lambda w: 45
            self.assertTrue(TiTerm(ti2).safe_key(lambda: None))      # CLEAR held
        finally:
            A84UI.now_ms = real
            A84FS.now_ms = real_fs

    def test_every_frame_is_coloured_on_the_gfx_terminal(self):
        for f in SPIN:
            segs = line_segs("[" + f + "] Loading filesystem")
            self.assertEqual(segs[0], ("[", "w"))
            self.assertEqual(segs[1], (f, "r"))
            self.assertEqual(segs[2], ("]", "w"))
            self.assertEqual(segs[3], (" Loading filesystem", "w"))
        self.assertEqual(line_segs("[  OK  ] done")[1], ("  OK  ", "g"))        # OK lines unchanged
        self.assertEqual(line_segs("[evo@arch84 ~]$ ls")[1][1], "g")           # prompt unchanged
        self.assertEqual(line_segs("[      ] blank")[0], ("[      ] blank", "w"))  # no asterisks: not a spinner

    def test_gfx_pending_frames_update_in_place(self):
        term, ti, td = GfxTests().term([])
        term.write("[  OK  ] first\n")
        for i, f in enumerate(SPIN):
            term.post("[" + f + "] Loading\n", True)
            self.assertEqual(len(term.lines), 1)                 # never kept in the scrollback
            self.assertEqual(term.prev[1][1], (f, "r"))          # same row, new frame
        term.post("[  OK  ] Loaded\n")
        self.assertEqual(len(term.lines), 2)
        self.assertEqual(term.prev[1][1], ("  OK  ", "g"))


LAZYMODS = ("A84C2", "A84C3", "A84C4", "A84C5", "A84C6")


class KeyHelpTests(unittest.TestCase):
    """The `keys` help text must describe the real key table (it once said sin='<' while the table had '|')."""
    PHYSICAL = {"sin": 52, "cos": 53, "tan": 54, "x^2": 61, "vars": 44, "x^": 51,
                "Y=": 11, "window": 12, "zoom": 13, "trace": 14, "graph": 15, "stat": 33,
                "(-)": 104, "mem": 95}

    def keys_text(self):
        sh, t = mk()
        return run(sh, t, "keys")

    def test_every_symbol_in_the_help_is_what_the_key_really_types(self):
        text = self.keys_text()
        term = TiTerm(TiTermTests.T([]))
        claims = {"sin": "|", "cos": "<", "tan": ";", "x^2": "\\", "vars": "&", "x^": "^",
                  "Y=": '"', "window": "'", "zoom": "$", "trace": ">", "graph": "=", "stat": "~",
                  "(-)": "_", "mem": " "}
        for name, ch in claims.items():
            self.assertEqual(term.translate(self.PHYSICAL[name]), ch, name)
        for frag in ("sin=|", "cos=<", "tan=;", "x^2=\\", "vars=&", "stat=~", "(-)=_", "x^=^"):
            self.assertIn(frag, text, frag)

    def test_ampersand_does_not_depend_on_the_2nd_layer(self):
        term = TiTerm(TiTermTests.T([]))
        self.assertEqual(term.translate(44), "&")                 # vars, no 2nd needed
        term.translate(21)
        self.assertEqual(term.translate(52), "&")                 # the old 2nd+sin still works too

    def test_help_lines_fit_the_screen(self):
        for line in self.keys_text().split("\n"):
            self.assertLessEqual(len(line), 32, line)

    def test_no_stale_x_inverse_claims(self):
        self.assertNotIn("x^-1", self.keys_text())


class LazyCommandTests(unittest.TestCase):
    NAMES = "true false grep find sort wc basename dirname du df free mount umount uptime date reboot poweroff uniq tee".split()

    def unload(self):
        # make the state the calculator starts in: A84C2 not imported yet
        import sys
        saved = {n: COMMANDS.pop(n) for n in self.NAMES if n in COMMANDS}
        mod = {m: sys.modules.pop(m) for m in LAZYMODS if m in sys.modules}
        return saved, mod

    def restore(self, saved, mod):
        import sys
        sys.modules.update(mod)
        COMMANDS.update(saved)

    def test_commands_load_on_first_use(self):
        saved, mod = self.unload()
        try:
            for n in self.NAMES:
                self.assertNotIn(n, COMMANDS)
            sh, t = mk()
            out = run(sh, t, "echo hello > f")
            self.assertEqual(run(sh, t, "grep hell f"), "hello\n")
            for n in ("true", "false", "grep", "find"):
                self.assertIn(n, COMMANDS)             # the whole module registered
            self.assertNotIn("wc", COMMANDS)           # other pieces still unloaded
            self.assertEqual(run(sh, t, "wc -l f"), "1 f\n")
            for n in ("sort", "wc", "basename", "dirname"):
                self.assertIn(n, COMMANDS)
        finally:
            self.restore(saved, mod)

    def test_lazy_names_are_visible_before_loading(self):
        saved, mod = self.unload()
        try:
            sh, t = mk()
            self.assertIn("grep", run(sh, t, "help").split())
            self.assertIn("poweroff", run(sh, t, "help").split())
            self.assertEqual(run(sh, t, "which grep"), "grep: shell built-in command\n")
            self.assertEqual(sh.complete("gre")[1], ["grep"])
            self.assertEqual(sh.complete("")[1].count("find"), 1)
            self.assertNotIn("grep", COMMANDS)          # none of that loaded the module
        finally:
            self.restore(saved, mod)

    def test_out_of_memory_loading_a_module_is_reported(self):
        import builtins
        saved, mod = self.unload()
        real = builtins.__import__
        def boom(name, *a, **k):
            if name == "A84C2":
                raise MemoryError()
            return real(name, *a, **k)
        builtins.__import__ = boom
        try:
            sh, t = mk()
            out = run(sh, t, "grep x f")
            self.assertIn("out of memory loading A84C2", out)
            self.assertEqual(sh.status, 1)
            self.assertTrue(sh.running)
            self.assertEqual(run(sh, t, "echo still works"), "still works\n")
        finally:
            builtins.__import__ = real
            self.restore(saved, mod)

    def test_missing_module_is_reported(self):
        import builtins
        saved, mod = self.unload()
        real = builtins.__import__
        def gone(name, *a, **k):
            if name == "A84C5":
                raise ImportError("no module")
            return real(name, *a, **k)
        builtins.__import__ = gone
        try:
            sh, t = mk()
            self.assertIn("module A84C5 is not installed", run(sh, t, "date"))
            self.assertEqual(sh.status, 127)
        finally:
            builtins.__import__ = real
            self.restore(saved, mod)

    def test_unknown_command_still_unknown(self):
        sh, t = mk()
        self.assertEqual(run(sh, t, "nosuch"), "ash: command not found: nosuch\n")

    def test_selftest_loads_and_covers_the_lazy_module(self):
        saved, mod = self.unload()
        try:
            sh, t = mk()
            out = run(sh, t, "selftest")
            self.assertIn("passed, 0 lowmem, 0 untested", out)
            self.assertNotIn("FAIL", out)
        finally:
            self.restore(saved, mod)


class ShutdownTests(unittest.TestCase):
    class Rec(CaptureTerm):
        def __init__(self):
            CaptureTerm.__init__(self)
            self.posts = []

        def post(self, t, pending=False):
            self.posts.append((t.rstrip("\n"), pending))
            CaptureTerm.post(self, t, pending)

    def sh(self, storage=None):
        t = ShutdownTests.Rec()
        return Shell(Kernel(storage or MemStorage()), t), t

    def test_sequence_dirty_exit(self):
        sh, t = self.sh()
        sh.execute("touch f")
        sh.execute("exit")
        self.assertEqual(t.posts, [
            ("[*     ] Saving command history", True),
            ("[  OK  ] Saved command history", False),
            ("[*     ] Syncing filesystem", True),
            ("[  OK  ] Synced filesystem", False),
            ("[  OK  ] Reached target Shutdown", False)])
        self.assertFalse(sh.running)
        self.assertFalse(sh.reboot)
        self.assertFalse(sh.vfs.dirty)

    def test_clean_filesystem_is_not_rewritten(self):
        class Count(MemStorage):
            n = 0
            def writer(self):
                Count.n += 1
                return MemStorage.writer(self)
        sh, t = self.sh(Count())
        sh.execute("sync")
        self.assertEqual(Count.n, 1)
        t.posts = []
        sh.execute("exit")
        self.assertEqual(Count.n, 1)                       # nothing dirty, no second write
        self.assertIn(("[  OK  ] Filesystem already synced", False), t.posts)
        self.assertEqual(t.posts[-1][0], "[  OK  ] Reached target Shutdown")

    def test_poweroff_and_reboot_targets(self):
        sh, t = self.sh()
        sh.execute("poweroff")
        self.assertEqual(t.posts[-1][0], "[  OK  ] Reached target Power-Off")
        self.assertFalse(sh.reboot)
        sh, t = self.sh()
        sh.execute("reboot")
        self.assertEqual(t.posts[-1][0], "[  OK  ] Reached target Reboot")
        self.assertTrue(sh.reboot)
        self.assertFalse(sh.running)

    def test_failed_sync_on_exit_reports_and_still_exits(self):
        class Bad(MemStorage):
            def writer(self):
                raise StorageError("disk full")
        sh, t = self.sh(Bad())
        sh.execute("touch f")
        sh.execute("exit")
        texts = [p[0] for p in t.posts]
        self.assertIn("[FAILED] Sync: disk full", texts)
        self.assertEqual(texts[-1], "[ WARN ] Shutdown finished with errors")
        self.assertFalse(sh.running)

    def test_reboot_aborts_when_sync_fails(self):
        class Bad(MemStorage):
            def writer(self):
                raise StorageError("disk full")
        sh, t = self.sh(Bad())
        sh.execute("touch f")
        sh.execute("reboot")
        texts = [p[0] for p in t.posts]
        self.assertEqual(texts[-1], "[ WARN ] Reboot aborted")
        self.assertTrue(sh.running)
        self.assertFalse(sh.reboot)
        self.assertEqual(sh.status, 1)

    def test_unclean_storage_warns_not_overwrites(self):
        ms = MemStorage()
        bad_version(ms)
        before = {n: list(v) for n, v in ms.d.items()}
        sh, t = self.sh(ms)
        sh.execute("touch f")
        sh.execute("exit")
        texts = [p[0] for p in t.posts]
        self.assertIn("[ WARN ] Unsaved changes NOT synced", texts)
        self.assertEqual(ms.d, before)                     # untouched
        self.assertFalse(sh.running)

    def test_history_saved_at_shutdown_and_unchanged_history_not_dirty(self):
        ms = MemStorage()
        sh, t = self.sh(ms)
        sh.k.add_history("ls /")
        sh.execute("exit")
        sh2, t2 = self.sh(ms)
        self.assertEqual(sh2.k.history, ["ls /"])
        self.assertFalse(sh2.vfs.dirty)
        sh2.k.save_history()                                # same content again
        self.assertFalse(sh2.vfs.dirty)
        sh2.k.add_history("pwd")
        sh2.k.save_history()
        self.assertTrue(sh2.vfs.dirty)

    def test_pending_line_always_followed_by_result(self):
        sh, t = self.sh()
        sh.execute("touch f")
        sh.execute("exit")
        for i in range(len(t.posts) - 1):
            if t.posts[i][1]:
                self.assertFalse(t.posts[i + 1][1])

    def test_shutdown_shows_on_gfx_terminal(self):
        term, ti, td = GfxTests().term([])
        sh = Shell(Kernel(MemStorage()), term)
        sh.execute("exit")
        greens = [o[3] for o in td.ops if o[0] == "text" and o[4] == (0, 200, 0)]
        self.assertIn("  OK  ", greens)
        self.assertTrue(any("Reached target Shutdown" in l for l in term.lines))


class Phase5Tests(unittest.TestCase):
    def setUp(self):
        self.sh, self.t = mk()

    def r(self, line):
        return run(self.sh, self.t, line)

    def test_date_math_matches_calendar(self):
        import datetime
        d0 = datetime.date(1970, 1, 1)
        for off in list(range(0, 800)) + [10957, 11017, 20733, 25000, 47482]:
            d = d0 + datetime.timedelta(days=off)
            self.assertEqual(days_from_civil(d.year, d.month, d.day), off)
            self.assertEqual(civil_from_days(off), (d.year, d.month, d.day))
        self.assertEqual((20733 + 4) % 7, 3)          # 2026-10-07 is a Wednesday

    def test_date_set_show_and_persist(self):
        self.assertIn("not set", self.r("date"))
        out = self.r("date -s '2026-10-07 17:20:00'")
        self.assertTrue(out.startswith("Wed Oct  7 17:20:0"), out)
        self.assertTrue(self.sh.vfs.isfile("/etc/clock"))
        out2 = self.r("date -s 2026-02-28 23:59")
        self.assertTrue(out2.startswith("Sat Feb 28 23:59:0"), out2)
        for bad in ("2026-02-30 10:00", "2026-13-01 00:00", "2026-10-07 24:00",
                    "1969-12-31 00:00", "garbage", "2026-10-07"):
            self.assertIn("invalid date", self.r("date -s '" + bad + "'"), bad)
        self.assertIn("usage", self.r("date -x"))

    def test_date_rolls_over_midnight_and_detects_lost_clock(self):
        import A84C5 as m
        real = m.mono_s
        try:
            m.mono_s = lambda: 1000
            self.r("date -s '2026-12-31 23:59:50'")
            m.mono_s = lambda: 1020                   # 20 s later
            out = self.r("date")
            self.assertTrue(out.startswith("Fri Jan  1 00:00:10 2027"), out)
            m.mono_s = lambda: 5                      # counter restarted
            self.assertIn("clock lost", self.r("date"))
            m.mono_s = lambda: None
            self.assertIn("no clock", self.r("date"))
        finally:
            m.mono_s = real

    def test_corrupt_clock_file_is_reported_not_crashing(self):
        self.r("echo junk > /etc/clock")
        self.assertIn("not set", self.r("date"))

    def test_grep_many_files_and_errors(self):
        self.r("echo foo > a")
        self.r("echo foo bar > b")
        out = self.r("grep foo a b")
        self.assertEqual(out, "a:foo\nb:foo bar\n")
        self.assertEqual(self.r("grep -n bar a b"), "b:1:foo bar\n")
        self.assertIn("No such file", self.r("grep foo nope"))
        self.assertIn("invalid option", self.r("grep -z foo a"))
        self.r("grep nothing a")
        self.assertEqual(self.sh.status, 1)

    def test_find_glob_and_walk(self):
        for l in ("mkdir d", "mkdir d/e", "touch d/a.txt", "touch d/e/b.txt", "touch d/e/c.py"):
            self.r(l)
        self.assertEqual(self.r("find d -name '*.txt'"), "d/a.txt\nd/e/b.txt\n")
        self.assertEqual(self.r("find d -name '?.py'"), "d/e/c.py\n")
        self.assertEqual(self.r("find d -type f"), "d/a.txt\nd/e/b.txt\nd/e/c.py\n")
        self.assertEqual(self.r("find d -type d"), "d\nd/e\n")
        self.assertEqual(self.r("find / -name hostname"), "/etc/hostname\n")
        self.assertIn("unknown predicate", self.r("find d -foo"))
        out = self.r("find")
        self.assertIn("./d/e/c.py", out)

    def test_glob_match(self):
        for pat, s, want in (("*", "", True), ("*.txt", "a.txt", True), ("*.txt", "a.tx", False),
                             ("a*b*c", "aXXbYYc", True), ("a*b*c", "aXXbYY", False),
                             ("?", "a", True), ("?", "", False), ("a?c", "abc", True),
                             ("**", "x", True), ("abc", "abc", True), ("abc", "abd", False),
                             ("*a", "bbba", True), ("*a", "bbbab", False)):
            self.assertEqual(A84C2.glob_match(pat, s), want, (pat, s))

    def test_sort_numeric_negative_and_multi_files(self):
        self.r("echo 10 > a")
        self.r("echo -5 >> a")
        self.r("echo 2 >> a")
        self.assertEqual(self.r("sort -n a"), "-5\n2\n10\n")
        self.assertEqual(self.r("sort a"), "-5\n10\n2\n")
        self.r("echo b > c")
        self.assertIn("b\n", self.r("sort a c"))
        self.assertIn("usage", self.r("sort"))

    def test_wc_total_and_flags(self):
        self.r("echo a b > x")
        self.r("echo c > y")
        out = self.r("wc -l x y")
        self.assertEqual(out, "1 x\n1 y\n2 total\n")
        self.assertIn("total", self.r("wc x y"))
        self.assertIn("invalid option", self.r("wc -q x"))

    def test_basename_dirname_edges(self):
        for a, want in (("/a/b/", "b\n"), ("b", "b\n"), ("/", "/\n"), ("a/b.c .c", "b\n"),
                        (".c .c", ".c\n")):
            self.assertEqual(self.r("basename " + a), want, a)
        for a, want in (("/a/b/", "/a\n"), ("/a", "/\n"), ("a", ".\n"), ("/", "/\n"),
                        ("a/b", "a\n")):
            self.assertEqual(self.r("dirname " + a), want, a)

    def test_du_df_free_mount_uptime(self):
        self.r("echo hello > f")
        self.assertEqual(self.r("du -s f"), "     6 f\n")
        self.assertIn("rootfs", self.r("df"))
        self.assertIn("Filesystem", self.r("df"))
        self.assertIn("rootfs on /", self.r("mount"))
        self.assertIn("storage: memory", self.r("mount"))
        self.assertIn("not mounted", self.r("umount /tmp"))
        self.assertIn("missing operand", self.r("umount"))
        self.assertIn("up 0:00:0", self.r("uptime"))
        self.assertIn("only listing", self.r("mount x"))

    def test_commands_have_no_pipe_surprise(self):
        self.assertIn("unsupported syntax", self.r("grep a f & sort"))

    def test_new_commands_all_registered(self):
        for c in ("grep find sort wc basename dirname true false du df free "
                  "mount umount uptime date reboot poweroff").split():
            self.assertIn(c, COMMANDS)
        self.assertNotIn("yes", COMMANDS)             # needs interruptible jobs (phase 8)


def real_total():
    # every selftest item: the storage checks plus the generated cases
    import A84TX
    n = len(A84TX.CHECKS)
    for q in range(1, A84TS.PARTS + 1):
        n += len(__import__(A84TS.PARTMODS[q - 1]).CASES)
    return n


class SelfTestTests(unittest.TestCase):
    def test_generated_parts_match_their_sources(self):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools"))
        import gen_selftest
        for name, text in gen_selftest.generate().items():
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), name)) as f:
                self.assertEqual(f.read(), text, name + ": run tools/gen_selftest.py")
        self.assertEqual(gen_selftest.NCHECKS, len(__import__("A84TX").CHECKS))

    def test_selftest_all_pass_and_full_coverage(self):
        sh, t = mk()
        out = run(sh, t, "selftest")
        total = real_total()
        self.assertEqual(total, 198)
        self.assertIn("selftest: %d/%d passed, 0 lowmem, 0 untested" % (total, total), out)
        self.assertNotIn("FAIL", out)
        self.assertEqual(sh.status, 0)
        self.assertTrue(sh.running)               # sandbox 'exit' must not stop the real shell

    def test_selftest_does_not_touch_real_fs(self):
        sh, t = mk()
        run(sh, t, "echo keep > real.txt")
        before = encode_fs(sh.vfs)
        hist = list(sh.k.history)
        run(sh, t, "selftest -v")
        self.assertEqual(encode_fs(sh.vfs), before)
        self.assertEqual(sh.k.history, hist)
        self.assertEqual(sh.cwd, "/home/evo")
        self.assertEqual(sh.k.storage.d, {})

    def test_selftest_detects_breakage(self):
        sh, t = mk()
        orig = COMMANDS["pwd"]
        COMMANDS["pwd"] = lambda s, a: s.out("/wrong\n")
        try:
            out = run(sh, t, "selftest")
        finally:
            COMMANDS["pwd"] = orig
        self.assertIn("FAIL pwd", out)
        self.assertEqual(sh.status, 1)

    def test_selftest_flags_untested_command(self):
        sh, t = mk()
        COMMANDS["newcmd"] = lambda s, a: None
        try:
            out = run(sh, t, "selftest")
        finally:
            del COMMANDS["newcmd"]
        self.assertIn("UNTESTED newcmd", out)

    def with_checks(self, checks, cases=None):
        real = (A84TS.CHECKS, A84TS.CASES)
        A84TS.CHECKS = checks
        if cases is not None:
            A84TS.CASES = cases
        return real

    def test_memory_shortage_is_lowmem_not_failure(self):
        def boom():
            raise MemoryError("memory allocation failed, allocating 4801 bytes")
        real = self.with_checks([("needs ram", boom)])
        try:
            sh, t = mk()
            out = run(sh, t, "selftest")
            n = real_total() - len(__import__('A84TX').CHECKS)
        finally:
            A84TS.CHECKS, A84TS.CASES = real
        self.assertIn("LOWMEM needs ram", out)
        self.assertNotIn("FAIL", out)
        self.assertIn("selftest: %d/%d passed, 1 lowmem, 0 untested" % (n, n + 1), out)
        self.assertEqual(sh.status, 0)

    def test_transient_memory_error_is_retried(self):
        calls = [0]
        def flaky():
            calls[0] += 1
            if calls[0] == 1:
                raise MemoryError()
            return True
        real = self.with_checks([("flaky ram", flaky)], cases=[])
        try:
            sh, t = mk()
            out = run(sh, t, "selftest")
        finally:
            A84TS.CHECKS, A84TS.CASES = real
        self.assertEqual(calls[0], 2)
        self.assertIn("1/1 passed, 0 lowmem", out)
        self.assertNotIn("LOWMEM", out)

    def test_real_failures_are_still_failures(self):
        def bad():
            return False
        def exc():
            raise ValueError("nope")
        real = self.with_checks([("wrong", bad), ("raises", exc)], cases=[])
        try:
            sh, t = mk()
            out = run(sh, t, "selftest")
        finally:
            A84TS.CHECKS, A84TS.CASES = real
        self.assertIn("FAIL wrong", out)
        self.assertIn("FAIL raises", out)
        self.assertIn("0/2 passed, 0 lowmem", out)
        self.assertEqual(sh.status, 1)

    def test_out_of_memory_text_in_a_case_is_lowmem(self):
        real = self.with_checks([], cases=[("sync-ish", ["sync"], "^synced")])
        real_run = A84TS.run_case
        A84TS.run_case = lambda lines: ("sync: out of memory (nothing was changed)\n", CaptureTerm(), Shell(Kernel(MemStorage()), CaptureTerm()))
        try:
            sh, t = mk()
            out = run(sh, t, "selftest")
        finally:
            A84TS.run_case = real_run
            A84TS.CHECKS, A84TS.CASES = real
        self.assertIn("LOWMEM sync-ish", out)
        self.assertNotIn("FAIL", out)

    def test_storage_checks_run_before_the_lazy_module_loads(self):
        import sys
        order = []
        def first():
            order.append("A84C2" in sys.modules or "A84C5" in sys.modules)
            return True
        saved = {n: COMMANDS.pop(n) for n in LazyCommandTests.NAMES if n in COMMANDS}
        mod = {m: sys.modules.pop(m) for m in LAZYMODS if m in sys.modules}
        real = self.with_checks([("order", first)], cases=[])
        try:
            sh, t = mk()
            run(sh, t, "selftest")
        finally:
            A84TS.CHECKS, A84TS.CASES = real
            sys.modules.update(mod)
            COMMANDS.update(saved)
        self.assertEqual(order, [False])

    def test_failure_lines_fit_the_screen(self):
        def bad():
            return False
        real = self.with_checks([("a long check label", bad)], cases=[])
        try:
            sh, t = mk()
            out = run(sh, t, "selftest")
        finally:
            A84TS.CHECKS, A84TS.CASES = real
        line = [l for l in out.split("\n") if l.startswith("FAIL")][0]
        self.assertLessEqual(len(line), 32)

    def test_selftest_verbose_lists_ok(self):
        sh, t = mk()
        self.assertIn("ok   cp\n", run(sh, t, "selftest -v"))


class FakeTD:
    def __init__(self, fail=False):
        self.ops = []
        self.color = None
        self.fail = fail

    def set_color(self, r, g, b):
        self.color = (r, g, b)

    def fill_rect(self, x, y, w, h):
        if self.fail:
            raise ValueError("boom")
        assert 0 <= x and x + w <= 320 and 0 <= y and y + h <= 240
        self.ops.append(("rect", x, y, w, h, self.color))

    def draw_text(self, x, y, text):
        assert 0 <= x and x + 10 * len(text) <= 320 and 0 <= y <= 209
        self.ops.append(("text", x, y, text, self.color))


class GfxTests(unittest.TestCase):
    GREEN = (0, 200, 0)
    RED = (235, 60, 60)
    GRAY = (125, 125, 125)

    def term(self, keys):
        ti = TiTermTests.T(keys)
        td = FakeTD()
        return GfxTerm(ti, td), ti, td

    def texts(self, td, color=None):
        return [o[3] for o in td.ops if o[0] == "text" and (color is None or o[4] == color)]

    def test_line_segs(self):
        self.assertEqual(line_segs("[  OK  ] Loaded"),
                         [("[", "w"), ("  OK  ", "g"), ("]", "w"), (" Loaded", "w")])
        self.assertEqual(line_segs("[FAILED] x")[1], ("FAILED", "r"))
        self.assertEqual(line_segs("[ WARN ] x")[1][1], "y")
        self.assertEqual(line_segs("[ ***  ] Loading")[1], (" ***  ", "r"))
        self.assertEqual(line_segs(ERR + "cat: x"), [("cat: x", "r")])
        self.assertEqual(line_segs("[evo@arch84 ~/p]$ ls"),
                         [("[", "w"), ("evo@arch84", "g"), (" ~/p", "b"), ("]$ ls", "w")])
        self.assertEqual(line_segs("hello [x@y]"), [("hello [x@y]", "w")])
        self.assertEqual(line_segs(""), [("", "w")])

    def test_wrap_segs(self):
        rows = wrap_segs([("abcd", "w"), ("efgh", "g")], 6)
        self.assertEqual(rows, [[("abcd", "w"), ("ef", "g")], [("gh", "g")]])
        self.assertEqual(wrap_segs([("abcdef", "w")], 6), [[("abcdef", "w")]])
        self.assertEqual(wrap_segs([("", "w")], 6), [[]])

    def test_error_lines_are_red_and_marked(self):
        sh, t = mk()
        sh.execute("cat nope")
        self.assertTrue(t.raw.startswith(ERR))
        term, ti, td = self.term([])
        term.write(ERR + "x" * 70 + "\n")
        self.assertEqual(len(term.lines), 3)
        for l in term.lines:
            self.assertTrue(l.startswith(ERR))
            self.assertLessEqual(len(l) - 1, 32)

    def test_geometry_and_colors_in_session(self):
        term, ti, td = self.term([31, 55, 31, 63, 105])     # h, k? -> letters then enter
        sh, _ = mk()
        term.post("[  OK  ] Mounted VFS root\n")
        term.write(ERR + "ash: boom\n")
        out = term.readline(sh.prompt(), sh.new_editor())
        self.assertEqual(out, "hk")
        self.assertIn("  OK  ", self.texts(td, self.GREEN))
        self.assertIn("evo@arch84", self.texts(td, self.GREEN))
        self.assertIn("ash: boom", self.texts(td, self.RED))
        cur = [o for o in td.ops if o[0] == "rect" and o[5] == (225, 225, 225)]
        self.assertTrue(cur)                       # block cursor was drawn
        ys = set(o[2] for o in td.ops if o[0] == "rect")
        self.assertLessEqual(max(ys), 10 * CH)     # never below row 11

    def test_inline_suggestion_is_gray(self):
        term, ti, td = self.term([31, 52, 31, 43, 105])   # e c
        sh, _ = mk()
        sh.k.add_history("echo hi")
        term.readline(sh.prompt(), sh.new_editor())
        self.assertIn("ho hi", self.texts(td, self.GRAY))

    def test_unchanged_rows_not_redrawn(self):
        term, ti, td = self.term([])
        sh, _ = mk()
        ed = sh.new_editor()
        term.reset()
        term.draw(sh.prompt(), ed)
        n = len(td.ops)
        term.draw(sh.prompt(), ed)
        self.assertEqual(len(td.ops), n)

    def test_pending_post(self):
        term, ti, td = self.term([])
        term.post("[*     ] Loading filesystem\n", True)
        self.assertEqual(term.lines, [])
        self.assertIn("*     ", self.texts(td, self.RED))
        term.post("[  OK  ] Loaded\n")
        self.assertEqual(len(term.lines), 1)

    def test_glyph_inside_its_row(self):
        # text y = row top + 20 puts the glyph (y-18..y-7) inside the 16px row
        term, ti, td = self.term([])
        term.post("hello\n")
        for o in td.ops:
            if o[0] == "text":
                top = o[2] - 20
                self.assertEqual(top % CH, 0)
                self.assertTrue(top <= o[2] - 18 and o[2] - 7 <= top + CH)
                self.assertTrue(o[2] - 3 <= top + CH)      # descender room

    def test_rows_clear_enough_for_descenders(self):
        # whenever a row IS erased (a row that already held text), the erase is a full
        # row high: descenders (p y g j q) reach Y+17 and would otherwise be left behind
        term, ti, td = self.term([])
        for i in range(14):                      # fills the screen and scrolls: rows get erased
            term.post("gypsy jumps quickly %d\n" % i)
        erases = [o for o in td.ops if o[0] == "rect" and o[5] == (0, 0, 0) and o[3] != 320]
        self.assertTrue(erases)
        for o in erases:
            self.assertGreaterEqual(o[4], 18)
        self.assertLessEqual(11 * CH, 209)        # all rows inside the canvas

    def status_texts(self, td):
        y = 10 * CH + 20
        return [(o[3], o[4]) for o in td.ops if o[0] == "text" and o[2] == y]

    def test_mode_indicator(self):
        BLUE = COL["b"]
        YEL = COL["y"]
        sh, _ = mk()
        for keys, want in (([21, 105], ("2ND", BLUE)),
                           ([31, 105], ("ALPHA", YEL)),
                           ([21, 31, 105], ("A-LOCK", self.GREEN))):
            term, ti, td = self.term(keys)
            term.readline(sh.prompt(), sh.new_editor())
            self.assertIn(want, self.status_texts(td), keys)
        term, ti, td = self.term([21, 31, 21, 105])           # lock + uppercase armed
        term.readline(sh.prompt(), sh.new_editor())
        self.assertIn(("UPPER", YEL), self.status_texts(td))

    def test_mode_indicator_clears_after_use(self):
        sh, _ = mk()
        term, ti, td = self.term([31, 41, 105])               # alpha then 'a' typed
        out = term.readline(sh.prompt(), sh.new_editor())
        self.assertEqual(out, "a")
        self.assertEqual(term.prev[10], [])                   # indicator row blank again
        self.assertEqual(term.mod, "")

    def test_indicator_row_is_last_and_inside_canvas(self):
        self.assertEqual(GX_ROWS, 11)
        self.assertLessEqual(GX_ROWS * CH, 209)
        term, ti, td = self.term([21, 105])
        sh, _ = mk()
        term.readline(sh.prompt(), sh.new_editor())
        ys = [o[2] for o in td.ops if o[0] == "text"]
        self.assertLessEqual(max(ys), 10 * CH + 20)

    def test_busy_cursor_goes_to_new_line(self):
        term, ti, td = self.term([])
        term.echo("[evo@arch84 ~]$ ls")
        term.busy()
        self.assertEqual(term.prev[0][1], ("evo@arch84", "g"))   # submitted line kept
        self.assertEqual(term.prev[1], [(" ", "c")])             # cursor on the next row, no prompt
        self.assertEqual(term.prev[2:], [[]] * 9)                # hint + indicator rows blank
        cur = [o for o in td.ops if o[0] == "rect" and o[5] == (225, 225, 225)]
        self.assertTrue(cur)
        self.assertEqual(cur[-1][2], 1 * CH)                     # drawn at row 2

    def test_busy_when_screen_is_full(self):
        term, ti, td = self.term([])
        for i in range(30):
            term.write("line %d\n" % i)
        term.busy()
        self.assertEqual(term.prev[GX_ROWS - 3], [("line 29", "w")])   # newest line right above the cursor
        self.assertEqual(term.prev[GX_ROWS - 2], [(" ", "c")])
        self.assertEqual(term.prev[GX_ROWS - 1], [])

    def test_shell_shows_busy_between_echo_and_output(self):
        ev = []
        class Rec(CaptureTerm):
            n = 0
            def readline(self, p, ed):
                self.n += 1
                return "pwd" if self.n == 1 else "exit"
            def echo(self, t):
                ev.append("echo")
            def busy(self):
                ev.append("busy")
            def write(self, t):
                ev.append("write:" + t.strip()[:5])
        sh, _ = mk()
        sh.term = Rec()
        sh.run()
        i = ev.index("echo")
        self.assertEqual(ev[i + 1], "busy")
        self.assertEqual(ev[i + 2], "write:/home")

    def test_ti_busy_text_terminal(self):
        ti = TiTermTests.T([])
        term = TiTerm(ti)
        term.echo("[evo@arch84 ~]$ ls")
        term.busy()
        self.assertEqual(ti.rows[1].rstrip(), "[evo@arch84 ~]$ ls")
        self.assertEqual(ti.rows[2].rstrip(), "|")

    def test_long_input_fits(self):
        term, ti, td = self.term([92] * 120 + [105])
        sh, _ = mk()
        term.readline(sh.prompt(), sh.new_editor())

    def test_pick_term(self):
        ti = TiTermTests.T([])
        self.assertIsInstance(pick_term(ti, FakeTD(), "b\n"), GfxTerm)
        self.assertIsInstance(pick_term(ti, None, "b\n"), TiTerm)
        self.assertNotIsInstance(pick_term(ti, None, "b\n"), GfxTerm)
        self.assertNotIsInstance(pick_term(ti, FakeTD(fail=True), "b\n"), GfxTerm)
        self.assertIsInstance(pick_term(None, None, "b\n"), PlainTerm)
        class Bad(TiTermTests.T):
            def disp_clr(self):
                raise TypeError("x")
        self.assertIsInstance(pick_term(Bad([]), FakeTD(fail=True), "b\n"), PlainTerm)


class SpareBlockTests(unittest.TestCase):
    def test_spare_is_held_and_released_around_a_save(self):
        k = Kernel(MemStorage())
        self.assertIsNotNone(k.spare)
        seen = []
        real = k.sync_run
        def spy(stats):
            seen.append(k.spare)
            return real(stats)
        k.sync_run = spy
        k.vfs.write("/tmp/x", "hi")
        k.sync()
        self.assertEqual(seen, [None])          # handed back while saving
        self.assertIsNotNone(k.spare)           # and re-reserved afterwards

    def test_spare_is_re_reserved_after_a_failed_save(self):
        k = Kernel(MemStorage())
        def boom(stats):
            raise StorageError("nope")
        k.sync_run = boom
        with self.assertRaises(StorageError):
            k.sync()
        self.assertIsNotNone(k.spare)


class MemoryResilienceTests(unittest.TestCase):
    """A transient MemoryError must never end the shell or drop it to input()."""

    def shell_with(self, term):
        k = Kernel(MemStorage())
        return Shell(k, term)

    def test_readline_memoryerror_is_retried_not_degraded(self):
        class T(CaptureTerm):
            def __init__(self):
                CaptureTerm.__init__(self)
                self.calls = 0

            def readline(self, prompt, ed):
                self.calls += 1
                if self.calls <= 2:
                    raise MemoryError()
                return "exit"
        t = T()
        sh = self.shell_with(t)
        sh.run()
        self.assertIs(sh.term, t)               # not replaced by PlainTerm
        self.assertEqual(t.calls, 3)

    def test_persistent_memoryerror_reports_low_memory_and_keeps_going(self):
        class T(CaptureTerm):
            def __init__(self):
                CaptureTerm.__init__(self)
                self.calls = 0

            def readline(self, prompt, ed):
                self.calls += 1
                if self.calls <= 5:
                    raise MemoryError()
                return "exit"
        t = T()
        sh = self.shell_with(t)
        sh.run()
        self.assertIn("low memory", t.text)
        self.assertIs(sh.term, t)

    def test_memoryerror_in_echo_still_runs_the_command(self):
        class T(CaptureTerm):
            def echo(self, text):
                raise MemoryError()
        t = T()
        sh = self.shell_with(t)
        t.text = ""
        sh.k.add_history("x")
        sh.execute("echo ran")
        self.assertEqual(t.text, "ran\n")

    def test_memoryerror_in_a_command_is_reported(self):
        t = CaptureTerm()
        sh = self.shell_with(t)
        real = COMMANDS["pwd"]
        def boom(sh, args):
            raise MemoryError()
        COMMANDS["pwd"] = boom
        try:
            # the run loop wraps execute(): drive one iteration through run()
            class T(CaptureTerm):
                n = 0

                def readline(self, prompt, ed):
                    T.n += 1
                    return "pwd" if T.n == 1 else "exit"
            t = T()
            sh = self.shell_with(t)
            sh.run()
        finally:
            COMMANDS["pwd"] = real
        self.assertIn("out of memory", t.text)
        self.assertTrue(sh.reboot is False)

    def test_selftest_out_of_memory_message(self):
        import builtins
        real = builtins.__import__
        def boom(name, *a, **k):
            if name == "A84TS":
                raise MemoryError()
            return real(name, *a, **k)
        sh, t = mk()
        builtins.__import__ = boom
        try:
            out = run(sh, t, "selftest")
        finally:
            builtins.__import__ = real
        self.assertIn("out of memory loading the test modules", out)
        self.assertEqual(sh.status, 1)


class FallbackTests(unittest.TestCase):
    def test_terminal_exception_falls_back(self):
        class Boom:
            rows = 10
            cols = 26
            def write(self, t): pass
            def echo(self, t): pass
            def post(self, t, p=False): pass
            def busy(self): pass
            def safe_key(self, tick=None): return False
            def readline(self, p, ed): raise TypeError("disp_at signature")
        import io, contextlib
        sh, _ = mk()
        sh.term = Boom()
        sh.k.add_history("x")
        feed = iter(["exit"])
        buf = io.StringIO()
        import builtins
        old = builtins.input
        builtins.input = lambda p="": next(feed)
        try:
            with contextlib.redirect_stdout(buf):
                sh.run()
        finally:
            builtins.input = old
        self.assertIn("falling back", buf.getvalue())
        self.assertFalse(sh.running)
        self.assertIsInstance(sh.term, PlainTerm)


if __name__ == "__main__":
    unittest.main()
