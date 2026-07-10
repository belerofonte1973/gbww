"""Shared helpers."""
from __future__ import annotations
import difflib
import re

# Matches runs of 2+ letters that look like a name fragment
_FRAGMENT_RE = re.compile(r"[A-Za-z]{2,}")
_NON_ALPHA_RE = re.compile(r"[^a-z]")


def canonical(name: str) -> str:
    """Lowercase, strip everything that isn't a-z letter."""
    return _NON_ALPHA_RE.sub("", name.lower())


def fragments(name: str) -> list[str]:
    """Return a list of letter-fragments (>= 2 chars) of `name`.

    Used to handle 'Adam Smith' vs 'Smith' — fragment matching finds both
    have 'smith'. For OCR garbage like 'FIobbes' we extract 'bb' + 'es'
    and don't expect a match against 'hobbes'.
    """
    return _FRAGMENT_RE.findall(name.lower())


def find_fuzzy(conn, table: str, column: str, name: str,
               threshold: float = 0.78) -> int | None:
    """Find a row in `table` whose `column` value canonicalizes similarly to
    `name`. Returns the row id, or None if no row scores >= threshold.

    Scoring combines:
      - exact canonical similarity (SequenceMatcher ratio)
      - fragment overlap (e.g. 'adam smith' contains 'smith', so it
        matches 'Smith' at high score)
      - **suffix overlap** (handles OCR-prepended garbage: 'FIobbes'
        canonicalizes to 'fiiobbes', but its suffix 'bbes' matches
        'hobbes' -> 'bbes')
    """
    canon = canonical(name)
    if not canon:
        return None
    frags = fragments(name)
    cur = conn.execute(f"SELECT id, {column} FROM {table}")
    cols = [c[0] for c in cur.description]
    rows = cur.fetchall()
    best_id = None
    best_score = 0.0
    for r in rows:
        rec = dict(zip(cols, r))
        other = rec[column]
        existing = canonical(other)
        if not existing:
            continue
        seq_score = difflib.SequenceMatcher(None, canon, existing).ratio()
        # Fragment overlap
        other_frags = fragments(other)
        overlap = 0
        for f in frags:
            for g in other_frags:
                if f == g or (len(f) >= 4 and len(g) >= 4 and
                              difflib.SequenceMatcher(None, f, g).ratio() >= 0.85):
                    overlap += 1
                    break
        overlap_score = min(1.0, overlap / max(1, len(frags)))
        # Suffix overlap: compare last 3-4 chars of canon vs existing.
        # Handles 'FIobbes' (suffix 'bbes') vs 'Hobbes' (suffix 'bbes').
        suffix_score = 0.0
        for n in (3, 4, 5):
            if len(canon) >= n and len(existing) >= n:
                s1, s2 = canon[-n:], existing[-n:]
                ratio = difflib.SequenceMatcher(None, s1, s2).ratio()
                if ratio >= 0.85:
                    suffix_score = max(suffix_score, ratio)
        # Combine: when suffix_score is high (OCR-prepended garbage),
        # that signal dominates. Otherwise fall back to sequence + fragment.
        if suffix_score >= 0.85:
            score = max(suffix_score, 0.4 * seq_score + 0.4 * overlap_score + 0.2 * suffix_score + 0.15)
        else:
            score = 0.5 * seq_score + 0.35 * overlap_score + 0.15 * suffix_score
        if score > best_score:
            best_score = score
            best_id = rec["id"]
    return best_id if best_score >= threshold else None