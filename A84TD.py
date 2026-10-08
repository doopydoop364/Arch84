# A84TD: selftest cases (Arch84 module, split from A84TS to keep compile-time
# memory low; loaded only by the selftest command)
from A84FS import ERR, VERSION


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
