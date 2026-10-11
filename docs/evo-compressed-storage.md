# Versioned compressed `X` block candidate

## Status and format

**Prototype, desktop only.** `tools/evo_storage_codec.py` now emits either
the existing raw `A84BL` layout (magic 8486, three header numbers, up to 485
bytes of payload) or a versioned compressed block (magic 8487, four header
numbers, up to 480 stored bytes). The extra header contains an Adler-32 of
the decoded bytes. The third compressed header packs decoded and stored
lengths as `decoded*1024 + stored`. Numeric elements still use the existing
exact 40-bit packing with `+0.5`, and a list never exceeds 100 elements.

Each compressed block decodes independently to at most 768 bytes. The reader
checks magic, ordinal, header length, encoded length, zero padding, decoder
bounds, and checksum. Raw fallback keeps the existing on-device representation
and uses no more lists than the current 485-byte scheme. The codec does not
change `A84BL`, `A84BM`, snapshots, or existing calculator lists. There is
no automatic migration or on-device write flag yet.

The specification reserves 8487 for this candidate but it is **not a
committed production format**. Before any device writer: define the exact
filesystem record version and list ownership check; add a dual reader;
stream writes with bounded input; prove interrupted writes cannot replace
lists referenced by the selected snapshot; test older saves; and measure
compression on the Evo's fragmented heap. The current CPython `encode()`
collects all blocks and is unsuitable as an on-device file writer.

## Reproducible desktop benchmark

Run `python3 tools/evo_benchmark.py --output OUT.json --emulator` with
`A84_MICROPYTHON` set to the compatible 32-bit Unix port. It produces JSON
and a Markdown summary. [Recorded results](../research/results/evo-phase4-benchmark.json)
are from CPython compression and the MicroPython **emulator**, not the Evo.

| Corpus | Input | Old lists | Candidate lists | Reduction |
| --- | ---: | ---: | ---: | ---: |
| Repetitive text | 4,160 B | 9 | 6 | 3 |
| Random bytes, seeded | 4,096 B | 9 | 9 | 0 |
| `A84FS.py` source | 14,707 B | 31 | 24 | 7 |
| `A84SH.py` source | 12,729 B | 27 | 18 | 9 |
| `docs/NETWORK.md` | 7,954 B | 17 | 17 | 0 |
| Fortune package archive | 597 B | 2 | 1 | 1 |

CPython median encoding time was 17.1 ms for `A84FS.py` and 10.6 ms for
`A84SH.py`; decoding took 3.4 and 2.7 ms. `tracemalloc` peaks for whole-file
encoding were about 72.7 and 55.3 KiB respectively. These peaks include
the accumulated output blocks and demonstrate why a streaming device writer
is required; they do **not** predict the Evo's heap or CPU time. The
emulator shell benchmark booted with 39,424 B free and reached 36,816 B
minimum after GC under its configured 127,800 B requested heap, without
compressed on-device writes.

## Compatibility and corruption tests

Seven codec tests cover repetitive and incompressible data, legacy raw
fallback, header corruption, payload corruption, checksum mismatch, decoded
size limit and nonzero padding. Existing saved `X` blocks remain untouched
and readable by the existing Arch84 implementation. The present codec
reader handles both layouts offline; the deployed Arch84 reader handles only
8486. A damaged compressed block must raise an I/O error when a future dual
reader is integrated, never return partial file data.
