# A84KN: kernel (Arch84 module 4/11). Re-exports A84PE (parser, line editor).

from A84FS import (DEFAULT_DIRS, HOME, PROFILE, StorageError, VERSION, VFS,
    VFSError, decode_fs, ms_since, now_ms)
from A84CZ import decode_stream, fs_stream, same_tree


# --------------------------------------------------------------- kernel

HIST_MAX = 40
HIST_FILE = HOME + "/.ash_history"


# systemd-style progress frames: a 3-asterisk window sliding through 6 cells
# (the tag is 8 chars wide, like "[  OK  ]")
SPIN = ("*     ", "**    ", "***   ", " ***  ", "  *** ", "   ***", "    **",
        "     *")
SPIN_MS = 90


def need_bytes(msg):
    # " (needed N B)" from "...allocating N bytes", or ""
    i = msg.find("allocating ")
    if i < 0:
        return ""
    j = msg.find(" bytes", i)
    if j < 0:
        return ""
    return " (needed " + msg[i + 11:j] + " B)"


SPARE = 3072    # contiguous block held back for sync/df (see hold_spare)


class Kernel:
    def __init__(self, storage, log=None):
        self.spare = None
        self.hold_spare()       # first thing: the heap is still unfragmented
        self.storage = storage
        self.log = log      # called with each boot line as its step finishes
        self.spin_msg = None
        self.spin_i = 0
        self.spin_t = None
        storage.progress = self.tick     # the storage reports each list it reads/writes
        self.vfs = None     # built by boot(): loading must not hold a spare default tree
        self.env = {"USER": "evo", "HOME": HOME, "PATH": "/usr/local/bin:/usr/bin:/bin",
                    "SHELL": "/bin/ash"}
        self.aliases = {}
        self.history = []
        self.sync_ok = True
        self.t0 = now_ms()
        self.boot_msgs = []
        self.boot()

    def hold_spare(self):
        # The calculator heap fragments: after file work there can be 30 KB
        # free but no hole over ~1 KB, and the writer needs contiguous
        # buffers. One block is reserved at boot and handed back right
        # before a save so those buffers land in it.
        if self.spare is None:
            try:
                self.spare = bytearray(SPARE)
            except MemoryError:
                self.spare = None

    def release_spare(self):
        self.spare = None
        import gc
        gc.collect()

    def spin(self, msg):
        # a task is running: "[*     ] msg", the asterisks slide as work is
        # reported through tick(), until say() (or stop_spin) ends it
        self.spin_msg = msg
        self.spin_i = 0
        self.spin_t = now_ms()
        self.show_spin()

    def pend(self, msg):
        self.spin(msg)

    def show_spin(self):
        if self.log is not None and self.spin_msg is not None:
            self.log("[" + SPIN[self.spin_i] + "] " + self.spin_msg + "\n", True)

    def tick(self):
        # called after every unit of real work (a list read/written, a frame
        # compressed); advances the animation at most every SPIN_MS
        if self.spin_msg is None:
            return
        d = ms_since(self.spin_t)
        if d is not None and d < SPIN_MS:
            return
        self.spin_t = now_ms()
        self.spin_i = (self.spin_i + 1) % len(SPIN)
        self.show_spin()

    def stop_spin(self):
        self.spin_msg = None

    def say(self, msg):
        self.spin_msg = None
        self.boot_msgs.append(msg)
        if self.log is not None:
            self.log(msg + "\n")

    def boot(self):
        ok = "[  OK  ] "
        bad = "[FAILED] "
        got = None
        migrated = False
        self.pend("Loading filesystem")
        try:
            got = self.storage.read()
        except StorageError as e:
            self.sync_ok = False
            self.say(bad + "Load fs: " + str(e))
            self.say("[ WARN ] Saving off (sync -f)")
        except MemoryError:
            self.sync_ok = False
            self.say(bad + "Load fs: out of memory")
            self.say("[ WARN ] Saving off (sync -f)")
        if got is not None:
            try:
                if got[0] == 1:
                    self.vfs = decode_fs(b"".join(got[1]).decode())
                    migrated = True
                else:
                    self.vfs = decode_stream(got[1])
                self.say(ok + "Restored fs (" + str(self.vfs.count()) + " nodes)")
            except (ValueError, StorageError, MemoryError) as e:
                self.sync_ok = False
                if "MemoryError" in repr(e) or isinstance(e, MemoryError):
                    self.say(bad + "Load fs: out of memory" + need_bytes(repr(e)))
                else:
                    self.say(bad + "Corrupt fs: " + str(e))
                self.say("[ WARN ] Saving off (sync -f)")
        elif self.sync_ok:
            self.say(ok + "Created new filesystem")
        if self.vfs is None:
            self.vfs = VFS()
            self.vfs.reset_default()
        if migrated and self.sync_ok:
            self.say("[ FIX  ] Upgrading filesystem to v2")
        self.pend("Checking system files")
        n = self.fix_system_files()
        if n:
            self.say("[ FIX  ] Repaired " + str(n) + " system files")
        else:
            self.say(ok + "Checked system files")
        self.pend("Mounting VFS root")
        if self.vfs.isdir("/") and self.vfs.isdir(HOME):
            self.say(ok + "Mounted VFS root")
        else:
            self.say(bad + "Mounted VFS root: no /home/evo")
        self.pend("Loading history")
        self.load_history()
        self.say(ok + "Loaded history (" + str(len(self.history)) + ")")
        if migrated and self.sync_ok:
            self.vfs.dirty = True       # the next sync (or exit) writes v2

    def fix_system_files(self):
        # recreate missing system dirs/files; returns how many were repaired
        v = self.vfs
        n = 0
        for d in DEFAULT_DIRS:
            if not v.exists(d):
                v.mkdir(d)
                n += 1
        if not v.isfile("/etc/hostname"):
            v.write("/etc/hostname", "arch84\n")
            n += 1
        if not v.isfile("/etc/profile"):
            v.write("/etc/profile", PROFILE)
            n += 1
        if not v.isfile("/etc/version") or v.read("/etc/version") != VERSION + "\n":
            v.write("/etc/version", VERSION + "\n")
        return n

    def hostname(self):
        try:
            h = self.vfs.read("/etc/hostname").strip()
        except VFSError:
            h = ""
        if h == "":
            h = "arch84"
        return h

    def load_history(self):
        if self.vfs.isfile(HIST_FILE):
            for line in self.vfs.read(HIST_FILE).split("\n"):
                if line != "":
                    self.history.append(line)
            self.history = self.history[-HIST_MAX:]

    def add_history(self, line):
        if line.strip() == "":
            return
        if self.history and self.history[-1] == line:
            return
        self.history.append(line)
        if len(self.history) > HIST_MAX:
            self.history = self.history[-HIST_MAX:]

    def save_history(self):
        # writes ~/.ash_history only if it changed (so it does not dirty the fs)
        if not self.vfs.isdir(HOME):
            return
        data = "\n".join(self.history) + "\n"
        if not self.vfs.isfile(HIST_FILE) or self.vfs.read(HIST_FILE) != data:
            self.vfs.write(HIST_FILE, data)

    def verify(self, w):
        # read the freshly written (not yet live) slot back; the caller
        # commits only if this returns. Returns a list of warnings.
        gen = w.readback()
        try:
            back = decode_stream(gen)
        except StorageError as e:
            raise StorageError("verify failed: " + str(e))
        except ValueError as e:
            if "MemoryError" not in str(e):
                raise StorageError("verify failed: " + str(e))
            back = None
        try:
            for x in gen:       # drain: runs the stream checksum
                pass
        except StorageError as e:
            raise StorageError("verify failed: " + str(e))
        if back is None:
            return ["verify: tree compare skipped (low memory)"]
        if not same_tree(back, self.vfs):
            raise StorageError("verify failed: saved tree differs")
        return []

    def sync(self, force=False):
        if not self.sync_ok and not force:
            raise StorageError("sync disabled: storage did not load cleanly "
                               "(sync -f to overwrite)")
        self.save_history()
        stats = [0, 0]
        self.release_spare()
        try:
            try:
                return self.sync_run(stats)
            except StorageError as e:
                if not str(e).startswith("out of memory"):
                    raise
            # A first attempt can fail only because the heap was full of
            # garbage / fragmented at that moment (the same save then works a
            # moment later). The inactive slot is simply rewritten.
            import gc
            gc.collect()
            stats[0] = 0
            stats[1] = 0
            return self.sync_run(stats)
        finally:
            self.hold_spare()

    def sync_run(self, stats):
        try:
            w = self.storage.writer()
            for fr in fs_stream(self.vfs, stats):
                w.feed(fr)
                self.tick()
            w.finish()
            self.tick()
            warnings = self.verify(w)
            nblocks, more = w.commit()
        except MemoryError:
            raise StorageError("out of memory (nothing was changed)")
        self.vfs.dirty = False
        self.sync_ok = True
        return stats[0], stats[1], nblocks, warnings + more
