# Arch84 0.0.7

Not yet run on a real calculator: everything below was tested on the desktop and in a 32-bit
MicroPython 1.20 emulator with a device-sized heap (see docs/OPTIMIZATION_CAMPAIGN.md for fidelity limits).

## New
* **Pipes and stdin**: `|` and `<`; `cat head tail grep sort wc` read stdin; new `uniq`, `tee`.
  Keys: `|` = x^-1, `<` = sin, `\` = x^2.
* **`edit FILE`**: full-screen editor (CLEAR = command line: w q qq wq N /text n d y p s/a/b/).
* **Scripts**: files on PATH run as scripts (`$1..$9`, `$#`), output works with pipes/redirects.
* **`.ar84` packages**: `makepkg` builds, `pacman -U/-S/-R/-Q/-Qi/-Ql/-Qk/-Qo/-Qp/-Sl` manage them
  (checksummed text format, validated before install, rollback on failure, dependency checks).

## Fixed
* Names over 255 bytes made every later save fail.
* `sort -n` ordered equal keys arbitrarily on MicroPython.
* Tab completion inside an open quote doubled the quote.
* Startup could hang if the tick counter wrapped during the hold-CLEAR window.
* A memory error in the post-save compare aborted a finished save.
* `rm -f`, `-fr`, `-Rf`, `--` were not understood.
* `reboot` kept the old filesystem tree alive (9-15 KB).
* Out-of-memory during load or save is retried once after a garbage collection.

## Memory (emulator, 127,800 B heap)
Load/save allocate about half as much garbage; files surviving save-reboot-edit-resave with full
verification 51 -> 120. New features cost ~2.4 KB of resident heap (44.7 KB free at the prompt).

## Deploy
`python3 deploy.py` (new modules: A84V1 A84C6 A84ED A84EV A84PM A84PD A84PI A84PB A84PX A84SC A84SD).
