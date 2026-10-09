# Arch84 networking: the PC bridge

The calculator has no network. Arch84 gets internet access through a program on the computer it is
plugged into (`tools/a84bridge.py`, run as a systemd user service). With it:

| command | what it does |
|---|---|
| `wget [-q] [-O FILE] URL` | download a page or file into the filesystem |
| `curl URL` | print a page |
| `ping [-c N]` | test the bridge, show the round trip |
| `net` | bridge status (version, uptime, allowed hosts) |
| `ntpdate` | set the clock (`date`) from the computer's |
| `pacman -Sy` | download the package index from the mirror |
| `pacman -S NAME...` | install packages (and dependencies) from the mirror |

Everything needs the colour terminal, the bridge running, and the calculator on the Arch84 prompt.
CLEAR cancels a request that is waiting.

## Setup

```
tools/install-bridge.sh        # systemd user service: installs, enables, starts
systemctl --user status arch84-bridge
journalctl --user -u arch84-bridge -f
tools/install-bridge.sh --remove
loginctl enable-linger "$USER"   # optional: keep it running when you are logged out
```

Hosts the bridge may fetch from: `doopydoop364.github.io` by default; add more in
`~/.config/arch84/bridge.conf` (`allow = host1 host2`) or with `--allow HOST`, then restart the
service. Only `http(s)` is served, redirects are re-checked against the list, bodies are capped at
2 MB, the bridge listens on no port, and the calculator can ask for nothing but "GET this URL",
"time", "ping", "status" and "echo". The mirror used by pacman is `https://doopydoop364.github.io/arch84/pkgs`
(change it with a one-line file `/etc/pacman.d/mirror` on the calculator).

Several programs must never talk to the calculator over USB at the same time; every tool takes the
shared lock `tools/usblock.py` (`/tmp/arch84-usb.lock`). Use `tools/evo` instead of `python3 evo_usb.py`
for ad-hoc commands while the bridge runs (it adds the lock); `deploy.py` and `tools/type.py` already do.
The bridge also presses one harmless key (scancode 0x28, the only key Arch84 ignores everywhere) every
150 s so the calculator does not switch itself off.

## Why the screen and the keys (and not lists or the clipboard)

The obvious channel is calculator lists (`store_list`/`recall_list` on the calculator, variable
transfers on the PC). **It does not work: any variable transfer over USB, in either direction, closes the
running Python app** (measured: a list read or write returns the calculator to the home screen within half
a second, no shutdown). The two things that leave the app alone are screenshots and key injection, so:

* **calculator -> PC: the screen.** Arch84 draws its request as rows of characters; the bridge takes a
  screenshot (~0.2 s) every half second and reads them (`tools/a84screen.py`). The font is crisp (no
  anti-aliasing), so each 10x18 cell is matched exactly against glyph shapes learned once from a screenshot
  (`tools/glyphs.json`; `python3 tools/a84screen.py --learn` re-learns them from a screenshot of
  row 0 = `" " + ALPHA[:30]`, row 1 = `" " + ALPHA[2:]`). Text columns 1..30 of rows 1..10 carry
  5 bits per character; row 0 is a banner for humans ("NET ... CLEAR=quit"). 187 bytes fit.
* **PC -> calculator: key presses.** The bridge types the answer with `evo_usb.py --keys`. 32 harmless keys
  carry 5 bits each (no Enter, CLEAR, 2nd, alpha, mode, del). Measured: 300 of 300 random keys arrive in
  order at full speed, 20-70 keys/s depending on what the calculator is doing (40-70 while it only listens).
  Several keys per USB transfer are ignored by the calculator, so it is one transfer per key.

## Wire format (`A84NT.py` is the reference; `tools/a84bridge.py` is the other end)

Both directions carry the same frame, as a stream of 5-bit symbols (`A84NT.ALPHA` characters on the
screen, `A84NT.KEYS` keys on the keyboard):

```
A8  type  seq(3)  len(2)  payload(len)  checksum(4)       checksum = Adler-32 style (A84ST.adler) of everything before it
type: 1 REQ  2 STATUS  3 DATA  4 FIN
```

A key stream starts every frame with `SYNC` (symbols 31,0 four times). The receiver scans for it, reads the
header, then exactly `len + 11` bytes; a frame that fails its checksum is dropped and the symbols it swallowed
are rescanned for the next `SYNC`.

1. The calculator draws a **REQ** frame (`op` byte + arguments) and waits for keys (polling `get_key(0)` in a loop that allocates nothing per key,
   ignoring anything that is not a symbol key; CLEAR cancels; 40 s without any key, or 20 s of silence after the first, is an error).
2. The bridge sees the new `seq`, does the work and builds the answer: one status byte (0 ok, 1 bad request,
   2 denied, 3 fetch failed, 4 http error, 5 too big, 6 unknown op) followed by the data.
3. The answer is cut into 300 byte pieces; each goes out as a **DATA** frame `idx(2) flag(1) rawlen(2) data`, LZSS
   compressed (`A84CY.lz_compress` on the PC, `A84CZ.lz_decompress` on the calculator) when that is smaller.
   The calculator accepts DATA in order only (go-back-N) and appends each chunk straight to the file.
4. The bridge ends with a **FIN** frame `total(2) round(1)`. The calculator draws a **STATUS** frame
   `have(2) done(1) round(1)` and, if it has everything, takes the screen down. The bridge matches the round
   number (so it never mistakes an old status for a new one), resends from the first missing chunk if needed
   (a lost key costs one chunk; if the same chunk keeps failing the rest is re-sliced into smaller pieces), checks the
   screen between chunks and stops as soon as the request is gone (the calculator takes it down on any error, so the
   bridge never keeps typing into the prompt), and finishes when the screen shows no request any more.

Operations (`A84NT.OP_*`): 1 PING, 2 TIME (epoch, UTC offset, zone), 3 GET url (the whole body; the calculator
enforces its own size limit), 4 ECHO, 5 STAT.

Measured on a real TI-84 Evo: ping 3-5 s, a 642 byte page 31 s, `pacman -S cowfortune` (two dependencies, three
downloads, one chunk resent after a dropped key) 74 s. Throughput is the key rate: ~25-45 bytes/s of compressed data.

## Packages

`repo/src/<name>/PKGINFO` (`version = 1.0`, `desc = ...`, `depends = a b`) and `repo/src/<name>/root/...` (the files as
they appear on the calculator, e.g. `usr/bin/hello`). `python3 tools/mkrepo.py` builds `repo/pkgs/` with the
calculator's own makepkg code (`A84PB.build`) and writes `index`:

```
ARCH84-REPO 1
name  version  name-version.ar84  size(characters)  checksum  depends  escaped description      (tab separated)
```

`python3 tools/mkrepo.py --publish` copies `repo/pkgs` into `arch84/pkgs` of a clone of `doopydoop364.github.io`
(`~/.cache/arch84/site`), commits and pushes.

On the calculator `pacman -Sy` downloads `index` into `/var/lib/pacman/sync/remote.db` (`A84PN.refresh`) and rebuilds the
local index, in which packages that only the mirror has appear with the file `net:<file>`. `pacman -S` resolves
dependencies exactly as for local packages; before installing a `net:` package it downloads it into
`/var/cache/pacman/pkg` (`A84PN.fetch`, kept in lists, see docs/FILES_IN_LISTS.md), refuses it unless size and checksum
match the index, installs everything, and deletes the downloaded copy again (the mirror has it). A local file in the
cache (for example from `makepkg`) wins over the mirror at the same version and is left alone. Offline (no bridge, or a text terminal), `-Sy` only syncs the local
repository, with a warning when the bridge did not answer.

Packages so far: `hello`, `cowsay`, `fortune`, `cowfortune` (depends on both), `ascii`: shell scripts and data files.

## Tests

`python3 test_net.py` runs the calculator code and the real bridge against a simulated calculator (screen frame,
key queue with optional key loss), a local web server and a repository built by `mkrepo`; `ScreenTests` read a real
screenshot (`tools/fixtures/glyphs.rgb.gz`). No hardware needed.
