#!/usr/bin/env python3
"""Read-only proof of concept: export one Arch84 X list to desktop storage.

This does not remove the calculator variable or change Arch84's filesystem.
Run only after exiting the Python app; USB variable reads close that app.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from evo_research import list_files_with_timeout, long_read_timeout


def export(evo, lock, name, output):
    if not re.fullmatch(r"X[0-9]{4}", name):
        raise ValueError("only an Arch84 X0000..X9999 list can be exported")
    output = Path(output)
    if output.exists():
        raise FileExistsError(str(output))
    if not output.parent.is_dir():
        raise FileNotFoundError(str(output.parent))
    with lock(timeout=120):
        matches = [item for item in list_files_with_timeout(evo)
                   if item.get("name") == name and item.get("type") == 1]
        if len(matches) != 1:
            raise ValueError("list is absent or ambiguous: " + name)
        with tempfile.TemporaryDirectory(dir=output.parent) as td:
            temporary = Path(td) / "variable.evo"
            with long_read_timeout(evo):
                evo.get_variable(name, 1, str(temporary))
            data = temporary.read_bytes()
            os.chmod(temporary, 0o600)
            # Link is atomic and fails if another process created output.
            os.link(temporary, output)
    return {"name": name, "type": 1, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "output": str(output),
            "calculator_changed": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="existing X0000..X9999 list")
    parser.add_argument("output", type=Path, help="new local file; must not exist")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    import evo_usb
    from usblock import usb_lock
    print(json.dumps(export(evo_usb, usb_lock, args.name, args.output),
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
