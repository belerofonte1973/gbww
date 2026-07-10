#!/usr/bin/env python3
"""
GBWW site server (v2).

Endpoints
---------
GET  /                                  -> index.html
GET  /ideias/                           -> ideas.html
GET  /ideias/N/                         -> idea.html (topics under idea N)
GET  /ideias/N/<topic>/                 -> topic.html (refs under topic)
GET  /autores/                          -> authors.html
GET  /autores/<name>/                   -> author.html
GET  /obras/                            -> works.html
GET  /obras/<id>/                       -> work.html (full text, page by page)
GET  /api/ideas                         -> [{number, name, n_topics, n_refs}]
GET  /api/idea/<n>                      -> idea detail + topics
GET  /api/idea/<n>/topic/<label>        -> refs under that topic
GET  /api/authors                       -> [{name, gbww_number, n_works, n_refs}]
GET  /api/author/<name>                 -> refs (grouped by work)
GET  /api/works                         -> [{id, title, volume_id, volume_display, n_refs}]
GET  /api/work/<id>                     -> refs grouped by page-chunk
GET  /api/page?volume=N&page=M          -> page_text row
GET  /api/page/range?volume=N&page_start=A&page_end=B -> concatenated pages
GET  /api/search?q=...                  -> FTS5 hits

Run:
    cd /home/rodrigo/gbww/gbww-site/site
    python3 ../serve.py            # default 8765
"""

from __future__ import annotations

import argparse
import http.server
import json
import re
import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent / "site"
sys.path.insert(0, str(HERE.parent))
from core.db import connect, default_db_path  # noqa: E402


# --- Helpers --------------------------------------------------------------

def _json(payload, status: int = 200) -> tuple[bytes, str, int]:
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    return body, "application/json; charset=utf-8", status


def _strip_volume_marker(marker: str) -> tuple[str, str | None]:
    """Split '53a' -> ('53', 'a'); '53' -> ('53', None)."""
    m = re.match(r"^(\d+)([a-d])?$", marker.strip())
    if not m:
        return marker, None
    return m.group(1), m.group(2)


def _ordered_page_range(volume_id: int, page_start: str, page_end: str | None,
                        db_path) -> list[str]:
    """Return the inclusive list of page markers between start and end.

    Example: vol 4 (Homer), '49a'..'50b' returns ['49a','49b','50a','50b']
    if all exist; otherwise returns whatever subset exists. Falls back to
    the two endpoints if we can't infer the full range.
    """
    if not page_start:
        return []
    n1, _ = _strip_volume_marker(page_start)
    n2 = n1
    if page_end:
        n2, _ = _strip_volume_marker(page_end)
    n1_i, n2_i = int(n1), int(n2)
    if n2_i < n1_i:
        n1_i, n2_i = n2_i, n1_i
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT page_marker FROM page_text WHERE volume_id = ? AND "
            "  CAST(SUBSTR(page_marker, 1, LENGTH(page_marker) - "
            "    CASE WHEN page_marker GLOB '*[a-d]' THEN 1 ELSE 0 END) AS INTEGER) "
            "  BETWEEN ? AND ? "
            "ORDER BY page_marker",
            (volume_id, n1_i, n2_i),
        ).fetchall()
    return [r["page_marker"] for r in rows]


# --- API handlers ---------------------------------------------------------

def api_ideas(db_path) -> dict:
    with connect(db_path) as conn:
        rows = conn.execute("""
            SELECT i.number, i.name,
                   (SELECT COUNT(*) FROM topics WHERE idea_number = i.number) AS n_topics,
                   (SELECT COUNT(*) FROM `references` WHERE idea_number = i.number) AS n_refs
            FROM ideas i ORDER BY i.number
        """).fetchall()
    return {"ideas": [dict(r) for r in rows]}


def api_idea_detail(number: int, db_path) -> dict | None:
    with connect(db_path) as conn:
        idea = conn.execute(
            "SELECT number, name, volume_id FROM ideas WHERE number = ?",
            (number,),
        ).fetchone()
        if not idea:
            return None
        topics = conn.execute("""
            SELECT t.label, t.title, t.parent_label,
                   (SELECT COUNT(*) FROM `references` r
                    WHERE r.idea_number = t.idea_number AND r.topic_label = t.label
                   ) AS n_refs
            FROM topics t WHERE t.idea_number = ?
            ORDER BY
              CASE WHEN t.parent_label IS NULL THEN 0 ELSE 1 END,
              CAST(t.label AS INTEGER),
              t.label
        """, (number,)).fetchall()
    return {"idea": dict(idea), "topics": [dict(t) for t in topics]}


def api_topic_refs(idea_number: int, label: str, db_path) -> dict:
    with connect(db_path) as conn:
        rows = conn.execute("""
            SELECT r.id, r.idea_number, r.topic_label, r.page_start, r.page_end,
                   r.ref_text, a.name AS author_name, w.id AS work_id,
                   w.title AS work_title, v.number AS volume_id,
                   v.display_name AS volume_display
            FROM `references` r
            JOIN authors a ON a.id = r.author_id
            JOIN works   w ON w.id = r.work_id
            LEFT JOIN volumes v ON v.number = w.volume_id
            WHERE r.idea_number = ? AND r.topic_label = ?
            ORDER BY a.name, w.title, r.page_start, r.id
        """, (idea_number, label)).fetchall()
    refs = []
    for r in rows:
        refs.append({
            "id": r["id"],
            "author_name": r["author_name"],
            "work_id": r["work_id"],
            "work_title": r["work_title"],
            "page_start": r["page_start"],
            "page_end": r["page_end"],
            "ref_text": r["ref_text"],
            "volume_id": r["volume_id"],
            "volume_display": r["volume_display"],
        })
    return {"refs": refs}


def api_authors(db_path) -> dict:
    with connect(db_path) as conn:
        rows = conn.execute("""
            SELECT a.id, a.name, a.gbww_number,
                   (SELECT COUNT(DISTINCT work_id) FROM authorships
                    WHERE author_id = a.id) AS n_works,
                   (SELECT COUNT(*) FROM `references` WHERE author_id = a.id) AS n_refs
            FROM authors a
            ORDER BY a.name COLLATE NOCASE
        """).fetchall()
    return {"authors": [dict(r) for r in rows]}


def api_author_detail(name: str, db_path) -> dict:
    with connect(db_path) as conn:
        author = conn.execute(
            "SELECT id, name, gbww_number FROM authors WHERE LOWER(name) = LOWER(?)",
            (name,),
        ).fetchone()
        if not author:
            return {"error": f"author not found: {name!r}"}
        works = conn.execute("""
            SELECT w.id AS work_id, w.title AS work_title, w.volume_id,
                   v.display_name AS volume_display,
                   (SELECT COUNT(*) FROM `references` r
                    WHERE r.author_id = ? AND r.work_id = w.id) AS n_refs
            FROM authorships au
            JOIN works   w ON w.id = au.work_id
            LEFT JOIN volumes v ON v.number = w.volume_id
            WHERE au.author_id = ?
            ORDER BY w.title COLLATE NOCASE
        """, (author["id"], author["id"])).fetchall()
    return {
        "author": dict(author),
        "works": [dict(w) for w in works],
    }


def api_works(db_path) -> dict:
    """Return a deduplicated list of real works (per volume × canonical
    title). The full `works` table also holds sub-spec fragments
    ("Summa Theologica, part i, q 22"), which we collapse to the
    parent title here so the front-end does not show dozens of stubs
    for the same book.

    Heuristic: for every (volume_id, normalised-title-prefix) bucket,
    keep the entry with the highest number of Syntopicon citations.
    The normaliser strips trailing punctuation and brackets, then
    keeps only entries whose normalised title is plausibly real
    (length >= 6, contains a vowel pattern, does not begin with a
    Roman subscript).
    """
    import re as _re
    _re_noise = _re.compile(r"^[IVX]+\b")  # bare Roman
    _re_brackets = _re.compile(r"[\[\]\(\)]")
    def _normalize(title: str) -> str:
        s = title.strip().rstrip(".,;:- ").lower()
        s = _re_brackets.sub("", s)
        s = _re.sub(r"\s+", " ", s)
        return s
    with connect(db_path) as conn:
        rows = conn.execute("""
            SELECT w.id, w.title, w.volume_id, v.display_name AS volume_display,
                   (SELECT COUNT(*) FROM `references` WHERE work_id = w.id) AS n_refs
            FROM works w
            LEFT JOIN volumes v ON v.number = w.volume_id
            WHERE LENGTH(w.title) >= 6
              AND w.title NOT LIKE '%]'
              AND w.title NOT LIKE '%[%'
              AND w.title NOT LIKE '%0%' AND w.title NOT LIKE '%1%'
              AND w.title NOT LIKE '%2%' AND w.title NOT LIKE '%3%'
              AND w.title NOT LIKE '%4%' AND w.title NOT LIKE '%5%'
              AND w.title NOT LIKE '%6%' AND w.title NOT LIKE '%7%'
              AND w.title NOT LIKE '%8%' AND w.title NOT LIKE '%9%'
              AND w.title NOT LIKE '%-'
        """).fetchall()
    # 1) Accept only entries whose normalised form passes the noise gate
    #    (length, ends plausibly, no Roman subscript alone, has at least
    #    one alphabetic word >= 3 letters).
    canonical: dict[tuple, dict] = {}
    for r in rows:
        norm = _normalize(r["title"])
        if not norm or len(norm) < 6:
            continue
        if _re_noise.match(norm):
            continue
        first_word = norm.split(" ", 1)[0].rstrip(",.")
        # Real works typically have at least one word >= 5 letters in
        # their title (Plato, Aristotle, Republic, Metaphysics, Soul,
        # Cratylus, etc.). Fragment-only works have only 1-3 letter
        # words. We require exactly this.
        if not any(len(w) >= 5 for w in re.findall(r"[a-z]+", norm)):
            continue
        key = (r["volume_id"], norm)
        cur = canonical.get(key)
        if cur is None or r["n_refs"] > cur["n_refs"]:
            canonical[key] = dict(r)
    # 2) Collapse "Republic, bk 1" / "Republic bk 1" / "Republic, 5"
    #    into the same canonical "Republic" by grouping on the longest
    #    shared prefix that does NOT contain a Roman/alphanum suffix.
    #
    #    We then do a second pass that groups fuzzy variants of the
    #    same work ("Tifnaeus" / "Titnaeus" / "Timaeus", "Sytnposium"
    #    / "Symposium", "Advancement ofLearning" / "Advancement of
    #    Learning") by SequenceMatcher ratio >= 0.85 *within the
    #    same volume*. The representative is the row with the most
    #    refs; the rest are discarded.
    from difflib import SequenceMatcher
    # Sort by n_refs desc so the best entry becomes the cluster head.
    by_refs = sorted(canonical.values(), key=lambda r: -r["n_refs"])
    by_volume: dict[int, list[dict]] = {}
    for r in by_refs:
        by_volume.setdefault(r["volume_id"], []).append(r)
    survivors: list[dict] = []
    for vol_id, items in by_volume.items():
        # Cluster items by similarity of normalized title.
        # Items are pre-sorted by n_refs, so the first-seen item in a
        # cluster is the highest-refs representative.
        consumed = [False] * len(items)
        for i, head in enumerate(items):
            if consumed[i]:
                continue
            head_norm = _normalize(head["title"])
            # Compare head with every later item. Threshold 0.85 is
            # tight enough that "Republic" merges with "Republic" but
            # not with "Republica" or "Republics".
            for j in range(i + 1, len(items)):
                if consumed[j]:
                    continue
                other_norm = _normalize(items[j]["title"])
                if not other_norm:
                    continue
                ratio = SequenceMatcher(None, head_norm, other_norm).ratio()
                # Threshold 0.85 merges OCR variants where the
                # character-level alignment is mostly intact
                # ("Ttmaeus" / "Timaeus" is 0.857, "Cratylus" /
                # "Cratyhts" is 0.75 — too low, kept) but keeps
                # distinct works apart ("Fifth Ennead" / "Fourth
                # Ennead" is 0.80, "Republic" / "Republics" is 0.89 —
                # both safely below 0.85 / above 0.85 in the right
                # direction). We do not relax the threshold further
                # because Plotinus's 9 Enneads, Plutarch's Lives, and
                # other name-heavy collections would collapse.
                if ratio >= 0.85:
                    consumed[j] = True
            survivors.append(head)
    out = sorted(survivors, key=lambda r: r["title"].lower())
    return {"works": out}


def api_work_detail(work_id: int, db_path) -> dict:
    with connect(db_path) as conn:
        work = conn.execute("""
            SELECT w.id, w.title, w.volume_id, v.display_name AS volume_display,
                   v.txt_path
            FROM works w
            LEFT JOIN volumes v ON v.number = w.volume_id
            WHERE w.id = ?
        """, (work_id,)).fetchone()
        if not work:
            return {"error": f"work not found: {work_id}"}
        refs = conn.execute("""
            SELECT r.id, r.idea_number, r.topic_label, r.page_start, r.page_end,
                   r.ref_text, i.name AS idea_name,
                   t.title AS topic_title, a.name AS author_name
            FROM `references` r
            JOIN ideas   i ON i.number = r.idea_number
            LEFT JOIN topics t ON t.idea_number = r.idea_number
                              AND t.label = r.topic_label
            JOIN authors a ON a.id = r.author_id
            WHERE r.work_id = ?
            ORDER BY r.idea_number, r.topic_label, r.id
        """, (work_id,)).fetchall()
        pages = []
        if work["volume_id"]:
            pages = conn.execute("""
                SELECT page_marker, text, word_count
                FROM page_text WHERE volume_id = ?
                ORDER BY CAST(SUBSTR(page_marker, 1,
                    LENGTH(page_marker) -
                    CASE WHEN page_marker GLOB '*[a-d]' THEN 1 ELSE 0 END
                ) AS INTEGER),
                page_marker
            """, (work["volume_id"],)).fetchall()
    return {
        "work": dict(work),
        "refs": [dict(r) for r in refs],
        "pages": [dict(p) for p in pages],
    }


def api_page(volume_id: int, page_marker: str, db_path) -> dict:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT text, word_count FROM page_text "
            "WHERE volume_id = ? AND page_marker = ?",
            (volume_id, page_marker),
        ).fetchone()
    if not row:
        return {"error": f"page not found: vol {volume_id} {page_marker}"}
    return {
        "volume_id": volume_id,
        "page_marker": page_marker,
        "text": row["text"],
        "word_count": row["word_count"],
    }


def api_page_range(volume_id: int, page_start: str, page_end: str,
                   db_path) -> dict:
    markers = _ordered_page_range(volume_id, page_start, page_end, db_path)
    if not markers:
        return {"error": "no pages resolved", "page_start": page_start, "page_end": page_end}
    with connect(db_path) as conn:
        placeholders = ",".join(["?"] * len(markers))
        rows = conn.execute(
            f"SELECT page_marker, text FROM page_text "
            f"WHERE volume_id = ? AND page_marker IN ({placeholders}) "
            f"ORDER BY page_marker",
            [volume_id] + markers,
        ).fetchall()
    return {
        "volume_id": volume_id,
        "pages": [dict(r) for r in rows],
        "page_start": page_start,
        "page_end": page_end,
    }


def api_search(query: str, limit: int, db_path) -> dict:
    if not query.strip():
        return {"hits": []}
    with connect(db_path) as conn:
        rows = conn.execute("""
            SELECT r.id, r.idea_number, i.name AS idea_name,
                   r.topic_label, t.title AS topic_title,
                   a.name AS author_name, w.title AS work_title,
                   w.volume_id, v.display_name AS volume_display,
                   r.page_start, r.page_end, r.ref_text, refs_fts.rank AS rank
            FROM refs_fts
            JOIN `references` r ON r.id = refs_fts.rowid
            JOIN authors   a ON a.id = r.author_id
            JOIN works     w ON w.id = r.work_id
            LEFT JOIN volumes v ON v.number = w.volume_id
            JOIN ideas     i ON i.number = r.idea_number
            LEFT JOIN topics t ON t.idea_number = r.idea_number
                              AND t.label = r.topic_label
            WHERE refs_fts MATCH ?
            ORDER BY refs_fts.rank
            LIMIT ?
        """, (query, limit)).fetchall()
    return {"hits": [dict(r) for r in rows]}


# --- Static handler -------------------------------------------------------

class Handler(http.server.SimpleHTTPRequestHandler):
    db_path = default_db_path()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def log_message(self, format, *args):
        sys.stderr.write(f"[serve] {format % args}\n")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")

        try:
            # API routes
            if path == "/api/ideas":
                body, ctype, status = _json(api_ideas(self.db_path))
            elif path.startswith("/api/idea/") and path.count("/") == 4 and path.endswith("/topic"):
                # /api/idea/N/topic -> use label from query ?label=X
                idea_n = int(path.split("/")[3])
                label = (query.get("label") or [""])[0]
                body, ctype, status = _json(api_topic_refs(idea_n, label, self.db_path))
            elif path.startswith("/api/idea/") and "/topic/" in path:
                # /api/idea/N/topic/<label>
                parts = path.split("/")
                idea_n = int(parts[3])
                label = urllib.parse.unquote(parts[5])
                body, ctype, status = _json(api_topic_refs(idea_n, label, self.db_path))
            elif path.startswith("/api/idea/") and path.count("/") == 3:
                # /api/idea/N
                idea_n = int(path.rsplit("/", 1)[-1])
                data = api_idea_detail(idea_n, self.db_path)
                if data is None:
                    body, ctype, status = _json({"error": "idea not found"}, 404)
                else:
                    body, ctype, status = _json(data)
            elif path == "/api/authors":
                body, ctype, status = _json(api_authors(self.db_path))
            elif path.startswith("/api/author/"):
                name = urllib.parse.unquote(path[len("/api/author/"):])
                body, ctype, status = _json(api_author_detail(name, self.db_path))
            elif path == "/api/works":
                body, ctype, status = _json(api_works(self.db_path))
            elif path.startswith("/api/work/"):
                try:
                    wid = int(path.rsplit("/", 1)[-1])
                except ValueError:
                    body, ctype, status = _json({"error": "work id must be int"}, 400)
                    return self._send(body, ctype, status)
                body, ctype, status = _json(api_work_detail(wid, self.db_path))
            elif path == "/api/page":
                vid = int((query.get("volume") or ["0"])[0])
                marker = (query.get("page") or [""])[0]
                body, ctype, status = _json(api_page(vid, marker, self.db_path))
            elif path == "/api/page/range":
                vid = int((query.get("volume") or ["0"])[0])
                ps = (query.get("page_start") or [""])[0]
                pe = (query.get("page_end") or [""])[0]
                body, ctype, status = _json(api_page_range(vid, ps, pe, self.db_path))
            elif path == "/api/search":
                q = (query.get("q") or [""])[0]
                limit = int((query.get("limit") or ["20"])[0])
                body, ctype, status = _json(api_search(q, limit, self.db_path))
            else:
                # /obras/<id>/obra.html -> serve the same obra.html
                # template regardless of the id; the work id is read
                # from the URL by js/work.js. The HTML template uses
                # <base href="/"> so relative paths resolve from the
                # server root.
                m = re.match(r"^/obras/(\d+)/obra\.html$", path)
                if m:
                    self.path = "/obras/obra.html"
                return super().do_GET()
        except (ValueError, KeyError) as e:
            body, ctype, status = _json({"error": str(e)}, 400)
        except Exception as e:
            body, ctype, status = _json({"error": str(e)}, 500)

        self._send(body, ctype, status)

    def _send(self, body, ctype, status):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--db", type=Path, default=None)
    args = p.parse_args()
    if args.db is not None:
        Handler.db_path = args.db
    server = http.server.ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"GBWW site serving at http://{args.host}:{args.port}/")
    print(f"DB: {Handler.db_path}")
    print("Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping.")


if __name__ == "__main__":
    main()