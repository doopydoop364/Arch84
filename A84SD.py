# A84SD: startup files and shutdown sequence (Arch84 module, mixed into Shell;
# split from A84SH to keep each module's compile-time memory peak low).
from A84FS import ERR, HOME, StorageError, VFSError
from A84PE import isname

NOSTARTUP = ("exit", "reboot", "poweroff")


class Lifecycle:
    def load_environment(self):
        # /etc/environment: NAME=value lines replace the built-in defaults
        # (USER, HOME, PATH, SHELL, HISTSIZE, HISTFILE, HOSTNAME ...)
        path = "/etc/environment"
        if not self.vfs.isfile(path):
            return 0
        n = 0
        for line in self.vfs.lines(path):
            line = line.strip()
            i = line.find("=")
            if i < 1 or line[0] == "#":
                continue
            name = line[:i].strip()
            ok = not ("0" <= name[0] <= "9")
            for c in name:
                if not isname(c):
                    ok = False
            if ok:
                self.k.env[name] = line[i + 1:].strip()
                n += 1
        return n

    def startup(self):
        # /etc/profile, ~/.profile, ~/.ashrc: one command per line.
        # exit/reboot/poweroff are refused here so a bad file cannot lock
        # the user out (there is no editor on the device yet).
        t = self.term
        self.load_environment()
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
