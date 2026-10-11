# Evo phase 4 desktop benchmark

Revision: `aaa0cf60700bac476687efba493a652d044ccdb1`. All compression numbers are CPython host results.

| Corpus | Bytes | Current lists | Candidate lists | Saved | Elements saved |
| --- | ---: | ---: | ---: | ---: | ---: |
| small_text | 13 | 1 | 1 | 0 | 0 |
| repetitive_4k | 4160 | 9 | 6 | 3 | 701 |
| random_4k | 4096 | 9 | 9 | 0 | 0 |
| source_A84FS | 14707 | 31 | 24 | 7 | 834 |
| source_A84SH | 12729 | 27 | 18 | 9 | 984 |
| document_NETWORK | 7954 | 17 | 17 | 0 | 0 |
| package_fortune | 597 | 2 | 1 | 1 | 27 |

Emulator boot free: 39552 B; minimum after GC: 36848 B; boot time: 528 ms; return code: 0.

No physical Evo performance measurement is included.
