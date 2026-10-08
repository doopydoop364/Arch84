# A84SH: shell (Arch84 module 9/10)

from A84FS import ERR, HOME, StorageError, VFSError, dappend, dlen, iter_lines, normalize
from A84PE import LineEditor, ParseError, parse
from A84UI import PlainTerm
from A84CD import COMMANDS, LAZY, load_command
from A84CP import Completer
import A84CE    # registers its commands into COMMANDS


# ----------------------------------------------------- shell + commands

NOSTARTUP = ("exit", "reboot", "poweroff")


class Shell(Completer):
    def __init__(self, kernel, term):
        self.k = kernel
        if kernel.log is None:
            kernel.log = term.post       # progress/pending lines go to this terminal
        self.vfs = kernel.vfs
        self.term = term
        self.cwd = HOME
        self.running = True
        self.reboot = False
        self.status = 0
        self._out = []
        self._outn = 0
        self._rpath = None
        self._rname = ""
        self._rfail = False
        self.stdin = None       # canonical file data of the pipe/`<` feeding this command
        self._cap = None        # canonical data collecting the output of a non-final stage

    # -- helpers used by commands
    def lines(self, arg):
        # lines of FILE, or of standard input for "-"
        if arg == "-":
            if self.stdin is None:
                return iter_lines("")
            return iter_lines(self.stdin)
        return self.vfs.lines(self.resolve(arg))

    def fsize(self, arg):
        if arg == "-":
            if self.stdin is None:
                return 0
            return dlen(self.stdin)
        return self.vfs.size(self.resolve(arg))

    def out(self, text):
        # output is flushed in ~512 B batches (on a line boundary), so a command
        # that prints a big file never builds one big string
        self._out.append(text)
        self._outn += len(text)
        if self._outn >= 512 and text.endswith("\n"):
            self.flush_out()

    def flush_out(self):
        text = "".join(self._out)
        self._out = []
        self._outn = 0
        if self._rpath is None and self._cap is not None:
            self._cap = dappend(self._cap, text)       # a pipe: kept in pieces, never one big string
        elif self._rpath is not None:
            try:
                self.vfs.append(self._rpath, text)
            except VFSError as e:
                self.err("ash: " + self._rname + ": " + str(e))
                self._rfail = True
                self._rpath = None
        elif text != "":
            self.term.write(text)

    def err(self, text):
        self.term.write(ERR + text + "\n")

    def resolve(self, path):
        return normalize(path, self.cwd, self.k.env.get("HOME", HOME))

    def prompt(self):
        home = self.k.env.get("HOME", HOME)
        p = self.cwd
        if p == home:
            p = "~"
        elif p.startswith(home + "/"):
            p = "~" + p[len(home):]
        return "[" + self.k.env.get("USER", "evo") + "@" + self.k.hostname() + " " + p + "]$ "

    def new_editor(self):
        return LineEditor(self.k.history, self.complete)

    # -- execution
    def expand_alias(self, line):
        seen = []
        while True:
            s = line.lstrip()
            i = 0
            while i < len(s) and s[i] != " " and s[i] != "\t":
                i += 1
            first = s[:i]
            if first in self.k.aliases and first not in seen:
                seen.append(first)
                line = self.k.aliases[first] + s[i:]
            else:
                return line

    def execute(self, line):
        env = dict(self.k.env)
        env["?"] = str(self.status)
        try:
            stages = parse(self.expand_alias(line), env,
                           self.k.env.get("HOME", HOME), True)
        except ParseError as e:
            self.err("ash: " + str(e))
            self.status = 2
            return
        n = len(stages)
        stdin = None
        try:
            for i in range(n):
                words, redir, infile = stages[i]
                if infile is not None:
                    try:
                        stdin = self.vfs._file(self.resolve(infile)).data   # shared, not copied
                    except VFSError as e:
                        self.err("ash: " + infile + ": " + str(e))
                        self.status = 1
                        return
                self.stdin = stdin
                self._cap = None
                if i < n - 1:
                    self._cap = ""
                self.run_stage(words, redir)
                stdin = self._cap       # "" (empty pipe) is still an input
        finally:
            self.stdin = None
            self._cap = None

    def run_stage(self, words, redir):
        if not words:
            if redir is not None:
                self.redirect(redir, "")
            return
        fn = COMMANDS.get(words[0])
        if fn is None and words[0] in LAZY:
            try:
                fn = load_command(words[0])
            except MemoryError:
                self.err("ash: " + words[0] + ": out of memory loading " + LAZY[words[0]])
                self.status = 1
                return
            except ImportError:
                self.err("ash: " + words[0] + ": module " + LAZY[words[0]] + " is not installed")
                self.status = 127
                return
        if fn is None:
            self.err("ash: command not found: " + words[0])
            self.status = 127
            return
        self._out = []
        self._outn = 0
        self._rpath = None
        self._rfail = False
        if redir is not None:
            # like a real shell: the target is opened (and a '>' target
            # truncated) before the command runs, and a bad target stops it
            mode, target = redir
            path = self.resolve(target)
            try:
                if mode == ">>":
                    self.vfs.append(path, "")
                else:
                    self.vfs.write(path, "")
            except VFSError as e:
                self.err("ash: " + target + ": " + str(e))
                self.status = 1
                return
            self._rpath = path
            self._rname = target
        st = fn(self, words[1:])
        self.flush_out()
        self.status = 0
        if st:
            self.status = st
        if self._rfail:
            self.status = 1
        self._rpath = None

    def redirect(self, redir, text):
        mode, target = redir
        path = self.resolve(target)
        try:
            if mode == ">>":
                self.vfs.append(path, text)
            else:
                self.vfs.write(path, text)
        except VFSError as e:
            self.err("ash: " + target + ": " + str(e))
            self.status = 1

    # -- completion: returns (start_index, [replacement, ...])
    def startup(self):
        # /etc/profile, ~/.profile, ~/.ashrc: one command per line.
        # exit/reboot/poweroff are refused here so a bad file cannot lock
        # the user out (there is no editor on the device yet).
        t = self.term
        home = self.k.env.get("HOME", HOME)
        for path in ("/etc/profile", home + "/.profile", home + "/.ashrc"):
            if not self.vfs.isfile(path):
                continue
            self.k.spin("Running " + path)
            errs = 0
            for line in self.vfs.read(path).split("\n"):
                line = line.strip()
                if line == "" or line[:1] == "#":
                    continue
                if line.split(" ")[0] in NOSTARTUP:
                    errs += 1
                    t.write(ERR + path + ": '" + line.split(" ")[0] + "' not allowed\n")
                    continue
                self.k.tick()
                self.execute(line)
                if self.status != 0:
                    errs += 1
            self.status = 0
            if errs:
                t.post("[ WARN ] " + path + ": " + str(errs) + " errors\n")
            else:
                t.post("[  OK  ] Ran " + path + "\n")

    def shutdown(self, kind):
        # kind: "exit", "poweroff" or "reboot". Shows each real task like
        # the boot does. Returns False only if a reboot was aborted.
        t = self.term
        ok = "[  OK  ] "
        errs = 0
        self.k.spin("Saving command history")
        try:
            self.k.save_history()
            t.post(ok + "Saved command history\n")
        except VFSError as e:
            errs += 1
            t.post("[FAILED] History: " + str(e) + "\n")
        if self.vfs.dirty:
            if self.k.sync_ok:
                self.k.spin("Syncing filesystem")
                try:
                    self.k.sync()
                    t.post(ok + "Synced filesystem\n")
                except StorageError as e:
                    t.post("[FAILED] Sync: " + str(e) + "\n")
                    if kind == "reboot":
                        t.post("[ WARN ] Reboot aborted\n")
                        return False
                    errs += 1
            else:
                errs += 1
                t.post("[ WARN ] Unsaved changes NOT synced\n")
        else:
            t.post(ok + "Filesystem already synced\n")
        if errs:
            t.post("[ WARN ] Shutdown finished with errors\n")
        elif kind == "reboot":
            t.post(ok + "Reached target Reboot\n")
        elif kind == "poweroff":
            t.post(ok + "Reached target Power-Off\n")
        else:
            t.post(ok + "Reached target Shutdown\n")
        self.running = False
        if kind == "reboot":
            self.reboot = True
        return True

    def run(self):
        t = self.term
        self.k.spin("Startup (hold CLEAR to skip)")
        if t.safe_key(self.k.tick):
            t.post("[ WARN ] Startup files skipped\n")
        else:
            self.startup()
        self.k.spin("Starting shell")
        if self.vfs.isdir(self.cwd) and len(COMMANDS) > 0:
            t.post("[  OK  ] Reached target Shell\n")
        else:
            self.cwd = "/"
            t.post("[FAILED] Shell: bad cwd, using /\n")
        t.post(self.k.hostname() + " login: " + self.k.env["USER"]
               + " (auto)\n")
        memerr = 0
        while self.running:
            self.vfs = self.k.vfs
            prompt = self.prompt()
            try:
                line = t.readline(prompt, self.new_editor())
            except EOFError:
                line = "exit"
            except MemoryError:
                # a transient shortage while typing/drawing is not an API
                # mismatch: free garbage and retry before giving up the terminal
                import gc
                gc.collect()
                memerr += 1
                if memerr < 4:
                    continue
                memerr = 0
                self.term.write(ERR + "ash: low memory\n")
                continue
            except Exception as e:
                # key/display API mismatch: degrade to input() instead of dying
                print("terminal error:", repr(e))
                if isinstance(t, PlainTerm):
                    self.running = False   # nothing left to fall back to
                    continue
                print("falling back to plain input() shell")
                self.term = t = PlainTerm()
                self.k.log = t.post
                continue
            memerr = 0
            try:
                t.echo(prompt + line)
                t.busy()
                self.k.add_history(line)
            except MemoryError:
                # cosmetic steps only: carry on and run the command
                import gc
                gc.collect()
            try:
                self.execute(line)
            except MemoryError:
                import gc
                gc.collect()
                t.write(ERR + "ash: out of memory\n")
                self.status = 1
            except Exception as e:
                t.write("ash: internal error: " + repr(e) + "\n")
        if not self.reboot:
            t.close()


