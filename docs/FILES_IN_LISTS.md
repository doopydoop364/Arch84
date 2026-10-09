# Files kept in calculator lists

The whole filesystem tree lives in the Python heap (about 160 KB, tens of KB free at the prompt). Every
file and directory costs a tree node (about 150 bytes for a file, 250 for a directory) plus its text.
Installing many packages would not fit. Calculator **lists** live in user RAM (hundreds of KB free), a
different pool, so file text can be kept there and read back when needed.

## How it works (`A84BL.py`, loaded on demand)

* `vfs.externalize(path, minlen=200)` writes a file's text into lists `X0000`..`X9999`
  (`[8486, id, nbytes, data packed 5 bytes per element]`, 485 bytes of text per list, never splitting a UTF-8
  character) and leaves the node holding an `Ext`: the list numbers and the character count. Files shorter
  than `minlen` stay in the heap (the node costs more than the text).
* Everything that reads file data goes through `dlen` / `dtext` / `dpieces` / `iter_lines` (A84FS); for an
  `Ext` they read one list at a time. `cat`, pipes, `grep`, `wc`, scripts, `pacman -Qk`, `archive`... stream it.
  A missing or foreign list gives `Input/output error`, never garbage.
* Writing to a file (`>`, `>>`, the editor) brings its text back into the heap; `cp` and `mv` share the
  immutable `Ext`. The old lists are simply no longer referenced.
* The saved filesystem stores a file in lists as record `B` (character count, number of lists, the list
  numbers) instead of its text. After a restart the lists are still there, so is the file. A RAM clear loses
  lists and save together, as it always lost the save.
* **A list number is not handed out again until a save without it exists.** A crash before the next `sync`
  reloads the old save, whose files must still find their text (`mark_saved` after every sync and at boot).
  Numbers freed during a session therefore come back after the next save. Lists that are not ours (another
  program's `X0003`, say) are never overwritten.
* `fsck` checks that every list of every such file is present and ours.
* Lists full or out of memory: the file just stays in the heap.

## What uses it

* Network downloads: `wget` (files of 300+ characters); `pacman -S` downloads go straight into lists,
  are installed, and the cached copy is deleted afterwards (the mirror has it again).
* `pacman` installs: every installed file of 200+ characters, and the package's database entry.
* The package database is now **one file per package** (`/var/lib/pacman/local/<name>`: description lines,
  `%files`, then the file list) instead of a directory with `desc` and `files`: two tree nodes fewer
  per package, and a directory node is the most expensive kind. Older directory entries are still read,
  listed, removed and replaced.

## Measured and modelled

Desktop, the five packages of the repository (hello, cowsay, fortune, cowfortune, ascii): the tree grows by
12 files and 4 directories (it used to be 22 and 8 counting the per-package database folders), 367 characters
of text stay in the heap and 1281 characters are in 7 lists. A rough byte model (file node 150, directory 250,
text as is) gives about 7.3 KB of heap for the old layout (without the cached downloads, which added about
2 KB more) against about 3.8 KB now. Real numbers: `free` before and after `pacman -S` on the calculator.
