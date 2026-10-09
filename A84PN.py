# A84PN: the network side of pacman (Arch84 module, lazily loaded): `pacman -Sy` downloads the
# mirror's index, `pacman -S` downloads the package files it has to install. Everything goes
# through the PC bridge (A84NT, docs/NETWORK.md). Downloads are checked against the index
# (characters and checksum) before they enter the repository cache.
from A84FS import VFSError, dlen, dpieces
from A84PM import MIRROR, MIRRORCONF, REMOTEDB, REPO, PkgError, Sum
from A84PD import mkdirs, remote_rows
import A84NT

HEADER = "ARCH84-REPO 1"


def mirror(vfs):
    if vfs.isfile(MIRRORCONF):
        for line in vfs.lines(MIRRORCONF):
            line = line.strip()
            if line[:7] == "http://" or line[:8] == "https://":
                return line.rstrip("/")
    return MIRROR


def refresh(sh):
    # downloads the mirror's index -> (number of packages, None), (None, why not) or (None, None) when
    # this terminal has no network at all
    vfs = sh.vfs
    new = REMOTEDB + ".new"
    try:
        mkdirs(vfs, REMOTEDB[:REMOTEDB.rfind("/")], [])
        sh.k.spin("Downloading the package index")
        try:
            A84NT.fetch_file(sh, mirror(vfs) + "/index", new, 60000, "package index", 15.0)
        finally:
            sh.k.stop_spin()
        for line in vfs.lines(new):
            if line != HEADER:
                vfs.remove(new)
                return None, "not a package index"
            break
        vfs.rename(new, REMOTEDB)
    except A84NT.NoNet:
        return None, None               # no color terminal: no network, nothing to say
    except A84NT.NetError as e:
        return None, str(e)
    except VFSError as e:
        return None, str(e)
    return len(remote_rows(vfs)), None


def fetch(sh, file):
    # downloads the package file `file` of the index into the repository cache -> its path
    vfs = sh.vfs
    row = None
    for r in remote_rows(vfs):
        if r[2] == file:
            row = r
    if row is None:
        raise PkgError("not in the package index: " + file + " (pacman -Sy)")
    mkdirs(vfs, REPO, [])
    path = REPO + "/" + file
    sh.k.spin("Downloading " + file)
    try:
        A84NT.fetch_file(sh, mirror(vfs) + "/" + file, path, 60000, file, 25.0)
    except A84NT.NetError as e:
        raise PkgError("cannot download " + file + ": " + str(e))
    finally:
        sh.k.stop_spin()
    data = vfs._file(path).data
    s = Sum()
    for piece in dpieces(data):
        s.add(piece)
    if dlen(data) != row[3] or s.hex() != row[4]:
        vfs.remove(path)
        raise PkgError(file + ": corrupted download (size or checksum does not match the index)")
    return path
