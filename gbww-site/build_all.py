#!/usr/bin/env python3
"""
End-to-end build script for the GBWW site.

Order of operations:
  1. init_db()    — create schema (idempotent)
  2. index_volumes_and_works() — populate volumes/authors/works/authorships
     from txts-v2/ (or txts/ fallback)
  3. index_page_text()          — split each TXT into [Xa]/[Xb] page rows
  4. build_references()         — parse Syntopicon vol 2 + 3 and populate
     ideas/topics/references

Run from /home/rodrigo/gbww/gbww-site/:
    python3 build_all.py
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core.db import init_db
from core.indexer import index_volumes_and_works, index_page_text
from core.build_refs import build_references, _find_syntopicon_paths
from core.parser import parse_syntopicon


def main():
    print("[1/4] init schema")
    init_db()
    print("[2/4] index volumes + works")
    s = index_volumes_and_works()
    print(f"      {s}")
    print("[3/4] index page_text")
    n = index_page_text()
    print(f"      {n} page rows")
    print("[4/4] parse Syntopicon + build references")
    v2, v3 = _find_syntopicon_paths()
    print(f"      vol 2 = {v2.name}")
    print(f"      vol 3 = {v3.name}")
    parsed = parse_syntopicon(v2, v3)
    print(f"      ideas={len(parsed.ideas)} topics={len(parsed.topics)} "
          f"citations={len(parsed.citations)}")
    s = build_references(parsed)
    print(f"      inserted: {s}")
    print("\nDone. Start the server with:")
    print(f"  cd {Path(__file__).resolve().parent} && python3 serve.py")


if __name__ == "__main__":
    main()