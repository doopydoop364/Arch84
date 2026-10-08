#!/bin/sh
# Push HEAD to the working branch and to main ONLY if the full validation passes.
#   sh emu/push_main.sh [--quick]
cd "$(dirname "$0")/.." || exit 1
if [ -n "$(git status --porcelain)" ]; then echo "uncommitted changes: commit first"; exit 1; fi
python3 emu/run_all.py "$@" > /tmp/push_gate.txt 2>&1
rc=$?
tail -n 6 /tmp/push_gate.txt
if [ $rc -ne 0 ]; then echo "VALIDATION FAILED (rc=$rc): not pushing"; exit $rc; fi
b=$(git rev-parse --abbrev-ref HEAD)
git push origin "$b" && git push origin "$b:main"
