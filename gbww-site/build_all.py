#!/usr/bin/env python3
"""
End-to-end build script for the GBWW site.

Order of operations:
  1. init_db()               — create schema (idempotent)
  2. index_volumes_and_works() — populate volumes/authors/works
     /authorships from txts/ (fallback to txts-v2/)
  3. index_page_text()       — split each TXT into [Xa]/[Xb] page rows
  4. parse_syntopicon()       — parse the two Syntopicon volumes
  5. build_references()      — populate ideas/topics/references
  6. populate_text_corpus()  — fill idea_bodies (introduction +
     cross_references) and intro_sections (Preface + Explanation)

We intentionally do NOT run core.dedup_works here. The dedup is
optional and lives in a separate script (see core/dedup_works.py).
Running dedup inside build_all.py can drop 30k+ references when the
canonical and variant rows collide on the (idea, topic, author,
work) tuple — refs that are not actually duplicates. The
best-effort migration is destructive and worth running only after
the user has inspected the build output. The canonical DB state
returned by this script is the one referenced by the test suite
(test_syntopicon.py).

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
from core.text_corpus import populate_text_corpus


def main():
    print("[1/6] init schema")
    init_db()
    print("[2/6] index volumes + works")
    s = index_volumes_and_works()
    print(f"      {s}")
    print("[3/6] index page_text")
    n = index_page_text()
    print(f"      {n} page rows")
    print("[4/6] parse Syntopicon")
    v2, v3 = _find_syntopicon_paths()
    print(f"      vol 2 = {v2.name}")
    print(f"      vol 3 = {v3.name}")
    parsed = parse_syntopicon(v2, v3)
    print(f"      ideas={len(parsed.ideas)} topics={len(parsed.topics)} "
          f"citations={len(parsed.citations)}")
    print("[5/6] build_references")
    s = build_references(parsed)
    print(f"      inserted: {s}")
    print("[6/6] populate text corpus (idea_bodies, intro_sections)")
    populate_text_corpus(parsed)
    print("\nDone. Start the server with:")
    print(f"  cd {Path(__file__).resolve().parent} && python3 serve.py")
    print("\nOptional: run dedup_works afterwards to merge fuzzy variants.")
    print("  python3 -m core.dedup_works  (idempotent, inspect output first)")


if __name__ == "__main__":
    main()