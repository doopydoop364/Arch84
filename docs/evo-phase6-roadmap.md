# Phase 6 evidence gates

1. **Recovery and variable staging (highest priority, moderate risk).**
   Finish mock failure injection around every USB send/delete boundary.
   Use only newly created variables to test RAM-to-Archive-to-RAM round trips,
   exact readback, and Python recall after unarchiving. Do not infer that a
   successful export is a general restore guarantee. The Phase 5 `ARCHIVED`
   error rules out direct `recall_list` use of one archived scratch list on
   OS 7.0.0.3996.
2. **Python memory reliability (low hardware risk).** Compare the updated
   `A84CD.evict()` recovery path in a matched constrained MicroPython test.
   The desktop trace reduced its peak temporary allocation, while the
   emulator prompt heap stayed level. Device replacement of `A84CD` needs a
   separate backed-up deployment plan; no physical result is claimed.
3. **Storage format (moderate migration risk).** Build a bounded streaming
   compressed writer and versioned dual reader with power-cut tests. Keep
   compressed writes off by default; the Phase 4 whole-file encoder's host
   peak is too large to assume device safety. Test scratch lists before
   touching an Arch84 snapshot.
4. **Firmware and Python heap (offline, low hardware risk).** Map the ten
   official 7.1 images using reproducible static analysis, identify the
   Python runtime component, and seek a second authentic release for a
   controlled diff. Locate heap initialization only with independently
   checkable code/data references. No supported heap-resize API is known.
5. **Native execution (high hardware risk).** Identify exact CPU core,
   execution and privilege policy, trusted-key enforcement, official loader,
   and tested recovery route. The MCUboot-style signature fields and
   Cortex-M vector candidates do not establish a usable native app path.
   Keep firmware changes and native payloads offline until these gates and
   separate physical approval are satisfied.

Phase 5 sources and results: [experiment log](evo-phase5-experiments.md),
[firmware inventory](../research/results/evo-phase5-firmware-7.1-static.json),
[memory profile](evo-memory-profile.md), and
[native evidence](evo-native-execution.md).
