# A84SC: running script files (Arch84 module, loaded the first time a command is
# not built in). A file on PATH, or named with a "/", runs its lines as commands
# with $0..$9 and $#; exit/reboot/poweroff are refused; scripts nest 4 deep.
from A84FS import dpieces
from A84SD import NOSTARTUP

NAMES = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "#"]


def script_path(sh, name):
    if "/" in name:
        p = sh.resolve(name)
        if sh.vfs.isfile(p):
            return p
        return None
    for d in sh.k.env.get("PATH", "").split(":"):
        if d != "":
            p = d.rstrip("/") + "/" + name
            if sh.vfs.isfile(p):
                return p
    return None


def run_script(sh, path, argv):
    if sh._depth >= 4:
        sh.err("ash: " + path + ": scripts nested too deeply")
        return 126
    saved = (sh.stdin, sh._cap, sh._out, sh._outn, sh._rpath, sh._rname, sh._rfail, sh._tee)
    env = sh.k.env
    old = [env.get(n) for n in NAMES]
    for i in range(10):
        if i < len(argv):
            env[NAMES[i]] = argv[i]
        elif NAMES[i] in env:
            del env[NAMES[i]]
    env["#"] = str(len(argv) - 1)
    sh._depth += 1
    sh._tee = ""
    status = 0
    try:
        for line in sh.vfs.lines(path):
            line = line.strip()
            if line == "" or line[:1] == "#":
                continue
            if line.split(" ")[0] in NOSTARTUP:
                sh.err(path + ": '" + line.split(" ")[0] + "' not allowed in scripts")
                status = 1
                continue
            sh.execute(line)
            status = sh.status
    finally:
        out = sh._tee
        sh._depth -= 1
        for i in range(len(NAMES)):
            if old[i] is None:
                if NAMES[i] in env:
                    del env[NAMES[i]]
            else:
                env[NAMES[i]] = old[i]
        (sh.stdin, sh._cap, sh._out, sh._outn, sh._rpath, sh._rname, sh._rfail, sh._tee) = saved
    for piece in dpieces(out):
        sh.out(piece)
    return status
