"""
Indexer: walks txts-v2/, populates volumes + authors + works + authorships.

Run after the extractor finishes:
    python3 -m core.indexer
"""

from __future__ import annotations

import re
from pathlib import Path

from .db import connect, init_db
from .util import canonical, find_fuzzy, fragments
import difflib  # noqa: E402


class _AuthorCache:
    """In-memory cache for the indexer too."""
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
            # Reject author lookups where the cache hit is on a tiny
            # common suffix like "ii" / "ius" / "ius" that does not
            # by itself prove the two names refer to the same author.
            # Require either a high overall sequence ratio OR enough
            # fragment overlap to avoid matching authors whose only
            # shared trait is a generic roman-numeral ending.
            if seq < 0.75 and overlap_score < 0.40:
                continue
            if score > best_score:
                best_score = score
                best_id = eid
        if best_score >= threshold:
            return best_id
        return None


_AUTH_CACHE = _AuthorCache()

# Default source: txts-v2/ inside /home/rodrigo/gbww (preferred — has page
# markers). Fall back to txts/ for volumes still being re-extracted.
_DEFAULT_TXT_DIR = Path("/home/rodrigo/gbww/txts-v2")
_FALLBACK_TXT_DIR = Path("/home/rodrigo/gbww/txts")
_SYN_TOPICON_DIR = Path("/home/rodrigo/gbww/txts-v2")  # vol 2 and vol 3 live here too

# Filenames for vol 2 (Great Ideas I) and vol 3 (Great Ideas II)
SYNTOPICON_VOL2_GLOB = "*Great Ideas I*"
SYNTOPICON_VOL3_GLOB = "*Great Ideas II*"

# "Encyclopædia Britannica - Great Books of the Western World, Volume 7 - Plato.txt"
FILENAME_RE = re.compile(r"Volume\s+(\d+)\s+-\s+(.+?)\.txt$", re.IGNORECASE)


def parse_filename(path: Path) -> tuple[int, str] | None:
    m = FILENAME_RE.search(path.name)
    if not m:
        return None
    return int(m.group(1)), m.group(2).strip()


def index_volumes_and_works(txt_dir: Path | None = None) -> dict:
    """Walk txt_dir and populate volumes / authors / works / authorships.

    Returns a summary dict for logging.
    """
    txt_dir = txt_dir or _DEFAULT_TXT_DIR
    if not txt_dir.is_dir():
        raise SystemExit(f"txt dir not found: {txt_dir}")
    init_db()

    # Pre-load the author cache from a separate connection so the DELETE
    # below doesn't wipe it.
    with connect() as _boot_conn:
        _AUTH_CACHE.load(_boot_conn)

    n_volumes = n_authors = n_works = n_links = 0

    with connect() as conn:
        conn.execute("DELETE FROM volumes")
        conn.execute("DELETE FROM authors")
        conn.execute("DELETE FROM works")
        conn.execute("DELETE FROM authorships")
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('authors','works')")

        files = sorted(txt_dir.glob("*.txt"))
        for path in files:
            parsed = parse_filename(path)
            if not parsed:
                continue
            number, display = parsed
            is_syn = (number in (2, 3))
            # Split display into authors + works heuristically:
            #   "Plato" -> authors=["Plato"], works=[]
            #   "Machiavelli, Hobbes" -> authors=["Machiavelli","Hobbes"]
            #   "Thomas Aquinas I" -> authors=["Thomas Aquinas I"]
            authors = [a.strip() for a in display.split(",") if a.strip()]
            conn.execute(
                "INSERT INTO volumes (number, display_name, authors, works, txt_path, is_syntopicon) "
                "VALUES (?, ?, ?, '', ?, ?)",
                (number, display, ", ".join(authors), str(path), is_syn),
            )
            n_volumes += 1

            for author_name in authors:
                cur = conn.execute(
                    "SELECT id FROM authors WHERE LOWER(REPLACE(REPLACE(name, '.', ''), ' ', '')) = "
                    "  LOWER(REPLACE(REPLACE(?, '.', ''), ' ', ''))",
                    (author_name,),
                ).fetchone()
                if cur:
                    aid = cur["id"]
                else:
                    fid = _AUTH_CACHE.find(author_name)
                    if fid is not None:
                        aid = fid
                    else:
                        # Use the volume's GBWW number as a fallback
                        # gbww_number for the author. This is correct
                        # for single-author volumes ("Homer" -> gbww=4)
                        # and approximate for multi-author volumes —
                        # the Syntopicon parser will overwrite this
                        # later via _get_or_create_author's backfill.
                        cur = conn.execute(
                            "INSERT INTO authors (name, gbww_number) VALUES (?, ?) RETURNING id",
                            (author_name, number),
                        )
                        aid = cur.fetchone()["id"]
                        _AUTH_CACHE.entries.append((aid, author_name, canonical(author_name), fragments(author_name)))
                n_authors += 1
                # Auto-create one work per volume-author pair, named after
                # the author (these get merged into specific works later when
                # the Syntopicon parser runs and emits per-reference works).
                work_title = author_name
                title_norm = work_title.lower().strip()
                cur = conn.execute(
                    "INSERT OR IGNORE INTO works (volume_id, title, title_norm) "
                    "VALUES (?, ?, ?) RETURNING id",
                    (number, work_title, title_norm),
                )
                row = cur.fetchone()
                if row:
                    wid = row["id"]
                else:
                    wid = conn.execute(
                        "SELECT id FROM works WHERE volume_id = ? AND title_norm = ?",
                        (number, title_norm),
                    ).fetchone()["id"]
                n_works += 1
                conn.execute(
                    "INSERT OR IGNORE INTO authorships (author_id, work_id) VALUES (?, ?)",
                    (aid, wid),
                )
                n_links += 1
    return {
        "n_volumes": n_volumes,
        "n_authors": n_authors,
        "n_works": n_works,
        "n_links": n_links,
    }


# Page-marker regex used by gbww_extract.py output: [1a], [1b], [42c], ...
#
# The 1952 Britannica Syntopicon set is sometimes produced by pymupdf
# with the marker glued to the surrounding paragraph ("[203]  I  was
# going...") or with the marker on its own line ("[203]"). Both are
# legal — we accept a marker wherever it appears on the line, but only
# when followed by at least one space (or end of line), so we do not
# confuse it with a [bracketed] word that happens to start with digits.
PAGE_MARKER_RE = re.compile(r"\[(\d{1,4}[a-d]?)\](?:\s|$)")


def index_page_text(txt_dir: Path | None = None, only_volume: int | None = None) -> int:
    """Read every [Xa]/[Xb]/... marker block from each TXT and store as a
    row in `page_text`.

    Returns total number of page-marker rows inserted.
    """
    txt_dir = txt_dir or _DEFAULT_TXT_DIR
    init_db()
    inserted = 0
    with connect() as conn:
        if only_volume is not None:
            rows = conn.execute(
                "SELECT number, txt_path FROM volumes WHERE number = ?", (only_volume,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT number, txt_path FROM volumes").fetchall()
        for r in rows:
            vol = r["number"]
            path = r["txt_path"]
            if not path or not Path(path).exists():
                continue
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
            # Walk: at each [Xa]-style marker, capture everything until the
            # next marker (or EOF). The marker may be inline on a content
            # line ("[203]  I was going...") — in that case the textual
            # content starts AFTER the marker on the same line.
            # We record the char offset of the marker (within the file
            # text) so multiple works sharing the same (volume, page)
            # can be distinguished.
            i = 0
            char_offset = 0
            buffer_marker: str | None = None
            buffer_offset: int | None = None
            buffer_lines: list[str] = []
            pending_rows: list[tuple] = []
            while i < len(lines):
                line = lines[i]
                m = PAGE_MARKER_RE.search(line)
                if m:
                    if buffer_marker is not None:
                        text = "".join(buffer_lines).strip()
                        if text and text != "[página ilustrada]":
                            wc = len(re.findall(r"\S+", text))
                            if wc >= 5:
                                pending_rows.append(
                                    (vol, buffer_marker, buffer_offset, text, wc)
                                )
                    end = m.end()
                    buffer_marker = m.group(1)
                    buffer_offset = char_offset + m.start()
                    buffer_lines = [line[end:]]
                elif buffer_marker is not None:
                    buffer_lines.append(line)
                char_offset += len(line)
                i += 1
            if buffer_marker is not None:
                text = "".join(buffer_lines).strip()
                if text and text != "[página ilustrada]":
                    wc = len(re.findall(r"\S+", text))
                    if wc >= 5:
                        pending_rows.append(
                            (vol, buffer_marker, buffer_offset, text, wc)
                        )
            if pending_rows:
                conn.execute("DELETE FROM page_text WHERE volume_id = ?", (vol,))
                conn.executemany(
                    "INSERT OR REPLACE INTO page_text "
                    "(volume_id, page_marker, text_offset, text, word_count) "
                    "VALUES (?, ?, ?, ?, ?)",
                    pending_rows,
                )
                inserted += len(pending_rows)
    return inserted


if __name__ == "__main__":
    import sys
    print("Indexing volumes and works...")
    s = index_volumes_and_works()
    print(s)
    if "--pages" in sys.argv:
        print("Indexing page_text...")
        n = index_page_text()
        print({"pages": n})