#!/usr/bin/env python3
"""
Run all GBWW site tests in order. The first suite (test_syntopicon)
checks the SQLite database directly. The second suite (test_api)
needs the HTTP server running on port GBWW_PORT (default 8781).

Usage:
    ./tests/run_all.sh           # both suites (start server if needed)
    ./tests/run_all.sh --no-server   # just test_syntopicon
"""
import subprocess
import sys
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
VENV = Path("/home/rodrigo/gbww/venv/bin/python3")
PORT = os.environ.get("GBWW_PORT", "8781")


def run(label: str, args: list[str]) -> bool:
    print(f"\n=== {label} ===")
    proc = subprocess.run([str(VENV)] + args, cwd=str(ROOT))
    return proc.returncode == 0


def main() -> int:
    only_db = "--no-server" in sys.argv
    ok = True
    ok &= run("test_syntopicon (database)", [str(HERE / "test_syntopicon.py")])
    if not only_db:
        ok &= run("test_api (HTTP)", [str(HERE / "test_api.py")])
    print()
    print("ALL PASSED" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
