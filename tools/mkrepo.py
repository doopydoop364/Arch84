#!/usr/bin/env python3
"""Build the Arch84 package repository from repo/src.

    repo/src/<name>/PKGINFO         version = 1.0 / desc = ... / depends = a b   (name = the folder)
    repo/src/<name>/root/...        the files, laid out as they appear on the calculator (usr/bin/...)

    python3 tools/mkrepo.py                    build repo/src -> repo/pkgs (the .ar84 files + index)
    python3 tools/mkrepo.py --publish          also copy repo/pkgs to <site>/arch84/pkgs, commit and push
                                               (site = a clone of doopydoop364.github.io, see --site)

The packages are built with the calculator's own makepkg code (A84PB.build) so they are exactly
what `pacman -U` expects; the index (ARCH84-REPO 1, one line per package: name, version, file,
size in characters, checksum, depends, escaped description, tab separated) is what `pacman -Sy`
downloads and `pacman -S` checks every download against.
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from A84FS import VFS, dpieces, dlen
from A84PM import REPO, Sum, esc
import A84PB


def read_info(path):
    info = {"version": "", "desc": "", "depends": ""}
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.strip() == "" or line.startswith("#"):
            continue
        k, _, v = line.partition("=")
        info[k.strip()] = v.strip()
    return info


def load_tree(vfs, disk, dest):
    vfs.mkdir(dest) if not vfs.isdir(dest) else None
    for name in sorted(os.listdir(disk)):
        p = os.path.join(disk, name)
        q = dest.rstrip("/") + "/" + name
        if os.path.isdir(p):
            if not vfs.isdir(q):
                vfs.mkdir(q)
            load_tree(vfs, p, q)
        else:
            vfs.write(q, open(p, encoding="utf-8").read())


def build_package(src_dir, name):
    info = read_info(os.path.join(src_dir, "PKGINFO"))
    if not info["version"]:
        raise SystemExit(name + ": PKGINFO needs a version")
    vfs = VFS()
    vfs.reset_default()
    for d in ("/tmp/pk", "/tmp/pk/usr"):
        if not vfs.isdir(d):
            vfs.mkdir(d)
    load_tree(vfs, os.path.join(src_dir, "root"), "/tmp/pk")
    out, nfiles, nbytes = A84PB.build(vfs, "/tmp/pk", name, info["version"], info["desc"], info["depends"].split())
    data = vfs._file(out).data
    text = "".join(dpieces(data))
    return info, text


def build_all(src, out):
    os.makedirs(out, exist_ok=True)
    rows = []
    for name in sorted(os.listdir(src)):
        d = os.path.join(src, name)
        if not os.path.isfile(os.path.join(d, "PKGINFO")):
            continue
        info, text = build_package(d, name)
        file = "%s-%s.ar84" % (name, info["version"])
        with open(os.path.join(out, file), "w", encoding="utf-8", newline="") as f:
            f.write(text)
        s = Sum()
        s.add(text)
        rows.append("\t".join([name, info["version"], file, str(len(text)), s.hex(),
                               info["depends"], esc(info["desc"])]))
        print("built %-28s %6d chars  %s" % (file, len(text), s.hex()))
    with open(os.path.join(out, "index"), "w", encoding="utf-8", newline="") as f:
        f.write("ARCH84-REPO 1\n" + "".join(r + "\n" for r in rows))
    print("index: %d packages" % len(rows))
    return rows


def git(site, *args):
    return subprocess.run(["git", "-C", site] + list(args), check=True, capture_output=True, text=True).stdout


def publish(out, site, subdir="arch84/pkgs", message="Arch84 package repository: update packages"):
    if not os.path.isdir(os.path.join(site, ".git")):
        os.makedirs(os.path.dirname(site), exist_ok=True)
        subprocess.run(["git", "clone", "https://github.com/doopydoop364/doopydoop364.github.io", site], check=True)
    git(site, "pull", "--rebase", "--autostash")
    dest = os.path.join(site, subdir)
    os.makedirs(dest, exist_ok=True)
    for f in os.listdir(dest):                      # replace the whole folder: removed packages go too
        if f.endswith(".ar84") or f == "index":
            os.remove(os.path.join(dest, f))
    for f in os.listdir(out):
        with open(os.path.join(out, f), "rb") as a, open(os.path.join(dest, f), "wb") as b:
            b.write(a.read())
    git(site, "add", subdir)
    if not git(site, "status", "--porcelain", subdir).strip():
        print("the site already has these packages")
        return
    git(site, "commit", "-m", message)
    print(git(site, "push", "origin", "HEAD:main") or "pushed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", default=os.path.join(ROOT, "repo", "src"))
    ap.add_argument("--out", default=os.path.join(ROOT, "repo", "pkgs"))
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--site", default=os.path.expanduser("~/.cache/arch84/site"))
    ap.add_argument("--message", default="Arch84 package repository: update packages")
    a = ap.parse_args()
    build_all(a.src, a.out)
    if a.publish:
        publish(a.out, a.site, message=a.message)
