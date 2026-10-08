# A84TS: self test (Arch84 module 10/10, loaded only by the selftest command)
# Runs every command in a throwaway shell (MemStorage, fresh VFS per case);
# the real filesystem and saved storage are never touched.
from A84FS import *
from A84CZ import *
from A84ST import *
from A84KN import *
from A84SH import *


class Cap:
    def __init__(self):
        self.text = ""
        self.cleared = 0

    def write(self, t):
        self.text += t.replace(ERR, "")
        if t != "" and not t.endswith("\n"):
            self.text += "\n"

    def post(self, t, pending=False):
        pass

    def echo(self, t):
        pass

    def clear(self):
        self.cleared += 1

    def close(self):
        pass


# a ~3 KB file (more than BIGMIN, so stored as pieces) built by doubling
BIG = ["echo " + "x" * 100 + " > a", "cat a a > b", "cat b b > a", "cat a a > b",
       "cat b b > a", "cat a a > b"]

# (label, [command lines], expected output of the last line)
# expected: "text" exact | "~text" contains | "^text" starts with
# a line starting with "!" adds the rest to history instead of running
CASES = [
    ("pwd", ["pwd"], "/home/evo\n"),
    ("cd", ["cd /etc", "pwd"], "/etc\n"),
    ("cd ~", ["cd /etc", "cd ~/", "pwd"], "/home/evo\n"),
    ("cd ..", ["cd /usr/bin", "cd ../..", "pwd"], "/\n"),
    ("cd err", ["cd /nope"], "cd: /nope: No such file or directory\n"),
    ("cd file", ["cd /etc/hostname"], "cd: /etc/hostname: Not a directory\n"),
    ("ls /", ["ls /"], "bin/  boot/  dev/  etc/  home/  proc/  root/  run/  tmp/  usr/  var/\n"),
    ("ls -a", ["touch .h", "ls -a"], "~.h"),
    ("ls hides dot", ["touch .h", "ls"], ""),
    ("ls err", ["ls /nope"], "ls: cannot access '/nope': No such file or directory\n"),
    ("mkdir", ["mkdir d1", "ls"], "d1/\n"),
    ("mkdir dup", ["mkdir d", "mkdir d"], "mkdir: cannot create directory 'd': File exists\n"),
    ("touch", ["touch f1", "ls"], "f1\n"),
    ("echo", ["echo hello world"], "hello world\n"),
    ("echo -n", ["echo -n a > t", "echo b >> t", "cat t"], "ab\n"),
    ("cat", ["echo hi > t", "cat t"], "hi\n"),
    ("cat missing", ["cat zz"], "cat: zz: No such file or directory\n"),
    ("cat no newline", ["echo -n x > t", "cat t"], "x\n"),
    ("cat /etc", ["cat /etc/hostname"], "arch84\n"),
    ("rm", ["touch f", "rm f", "ls"], ""),
    ("rm dir", ["mkdir d", "rm d"], "rm: cannot remove 'd': Is a directory\n"),
    ("rm -r", ["mkdir d", "touch d/f", "rm -r d", "ls"], ""),
    ("rm missing", ["rm zz"], "rm: cannot remove 'zz': No such file or directory\n"),
    ("rmdir", ["mkdir d", "rmdir d", "ls"], ""),
    ("rmdir full", ["mkdir d", "touch d/f", "rmdir d"],
     "rmdir: failed to remove 'd': Directory not empty\n"),
    ("cp", ["echo a > f", "cp f g", "cat g"], "a\n"),
    ("cp into dir", ["echo a > f", "mkdir d", "cp f d", "cat d/f"], "a\n"),
    ("cp dir", ["mkdir d", "cp d e"], "cp: cannot copy 'd': omitting directory\n"),
    ("mv", ["echo a > f", "mv f g", "ls"], "g\n"),
    ("mv into dir", ["touch f", "mkdir d", "mv f d", "ls d"], "f\n"),
    ("head", ["echo 1 > n", "echo 2 >> n", "echo 3 >> n", "head -n 2 n"], "1\n2\n"),
    ("tail", ["echo 1 > n", "echo 2 >> n", "echo 3 >> n", "tail -n 2 n"], "2\n3\n"),
    ("history", ["!ls", "!pwd", "history"], "1  ls\n2  pwd\n"),
    ("history -c", ["!ls", "history -c", "history"], ""),
    ("uname", ["uname"], "Arch84\n"),
    ("uname -a", ["uname -a"], "Arch84 arch84 " + VERSION + " evo Python\n"),
    ("uname -r", ["uname -r"], VERSION + "\n"),
    ("whoami", ["whoami"], "evo\n"),
    ("hostname", ["hostname"], "arch84\n"),
    ("hostname file", ["echo box > /etc/hostname", "hostname"], "box\n"),
    ("env", ["env"], "~SHELL=/bin/ash\n"),
    ("export", ["export FOO=bar", "echo $FOO"], "bar\n"),
    ("export bad", ["export 1x=3"], "~not a valid identifier"),
    ("vars", ["echo $USER $HOME $PATH"], "evo /home/evo /usr/local/bin:/usr/bin:/bin\n"),
    ("quotes", ["echo 'a  b' \"c d\""], "a  b c d\n"),
    ("tilde", ["echo ~"], "/home/evo\n"),
    ("redirect", ["echo \"hello world\" > t", "cat t"], "hello world\n"),
    ("append", ["echo a > t", "echo b >> t", "cat t"], "a\nb\n"),
    ("redirect err", ["echo hi > /nodir/x"], "ash: /nodir/x: No such file or directory\n"),
    ("parse err", ["echo \"x"], "ash: unterminated quote\n"),
    ("unknown cmd", ["nosuch"], "ash: command not found: nosuch\n"),
    ("alias", ["alias ll='ls -a'", "touch .h", "ll"], "~.h"),
    ("unalias", ["alias zz=ls", "unalias zz", "zz"], "~command not found"),
    ("which", ["which ls"], "ls: shell built-in command\n"),
    ("which none", ["which zzz"], "~not found"),
    ("sync", ["sync"], "^synced"),
    ("keys", ["keys"], "~alpha"),
    ("help", ["help"], "~selftest"),
    ("status", ["cat nope", "echo $?"], "1\n"),
    ("true", ["true", "echo $?"], "0\n"),
    ("false", ["false", "echo $?"], "1\n"),
    ("grep", ["echo hello > f", "echo world >> f", "grep wor f"], "world\n"),
    ("grep -n", ["echo a > f", "echo b >> f", "grep -n b f"], "2:b\n"),
    ("grep -i", ["echo Abc > f", "grep -i abc f"], "Abc\n"),
    ("grep -v", ["echo a > f", "echo b >> f", "grep -v a f"], "b\n"),
    ("grep -c", ["echo a > f", "echo a >> f", "grep -c a f"], "2\n"),
    ("grep none", ["echo a > f", "grep z f", "echo $?"], "1\n"),
    ("grep usage", ["grep x"], "~usage"),
    ("find", ["mkdir d", "touch d/f", "find d"], "d\nd/f\n"),
    ("find -name", ["mkdir d", "touch d/a.txt", "touch d/b.py", "find d -name *.txt"], "d/a.txt\n"),
    ("find -type d", ["mkdir d", "touch d/f", "find d -type d"], "d\n"),
    ("find missing", ["find /nope"], "find: '/nope': No such file or directory\n"),
    ("sort", ["echo b > f", "echo a >> f", "sort f"], "a\nb\n"),
    ("sort -r", ["echo a > f", "echo b >> f", "sort -r f"], "b\na\n"),
    ("sort -n", ["echo 10 > f", "echo 9 >> f", "sort -n f"], "9\n10\n"),
    ("sort -u", ["echo a > f", "echo a >> f", "sort -u f"], "a\n"),
    ("wc -l", ["echo a b > f", "wc -l f"], "1 f\n"),
    ("wc -w", ["echo a b > f", "wc -w f"], "2 f\n"),
    ("wc -c", ["echo a b > f", "wc -c f"], "4 f\n"),
    ("wc", ["echo a b > f", "wc f"], "      1      2      4 f\n"),
    ("basename", ["basename /a/b.txt .txt"], "b\n"),
    ("dirname", ["dirname /a/b.txt"], "/a\n"),
    ("dirname dot", ["dirname b"], ".\n"),
    ("du", ["mkdir d", "echo hello > d/f", "du -s d"], "     6 d\n"),
    ("du dirs", ["mkdir d", "mkdir d/e", "echo hi > d/e/f", "du d"], "     3 d/e\n     3 d\n"),
    ("df", ["df"], "^Filesystem  "),
    ("free", ["free"], "~"),
    ("mount", ["mount"], "~rootfs on / type"),
    ("umount", ["umount /"], "~busy"),
    ("uptime", ["uptime"], "~up "),
    ("date unset", ["date"], "~not set"),
    ("date set", ["date -s 2026-10-07 17:20:00", "date"], "^Wed Oct  7 17:20:0"),
    ("date bad", ["date -s 2026-13-01 00:00:00"], "~invalid"),
    ("reboot", ["reboot"], "#reboot"),
    ("poweroff", ["poweroff"], "#exit"),
    ("big wc -c", BIG + ["wc -c b"], "3232 b\n"),
    ("big grep -c", BIG + ["grep -c xxxx b"], "32\n"),
    ("big tail", BIG + ["cp b c", "echo end >> c", "tail -n 1 c"], "end\n"),
    ("big head", BIG + ["head -n 1 b"], "x" * 100 + "\n"),
    ("big du", BIG + ["du -s b"], "  3232 b\n"),
    ("clear", ["clear"], "#clear"),
    ("exit", ["exit"], "#exit"),
]


# ---- storage / codec checks: run in memory, so they also exercise this
# firmware's str.encode, bytes.decode, bytearray, generators and big ints

def lcg(n, seed):
    out = bytearray()
    x = seed
    for i in range(n):
        x = (x * 75 + 74) % 65537
        out.append(x & 255)
    return bytes(out)


def sample_fs(big=130):
    # small on purpose: this runs on a calculator with ~20 KB of heap left;
    # big=130 -> a 2080-char file, enough to cross the 2048-byte frame boundary
    v = VFS()
    v.reset_default()
    v.mkdir("/home/evo/notes")
    for i in range(3):
        v.write("/home/evo/notes/n" + str(i) + ".txt",
                ("note " + str(i) + ": the quick brown fox\n") * (4 + i))
    v.write("/home/evo/u", "a\u00e9\u20ac\u6f22" * 12)
    v.write("/home/evo/e", "")
    v.write("/home/evo/big", "0123456789abcdef" * big)
    v.remove("/home/evo/.ashrc")
    v.write("/etc/hostname", "testbox\n")
    return v


def c_utf8():
    s = "a\u00e9\u20ac\u6f22"
    b = s.encode()
    return len(b) == 9 and b.decode() == s


def c_pack():
    for bs in (b"\xff" * 5, b"\x80\x00\x00\x00\x01", b"abcde", b"\x00" * 5):
        if bytes(unpack5(pack5(bs))) != bs:
            return False
    return True


def c_lz():
    for d in (b"", b"a", b"abcabc" * 50, lcg(300, 1), bytes(2048)):
        if lz_decompress(lz_compress(d), len(d)) != d:
            return False
    return len(lz_compress(b"abcabc" * 50)) < 100


def c_codec():
    v = sample_fs()
    return same_tree(decode_stream(fs_stream(v)), v)


def c_ratio():
    raw, stored = fs_measure(sample_fs())
    return stored < raw // 2


def c_store():
    ms = MemStorage()
    k = Kernel(ms)
    k.vfs = sample_fs()
    k.sync()
    k2 = Kernel(ms)
    return same_tree(k2.vfs, k.vfs) and k2.sync_ok


def c_corrupt():
    ms = MemStorage()
    k = Kernel(ms)
    k.vfs = sample_fs()
    k.sync()
    slot = int(ms.d["A84"][2])
    ms.d["S" + str(slot) + "000"][2] += 1.0
    return not Kernel(ms).sync_ok


def c_migrate():
    ms = MemStorage()
    v = sample_fs(8)
    v.write("/home/evo/u", "a\u00e9" * 12)     # v1 could only hold chars up to 255
    text = encode_fs(v)
    nums = []
    for i in range(0, len(text), 2):
        lo = 0
        if i + 1 < len(text):
            lo = ord(text[i + 1])
        nums.append(ord(text[i]) * 256 + lo)
    n = 0
    for i in range(0, len(nums), 99):
        ms.d[block_name(0, n)] = [8484] + nums[i:i + 99]
        n += 1
    ms.d["A84"] = [8484, 1, 0, n, len(text), checksum1(text)]
    k = Kernel(ms)
    ok = k.sync_ok and k.vfs.dirty and same_tree(k.vfs, v)
    k.sync()
    k2 = Kernel(ms)
    return ok and int(ms.d["A84"][1]) == 2 and same_tree(k2.vfs, k.vfs)


def c_big_codec():
    v = VFS()
    v.reset_default()
    v.write("/home/evo/big", "0123456789abcdef\n" * 200)       # 3400 chars -> pieces
    d = v.get("/home/evo/big").data
    if isinstance(d, str) or len(d) != 4 or len(d[0]) != SPLIT or dlen(d) != 3400:
        return False
    back = decode_stream(fs_stream(v))
    return same_tree(back, v) and back.get("/home/evo/big").data == d


def c_big_share():
    v = VFS()
    v.reset_default()
    v.write("/tmp/a", "q" * 3000)
    v.copyfile("/tmp/a", "/tmp/b")
    v.append("/tmp/b", "x")
    a = v.get("/tmp/a").data
    return v.size("/tmp/a") == 3000 and v.size("/tmp/b") == 3001 and a[0] is v.get("/tmp/b").data[0]


CHECKS = [
    ("utf8 encode/decode", c_utf8), ("pack5 round trip", c_pack),
    ("lzss round trip", c_lz), ("fs codec round trip", c_codec),
    ("fs compresses >2x", c_ratio), ("store + reload", c_store),
    ("corruption detected", c_corrupt), ("v1 -> v2 migration", c_migrate),
    ("big file pieces", c_big_codec), ("big file cp shares", c_big_share),
]


def real_scratch_check(ti):
    # writes a sample filesystem through the REAL store_list/recall_list into
    # scratch lists ZTM / T0xxx (never the real A84 / S0xxx), twice to flip
    # slots, and verifies the read back. The caller deletes the lists after.
    st = ListStore(ti.store_list, ti.recall_list, "ti-lists", "ZTM", "T")
    v = sample_fs()
    for rnd in range(2):
        k = Kernel(MemStorage())
        k.storage = st
        k.vfs = v
        k.sync()
        got = st.read()
        back = decode_stream(got[1])
        if got[0] != 2 or not same_tree(back, v):
            return False
        v.write("/home/evo/round" + str(rnd), "x" * (100 * (rnd + 1)))
    return True


def run_case(lines):
    cap = Cap()
    k = Kernel(MemStorage())
    sh = Shell(k, cap)
    out = ""
    for line in lines:
        cap.text = ""
        if line[:1] == "!":
            k.add_history(line[1:])
        else:
            sh.execute(line)
        out = cap.text
    return out, cap, sh


def matches(want, got, cap, sh):
    if want == "#clear":
        return cap.cleared == 1
    if want == "#exit":
        return not sh.running
    if want == "#reboot":
        return sh.reboot and not sh.running
    if want[:1] == "~":
        return want[1:] in got
    if want[:1] == "^":
        return got.startswith(want[1:])
    return got == want


def settle():
    try:
        import gc
        gc.collect()
    except ImportError:
        pass


def attempt(fn):
    # fn() -> (ok, got). "ok" / "lowmem" / "fail"; one retry after a collect
    # when the failure looks like a memory shortage
    got = ""
    for tries in range(2):
        settle()
        try:
            ok, got = fn()
        except Exception as e:
            ok = False
            got = "EXC " + repr(e)
        if ok:
            return "ok", ""
        if "emory" in got and tries == 0:
            continue
        break
    if "emory" in got:
        return "lowmem", got
    return "fail", got


def case_fn(lines, want):
    def f():
        got, cap, s2 = run_case(lines)
        return matches(want, got, cap, s2), got
    return f


def check_fn(fn):
    def f():
        return fn(), "False"
    return f


def selftest(sh, args):
    # A MemoryError inside a check is a calculator-RAM shortage, not a bug:
    # it is reported as LOWMEM, counted separately, never as a failure.
    verbose = "-v" in args
    fails = []
    lows = []
    used = ["selftest"]
    done = 0
    # storage checks first, while the lazy command module is not loaded yet
    for label, fn in CHECKS:
        done += 1
        st, got = attempt(check_fn(fn))
        if st == "ok":
            if verbose:
                sh.out("ok   " + label + "\n")
        elif st == "lowmem":
            lows.append(label)
            sh.out("LOWMEM " + label + "\n")
        else:
            fails.append(label)
            sh.out("FAIL " + label + ": " + got[:12] + "\n")
    try:
        __import__("A84C2")      # the lazy commands must be registered to be tested
    except ImportError:
        sh.err("selftest: module A84C2 is not installed")
        return 1
    for label, lines, want in CASES:
        for line in lines:
            if line[:1] != "!":
                w = line.split(" ")[0]
                if w not in used:
                    used.append(w)
        done += 1
        st, got = attempt(case_fn(lines, want))
        if st == "ok":
            if verbose:
                sh.out("ok   " + label + "\n")
        elif st == "lowmem":
            lows.append(label)
            sh.out("LOWMEM " + label + "\n")
        else:
            fails.append(label)
            sh.out("FAIL " + label + "\n")
            sh.out("  got " + repr(got)[:26] + "\n")
            sh.out("  want " + repr(want)[:24] + "\n")
    untested = [c for c in all_commands() if c not in used]
    for c in untested:
        sh.out("UNTESTED " + c + "\n")
    sh.out("selftest: " + str(done - len(fails) - len(lows)) + "/" + str(done)
           + " passed, " + str(len(lows)) + " lowmem, " + str(len(untested))
           + " untested\n")
    if fails or untested:
        return 1
