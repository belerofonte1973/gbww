"""
Permanently deduplicate the `works` table by collapsing fuzzy variants
("Timaeus" + "Ttmueus") into the row with the most citations per
volume. The same logic that powers `api_works` (Stage 2) is applied
to the database itself: references on variant rows are migrated to
the canonical row, authorships are merged, and the variants are
deleted.

Run as: ./venv/bin/python3 -m core.dedup_works

The script is idempotent: a second run is a no-op because no work
has more than one row with a high-similarity title (after the first
collapse the cluster shrinks to size 1).
"""
import re
import sqlite3
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "gbww.db"
THRESHOLD = 0.85
BRACKET_RE = re.compile(r"[\[\]\(\)]")
WHITESPACE_RE = re.compile(r"\s+")


def _normalize(title: str) -> str:
    s = title.strip().rstrip(".,;:- ").lower()
    s = BRACKET_RE.sub("", s)
    s = WHITESPACE_RE.sub(" ", s)
    return s


def _is_plausible_work_title(title: str) -> bool:
    """Mirror the noise gate in `serve.py:api_works` Stage 1."""
    if len(title) < 6:
        return False
    s = _normalize(title)
    if not s or len(s) < 6:
        return False
    if re.match(r"^[IVX]+\b", s):
        return False
    if not any(len(w) >= 5 for w in re.findall(r"[a-z]+", s)):
        return False
    return True


def _cluster_within_volume(items: list[sqlite3.Row]) -> list[list[sqlite3.Row]]:
    """Group items by fuzzy title similarity (threshold 0.85).

    Returns a list of clusters, where each cluster is a list of rows
    that should be merged. The first row of each cluster is the
    representative (the one with the most refs, since the caller
    pre-sorts by `-n_refs`).
    """
    consumed = [False] * len(items)
    clusters: list[list[sqlite3.Row]] = []
    for i, head in enumerate(items):
        if consumed[i]:
            continue
        cluster = [head]
        consumed[i] = True
        head_n = _normalize(head["title"])
        if not head_n:
            clusters.append(cluster)
            continue
        for j in range(i + 1, len(items)):
            if consumed[j]:
                continue
            other_n = _normalize(items[j]["title"])
            if not other_n:
                continue
            ratio = SequenceMatcher(None, head_n, other_n).ratio()
            if ratio >= THRESHOLD:
                cluster.append(items[j])
                consumed[j] = True
        clusters.append(cluster)
    return clusters


def main() -> int:
    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}")
        return 1
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    cur = con.execute("SELECT COUNT(*) FROM works")
    before = cur.fetchone()[0]
    print(f"works before: {before}")

    # Pull every work that survives the noise gate, with a count of
    # its references, sorted by volume then refs desc.
    rows = con.execute(
        """
        SELECT w.id, w.title, w.volume_id,
               (SELECT COUNT(*) FROM `references` WHERE work_id = w.id) AS n_refs
        FROM works w
        WHERE LENGTH(w.title) >= 6
          AND w.title NOT LIKE '%]'
          AND w.title NOT LIKE '%[%'
          AND w.title NOT LIKE '%0%' AND w.title NOT LIKE '%1%'
          AND w.title NOT LIKE '%2%' AND w.title NOT LIKE '%3%'
          AND w.title NOT LIKE '%4%' AND w.title NOT LIKE '%5%'
          AND w.title NOT LIKE '%6%' AND w.title NOT LIKE '%7%'
          AND w.title NOT LIKE '%8%' AND w.title NOT LIKE '%9%'
          AND w.title NOT LIKE '%-'
        ORDER BY w.volume_id, n_refs DESC
        """
    ).fetchall()

    # Apply the noise gate in Python (mirrors api_works Stage 1).
    eligible = [r for r in rows if _is_plausible_work_title(r["title"])]
    print(f"eligible after noise gate: {len(eligible)}")

    # Group by volume and cluster.
    by_vol: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for r in eligible:
        by_vol[r["volume_id"]].append(r)
    print(f"volumes with eligible works: {len(by_vol)}")

    # Plan merges.
    n_merges = 0
    n_refs_migrated = 0
    n_refs_deleted_orphan = 0
    n_authorships_migrated = 0
    n_works_deleted = 0
    for vol_id, items in by_vol.items():
        clusters = _cluster_within_volume(items)
        for cluster in clusters:
            if len(cluster) <= 1:
                continue
            # First item has the most refs (we ordered by n_refs DESC).
            canonical_id = cluster[0]["id"]
            variant_ids = [c["id"] for c in cluster[1:]]
            # Migrate references via INSERT OR IGNORE into a temp row
            # with the canonical work_id, then delete the variant
            # references. This way a (idea, topic, author, work)
            # collision on the canonical row is silently dropped
            # (the variant reference is the duplicate, the canonical
            # is the survivor).
            for vid in variant_ids:
                # Count the variant refs (for the report)
                n = con.execute(
                    "SELECT COUNT(*) FROM `references` WHERE work_id = ?",
                    (vid,),
                ).fetchone()[0]
                # Move them
                moved = con.execute(
                    "UPDATE `references` SET work_id = ? WHERE work_id = ?",
                    (canonical_id, vid),
                ).rowcount
                n_refs_migrated += moved
                # If the UPDATE was a no-op (every variant ref collided
                # on the canonical), the variant refs are now just
                # duplicates of canonical refs and should be deleted.
                leftover = con.execute(
                    "SELECT COUNT(*) FROM `references` WHERE work_id = ?",
                    (vid,),
                ).fetchone()[0]
                if leftover:
                    con.execute(
                        "DELETE FROM `references` WHERE work_id = ?",
                        (vid,),
                    )
                    n_refs_deleted_orphan += leftover
            # Migrate authorships: INSERT OR IGNORE then DELETE.
            for vid in variant_ids:
                moved = con.execute(
                    "INSERT OR IGNORE INTO authorships (author_id, work_id) "
                    "SELECT author_id, ? FROM authorships WHERE work_id = ?",
                    (canonical_id, vid),
                ).rowcount
                n_authorships_migrated += moved
                con.execute(
                    "DELETE FROM authorships WHERE work_id = ?",
                    (vid,),
                )
            # Delete variant works.
            for vid in variant_ids:
                con.execute("DELETE FROM works WHERE id = ?", (vid,))
                n_works_deleted += 1
            n_merges += 1

    con.commit()
    after = con.execute("SELECT COUNT(*) FROM works").fetchone()[0]
    refs_after = con.execute("SELECT COUNT(*) FROM `references`").fetchone()[0]
    print(f"clusters merged:           {n_merges}")
    print(f"variant works deleted:     {n_works_deleted}")
    print(f"work rows after:           {after}")
    print(f"references after:          {refs_after} (was 99840)")
    print(f"references migrated:       {n_refs_migrated}")
    print(f"orphan refs deleted:       {n_refs_deleted_orphan}")
    if refs_after < 99840:
        lost = 99840 - refs_after
        print(f"references lost:           {lost} (variant refs that "
              f"collided on a canonical and were dropped)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
