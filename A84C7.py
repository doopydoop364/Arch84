# A84C7: uname whoami hostname which keys selftest (Arch84 module, loaded on first use;
# split from A84CE so the always-resident part stays small). Registers itself into COMMANDS.
from A84FS import VERSION
from A84CD import COMMANDS, LAZY, need


def cmd_uname(sh, args):
    host = sh.k.hostname()
    if not args:
        sh.out("Arch84\n")
        return
    parts = []
    for a in args:
        if a == "-a":
            parts = ["Arch84", host, VERSION, "evo", "Python"]
            break
        elif a == "-s":
            parts.append("Arch84")
        elif a == "-n":
            parts.append(host)
        elif a == "-r":
            parts.append(VERSION)
        else:
            sh.err("uname: invalid option '" + a + "'")
            return 1
    sh.out(" ".join(parts) + "\n")


def cmd_whoami(sh, args):
    sh.out(sh.k.env.get("USER", "evo") + "\n")


def cmd_hostname(sh, args):
    sh.out(sh.k.hostname() + "\n")


def cmd_which(sh, args):
    if not need(sh, "which", args):
        return 1
    st = 0
    for a in args:
        if a in sh.k.aliases:
            sh.out(a + ": aliased to " + sh.k.aliases[a] + "\n")
        elif a in COMMANDS or a in LAZY:
            sh.out(a + ": shell built-in command\n")
        else:
            found = False
            for d in sh.k.env.get("PATH", "").split(":"):
                if d != "" and sh.vfs.isfile(d.rstrip("/") + "/" + a):
                    sh.out(d.rstrip("/") + "/" + a + "\n")
                    found = True
                    break
            if not found:
                sh.err(a + " not found in " + sh.k.env.get("PATH", ""))
                st = 1
    return st


def cmd_keys(sh, args):
    sh.out("alpha=1 letter  2nd+alpha=lock\n"
           "2nd then letter = UPPER\n"
           "mode=Tab del=bksp clear=clr\n"
           "2nd+: <=home >=end del=del\n"
           "mem=space (-)=_ stat=~\n"
           "Y=\" window' zoom$ trace> graph=\n"
           "math or trace = >  2nd+()-+={}[]\n"
           "x^=^ /*-+ . , ( )\n"
           "sin=| cos=< tan=; x^2=\\ vars=&\n"
           "2nd+up/down = scroll\n")


def unload_selftest():
    # the test modules (~15 KB resident) are only needed while testing: drop
    # them on the calculator so a later sync/command has the memory back
    import sys
    if getattr(sys.implementation, "name", "") != "micropython":
        return                  # desktop tests patch and re-run the module
    try:
        for m in ("A84TS", "A84T1", "A84T2", "A84T3", "A84T4", "A84TX"):
            if m in sys.modules:
                del sys.modules[m]
    except Exception:
        pass
    import gc
    gc.collect()


def cmd_selftest(sh, args):
    # runs in a sandbox shell; never touches the real filesystem
    try:
        from A84TS import selftest
    except ImportError:
        sh.err("selftest: module A84TS is not installed")
        return 1
    except MemoryError:
        sh.err("selftest: out of memory loading the test modules (try reboot first)")
        return 1
    try:
        return selftest(sh, args)
    finally:
        selftest = None         # drop the last reference, then unload
        unload_selftest()


COMMANDS.update({
    "uname": cmd_uname, "whoami": cmd_whoami, "hostname": cmd_hostname,
    "which": cmd_which, "keys": cmd_keys, "selftest": cmd_selftest,
})
