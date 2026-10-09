"""Generate a CI evidence snapshot for the public Arch84 progress dashboard.

Only explicitly mapped test-backed criteria may be auto-verified.
Failure to run a test is never a pass. No credentials are required.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "progress" / "assessment.json"
REPO = os.environ.get("GITHUB_REPOSITORY", "doopydoop364/Arch84")
SHA = os.environ.get("GITHUB_SHA", "")
RUN = os.environ.get("GITHUB_RUN_ID", "")
BASE = "https://github.com/" + REPO
RUN_URL = BASE + "/actions/runs/" + RUN if RUN else None

# These are existing tests, not assertions that entire milestones are finished.
SUITES = (
    ("vm", "Pager and backend regression", ["test_vm.py"]),
    ("vm_accept", "Bounded pager residency and dirty-write recovery", ["-m", "unittest", "test_progress_acceptance"]),
    ("parser", "Shell parser regression", ["-m", "unittest", "test_arch84.ParserTests"]),
    ("vfs", "Storage and persistence regression", ["test_storage.py"]),
    ("install", "Chunked-file regression", ["test_bigfiles.py"]),
)

# Strictly scoped evidence: the specific parser regression suite demonstrates
# that shell grammar is covered by tests. It does NOT verify allocation reductions.
AUTO_CRITERIA = {
    "parser": {"Existing shell grammar captured in regression tests": "parser"},
    "vm": {
        "Memory budgets and bounded page residency tested": "vm_accept",
        "Dirty page write failures preserve data": "vm_accept",
    },
}


def main():
    suites = []
    for ident, title, args in SUITES:
        cmd = [sys.executable] + args
        try:
            p = subprocess.run(cmd, cwd=str(ROOT), text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               timeout=180)
            passed = p.returncode == 0
            status = "passed" if passed else "failed"
            details = p.stdout[-6000:]
        except (OSError, subprocess.TimeoutExpired) as e:
            passed = False
            status = "error"
            details = str(e)
        print(title + ": " + status, flush=True)
        if details:
            print(details[-1000:], flush=True)
        suites.append({"id": ident, "name": title, "status": status,
                       "evidence": RUN_URL, "details": details})

    by_id = {s["id"]: s for s in suites}
    verifications = {}
    for feature, mappings in AUTO_CRITERIA.items():
        verifications[feature] = {}
        for criterion, suite_id in mappings.items():
            suite = by_id.get(suite_id)
            verifications[feature][criterion] = {
                "verified": bool(suite and suite["status"] == "passed" and RUN_URL),
                "evidence": RUN_URL if suite and suite["status"] == "passed" else None,
                "suite": suite_id,
            }

    payload = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sha": SHA, "run_url": RUN_URL, "suites": suites,
        "criteria": verifications,
        "all_passed": all(s["status"] == "passed" for s in suites),
        "scope": "CPython regression tests only; no hardware or constrained-heap verification.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print("Assessment written:", OUT, flush=True)
    return 0 if payload["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
