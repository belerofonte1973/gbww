"""
Populate the Syntopicon discursive corpus tables from a parsed
ParsedSyntopicon object.

The parser (core/parser.py) extracts the discursive bodies of every
idea (introduction essay + cross-references block) and the introductory
sections at the start of vol 2 (PREFACE / EXPLANATION OF REFERENCE
STYLE). This module persists those to the `idea_bodies` and
`intro_sections` tables.

Run after `parse_syntopicon(...)` has been called and the DB has been
initialised (via `init_db`).
"""

from __future__ import annotations

from typing import Iterable

from .db import connect
from .models import IntroSection, ParsedSyntopicon


def populate_text_corpus(parsed: ParsedSyntopicon) -> dict:
    """Insert ideas' discursive bodies and the vol 2 front-matter
    sections. Returns a small statistics dict.
    """
    n_intros = 0
    n_bodies = 0

    with connect() as conn:
        # Drop existing rows (corpus is fully regenerated on every
        # build).
        conn.execute("DELETE FROM idea_bodies")
        conn.execute("DELETE FROM intro_sections")

        for sec in parsed.introductions:
            _upsert_intro(conn, sec)
            n_intros += 1

        for idea_number, body in parsed.idea_bodies.items():
            conn.execute(
                "INSERT OR REPLACE INTO idea_bodies "
                "(idea_number, introduction, cross_references) "
                "VALUES (?, ?, ?)",
                (idea_number, body.introduction, body.cross_references),
            )
            n_bodies += 1

    return {"bodies": n_bodies, "intro_sections": n_intros}


def _upsert_intro(conn, sec: IntroSection) -> None:
    """Insert one IntroSection.

    The (volume_id, key) UNIQUE constraint means a re-build replaces
    the previous row. We compute volume_id heuristically: key
    "preface" / "explanation-of-reference-style" / "suggestions" /
    "the-great-ideas-today" all live in vol 2 (the Syntopicon proper
    + its editorial apparatus). We accept that vol 3 may carry its
    own versions in a future edition.
    """
    # Map popular keys to vol_id 2; everything else defaults to 2 too
    # (vol 2 is where the front-matter lives).
    volume_id = 2
    ord = _intro_order(sec.key)
    conn.execute(
        "INSERT INTO intro_sections (volume_id, key, title, body, ord) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(volume_id, key) DO UPDATE SET "
        "title=excluded.title, body=excluded.body, ord=excluded.ord",
        (volume_id, sec.key, sec.title, sec.body, ord),
    )


def _intro_order(key: str) -> int:
    """Hard-coded display order for the Introdução tab."""
    table = {
        "preface": 1,
        "suggestions-for-using-the-syntopicon": 2,
        "explanation-of-reference-style": 3,
        "the-great-ideas-today": 4,
    }
    return table.get(key, 99)


def fetch_intro_sections(conn) -> list[dict]:
    """Read all introductory sections ordered for the UI."""
    cur = conn.execute(
        "SELECT key, title, body, ord FROM intro_sections "
        "ORDER BY ord ASC, id ASC"
    )
    return [dict(r) for r in cur.fetchall()]


def fetch_idea_body(conn, idea_number: int) -> dict | None:
    cur = conn.execute(
        "SELECT idea_number, introduction, cross_references "
        "FROM idea_bodies WHERE idea_number = ?",
        (idea_number,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return dict(row)


def list_idea_bodies(conn) -> list[int]:
    """Return idea_numbers that have a body persisted."""
    cur = conn.execute("SELECT idea_number FROM idea_bodies ORDER BY idea_number")
    return [r["idea_number"] for r in cur.fetchall()]


def fetch_all_works_index(conn) -> list[dict]:
    """For the front-end "Obras" tab: every (author, work_title) pair
    in the Syntopicon, ordered by author then work_title. We return
    raw rows; the front-end formats them.
    """
    cur = conn.execute(
        "SELECT a.name AS author_name, a.gbww_number, "
        "       w.title AS work_title, "
        "       COUNT(r.id) AS n_refs "
        "FROM authors a "
        "JOIN works w ON w.id IS NOT NULL "
        "JOIN authorships ash ON ash.author_id = a.id AND ash.work_id = w.id "
        "LEFT JOIN \"references\" r ON r.work_id = w.id AND r.author_id = a.id "
        "GROUP BY a.id, w.id "
        "ORDER BY a.name, w.title"
    )
    return [dict(r) for r in cur.fetchall()]
