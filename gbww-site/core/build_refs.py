"""
Build the references table from the parsed Syntopicon.

Each parsed Citation becomes one row in `references`. We normalize
work_title, look up or create the author, look up or create the work
(under the volume resolved from the author's GBWW canonical number),
and insert.
"""

from __future__ import annotations
import re
import sqlite3
from pathlib import Path

from .db import connect, init_db
from .indexer import _DEFAULT_TXT_DIR, _FALLBACK_TXT_DIR
from .parser import ParsedSyntopicon, parse_syntopicon, normalize_work_title
from .util import canonical, find_fuzzy, fragments

# `difflib` is used inside the in-memory author cache; importing it here so
# the rest of this module doesn't need its own copy.
import difflib  # noqa: E402

# Keep _author_canonical as alias for backwards compat with callers.
def _author_canonical(name: str) -> str:
    return canonical(name)

# GBWW canonical author -> volume number. Copy from gbww-search/core/indexer.py
AUTHOR_TO_VOLUME: dict[int, tuple[int, list[str]]] = {
    4:  (4,  ["Homer"]),
    5:  (5,  ["Aeschylus", "Sophocles", "Euripides", "Aristophanes"]),
    6:  (6,  ["Herodotus", "Thucydides"]),
    7:  (7,  ["Plato"]),
    8:  (8,  ["Aristotle"]),
    9:  (9,  ["Aristotle"]),
    10: (10, ["Hippocrates", "Galen"]),
    11: (11, ["Euclid", "Archimedes", "Apollonius", "Nicomachus"]),
    12: (12, ["Lucretius", "Epictetus", "Marcus Aurelius"]),
    13: (13, ["Virgil"]),
    14: (14, ["Plutarch"]),
    15: (15, ["Tacitus"]),
    16: (16, ["Ptolemy", "Copernicus", "Kepler"]),
    17: (17, ["Plotinus"]),
    18: (18, ["Augustine"]),
    19: (19, ["Thomas Aquinas"]),
    20: (20, ["Thomas Aquinas"]),
    21: (21, ["Dante"]),
    22: (22, ["Chaucer"]),
    23: (23, ["Machiavelli", "Hobbes"]),
    24: (24, ["Rabelais"]),
    25: (25, ["Montaigne"]),
    26: (26, ["Shakespeare"]),
    27: (27, ["Shakespeare"]),
    28: (28, ["Gilbert", "Galileo", "Harvey"]),
    29: (29, ["Cervantes"]),
    30: (30, ["Francis Bacon"]),
    31: (31, ["Descartes"]),
    32: (32, ["Milton"]),
    33: (33, ["Pascal"]),
    34: (34, ["Newton", "Huygens"]),
    35: (35, ["Locke", "Berkeley"]),
    36: (36, ["Swift", "Sterne"]),
    37: (37, ["Fielding"]),
    38: (38, ["Montesquieu"]),
    39: (39, ["Adam Smith"]),
    40: (40, ["Gibbon"]),
    41: (41, ["Gibbon"]),
    42: (42, ["Kant"]),
    43: (43, ["American State Papers"]),
    44: (44, ["Boswell"]),
    45: (45, ["Lavoisier", "Fourier", "Faraday"]),
    46: (46, ["Hegel"]),
    47: (47, ["Goethe"]),
    48: (48, ["Melville"]),
    49: (49, ["Darwin"]),
    50: (50, ["Marx", "Engels"]),
    51: (51, ["Tolstoy"]),
    52: (52, ["Ibsen"]),
    53: (53, ["William James"]),
    54: (54, ["Freud"]),
}


def _resolve_volume(author_num: int, author_name: str) -> int | None:
    info = AUTHOR_TO_VOLUME.get(author_num)
    return info[0] if info else None


def _get_or_create_author(conn, name: str, gbww_number: int | None) -> int:
    """Resolve an author name to an authors.id, creating a new row if
    necessary.

    The parser's first pass normalises author names by majority vote
    within each author_num, so by the time build_references runs every
    name is in its canonical form ("Aquinas" not "Aqutnas"). We can
    therefore use a fast path keyed on the canonical string.

    We do NOT merge volume-splits. "Aristotle I" (gbww=8) and
    "Aristotle II" (gbww=9) are two distinct Syntopicon entries; the
    _get_or_create_author lookup keys on (canonical, gbww_number) so
    citations to Aristotle I go to the gbww=8 row and citations to
    Aristotle II go to the gbww=9 row.
    """
    # Sanity: discard pathological names. The CITATION_RE allows names
    # down to 1 char, but real author names are at least 3 letters
    # long. The Syntopicon has 54 authors, all of them 3+ letters.
    if not name or len(name.strip()) < 3:
        # Fall back to a placeholder keyed on the gbww_number.
        if gbww_number is not None:
            return _get_or_create_author(conn, f"Author {gbww_number}", None)
        return _get_or_create_author(conn, "Unknown", None)
    canon = _author_canonical(name)
    # 1. Exact (canonical, gbww_number) match. The most precise
    # lookup: a citation for "Aristotle" with gbww=9 should NOT
    # match "Aristotle I" (gbww=8).
    if canon and gbww_number is not None:
        cur = conn.execute(
            "SELECT id, name, gbww_number FROM authors "
            "WHERE LOWER(REPLACE(REPLACE(name, '.', ''), ' ', '')) = ? "
            "AND gbww_number = ?",
            (canon, gbww_number),
        ).fetchone()
        if cur:
            return cur["id"]
    # 2. Fallback: exact canonical match (any gbww_number). Only used
    # when the caller doesn't know the gbww_number (gbww_number is
    # None). When the caller DOES know the gbww_number, falling back
    # to a different row would lose the volume-split distinction, so
    # we skip the fallback and go straight to INSERT.
    if canon and gbww_number is None:
        cur = conn.execute(
            "SELECT id, name, gbww_number FROM authors WHERE LOWER(REPLACE(REPLACE(name, '.', ''), ' ', '')) = ?",
            (canon,),
        ).fetchone()
        if cur:
            if cur["gbww_number"] is None and gbww_number is not None:
                conn.execute(
                    "UPDATE authors SET gbww_number = ? WHERE id = ?",
                    (gbww_number, cur["id"]),
                )
            return cur["id"]
    try:
        conn.execute(
            "INSERT OR IGNORE INTO authors (name, gbww_number) VALUES (?, ?)",
            (name, gbww_number),
        )
        if canon and gbww_number is not None:
            cur = conn.execute(
                "SELECT id, name FROM authors "
                "WHERE LOWER(REPLACE(REPLACE(name, '.', ''), ' ', '')) = ? "
                "AND gbww_number = ?",
                (canon, gbww_number),
            ).fetchone()
            if cur:
                return cur["id"]
        if canon and gbww_number is None:
            cur = conn.execute(
                "SELECT id, name FROM authors WHERE LOWER(REPLACE(REPLACE(name, '.', ''), ' ', '')) = ?",
                (canon,),
            ).fetchone()
            if cur:
                return cur["id"]
        cur = conn.execute("SELECT id, name FROM authors WHERE name = ?", (name,)).fetchone()
        if cur:
            return cur["id"]
        raise RuntimeError(f"failed to insert or find author: {name!r}")
    except sqlite3.IntegrityError:
        if canon:
            cur = conn.execute(
                "SELECT id FROM authors WHERE LOWER(REPLACE(REPLACE(name, '.', ''), ' ', '')) = ?",
                (canon,),
            ).fetchone()
            if cur:
                return cur["id"]
        raise


class _AuthorCache:
    """In-memory cache of (id, name, canonical, fragments) for fast fuzzy lookup."""

    def __init__(self) -> None:
        self.entries: list[tuple[int, str, str, list[str]]] = []

    def load(self, conn) -> None:
        cur = conn.execute("SELECT id, name FROM authors")
        cols = [c[0] for c in cur.description]
        self.entries = []
        for r in cur.fetchall():
            rec = dict(zip(cols, r))
            self.entries.append((rec["id"], rec["name"], canonical(rec["name"]), fragments(rec["name"])))

    def find(self, name: str, threshold: float = 0.7) -> int | None:
        if not self.entries:
            return None
        c = canonical(name)
        if not c:
            return None
        fs = fragments(name)
        best_id, best_score = None, 0.0
        for (eid, _ename, existing, other_frags) in self.entries:
            if not existing:
                continue
            seq = difflib.SequenceMatcher(None, c, existing).ratio()
            overlap = 0
            for f in fs:
                for g in other_frags:
                    if f == g or (len(f) >= 4 and len(g) >= 4 and
                                  difflib.SequenceMatcher(None, f, g).ratio() >= 0.85):
                        overlap += 1
                        break
            overlap_score = min(1.0, overlap / max(1, len(fs)))
            suffix = 0.0
            for n in (3, 4, 5):
                if len(c) >= n and len(existing) >= n:
                    r = difflib.SequenceMatcher(None, c[-n:], existing[-n:]).ratio()
                    if r >= 0.85:
                        suffix = max(suffix, r)
            if suffix >= 0.85:
                score = max(suffix, 0.4 * seq + 0.4 * overlap_score + 0.2 * suffix + 0.15)
            else:
                score = 0.5 * seq + 0.35 * overlap_score + 0.15 * suffix
            if score > best_score:
                best_score = score
                best_id = eid
        return best_id if best_score >= threshold else None


_AUTHOR_CACHE = _AuthorCache()


def _remember(aid: int, name: str) -> None:
    _AUTHOR_CACHE.entries.append((aid, name, canonical(name), fragments(name)))


def _normalize_for_merge(c: str) -> str:
    """Normalise a canonical author name for the merge pass: strip
    volume-split Roman suffixes (e.g. "Aristotle I" -> "aristotle",
    "Shakespeare II" -> "shakespeare") and trailing whitespace.
    """
    return re.sub(r"\s+(I|II|III|IV|V)$", "", c).strip()


def _score_pair(c1: str, c2: str) -> float:
    """Score two canonical author names for fuzzy merge.

    A high score means the two strings are almost certainly OCR variants
    of the same author (e.g. "aquinas"/"aqutnas", "bacon"/"bacoxn"). The
    score combines:
      - SequenceMatcher ratio (overall similarity)
      - 2-gram overlap (shared letter pairs in any position)
      - 3-4-5 char suffix similarity (same ending, like "son" / "son")

    We require len_diff <= 2 to avoid merging distinct names that happen
    to share a prefix.
    """
    if not c1 or not c2:
        return 0.0
    if abs(len(c1) - len(c2)) > 3:
        return 0.0
    seq = difflib.SequenceMatcher(None, c1, c2).ratio()
    f1 = [c1[i:i+2] for i in range(len(c1)-1)]
    f2 = [c2[i:i+2] for i in range(len(c2)-1)]
    overlap = sum(1 for a in f1 for b in f2 if a == b or
                  (len(a) >= 4 and len(b) >= 4 and
                   difflib.SequenceMatcher(None, a, b).ratio() >= 0.85))
    overlap_score = min(1.0, overlap / max(1, len(f1)))
    suffix = 0.0
    for n in (3, 4, 5):
        if len(c1) >= n and len(c2) >= n:
            r = difflib.SequenceMatcher(None, c1[-n:], c2[-n:]).ratio()
            if r >= 0.85:
                suffix = max(suffix, r)
    if suffix >= 0.85:
        return max(suffix, 0.4 * seq + 0.4 * overlap_score + 0.2 * suffix + 0.15)
    return 0.5 * seq + 0.35 * overlap_score + 0.15 * suffix


def merge_fuzzy_authors(conn, threshold: float = 0.78) -> int:
    """After all authors are inserted with exact-canonical matching, do a
    pass that collapses OCR variants (FIobbes -> Hobbes, Aqulnas -> Aquinas).

    For each pair of distinct authors whose canonical forms are similar,
    merge the higher-id row into the lower-id one (update references +
    authorships, delete the higher-id row). Returns the number of merges.

    We do NOT merge two authors that have *different* `gbww_number`
    values — that would conflate the Syntopicon's volume-split entries
    (e.g. "Aristotle I" at gbww=8 and "Aristotle II" at gbww=9 are two
    distinct rows by design).
    """
    # Pull all (id, name, gbww_number) once
    cur = conn.execute("SELECT id, name, gbww_number FROM authors")
    rows = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
    # Group by (canonical, gbww_number). Two authors with different
    # gbww_numbers are NEVER merged even if their spellings are the same
    # canonical form.
    def key(r):
        return (canonical(r["name"]), r["gbww_number"])

    by_key: dict[tuple[str, int | None], list[dict]] = {}
    for r in rows:
        k = key(r)
        by_key.setdefault(k, []).append(r)

    merges = 0
    # First pass: same canonical AND same gbww_number -> merge.
    for k, group in by_key.items():
        if len(group) > 1:
            keep = group[0]
            for dup in group[1:]:
                _merge_authors(conn, keep["id"], dup["id"])
                merges += 1

    # Second pass: fuzzy across canonicals, but only between authors
    # that share the SAME gbww_number. We index groups by normalised
    # canonical AND gbww_number so that "aristotle" at gbww=8 and
    # "aristotle" at gbww=9 stay in separate buckets.
    norm_keys: list[tuple[str, int | None]] = [
        (_normalize_for_merge(k[0]), k[1]) for k in by_key
    ]
    parent: dict[tuple[str, int | None], tuple[str, int | None]] = {
        k: k for k in norm_keys
    }

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
            return True
        return False

    # Compare each pair only if they share the SAME gbww_number. Two
    # entries with different gbww_numbers are distinct Syntopicon rows
    # even if their spellings are similar (e.g. "Aristotle" at gbww=8
    # vs "Aristotle" at gbww=9). The pre-filter is the first 3 chars
    # plus the gbww_number, both as a tuple.
    by_first3_gbww: dict[tuple[str, int | None], list[tuple[str, int | None]]] = {}
    for k in norm_keys:
        first3 = k[0][:3] if len(k[0]) >= 3 else k[0]
        by_first3_gbww.setdefault((first3, k[1]), []).append(k)

    for (first3, gbww), group in by_first3_gbww.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if find(a) == find(b):
                    continue
                if abs(len(a[0]) - len(b[0])) > 3:
                    continue
                score = _score_pair(a[0], b[0])
                if score >= threshold:
                    union(a, b)
    # Apply unions: each cluster of normalised names (within a single
    # gbww_number bucket) becomes a single author row. We pick the
    # lowest-id row as the keeper; that row's gbww_number is preserved
    # because all entries in a cluster share the same gbww_number.
    clusters: dict[tuple[str, int | None], list[dict]] = {}
    for k in by_key:
        # k is (canonical, gbww_number) — the original bucket key.
        # We need the normalised (canonical, gbww_number) for lookup.
        norm_k = (_normalize_for_merge(k[0]), k[1])
        root = find(norm_k)
        clusters.setdefault(root, []).extend(by_key[k])

    for root, members in clusters.items():
        if not members:
            continue
        keep_rows = sorted(members, key=lambda r: r["id"])
        keep_id = keep_rows[0]["id"]
        for dup in keep_rows[1:]:
            _merge_authors(conn, keep_id, dup["id"])
            merges += 1
    return merges


def _merge_authors(conn, keep_id: int, dup_id: int) -> None:
    """Move all references and authorships from dup_id to keep_id, then
    delete dup_id. The keep row keeps its existing name (usually the
    first-seen, correct spelling).
    """
    if keep_id == dup_id:
        return
    conn.execute(
        "UPDATE OR IGNORE `references` SET author_id = ? WHERE author_id = ?",
        (keep_id, dup_id),
    )
    conn.execute("DELETE FROM `references` WHERE author_id = ?", (dup_id,))
    conn.execute(
        "UPDATE OR IGNORE authorships SET author_id = ? WHERE author_id = ?",
        (keep_id, dup_id),
    )
    conn.execute("DELETE FROM authorships WHERE author_id = ?", (dup_id,))
    conn.execute("DELETE FROM authors WHERE id = ?", (dup_id,))


def collapse_volume_split_authors(conn) -> int:
    """Final normalisation pass for the authors table.

    The Syntopicon has exactly 54 author numbers (4 through 54 — volumes
    1/2/3 are the Syntopicon itself and the introductory volumes). The
    GBWW indexer creates author rows for all 79 entries in its display
    names — that includes three volume-splits ("Aristotle I"/"II",
    "Shakespeare I"/"II", "Gibbon I"/"II") and a number of GBWW-only
    authors that the Syntopicon never cites ("Gilbert", "Copernicus",
    "Adam Smith", "Hume", "Huygens", etc.).

    We want the final `authors` table to have **exactly 54 rows**, one
    per Syntopicon author number. This pass:

    1. **Renames** volume-split rows in place — "Aristotle I" -> "Aristotle",
       "Shakespeare II" -> "Shakespeare", "Gibbon I" -> "Gibbon" — but
       keeps each row's own `id` and `gbww_number` so the references
       remain correctly attached. We do NOT merge them.
    2. **Deletes** any author row that has zero references AND no
       `gbww_number` (i.e. an indexer-only author like "Gilbert" of
       vol 28 that the Syntopicon never cites).
    """
    n_changed = 0

    # Step 1: rename volume-split rows. We keep the FIRST row of each
    # gbww bucket (lowest id) as the canonical "X" and any subsequent
    # volume-split row as the Roman-suffixed "X II" / "X III". The
    # `name` column is UNIQUE in the schema, so we cannot have two
    # rows with the same plain name — the Roman suffix disambiguates.
    cur = conn.execute("SELECT id, name, gbww_number FROM authors")
    by_gbww: dict[int, list] = {}
    for r in cur.fetchall():
        by_gbww.setdefault(r["gbww_number"], []).append(r)

    # GBWW volume-split pairs: (vol I, vol II). We strip the Roman
    # suffix from the FIRST volume and leave it on the SECOND.
    VOLUME_SPLIT_PAIRS = {
        8: "I",   # Aristotle I
        9: "II",  # Aristotle II
        19: "I", 20: "II",     # Aquinas I, II
        26: "I", 27: "II",     # Shakespeare I, II
        40: "I", 41: "II",     # Gibbon I, II
    }

    n_changed = 0
    for gbww, rows in by_gbww.items():
        if gbww is None or not (4 <= gbww <= 54):
            continue
        # For each volume-split pair, we may have one or two rows in
        # the same gbww bucket (e.g. "Aristotle I" at gbww=8 has only
        # the row for vol 8; the gbww=9 row is a separate "Aristotle II"
        # bucket). Strip the Roman suffix from the first row of each
        # gbww bucket — this turns "Aristotle I" into "Aristotle" but
        # leaves "Aristotle II" (gbww=9) as-is.
        for r in sorted(rows, key=lambda x: x["id"]):
            name = r["name"]
            m = re.match(r"^(.+?)\s+(I|II|III|IV|V)$", name)
            if not m:
                continue
            base = m.group(1).strip()
            # Skip the rename if a row already has the canonical name
            # for this gbww_number (the parser may have already
            # created one with the canon spelling, and renaming this
            # "X I" row to "X" would collide on UNIQUE(name, gbww)).
            existing = conn.execute(
                "SELECT id FROM authors WHERE name = ? AND gbww_number = ? AND id != ?",
                (base, gbww, r["id"]),
            ).fetchone()
            if existing:
                # Instead of renaming, delete this redundant indexer-
                # created row (it has 0 refs because the parser used
                # the canonical row instead).
                conn.execute("DELETE FROM authorships WHERE author_id = ?", (r["id"],))
                conn.execute("DELETE FROM authors WHERE id = ?", (r["id"],))
                continue
            conn.execute(
                "UPDATE authors SET name = ? WHERE id = ?",
                (base, r["id"]),
            )
            n_changed += 1
            break  # only the first row of this gbww bucket gets the rename

    # Step 2: drop redundant rows within each (canon, gbww) bucket.
    # We keep one row per (canon, gbww) — if multiple rows exist for the
    # same canonical author and same gbww_number, we keep the one with
    # the most references and delete the others (which were usually
    # created by the indexer alongside an already-correct parser row).
    cur = conn.execute("SELECT id, name, gbww_number FROM authors")
    rows = cur.fetchall()
    by_bucket: dict[tuple[str, int | None], list] = {}
    for r in rows:
        canon = canonical(r["name"])
        # Strip "X I/II/III" Roman suffix so "X I" and "X II" map to
        # the same canonical bucket when their canon-spelling matches.
        base_canon = re.sub(r"\s+(I|II|III|IV|V)$", "", canon).strip()
        # Strip leading "Thomas " so "Thomas Aquinas" and "Aquinas" map
        # to the same canonical bucket (the Syntopicon uses just
        # "Aquinas" — "Thomas" is a disambiguator added by the GBWW
        # indexer). Same for "William James" → "James" and "Marcus
        # Aurelius" → "Aurelius" — the Syntopicon uses the shorter
        # canonical form, and the GBWW indexer prepends the given
        # name to disambiguate.
        base_canon = re.sub(r"^(thomas|marcus|william)\s+", "", base_canon).strip()
        by_bucket.setdefault((base_canon, r["gbww_number"]), []).append(r)

    n_dropped = 0
    for (canon, gbww), group in by_bucket.items():
        if gbww is not None and 4 <= gbww <= 54:
            # Within a Syntopicon bucket, keep the row with refs.
            # If the bucket has any row with refs, drop all the others
            # (they were redundant duplicates created by the indexer).
            # If the bucket has no row with refs, also drop the entire
            # bucket — these are GBWW-only authors that the Syntopicon
            # does not cite ("Aeschylus", "Thucydides", "Berkeley",
            # "Hume", etc.). The Syntopicon has 54 author numbers
            # and they all carry references, so a bucket with no refs
            # cannot correspond to a Syntopicon author.
            rows_with_refs = [
                r for r in group
                if conn.execute(
                    "SELECT 1 FROM `references` WHERE author_id = ?",
                    (r["id"],),
                ).fetchone()
            ]
            if rows_with_refs:
                keep = rows_with_refs[0]
                for r in group:
                    if r["id"] == keep["id"]:
                        continue
                    conn.execute("DELETE FROM authorships WHERE author_id = ?", (r["id"],))
                    conn.execute("DELETE FROM authors WHERE id = ?", (r["id"],))
                    n_dropped += 1
            else:
                # No Syntopicon citations for this bucket — drop all rows.
                for r in group:
                    conn.execute("DELETE FROM authorships WHERE author_id = ?", (r["id"],))
                    conn.execute("DELETE FROM authors WHERE id = ?", (r["id"],))
                    n_dropped += 1
        else:
            # Out-of-band (gbww_number NULL or outside 4..54): delete
            # any row with zero references.
            for r in group:
                has_refs = conn.execute(
                    "SELECT 1 FROM `references` WHERE author_id = ?",
                    (r["id"],),
                ).fetchone()
                if has_refs:
                    continue
                conn.execute("DELETE FROM authorships WHERE author_id = ?", (r["id"],))
                conn.execute("DELETE FROM authors WHERE id = ?", (r["id"],))
                n_dropped += 1
    return n_changed + n_dropped


def _get_or_create_work(conn, title: str, volume_id: int) -> int:
    norm = title.lower().strip()
    cur = conn.execute(
        "SELECT id FROM works WHERE volume_id = ? AND title_norm = ?",
        (volume_id, norm),
    ).fetchone()
    if cur:
        return cur["id"]
    cur = conn.execute(
        "INSERT INTO works (volume_id, title, title_norm) VALUES (?, ?, ?) "
        "RETURNING id",
        (volume_id, title, norm),
    )
    return cur.fetchone()["id"]


def build_references(parsed) -> dict:
    """Insert ideas, topics, references into the DB. Idempotent for ideas
    and topics; clears references first to avoid duplicates on re-runs.

    `parsed` is either a ParsedSyntopicon or a list[Citation] (citations-only
    mode for incremental re-runs).

    Citations pointing to a volume that is NOT in the `volumes` table are
    silently skipped — this lets the build run while the PDF extractor is
    still finishing the last few volumes.
    """
    init_db()
    n_ideas = n_topics = n_refs = 0
    if hasattr(parsed, "ideas"):
        ideas = parsed.ideas
        topics = parsed.topics
        citations = parsed.citations
    else:
        ideas, topics, citations = [], [], parsed
    with connect() as conn:
        # Pre-load the in-memory author cache so fuzzy lookups inside the
        # loop are O(1) instead of O(N) SQL scan per insert.
        indexed_vols = {r[0] for r in conn.execute("SELECT number FROM volumes").fetchall()}
        _AUTHOR_CACHE.load(conn)
        # ideas: upsert by number
        for idea in ideas:
            conn.execute(
                "INSERT INTO ideas (number, name, volume_id, outline_offset) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(number) DO UPDATE SET name=excluded.name, "
                "  volume_id=excluded.volume_id, outline_offset=excluded.outline_offset",
                (idea.number, idea.name, idea.volume_id, idea.outline_offset),
            )
            n_ideas += 1
        # topics: upsert by (idea_number, label)
        for t in topics:
            conn.execute(
                "INSERT INTO topics (idea_number, label, title, parent_label) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(idea_number, label) DO UPDATE SET "
                "  title=excluded.title, parent_label=excluded.parent_label",
                (t.idea_number, t.label, t.title, t.parent_label),
            )
            n_topics += 1
        # references: rebuild fresh
        conn.execute("DELETE FROM `references`")
        skipped = 0
        n_skipped_unknown_topic = 0
        for c in citations:
            volume_id = _resolve_volume(c.author_number, c.author_name)
            if volume_id is None or volume_id not in indexed_vols:
                skipped += 1
                continue
            author_id = _get_or_create_author(conn, c.author_name, c.author_number)
            raw_title = c.work_title or c.author_name
            # Run the work title through the parser's normaliser so that
            # fragments like "Summa Theologica, part i, q 22, a 3" map
            # to the canonical "Summa Theologica". The parser's helper
            # also handles OCR garbage by returning an empty string for
            # short unrecoverable tokens (in which case we fall back to
            # the author name so the reference is still attached).
            work_title_norm = normalize_work_title(raw_title) or c.author_name
            work_id = _get_or_create_work(conn, work_title_norm, volume_id)
            conn.execute(
                "INSERT INTO authorships (author_id, work_id) VALUES (?, ?) "
                "ON CONFLICT DO NOTHING",
                (author_id, work_id),
            )
            # Skip citations that reference a (idea, topic) pair we
            # didn't actually capture in the outline — the parser emits
            # such pairs when OCR fragments produce topic-like labels
            # inside the references section (e.g. cap 1 "3e" inline).
            topic_row = conn.execute(
                "SELECT 1 FROM topics WHERE idea_number = ? AND label = ?",
                (c.idea_number, c.topic_label),
            ).fetchone()
            if topic_row is None:
                n_skipped_unknown_topic += 1
                continue
            ref_text = c.work_title_raw or c.work_title
            conn.execute(
                "INSERT INTO `references` (idea_number, topic_label, author_id, "
                "  work_id, page_start, page_end, ref_text) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    c.idea_number, c.topic_label, author_id, work_id,
                    c.page_start, c.page_end, ref_text,
                ),
            )
            n_refs += 1
        if skipped:
            print(f"      (skipped {skipped} citations whose volume is not yet indexed)")
        # Batch-merge OCR variants of the same author (FIobbes -> Hobbes, etc.)
        print("      merging fuzzy author duplicates...")
        n_merged = merge_fuzzy_authors(conn)
        print(f"      merged {n_merged} duplicate author rows")
        # Collapse volume-split authors ("Aristotle I" + "Aristotle II" ->
        # "Aristotle"; "Shakespeare I" + "Shakespeare II" -> "Shakespeare").
        # The Syntopicon parser produces canonical author names without
        # these suffixes; the indexer creates them per-volume. We use
        # majority vote from references to determine the canonical id.
        print("      collapsing volume-split authors...")
        n_collapsed = collapse_volume_split_authors(conn)
        print(f"      collapsed {n_collapsed} volume-split author rows")

        # Persist the discursive corpus (idea introductions + cross-
        # references blocks, and the vol-2 front-matter sections).
        from .text_corpus import populate_text_corpus

    populate_text_corpus(parsed)
    return {"ideas": n_ideas, "topics": n_topics, "refs": n_refs}


def _find_syntopicon_paths() -> tuple[Path, Path]:
    """Locate the two Syntopicon volumes (2 and 3). Prefer txts-v2/, fall
    back to txts/.
    """
    for base in (_DEFAULT_TXT_DIR, _FALLBACK_TXT_DIR):
        if not base.is_dir():
            continue
        v2 = next(base.glob("*Great Ideas I*"), None)
        v3 = next(base.glob("*Great Ideas II*"), None)
        if v2 is not None and v3 is not None:
            return v2, v3
    raise SystemExit(
        "Syntopicon volumes (vol 2 + vol 3) not found in txts-v2/ or txts/. "
        "Run gbww_extract.py on Volume 2 and Volume 3 PDFs first."
    )


if __name__ == "__main__":
    v2, v3 = _find_syntopicon_paths()
    print(f"Parsing Syntopicon: {v2.name} + {v3.name}")
    parsed = parse_syntopicon(v2, v3)
    print(f"  ideas={len(parsed.ideas)} topics={len(parsed.topics)} "
          f"citations={len(parsed.citations)}")
    print("Building references table...")
    s = build_references(parsed)
    print(s)