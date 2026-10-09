"""One lock for every program that talks to the calculator over USB.

The calculator has one serial link and its Kermit sessions cannot interleave: two programs
(the bridge polling lists, deploy.py, the key typer, a screenshot) at once desync it. Every
tool takes this lock around its USB conversation:

    with usb_lock():
        ...talk to the calculator...

The lock is an flock on a file in /tmp, so a crashed program never leaves it held, and it
is re-entrant inside one process.
"""
import contextlib
import fcntl
import os
import threading
import time

PATH = os.environ.get("ARCH84_USB_LOCK", "/tmp/arch84-usb.lock")
_local = threading.local()
_thread_lock = threading.RLock()


class LockTimeout(Exception):
    pass


@contextlib.contextmanager
def usb_lock(timeout=120.0, poll=0.05):
    with _thread_lock:
        depth = getattr(_local, "depth", 0)
        if depth:
            _local.depth = depth + 1
            try:
                yield
            finally:
                _local.depth -= 1
            return
        fd = os.open(PATH, os.O_CREAT | os.O_RDWR, 0o666)
        t0 = time.time()
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.time() - t0 > timeout:
                        raise LockTimeout("the calculator link is busy (lock " + PATH + ")")
                    time.sleep(poll)
            _local.depth = 1
            try:
                yield
            finally:
                _local.depth = 0
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
