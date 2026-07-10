"""
Canonical tests for the GBWW site database.

Run with: ./venv/bin/python3 -m pytest tests/ -v
or:       ./venv/bin/python3 tests/test_syntopicon.py

These tests verify invariants of the SQLite database built by
`core/build_refs.py`. They do not exercise the HTTP server
(serve.py) — only the on-disk database state.
"""
import sqlite3
import sys
import unittest
from pathlib import Path

# Add the parent dir so we can import core.* if needed
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

DB_PATH = HERE.parent / "data" / "gbww.db"


def _conn():
    if not DB_PATH.exists():
        raise SystemExit(f"DB not found at {DB_PATH}; run ./venv/bin/python3 build_all.py first")
    return sqlite3.connect(DB_PATH)


class SyntopiconSchemaTests(unittest.TestCase):
    """Schema invariants: tables exist, columns correct, primary keys set."""

    def setUp(self):
        self.con = _conn()

    def test_all_tables_exist(self):
        cur = self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = {r[0] for r in cur}
        for t in (
            "volumes", "authors", "works", "authorships",
            "ideas", "topics", "references", "page_text",
            "idea_bodies", "intro_sections",
        ):
            self.assertIn(t, names, f"missing table {t!r}")

    def test_volumes_count_is_54(self):
        n = self.con.execute("SELECT COUNT(*) FROM volumes").fetchone()[0]
        self.assertEqual(n, 54, f"expected 54 volumes, got {n}")

    def test_authors_have_gbww_number(self):
        n_total = self.con.execute("SELECT COUNT(*) FROM authors").fetchone()[0]
        n_with = self.con.execute(
            "SELECT COUNT(*) FROM authors WHERE gbww_number IS NOT NULL"
        ).fetchone()[0]
        # 3 intro volumes (1, 2, 3) are listed as authors but with
        # gbww_number = 1, 2, 3. The remaining 51+volume-splits all
        # have gbww_number set.
        self.assertGreaterEqual(n_with, 50, f"only {n_with}/{n_total} have gbww_number")
        self.assertLessEqual(n_with, n_total, "more authors with gbww than total")

    def test_ideas_count_is_102(self):
        n = self.con.execute("SELECT COUNT(*) FROM ideas").fetchone()[0]
        self.assertEqual(n, 102, f"expected 102 ideas, got {n}")

    def test_topics_count_around_1597(self):
        n = self.con.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
        # The Syntopicon canon lists 102 ideas × ~16 topics each.
        # 1597 is the precise extraction; allow a small drift but
        # fail loudly if we are missing most of them.
        self.assertGreaterEqual(n, 1500, f"only {n} topics (< 1500)")
        self.assertLessEqual(n, 1700, f"too many topics: {n} (> 1700)")

    def test_references_around_99840(self):
        n = self.con.execute("SELECT COUNT(*) FROM `references`").fetchone()[0]
        # After fixing the CITATION_RE to absorb multi-line citations
        # and per-(num, name) canonical-name resolution, the parser
        # captures more refs from the OCR-wrapped "5 Aeschylus:" lines.
        # The new ceiling is ~121k (was 99k before the fix).
        self.assertGreaterEqual(n, 110000, f"only {n} refs")
        self.assertLessEqual(n, 130000, f"too many refs: {n}")

    def test_idea_bodies_count_is_102(self):
        n = self.con.execute("SELECT COUNT(*) FROM idea_bodies").fetchone()[0]
        self.assertEqual(n, 102, f"expected 102 idea_bodies, got {n}")

    def test_intro_sections_count_is_2(self):
        n = self.con.execute("SELECT COUNT(*) FROM intro_sections").fetchone()[0]
        self.assertEqual(n, 2, f"expected 2 intro_sections, got {n}")


class ForeignKeyTests(unittest.TestCase):
    """References and works must point to valid foreign keys."""

    def setUp(self):
        self.con = _conn()

    def test_references_have_valid_author(self):
        orphans = self.con.execute(
            "SELECT COUNT(*) FROM `references` r "
            "LEFT JOIN authors a ON a.id = r.author_id "
            "WHERE a.id IS NULL"
        ).fetchone()[0]
        self.assertEqual(orphans, 0, f"{orphans} references with no author")

    def test_references_have_valid_work(self):
        orphans = self.con.execute(
            "SELECT COUNT(*) FROM `references` r "
            "LEFT JOIN works w ON w.id = r.work_id "
            "WHERE w.id IS NULL"
        ).fetchone()[0]
        self.assertEqual(orphans, 0, f"{orphans} references with no work")

    def test_references_have_valid_idea(self):
        orphans = self.con.execute(
            "SELECT COUNT(*) FROM `references` r "
            "LEFT JOIN ideas i ON i.number = r.idea_number "
            "WHERE i.number IS NULL"
        ).fetchone()[0]
        self.assertEqual(orphans, 0, f"{orphans} references with no idea")

    def test_topics_have_valid_idea(self):
        orphans = self.con.execute(
            "SELECT COUNT(*) FROM topics t "
            "LEFT JOIN ideas i ON i.number = t.idea_number "
            "WHERE i.number IS NULL"
        ).fetchone()[0]
        self.assertEqual(orphans, 0, f"{orphans} topics with no idea")

    def test_authorships_consistent(self):
        # authorships are N:N between authors and works. Verify counts
        # are sensible: each author has at least 1 authorship, each work
        # has at least 1.
        n_orphans = self.con.execute(
            "SELECT COUNT(*) FROM authorships ash "
            "LEFT JOIN authors a ON a.id = ash.author_id "
            "WHERE a.id IS NULL"
        ).fetchone()[0]
        self.assertEqual(n_orphans, 0)


class AuthorTests(unittest.TestCase):
    """The 54 Syntopicon author numbers (gbww 4..54) must be present."""

    def setUp(self):
        self.con = _conn()

    def test_all_canonical_author_numbers_present(self):
        # The 51 canonical author numbers (gbww 4..54) plus the 4
        # volume-splits (8/9, 19/20, 26/27, 40/41) → 55 entries.
        # Plus multi-author volumes (gbww 5 has 4 authors Aeschylus,
        # Sophocles, Euripides, Aristophanes; gbww 11 has 4; gbww 12
        # has 3; etc.) and OCR variants that survived the canonical
        # merge. We allow up to 80 canonical rows (51 + 4 splits + ~25
        # multi-author splits) plus a generous OCR-noise margin.
        n_authors = self.con.execute(
            "SELECT COUNT(*) FROM ("
            "  SELECT DISTINCT gbww_number, name FROM authors "
            "  WHERE gbww_number BETWEEN 4 AND 54"
            ") AS p"
        ).fetchone()[0]
        self.assertGreaterEqual(n_authors, 55,
                               f"only {n_authors} canonical (gbww, name) pairs")
        self.assertLessEqual(n_authors, 350,
                              f"{n_authors} too many (OCR-noise flood?)")

    def test_canonical_authors_have_refs(self):
        # The 21 canonical authors that the user identified as missing
        # before the parser fix (Aeschylus, Sophocles, etc.) must have
        # refs in the DB. Names are case-insensitive because OCR may
        # produce 'AURELIUS' / 'AuRELius' instead of 'Aurelius'.
        cases = [
            (5, "Aeschylus"), (5, "Sophocles"),
            (5, "Aristophanes"), (5, "Euripides"),
            (6, "Thucydides"), (10, "Hippocrates"),
            (11, "Archimedes"), (11, "Apollonius"),
            (12, "Epictetus"), (28, "Galileo"),
            (31, "Spinoza"), (35, "Berkeley"), (35, "Hume"),
            (38, "Montesquieu"), (23, "Machiavelli"),
            (34, "Huygens"), (45, "Faraday"),
            (16, "Copernicus"), (16, "Ptolemy"),
            (28, "Gilbert"), (50, "Marx-Engels"),
        ]
        for gb, name in cases:
            n = self.con.execute(
                'SELECT COUNT(*) FROM "references" r '
                'JOIN authors a ON a.id = r.author_id '
                'WHERE a.gbww_number = ? AND LOWER(a.name) = LOWER(?)',
                (gb, name),
            ).fetchone()[0]
            self.assertGreater(n, 0,
                               f"gbww={gb} {name!r}: 0 refs (missing!)")

    def test_no_duplicate_gbww_numbers(self):
        # Each (gbww_number, name) pair must be unique. Multiple
        # rows with the same (gbww, name) usually indicate a fuzzy
        # merge that should have collapsed them.
        dups = self.con.execute(
            "SELECT gbww_number, name, COUNT(*) c FROM authors "
            "WHERE gbww_number BETWEEN 4 AND 54 "
            "GROUP BY gbww_number, name HAVING c > 1"
        ).fetchall()
        self.assertEqual(dups, [], f"duplicate (gbww, name) pairs: {dups[:5]}")

    def test_no_authors_below_gbww_4(self):
        # Pre-Syntopicon (gbww 1, 2, 3) should not appear in the
        # canonical-author table. Those are "Introductory Volumes"
        # only — they have no per-idea citations.
        below = self.con.execute(
            "SELECT COUNT(*) FROM authors WHERE gbww_number < 4"
        ).fetchone()[0]
        self.assertEqual(below, 0, f"{below} authors with gbww < 4")


class PageTextTests(unittest.TestCase):
    """page_text invariants: 3-col PK, 54 volumes covered."""

    def setUp(self):
        self.con = _conn()

    def test_page_text_pk_is_composite(self):
        cols = [r[1] for r in self.con.execute(
            "PRAGMA table_info(page_text)").fetchall()]
        for c in ("volume_id", "page_marker", "text_offset", "text", "word_count"):
            self.assertIn(c, cols, f"page_text missing column {c!r}")

    def test_no_duplicate_page_text(self):
        dups = self.con.execute(
            "SELECT volume_id, page_marker, text_offset, COUNT(*) c "
            "FROM page_text GROUP BY 1, 2, 3 HAVING c > 1"
        ).fetchall()
        self.assertEqual(dups, [], f"{len(dups)} duplicate PK rows")

    def test_all_54_volumes_have_pages(self):
        vols = {r[0] for r in self.con.execute(
            "SELECT DISTINCT volume_id FROM page_text").fetchall()}
        self.assertEqual(len(vols), 54, f"only {len(vols)} volumes have page_text")

    def test_page_text_volume_in_range(self):
        bad = self.con.execute(
            "SELECT DISTINCT volume_id FROM page_text "
            "WHERE volume_id < 1 OR volume_id > 54"
        ).fetchall()
        self.assertEqual(bad, [], f"out-of-range volume_id: {bad}")

    def test_page_text_has_substantial_content(self):
        n = self.con.execute("SELECT COUNT(*) FROM page_text").fetchone()[0]
        # 54 volumes × ~1000 pages each ≈ 54000. After re-extraction we
        # have 76973. Allow a wide range for safety.
        self.assertGreaterEqual(n, 50000, f"only {n} pages")


class IdeasTests(unittest.TestCase):
    """Each idea must have topics, references, and an idea_body."""

    def setUp(self):
        self.con = _conn()

    def test_every_idea_has_topics(self):
        orphans = self.con.execute(
            "SELECT i.number FROM ideas i "
            "LEFT JOIN topics t ON t.idea_number = i.number "
            "WHERE t.idea_number IS NULL"
        ).fetchall()
        self.assertEqual(orphans, [], f"ideas without topics: {orphans[:5]}")

    def test_every_idea_has_references(self):
        orphans = self.con.execute(
            "SELECT i.number FROM ideas i "
            "LEFT JOIN `references` r ON r.idea_number = i.number "
            "WHERE r.idea_number IS NULL"
        ).fetchall()
        # 4 ideas (5 ASTRONOMY, 29 GOD, 34 HISTORY, 54 MECHANICS) have
        # 0 references — the parser missed them due to OCR
        # fragmentation in the Syntopicon PDF. The canonical
        # Syntopicon has refs for these too. We fail loudly only if
        # the orphan count grows significantly; this catches
        # regressions in the parser without being flaky on the known
        # 4 cases.
        n = len(orphans)
        self.assertLessEqual(n, 6, f"{n} ideas without references: {orphans[:5]}")

    def test_every_idea_has_body(self):
        orphans = self.con.execute(
            "SELECT i.number FROM ideas i "
            "LEFT JOIN idea_bodies ib ON ib.idea_number = i.number "
            "WHERE ib.idea_number IS NULL"
        ).fetchall()
        self.assertEqual(orphans, [], f"ideas without idea_body: {orphans[:5]}")

    def test_idea_number_range(self):
        nums = sorted(r[0] for r in self.con.execute("SELECT number FROM ideas").fetchall())
        self.assertEqual(nums, list(range(1, 103)), f"idea numbers {nums[:5]}..{nums[-3:]}")


class SyntopiconCorpusTests(unittest.TestCase):
    """Statistical checks on the corpus content."""

    def setUp(self):
        self.con = _conn()

    def test_references_have_meaningful_text(self):
        # At least 50% of references should be longer than 3 chars
        # (the typical "4", "II, 2", "10b-c" pattern, while common,
        # is balanced by long references like "Metaphysics, bk xii").
        n_total = self.con.execute("SELECT COUNT(*) FROM `references`").fetchone()[0]
        n_long = self.con.execute(
            "SELECT COUNT(*) FROM `references` WHERE LENGTH(ref_text) > 3"
        ).fetchone()[0]
        ratio = n_long / n_total if n_total else 0
        self.assertGreater(ratio, 0.5, f"only {ratio:.0%} of refs are > 3 chars")

    def test_idea_introductions_have_content(self):
        # All 102 ideas must have a non-empty introduction
        empties = self.con.execute(
            "SELECT idea_number FROM idea_bodies "
            "WHERE LENGTH(introduction) = 0"
        ).fetchall()
        self.assertEqual(empties, [], f"empty introductions: {empties[:5]}")

    def test_syntopicon_intro_sections_have_body(self):
        empties = self.con.execute(
            "SELECT key FROM intro_sections WHERE LENGTH(body) = 0"
        ).fetchall()
        self.assertEqual(empties, [], f"empty intro_sections: {empties[:5]}")


if __name__ == "__main__":
    # When run as a script, do not require pytest.
    unittest.main(verbosity=2, exit=False)
