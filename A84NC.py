# A84NC: wget curl ping net ntpdate (Arch84 module, lazily loaded): the network commands.
# They talk to the bridge program on the computer through A84NT (the request is drawn on the
# screen, the answer typed in by the bridge: nothing else may touch the calculator meanwhile;
# CLEAR cancels). Registers into COMMANDS.
from A84FS import VFSError, mono_s, now_ms, ms_since
from A84CD import COMMANDS, fail
import A84NT
from A84NT import NetError


def url_name(url):
    i = url.find("?")
    if i >= 0:
        url = url[:i]
    url = url.rstrip("/")
    j = url.rfind("/")
    n = url[j + 1:]
    if n == "" or url.find("//") + 1 == j:
        return "index.html"
    return n


def is_url(u):
    return u[:7] == "http://" or u[:8] == "https://"


def cmd_wget(sh, args):
    out = None
    quiet = False
    urls = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-O" and i + 1 < len(args):
            out = args[i + 1]
            i += 1
        elif a == "-q":
            quiet = True
        elif is_url(a):
            urls.append(a)
        else:
            sh.err("wget: usage: wget [-q] [-O FILE] URL")
            return 1
        i += 1
    if len(urls) != 1:
        sh.err("wget: usage: wget [-q] [-O FILE] URL")
        return 1
    url = urls[0]
    path = sh.resolve(out if out is not None else url_name(url))
    sh.k.spin("Downloading " + url_name(url))
    try:
        n = A84NT.fetch_file(sh, url, path)
    except NetError as e:
        sh.k.stop_spin()
        sh.err("wget: " + str(e))
        return 1
    except VFSError as e:
        sh.k.stop_spin()
        fail(sh, "wget", path, e)
        return 1
    sh.k.stop_spin()
    sh.vfs.externalize(path, 300)       # a big download lives in lists, not the heap
    A84NT.drop("A84BM")
    if not quiet:
        sh.out("saved " + path + " (" + str(n) + " bytes)\n")


def cmd_curl(sh, args):
    urls = [a for a in args if is_url(a)]
    if len(urls) != 1 or len(urls) != len([a for a in args if a != "-s"]):
        sh.err("curl: usage: curl [-s] URL")
        return 1
    try:
        A84NT.fetch_text(sh, urls[0], sh.out)
    except NetError as e:
        sh.err("curl: " + str(e))
        return 1


def cmd_ping(sh, args):
    n = 1
    if len(args) == 2 and args[0] == "-c":
        try:
            n = int(args[1])
        except ValueError:
            n = 0
    elif args:
        n = 0
    if n < 1 or n > 20:
        sh.err("ping: usage: ping [-c COUNT]")
        return 1
    bad = 0
    for k in range(n):
        t0 = now_ms()
        try:
            status, data = A84NT.call(sh, A84NT.OP_PING, b"", 25.0)
        except NetError as e:
            sh.err("ping: " + str(e))
            return 1
        ms = ms_since(t0)
        if status != 0:
            bad += 1
            sh.err("ping: " + A84NT.explain(status, data))
        else:
            sh.out("bridge: " + data.decode() + " time=" + str(ms) + " ms\n")
    if bad:
        return 1


def cmd_net(sh, args):
    if args:
        sh.err("net: usage: net")
        return 1
    try:
        status, data = A84NT.call(sh, A84NT.OP_STAT, b"", 25.0)
    except NetError as e:
        sh.out("bridge: not responding\n")
        sh.err("net: " + str(e))
        return 1
    if status != 0:
        sh.err("net: " + A84NT.explain(status, data))
        return 1
    sh.out("bridge: up\n" + data.decode() + "\n")


def cmd_ntpdate(sh, args):
    # set the clock from the computer's (the calculator has no clock of its own)
    if args:
        sh.err("ntpdate: usage: ntpdate")
        return 1
    try:
        status, data = A84NT.call(sh, A84NT.OP_TIME, b"", 25.0)
    except NetError as e:
        sh.err("ntpdate: " + str(e))
        return 1
    mono = mono_s()
    try:
        f = data.decode().split(" ")
        local = int(f[0]) + int(f[1])
    except (ValueError, IndexError, UnicodeError):
        status = 1
    if status != 0 or mono is None:
        sh.err("ntpdate: no time from the bridge")
        return 1
    try:
        sh.vfs.write("/etc/clock", str(local // 86400) + " " + str(local % 86400) + " " + str(mono) + "\n")
    except VFSError as e:
        fail(sh, "ntpdate", "/etc/clock", e)
        return 1
    from A84C5 import cmd_date
    cmd_date(sh, [])


COMMANDS.update({"wget": cmd_wget, "curl": cmd_curl, "ping": cmd_ping, "net": cmd_net,
                 "ntpdate": cmd_ntpdate})
