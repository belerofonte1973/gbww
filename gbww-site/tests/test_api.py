"""
Smoke tests for the GBWW site HTTP API (serve.py).

Run only when the server is up on http://localhost:<port>.
Defaults to port 8781. Override with the GBWW_PORT env var.

  GBWW_PORT=8781 ./venv/bin/python3 tests/test_api.py
"""
import json
import os
import sys
import unittest
import urllib.error
import urllib.request

PORT = os.environ.get("GBWW_PORT", "8781")
BASE = f"http://localhost:{PORT}"


def _get(path: str):
    try:
        body = urllib.request.urlopen(f"{BASE}{path}", timeout=10).read()
    except urllib.error.URLError as e:
        raise SystemExit(f"server not reachable at {BASE}: {e}")
    return json.loads(body)


def _get_status(path: str) -> int:
    try:
        r = urllib.request.urlopen(f"{BASE}{path}", timeout=10)
        return r.status
    except urllib.error.URLError:
        return -1


class ApiEndpointTests(unittest.TestCase):
    """Each API endpoint must respond 200 with the expected shape."""

    def test_api_ideas(self):
        data = _get("/api/ideas")
        self.assertIsInstance(data, dict)
        self.assertIn("ideas", data)
        self.assertEqual(len(data["ideas"]), 102)
        for idea in data["ideas"][:3]:
            self.assertIn("number", idea)
            self.assertIn("name", idea)

    def test_api_authors(self):
        data = _get("/api/authors")
        self.assertIsInstance(data, dict)
        self.assertIn("authors", data)
        # 55 author entries (54 Syntopicon + 1 for each volume-split)
        self.assertGreaterEqual(len(data["authors"]), 50)

    def test_api_works(self):
        data = _get("/api/works")
        self.assertIn("works", data)
        # After fuzzy dedup: 3044 (was 4158 before fuzzy)
        self.assertGreaterEqual(len(data["works"]), 1500)
        self.assertLessEqual(len(data["works"]), 4500)
        for w in data["works"][:5]:
            for k in ("id", "title", "volume_id", "n_refs"):
                self.assertIn(k, w, f"work missing {k!r}")

    def test_api_work_plato(self):
        # Plato (work id 77 in our build) must have 2000+ pages
        data = _get("/api/work/77")
        self.assertEqual(data["work"]["title"], "Plato")
        self.assertGreater(len(data["pages"]), 2000)

    def test_api_idea_detail(self):
        data = _get("/api/idea/1")
        self.assertEqual(data["idea"]["number"], 1)
        self.assertIn("topics", data)

    def test_api_search(self):
        # Search for "Republic" — should match citations
        data = _get("/api/search?q=Republic&limit=5")
        self.assertIn("hits", data)
        self.assertGreater(len(data["hits"]), 0)

    def test_static_assets(self):
        for path in ("/index.html", "/css/style.css", "/js/works.js",
                     "/obras/index.html", "/obras/obra.html",
                     "/autores/index.html", "/ideias/index.html"):
            status = _get_status(path)
            self.assertEqual(status, 200, f"{path} -> {status}")

    def test_obras_dynamic(self):
        # /obras/<id>/obra.html must serve the template
        status = _get_status("/obras/77/obra.html")
        self.assertEqual(status, 200, f"/obras/77/obra.html -> {status}")


class ApiContentTests(unittest.TestCase):
    """Spot-check the content returned by the API."""

    def test_works_fuzzy_dedup(self):
        # After fuzzy dedup, no two works in the same volume should
        # have titles that are very similar.
        data = _get("/api/works")
        from difflib import SequenceMatcher
        by_vol: dict[int, list[str]] = {}
        for w in data["works"]:
            by_vol.setdefault(w["volume_id"], []).append(w["title"])
        duplicates = []
        for vol, titles in by_vol.items():
            for i, t1 in enumerate(titles):
                for t2 in titles[i + 1 :]:
                    r = SequenceMatcher(None, t1.lower(), t2.lower()).ratio()
                    if r >= 0.85:
                        duplicates.append((vol, t1, t2, round(r, 3)))
        # Allow a small tolerance for edge cases
        self.assertLessEqual(len(duplicates), 5,
                              f"{len(duplicates)} near-duplicates: {duplicates[:3]}")

    def test_page_text_returned_for_known_works(self):
        # Works for which we have extracted text must return non-empty
        # pages. Plato (77), Aristotle (1000), Adam Smith (338) are
        # all well-known and should have full text.
        for wid in (77, 1000, 338):
            data = _get(f"/api/work/{wid}")
            self.assertGreater(len(data["pages"]), 100,
                                f"work {wid} has only {len(data['pages'])} pages")
            sample = data["pages"][0]
            self.assertGreater(len(sample["text"]), 100,
                                f"work {wid} page 0 too short: {len(sample['text'])}")


if __name__ == "__main__":
    unittest.main(verbosity=2, exit=False)
