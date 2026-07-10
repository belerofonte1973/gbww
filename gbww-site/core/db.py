"""
SQLite schema for the GBWW site.

Redesigned for the v2 layout:
  * `volumes` — one row per GBWW volume (1..54). `txt_path` points to the
    page-marker-aware TXT produced by gbww_extract.py.
  * `works` — distinct works, normalized (e.g. "Republic" not "Republic,
    bk i"). One row per (volume_id, work_title) pair; many works share a
    volume (Plato's dialogues all in vol 7).
  * `authors` — one row per distinct author name (no GBWW author number
    shown in UI; the number is kept only as internal join key).
  * `authorships` — (author_id, work_id) join table.
  * `ideas` — 102 Syntopicon ideas.
  * `topics` — Syntopicon topic labels per idea, with their hierarchical
    parent_label.
  * `references` — one row per (idea, topic, author, work, page-range).
    This is the granular table: a single Syntopicon reference that lists
    several page ranges (e.g. "Rep., bk v, 451c-453b / 457a-") becomes
    ONE row per page-range chunk. Each chunk is independently clickable.
  * `page_text` — (volume_id, page_marker) -> full extracted text of that
    column. Populated lazily when the user opens a passage.

We drop the old FTS5-on-citation_text because references no longer carry
the full original citation_text blob; we re-create a smaller FTS5 index
over (work_title, author_name, ref_text).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS volumes (
    number      INTEGER PRIMARY KEY,   -- 1..54
    display_name TEXT NOT NULL,
    authors     TEXT NOT NULL,         -- comma-separated
    works       TEXT NOT NULL,         -- comma-separated (used by site UI)
    txt_path    TEXT NOT NULL,
    is_syntopicon INTEGER NOT NULL DEFAULT 0  -- 1 for vol 2 or vol 3
);

CREATE TABLE IF NOT EXISTS authors (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    gbww_number  INTEGER,               -- 4..54 from Syntopicon; nullable
    UNIQUE(name, gbww_number)
);
CREATE INDEX IF NOT EXISTS idx_authors_name ON authors(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_authors_gbww ON authors(gbww_number);

CREATE TABLE IF NOT EXISTS works (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    volume_id    INTEGER NOT NULL,
    title        TEXT NOT NULL,
    title_norm   TEXT NOT NULL,         -- lowercase, stripped
    FOREIGN KEY (volume_id) REFERENCES volumes(number),
    UNIQUE(volume_id, title_norm)
);
CREATE INDEX IF NOT EXISTS idx_works_volume ON works(volume_id);
CREATE INDEX IF NOT EXISTS idx_works_title  ON works(title COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS authorships (
    author_id  INTEGER NOT NULL,
    work_id    INTEGER NOT NULL,
    PRIMARY KEY (author_id, work_id),
    FOREIGN KEY (author_id) REFERENCES authors(id),
    FOREIGN KEY (work_id)   REFERENCES works(id)
);

CREATE TABLE IF NOT EXISTS ideas (
    number        INTEGER PRIMARY KEY,   -- 1..102
    name          TEXT NOT NULL,
    volume_id     INTEGER NOT NULL,      -- 2 or 3 (Syntopicon volume)
    outline_offset INTEGER
);

CREATE TABLE IF NOT EXISTS topics (
    idea_number    INTEGER NOT NULL,
    label          TEXT NOT NULL,        -- "1", "2a", "3b"
    title          TEXT NOT NULL,
    parent_label   TEXT,                 -- NULL if top-level
    PRIMARY KEY (idea_number, label),
    FOREIGN KEY (idea_number) REFERENCES ideas(number)
);

CREATE TABLE IF NOT EXISTS `references` (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_number     INTEGER NOT NULL,
    topic_label     TEXT NOT NULL,
    author_id       INTEGER NOT NULL,
    work_id         INTEGER NOT NULL,
    -- the page-range "chunk" of the citation, e.g. "451c-453b"
    page_start      TEXT,
    page_end        TEXT,
    -- human-readable form, e.g. "bk v 451c-453b" (without the work title)
    ref_text        TEXT NOT NULL,
    FOREIGN KEY (idea_number, topic_label) REFERENCES topics(idea_number, label),
    FOREIGN KEY (author_id) REFERENCES authors(id),
    FOREIGN KEY (work_id)   REFERENCES works(id)
);
CREATE INDEX IF NOT EXISTS idx_ref_idea_topic
    ON `references` (idea_number, topic_label);
CREATE INDEX IF NOT EXISTS idx_ref_author    ON `references` (author_id);
CREATE INDEX IF NOT EXISTS idx_ref_work      ON `references` (work_id);
CREATE INDEX IF NOT EXISTS idx_ref_pages     ON `references` (work_id, page_start);

-- Pre-extracted text of every page+column. Populated by the indexer so the
-- site can serve passages without re-parsing 157 MB of TXT on each click.
--
-- A single GBWW volume hosts many independent works (e.g. volume 8
-- contains several Aristotelian treatises, each of which restarts
-- pagination at page 5). The primary key is therefore
-- (volume_id, page_marker, text_offset) so that a volume can hold
-- multiple page-5 entries — one per work. text_offset is the
-- monotonically-increasing character offset of the marker in the
-- volume TXT, used only to disambiguate when the same page marker
-- appears repeatedly within one volume.
CREATE TABLE IF NOT EXISTS page_text (
    volume_id   INTEGER NOT NULL,
    page_marker TEXT    NOT NULL,  -- "3a", "3b", "4a", ...
    text_offset INTEGER NOT NULL DEFAULT 0,
    text        TEXT    NOT NULL,
    word_count  INTEGER NOT NULL,
    PRIMARY KEY (volume_id, page_marker, text_offset)
);


-- FTS5 for global free-text search across references and works.
CREATE VIRTUAL TABLE IF NOT EXISTS refs_fts USING fts5(
    ref_text,
    work_title,
    author_name,
    content='references',
    content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS refs_ai AFTER INSERT ON `references` BEGIN
    INSERT INTO refs_fts(rowid, ref_text, work_title, author_name)
    SELECT new.id, new.ref_text, w.title, a.name
    FROM works w, authors a
    WHERE w.id = new.work_id AND a.id = new.author_id;
END;
CREATE TRIGGER IF NOT EXISTS refs_ad AFTER DELETE ON `references` BEGIN
    INSERT INTO refs_fts(refs_fts, rowid, ref_text, work_title, author_name)
    SELECT 'delete', old.id, old.ref_text, w.title, a.name
    FROM works w, authors a
    WHERE w.id = old.work_id AND a.id = old.author_id;
END;
CREATE TRIGGER IF NOT EXISTS refs_au AFTER UPDATE ON `references` BEGIN
    INSERT INTO refs_fts(refs_fts, rowid, ref_text, work_title, author_name)
    SELECT 'delete', old.id, old.ref_text, w.title, a.name
    FROM works w, authors a
    WHERE w.id = old.work_id AND a.id = old.author_id;
    INSERT INTO refs_fts(rowid, ref_text, work_title, author_name)
    SELECT new.id, new.ref_text, w.title, a.name
    FROM works w, authors a
    WHERE w.id = new.work_id AND a.id = new.author_id;
END;

-- Bodies of the 102 Syntopicon ideas: the discursive introduction essay
-- that precedes the Outline of Topics in each chapter, plus the
-- cross-references block. The site renders these on each idea's page.
CREATE TABLE IF NOT EXISTS idea_bodies (
    idea_number    INTEGER PRIMARY KEY,
    introduction   TEXT NOT NULL DEFAULT '',
    cross_references TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (idea_number) REFERENCES ideas(number)
);

-- The 2-3 introductory sections that precede Chapter 1: ANGEL in vol 2.
-- We keep both vol 2 ("PREFACE", "EXPLANATION OF REFERENCE STYLE") and
-- reserve a slot for vol 3 if it ever carries a similar preface.
CREATE TABLE IF NOT EXISTS intro_sections (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    volume_id INTEGER NOT NULL,        -- 2 or 3
    key       TEXT NOT NULL,           -- slug ("preface", "explanation-of-reference-style")
    title     TEXT NOT NULL,
    body      TEXT NOT NULL,
    ord       INTEGER NOT NULL DEFAULT 0,
    UNIQUE(volume_id, key)
);
"""


def default_db_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "gbww.db"


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = db_path or default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    """Create the schema if it doesn't exist yet. Idempotent.

    If the database was created with an older schema, this routine
    applies in-place migrations:
      1. If `page_text` has only 2 columns (volume_id, page_marker),
         rebuild it with the 3-column schema (volume_id, page_marker,
         text_offset) by copying data through a temp table.
    """
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        # Migration: page_text with old 2-column primary key.
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(page_text)").fetchall()]
        if "text_offset" not in cols:
            conn.executescript("""
                CREATE TABLE page_text_new (
                    volume_id   INTEGER NOT NULL,
                    page_marker TEXT    NOT NULL,
                    text_offset INTEGER NOT NULL DEFAULT 0,
                    text        TEXT    NOT NULL,
                    word_count  INTEGER NOT NULL,
                    PRIMARY KEY (volume_id, page_marker, text_offset)
                );
                INSERT INTO page_text_new
                    (volume_id, page_marker, text_offset, text, word_count)
                    SELECT volume_id, page_marker, 0, text, word_count
                    FROM page_text;
                DROP TABLE page_text;
                ALTER TABLE page_text_new RENAME TO page_text;
            """)


def reset_db(db_path: Path | None = None) -> None:
    """Drop all tables and recreate from SCHEMA. Used by build scripts."""
    with connect(db_path) as conn:
        for t in [
            "refs_fts", "refs_ai", "refs_ad", "refs_au",
            "`references`", "page_text", "authorships", "works",
            "authors", "topics", "ideas", "volumes",
        ]:
            try:
                conn.execute(f"DROP TABLE IF EXISTS {t}")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute(f"DROP TRIGGER IF EXISTS {t}")
            except sqlite3.OperationalError:
                pass
        conn.executescript(SCHEMA)