# A84VM: paged swap (virtual memory)

`A84VM.py` is a pager: pages of `page` bytes are resident in RAM (at most `window`) or in a backend.
Page table dicts: `loc[pid]` (backend location, -1 never stored, -2 all-zero), `res`, `dirty`, `use`.
LRU eviction by linear scan (no `sorted()`), write-back only of dirty pages, `gc.collect()` after each
eviction, optional eviction while `gc.mem_free() < low`.

## What the calculator can actually store (measured, OS 7.0.0.3996)
* `open()` is a stub (returns None for every mode), there is no `os`, Python cannot write the Archive:
  **binary AppVar swap files do not exist** on this firmware. `FileBackend` (r+b files, fixed slots,
  slot reuse, kept-open handle, zero-page elision, segment files of <= 32 KB) works on the emulator and on
  any firmware that implements `open()`.
* Lists are the only persistent store. Measured on the device:
  * real element, 40 bits (5 bytes): exact; write 1.6 ms/element, read 4 ms + 1.1 ms/element
  * 43+ bit values lose the .5 (14-digit mantissa): 46 bits wrong in 126/150
  * complex elements (10 bytes): 4% wrong, 5.9 ms write / 3.3 ms read per element: rejected
  * time follows the element count, not the list count
* So `ListBackend` stores 5 bytes/element, one list per 495-byte chunk, only up to the last non-zero byte
  (element 0 = head + length), all-zero pages not at all; freed slots are shrunk to one element and reused.
* Measured with it: 990-byte pages (400 used) fault in ~207 ms, flush 6 pages in 258 ms. Use small pages
  (128-256 B => ~35-60 ms per fault); 30-80 ms for 1-2 KB is not reachable with lists.
* Lists live in user RAM, which shrinks the Python heap (~0.31 per KB): swapping only pays off for data that
  is large and cold. Net heap gain per KB moved is ~0.44 KB.

Tests: `python3 test_vm.py` (also runs under the built MicroPython with `MICROPYPATH=.:emu`).

## Where the time goes (device, 495-byte page, 99 elements)
* `recall_list` ~111 ms (TI float conversion), `unpack5` 12 ms, `lz_decompress` 12 ms, `lz_compress` 48 ms.
* So Python overhead is ~10%; the OS list conversion is the floor. Bigger batches only remove the ~4 ms call cost.
* `ListBackend(comp=, decomp=)` compresses a chunk when that saves >= 30% (stored in the head element).
  Short text chunks (495 B, independent windows) compress only ~25% on average (10 source pages: 1000 -> 747
  elements), so it is off by default: it pays for text read far more often than written.
* Not usable: `ti_image` (`new_image` raises "Unsupported operation" here; `set_pixel/get_pixel` draw on the
  screen), there is no string store in `ti_system`, complex elements are inexact, 43+ bit reals lose the .5.
* A 6-byte/element encoding using the decimal exponent (sign + 13-digit mantissa + 16 exponents = 48 bits)
  is possible on paper (+20%), but decoding needs a threshold search per element and would cost more than it saves.
