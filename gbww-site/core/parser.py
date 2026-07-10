"""
Syntopicon parser (v2).

Three structural fixes vs. parser.py v1:

  1. CROSS-REFERENCES are NOT concatenated to the citation body. We stop
     reading as soon as we hit the line "THE GREAT IDEAS CROSS-REFERENCES"
     (or just "CROSS-REFERENCES") or another topic header.

  2. Page ranges are SPLIT into chunks. The Syntopicon reference for, e.g.,
     Plato's Republic uses notation like "bk v 451c-453b; 457a- / bk vi
     504b- / bk vii 514a-516a". Each `/`-separated work is one chunk; each
     `;`-separated page range within a chunk is one row.

  3. work_title is NORMALIZED to the parent work name. We strip every
     comma-separated sub-specification ("bk v", "part i, q 22, a 3",
     "ch 2-5", etc.) so that all references to "Summa Theologica" collapse
     into a single `works` row, which is what the site lists.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from .models import Citation, Idea, IdeaBody, IntroSection, ParsedSyntopicon, Topic

# ---------------------------------------------------------------------------
# Regexes (carried over from v1 with minor tightening)
# ---------------------------------------------------------------------------

# Chapter header regex. Syntopicon headings look like:
#   "Chapter 1: ANGEL"
#   "Chapter 14: CUSTOM AND CONVENTION"
#   "Chapteri: ANGEL"            (OCR dropped the space)
#   "Chapter\n1\n: ANGEL"        (OCR inserted line breaks)
# The name may span multiple capitalised words joined by "AND" / "&" /
# hyphens, e.g. "LIFE AND DEATH", "ONE AND MANY". The name ends at a
# structural break: a newline, "INTRODUCTION", "OUTLINE", "CROSS-REFERENCES",
# "REFERENCES", "For:", a [page-marker] or a digit-only token. Short names
# (3 chars like "ART", "LAW", "MAN", "SIN") must be allowed — minimum
# 2 chars after the initial letter.
CHAPTER_RE = re.compile(
    r"Chapter\s*([ivxlcdmIVXLCDM0-9S]{1,5})\s*[.:]\s*"
    r"([A-Z][A-Z0-9 \-&/()\.]{2,}?)"
    r"(?=\s*\n|\s+(?:INTRODUCTION|OUTLINE|CROSS|REFERENCES|For\s)|\s*\[|\s+\d+\b|$)",
    re.IGNORECASE,
)

# Some chapter headers are split across two lines in the PDF extract:
#   "Chapter 41"        (line N)
#   ": JUDGMENT"        (line N+1)
# We pre-join these in find_chapter_starts so the canonical CHAPTER_RE
# captures the full number+name.
_CHAPTER_HEADER_SPLIT_RE = re.compile(
    r"^\s*Chapter\s*([ivxlcdmIVXLCDM0-9S]{1,5})\s*$"
)

# OCR glitches that survive the ALL-CAPS preference. Mapped to the canonical
# Syntopicon chapter name.
_CHAPTER_OCR_FIXES = {
    "CiOD": "GOD",
    "IMMORTALIl Y": "IMMORTALITY",
}

# OCR variants in the chapter NUMBER. The Syntopicon also has individual
# digit errors in the printed edition (the '5' in "Chapter 35" was OCR'd
# as 'S' on page 793 of vol 2). We map (raw_num_str, raw_name) -> canonical
# (num, name) when the header is the only occurrence in the chapter range.
_CHAPTER_NUM_OCR_FIXES = {
    # "Chapter 3S: HONOR" — the '5' digit was misread as 'S'.
    ("3S", "HONOR"): (35, "HONOR"),
}
OUTLINE_HEADER_RE = re.compile(r"^\s*OUTLINE\s+OF\s+TOPICS\s*$", re.IGNORECASE)
# Topic header line. Syntopicon outline entries look like:
#   "1. The concept of element"
#   "2. Being and the one and the many"
#   "2a. Infinite being and the plurality of finite beings"
#   "2a, The celestial motors or secondary prime movers"  (OCR: ',' instead of '.')
#   "3a. The hierarchy of being: grades of reality"
#   "5J. The origin of the division"                     (OCR: 'J' instead of 'a')
#   "3^. The angelic nature"                             (OCR: '^' instead of 'b')
#   "^5"  (then "The society of the demons")             (OCR: caret is a 5b-style artefact)
#   "ya. Warfare between..."                             (OCR: 'y' instead of '7')
#   "53. The society of the demons"                      (OCR: digits stuck together)
#   "3/. Angelic action"                                (OCR: '/' instead of 'g')
#
# The number may be 1-3 digits, the letter is one of [a-zA-Z^/] (or
# absent), the separator is "." or ",", and there may be a space
# between the number and the letter. The title is everything after, up
# to end of line.
TOPIC_RE = re.compile(
    r"^\s*(\d{1,3})\s*([a-zA-Z^/]?)\s*[.,]\s+([A-Z][^\n]{3,})$"
)
CITATION_RE = re.compile(
    r"^\s*([0-9]{1,3})\s+([A-Z][A-Za-z'\- ]{1,40}?)\s*[:.]\s*(.+?)\s*$"
)

# GBWW page ref: "256a", "114b", "12b-d", "100b-107a"
PAGE_REF_RE = re.compile(
    r"\b([0-9]{1,4}[a-d])(?:\s*[-—–]\s*([0-9]{1,4}[a-d]))?\b"
)
# Author GBWW number prefix on a citation line
AUTHOR_NUM_PREFIX = re.compile(r"^\s*(\d{1,3})\s+([A-Z][A-Za-z'\.\- ]{1,40}?)\s*[:.]\s*")

# Cross-reference stop: the line immediately after the references list starts.
# Either "THE GREAT IDEAS CROSS-REFERENCES" or bare "CROSS-REFERENCES" or
# any line that begins with "FOR:" (OCR often drops the headline).
CROSSREF_TRIGGERS = (
    re.compile(r"\bCROSS[- ]REFERENCES?\b", re.IGNORECASE),
    re.compile(r"^\s*For\s*[:.]", re.IGNORECASE),
    re.compile(r"^\s*For\s+another\b", re.IGNORECASE),
)

# Sub-specifications that follow a work title and should be stripped when
# normalizing. e.g. "Summa Theologica, part i, q 22, a 3" -> "Summa Theologica"
SUBSPEC_PREFIXES = re.compile(
    r",\s*\b("
    r"bk|book|part|parts|chapter|ch|sect|section|q|qq|a|aa|ans|rep|"
    r"vol|volume|pp|pages?|no|n|tome|tr|trans|"
    r"en|sec|esp|prop|defs?|bk\s+i+|bk\s+[ivxlcdm]+|"
    r"bk\s*iv|bk\s*v|bk\s*vi"
    r")\b",
    re.IGNORECASE,
)

# Real-work-title filter: drop fragments that are too short or look
# like raw page/step references. A canonical work title must contain
# at least one letter and not begin with a bare Roman subscript then
# either a digit or a page-marker that the OCR glue produced. We
# accept titles like "Iliad" or "Iliad, bk viii" because the "Iliad"
# word is long and meaningful; we reject "I", "I [1234a]", "II, 2",
# etc. because they are essentially page / step fragments.
_BARE_FRAGMENT_RE = re.compile(r"^[IVXivx]+\s*[\[\d]")
_TRUNCATED_TITLE_RE = re.compile(r"^[IVXivx]+\s+\S{0,4}$")
# A title that's just a Roman numeral ("II", "VIII") is not a real
# work — it's the result of OCR clipping a reference like "II, en 2".
_TITLE_IS_PURE_ROMAN_RE = re.compile(r"^[IVXivx]+$")

# Bekker/Stephanus inline page numbers: e.g. "[1234a]", "[992a29~b9]"
# When these are the entire work-title, we keep them as-is (they ARE the
# canonical reference for Aristotle/Plato and the user wants to navigate
# to them).
INLINE_PAGE_RE = re.compile(r"^\s*\[[^\]]+\]\s*$")

# Continuation-only fragments: when a line in the Syntopicon starts with one
# of these, it's a sub-reference (q, a, ch...) of the SAME work that came
# on the previous citation line.
CONTINUATION_FRAGMENT = re.compile(
    r"^\s*(q\s|qq\s|a\s|aa\s|ans|rep|ch|chapter|bk\s|book\s|"
    r"part\s|section\s|sect\s|vol\s|volume\s|tome\s|tr\s|\d+\s*\.)",
    re.IGNORECASE,
)


def _clean_idea_name(raw: str) -> str:
    name = raw.strip()
    name = re.sub(r"\s+", " ", name)
    # Specific OCR fixes that survive the ALL-CAPS preference in
    # find_chapter_starts (so we have to handle them here).
    if name in _CHAPTER_OCR_FIXES:
        name = _CHAPTER_OCR_FIXES[name]
    name = name.replace("EVII.", "EVIL").replace("EVII", "EVIL")
    name = re.sub(r"I+\s*I+\s*ONOK", "HONOR", name)
    name = re.sub(r"\bII+\b", "HONOR", name)
    name = name.replace("TREASURE  AND  PAIN", "PLEASURE AND PAIN")
    name = name.replace("TREASURE AND PAIN", "PLEASURE AND PAIN")
    name = name.rstrip(".,;:")
    return name.strip()


def _clean_topic_label(num: str, letter: str | None) -> str:
    """Normalise a (num, letter) topic label.

    Common OCR confusions in the Syntopicon (Vol 2 page 67):
      - '3J'  -> '3a'  (J looks like a)
      - 'ya'  -> '7a'  (y looks like 7)
      - '3r'  -> '3c'  (r is misread from c)
      - '53'  -> '5c'  (3 looks like c)

    Position-dependent caret mapping ('^' = various sub-letters in cap 1)
    is handled by the chapter-specific repair pass in
    _extract_topics_for_chapter — see _CARET_REPAIR below.
    """
    n = num.strip().rstrip(".")
    if not letter:
        label = n
    else:
        label = f"{n}{letter.lower()}"
    return _TOPIC_LABEL_FIXES.get(label, label)


# Mapping for topics where the OCR misread the NUMBER or LETTER.
# Keys are the parsed label, values are the canonical label.
_TOPIC_LABEL_FIXES = {
    "ya": "7a",
    "yb": "7b",
    "yc": "7c",
    "yd": "7d",
    "5j": "5a",
    "3j": "3a",
    "3i": "3d",  # PDF has "3i" as 3d in cap 41
    "3r": "3c",  # PDF cap 1 has "3r" as 3c
    "53": "5c",  # PDF cap 1 has "53" as 5c
    "^5": "5b",  # PDF cap 1 has "^5" as 5b
    # The cap 1 outline uses caret '^' for various sub-letters, but
    # some inline topic headers in the references use 'e' instead.
    # Both should map to the same canonical sequence. We collapse all
    # caret/e variants under the canonical sub-letter 3b (first
    # occurrence) and let the outline+citations settle there.
    "3^": "3b",
}

# Position-dependent caret sub-letters used in cap 1 of the Syntopicon.
# The Syntopicon outline uses '^' (caret) as a placeholder for various
# sub-letters that the OCR misread. The order in the cap 1 outline is:
#   1st caret  -> "b"  ("The angelic nature")
#   2nd caret  -> "d"  ("The angelic intellect and angelic knowledge")
#   3rd caret  -> "e"  ("The angelic will and angelic love")
# We apply this repair inside the chapter extraction rather than here.
_CARET_REPAIR = {
    "1": ["b", "d", "e"],
}

# Populated by parse_volume for each chapter. Maps idea_number -> the
# list of canonical topic labels in outline order, so the citation
# extractor can map the i-th topic header in REFERENCES to the same
# canonical label (since both outline and references list topics in
# the same sequence).
_OUTLINE_LABELS_PER_CHAPTER: dict[int, list[str]] = {}


def _parent_of(label: str) -> str | None:
    m = re.match(r"^([0-9]+)[a-z]?$", label)
    if not m:
        return None
    base = m.group(1)
    if label == base:
        return None
    return base


def _roman_to_int(s: str) -> int | None:
    s = s.strip().lower()
    if not s or not all(c in "ivxlcdm" for c in s):
        return None
    vals = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    total, prev = 0, 0
    for c in reversed(s):
        v = vals[c]
        if v < prev:
            total -= v
        else:
            total += v
        prev = v
    return total if total > 0 else None


def _volume_id_from_path(path: Path) -> int:
    parts = path.stem.split()
    for i, tok in enumerate(parts):
        if tok.lower() == "volume" and i + 1 < len(parts):
            try:
                return int(parts[i + 1])
            except ValueError:
                continue
    raise ValueError(f"could not extract volume number from {path}")


# ---------------------------------------------------------------------------
# Reference chunking + work-title normalization
# ---------------------------------------------------------------------------

def normalize_work_title(raw: str) -> str:
    """Return the canonical (parent) work title.

    Examples:
      "Summa Theologica, part i, q 22, a 3, ans 130d-131c" -> "Summa Theologica"
      "Republic, bk v"  -> "Republic"
      "Iliad, bk viii"  -> "Iliad"
      "On Interpretation, ch 1"  -> "On Interpretation"
    """
    if not raw:
        return raw
    s = raw.strip()
    # Strip leading punctuation/OCR garbage (quotes, brackets, asterisks)
    s = re.sub(r"^[^A-Za-z]+", "", s).strip()
    # Cut at the first ", bk " / ", part " / ", ch " / etc.
    m = SUBSPEC_PREFIXES.search(s)
    if m:
        s = s[: m.start()].strip().rstrip(",")
    # Cut at the first page ref
    pm = PAGE_REF_RE.search(s)
    if pm:
        s = s[: pm.start()].strip().rstrip(",")
    s = re.sub(r"\s+", " ", s).strip().rstrip(",.;:")
    # OCR noise: fragments that begin with a Roman subscript then
    # either a digit or a page-marker are STEP / PROPOSITION numbers,
    # not real work titles. We accept titles like "Iliad" because
    # "Iliad" is a long, meaningful word; we reject "I", "I [1234a]",
    # "II 5" etc. because those are essentially page fragments.
    if s and _BARE_FRAGMENT_RE.match(s):
        return ""
    if s and _TRUNCATED_TITLE_RE.match(s):
        # "I v", "IV 7", "II 2" — Roman then short token (often a
        # chapter number).
        return ""
    if s and _TITLE_IS_PURE_ROMAN_RE.match(s):
        # "II", "VIII" — OCR clipping the leading "II, en 2" etc.
        return ""
    if not s or len(s) < 2:
        return ""
    return s


def split_reference_to_chunks(rest: str) -> list[tuple[str, str | None, str | None]]:
    """Split a Syntopicon reference body into [(work_title, page_start, page_end), ...].

    The Syntopicon uses two separators:
      - "/"   separates *different works* within one reference line
      - ";"   separates *different page ranges* within the same work

    Each chunk is a single (work, page_start, page_end) tuple. page_start
    and page_end may be None if the chunk has no page reference (rare).
    """
    # Normalize em-dash / en-dash
    rest = rest.replace("\u2014", "-").replace("\u2013", "-")
    # Drop trailing "passim" / "esp" qualifiers (they apply to the whole
    # sub-reference and are noise at chunk granularity)
    rest = re.sub(r"\bpassim\b", "", rest, flags=re.IGNORECASE)
    rest = re.sub(r"\besp\b", "", rest, flags=re.IGNORECASE)

    # Split into work-segments
    work_segments = [seg.strip().rstrip(",;.") for seg in rest.split("/")]
    chunks: list[tuple[str, str | None, str | None]] = []
    for seg in work_segments:
        if not seg:
            continue
        # Within a work-segment, the last page-ref or range belongs to the
        # trailing text; any prior "; " boundaries separate sub-ranges that
        # still belong to the same work (e.g. "204b-c; 328a-b").
        # We detect page refs and split on ';' *before* the first page-ref.
        # Find the position of the first PAGE_REF.
        first_pm = PAGE_REF_RE.search(seg)
        if not first_pm:
            # No page ref at all — if this segment looks like just a page
            # specifier (rare), skip; otherwise it's a single chunk.
            chunks.append((seg, None, None))
            continue
        head = seg[: first_pm.start()].strip()
        body = seg[first_pm.start():]
        # If the head is empty, this is a continuation page-range from the
        # previous segment (e.g. "bk v 451c-453b / 457a-"). Mark with a
        # sentinel so the caller knows to inherit the previous work title.
        if not head:
            head = "__CONTINUATION__"
        # Now split body by ';'
        sub_chunks = [s.strip().rstrip(",;.") for s in body.split(";")]
        for i, sub in enumerate(sub_chunks):
            if not sub:
                continue
            pm = PAGE_REF_RE.search(sub)
            if not pm:
                chunks.append((head, None, None))
                continue
            start_pg = pm.group(1)
            end_pg = pm.group(2) or start_pg
            chunks.append((head, start_pg, end_pg))
    return chunks


# ---------------------------------------------------------------------------
# Citation extraction (rewritten: stops at cross-references, splits chunks)
# ---------------------------------------------------------------------------

def _extract_citations_for_chapter(
    chapter_idea_number: int,
    lines: list[str],
    chapter_start: int,
    next_chapter_start: int | None,
    outline_labels: list[str] | None = None,
) -> list[Citation]:
    end = next_chapter_start or len(lines) + 1
    chunk = _de_ocr_fuse_headers(lines[chapter_start - 1 : end - 1])

    citations: list[Citation] = []
    current_topic: str | None = None
    last_author: tuple[int, str] | None = None
    last_work_raw: str | None = None
    last_work_norm: str | None = None
    crossref_started = False
    in_outline = False
    in_references = False
    sub_counters: dict[int, int] = {}
    if outline_labels is None:
        outline_labels = _OUTLINE_LABELS_PER_CHAPTER.get(chapter_idea_number, [])
    inline_ordinal = 0

    def _is_crossref(line: str) -> bool:
        return any(p.search(line) for p in CROSSREF_TRIGGERS)

    for line in chunk:
        stripped = line.strip()
        if not stripped:
            continue
        # Once we hit a cross-reference header, stop reading this chapter.
        if _is_crossref(stripped):
            break
        if not in_outline:
            if _OUTLINE_HEADER_LINE_RE.search(stripped):
                in_outline = True
            continue
        if not in_references and _REFERENCES_HEADER_RE.search(stripped):
            in_references = True
            # Reset inline counter for the references section
            inline_ordinal = 0
            continue
        # Topic bump.
        m_topic = TOPIC_RE.match(line)
        if m_topic:
            try:
                parent = int(m_topic.group(1))
            except ValueError:
                parent = None
            if parent is not None:
                title = m_topic.group(3).strip()
                if _looks_like_topic_title(title):
                    if in_references and outline_labels:
                        # Use the i-th outline label (same order in the
                        # references section).
                        if inline_ordinal < len(outline_labels):
                            current_topic = outline_labels[inline_ordinal]
                        else:
                            # No more outline labels — skip.
                            current_topic = None
                        inline_ordinal += 1
                    else:
                        # In the outline: structural counter.
                        idx = sub_counters.get(parent, 0)
                        if idx == 0:
                            current_topic = str(parent)
                        else:
                            sub_letter = chr(ord('a') + idx - 1)
                            current_topic = f"{parent}{sub_letter}"
                        sub_counters[parent] = idx + 1
                    if current_topic is not None:
                        last_author = None
                        last_work_raw = None
                        last_work_norm = None
                    continue
        # Citation line
        m_cite = CITATION_RE.match(line)
        if m_cite and current_topic:
            author_num = int(m_cite.group(1))
            author_name = m_cite.group(2).strip().rstrip(".'`\"")
            rest = m_cite.group(3).strip()
            # Stop if this line *is* the cross-reference header
            if _is_crossref(rest):
                break
            sub_chunks = split_reference_to_chunks(rest)
            prev_work_raw: str | None = None
            for work_title_raw, p_start, p_end in sub_chunks:
                if work_title_raw == "__CONTINUATION__":
                    if prev_work_raw is None:
                        continue
                    work_title_raw = prev_work_raw
                else:
                    prev_work_raw = work_title_raw
                work_norm = normalize_work_title(work_title_raw)
                if not work_norm:
                    work_norm = author_name
                last_work_raw = work_title_raw
                last_work_norm = work_norm
                citations.append(
                    Citation(
                        idea_number=chapter_idea_number,
                        topic_label=current_topic,
                        author_number=author_num,
                        author_name=author_name,
                        work_title=work_norm,
                        work_title_raw=work_title_raw,
                        citation_text=stripped,
                        page_start=p_start,
                        page_end=p_end,
                    )
                )
            last_author = (author_num, author_name)
            continue

        # Continuation lines only if we're inside a citation AND the line
        # doesn't look like a topic or cross-ref.
        if last_author and current_topic and stripped:
            # The continuation lines below a citation are usually page-number
            # garbage or section headings. Don't append them to citation_text;
            # only keep them if they introduce a new (work, pages) chunk with
            # no author prefix. We approximate by checking for PAGE_REF_RE.
            if PAGE_REF_RE.search(stripped) and not AUTHOR_NUM_PREFIX.match(stripped):
                # If the line starts with a continuation fragment (q X, a Y,
                # bk Z, etc.) and we have a previous work, inherit it.
                inherit = CONTINUATION_FRAGMENT.match(stripped) is not None
                rest = stripped
                sub_chunks = split_reference_to_chunks(rest)
                prev_work_raw = None
                for work_title_raw, p_start, p_end in sub_chunks:
                    if inherit and work_title_raw != "__CONTINUATION__":
                        if prev_work_raw is None and last_work_raw:
                            prev_work_raw = work_title_raw
                            work_title_raw = last_work_raw
                        elif prev_work_raw and last_work_norm and not work_title_raw.startswith(last_work_norm):
                            # Same author, different work — but if the line
                            # still looks like a sub-spec, keep inheriting.
                            work_title_raw = last_work_raw
                    if work_title_raw == "__CONTINUATION__":
                        if prev_work_raw is None:
                            continue
                        work_title_raw = prev_work_raw
                    else:
                        prev_work_raw = work_title_raw
                    work_norm = normalize_work_title(work_title_raw)
                    if not work_norm:
                        work_norm = last_work_norm or last_author[1]
                    last_work_raw = work_title_raw
                    last_work_norm = work_norm
                    citations.append(
                        Citation(
                            idea_number=chapter_idea_number,
                            topic_label=current_topic,
                            author_number=last_author[0],
                            author_name=last_author[1],
                            work_title=work_norm,
                            work_title_raw=work_title_raw,
                            citation_text=stripped,
                            page_start=p_start,
                            page_end=p_end,
                        )
                    )

    return citations


def _extract_topics_for_chapter(
    lines: list[str], chapter_start: int, next_chapter_start: int | None
) -> list[Topic]:
    """Walk lines from chapter_start, collecting topic headers.

    Syntopicon layout (printed edition):
      [prose introduction]
      ...
      OUTLINE OF TOPICS
      1. Topic one
      2. Topic two
      ...
      REFERENCES
      [citation list]
      [optional CROSS-REFERENCES]

    Topics only appear between OUTLINE OF TOPICS and REFERENCES. We track
    that range explicitly so that citation-header lines (e.g.
    "17 Plotinus: ...") further down — which also match the topic regex
    shape — are not misclassified.

    Topic labels are assigned structurally: for each parent number N seen
    in the outline, the FIRST occurrence is "N", the second is "Na", the
    third is "Nb", etc. The OCR'd letter on the line is ignored (it is
    usually wrong in the printed edition of the Syntopicon — "5J" for
    "5a", "ya" for "7a", "3^" for "3a", "53" for "5c"). The position in
    the outline is the only thing that determines the label.
    """
    end = next_chapter_start or len(lines) + 1
    chunk = _de_ocr_fuse_headers(lines[chapter_start - 1 : end - 1])
    topics: dict[str, str] = {}
    state = "pre_outline"  # -> "in_outline" -> "post_outline" (done)
    # Outline topics are assigned by **ordinal position** in the
    # outline, not by parent number. The first topic is "1", the second
    # is "2", the third is "2a", the fourth "2b", etc. (the parent
    # number on each line is unreliable OCR — "5J" for "5a", "ya" for
    # "7a", "53" for "5c" are all common). We trust the *order* in which
    # topic headers appear, and we trust the FIRST topic of each parent
    # to carry the parent number correctly (because the outline starts
    # with parent 1 and the parent numbers increase).
    #
    # We track the *expected* parent based on the previous topics we've
    # seen: e.g. after "1", the next parent is 2; after "2, 2a, 2b", the
    # next parent is 3; etc.
    expected_parent = 1
    seen_in_parent = 0  # how many topics we've seen for the current parent
    for line in chunk:
        stripped = line.strip()
        if not stripped:
            continue
        # State transitions
        if state == "pre_outline":
            if _OUTLINE_HEADER_LINE_RE.search(stripped):
                state = "in_outline"
            continue
        if state == "in_outline":
            if re.match(r"^\s*REFERENCES\s*$", stripped, re.IGNORECASE):
                # References section begins — stop collecting topics.
                state = "post_outline"
                break
            if re.match(r"^\s*(?:THE\s+GREAT\s+IDEAS\s+)?CROSS[- ]REFERENCES?\s*$",
                        stripped, re.IGNORECASE):
                state = "post_outline"
                break
            m = TOPIC_RE.match(line)
            if not m:
                continue
            try:
                parsed_num = int(m.group(1))
            except ValueError:
                continue
            # Decide parent and sub-position:
            #   - If parsed_num == expected_parent, this is the next
            #     topic of the same parent.
            #   - If parsed_num > expected_parent, the parent has
            #     advanced; treat this as the start of parent N.
            #   - If parsed_num < expected_parent, it's a stray OCR
            #     duplicate; skip.
            #   - Special case: parsed_num may be OCR-corrupted (e.g. 53
            #     instead of 5c); if it's > expected_parent+1, the
            #     original number is likely a corrupted parent number.
            #     We treat parsed_num as if it were the expected parent.
            if parsed_num < expected_parent:
                # Skip — duplicate of an already-seen topic
                continue
            if parsed_num > expected_parent + 1:
                # Likely a corrupted number; assume same parent
                parent = expected_parent
            else:
                parent = parsed_num
            if parent != expected_parent:
                expected_parent = parent
                seen_in_parent = 0
            # Assign label
            if seen_in_parent == 0:
                label = str(parent)
            else:
                sub_letter = chr(ord('a') + seen_in_parent - 1)
                label = f"{parent}{sub_letter}"
            seen_in_parent += 1
            title = m.group(3).strip()
            if label not in topics:
                topics[label] = title
        # post_outline: nothing more to do for topics
    return [
        Topic(
            idea_number=0,
            label=label,
            title=title,
            parent_label=_parent_of(label),
        )
        for label, title in topics.items()
    ]


def _looks_like_topic_title(title: str) -> bool:
    """Heuristic used by _extract_citations_for_chapter to decide whether
    a line that matches TOPIC_RE shape is really a topic or a citation
    header.

    Tópicos reais:
      - 3+ words
      - pelo menos uma palavra com inicial minúscula (artigo, preposição)
      - raramente contêm ":" (e quando contêm, é no singular)
      - nunca contêm page markers (123a, 456b-c)

    Citation headers (que devem ser rejeitados):
      - "17 Plotinus: Second Ennead, tr ix, ch 9 70d-72a" — tem ":" e page
      - "12 Lucretius: Nature of Things, bk" — tem ":" e formato Author: Work
      - "13 Virgil: Aeneid 103a-379a" — tem ":" e page

    Heurística final: rejeitar se tem ":" (citações sempre têm) OU se tem
    page marker.
    """
    if not title:
        return False
    if ":" in title:
        return False
    words = title.split()
    if len(words) < 3:
        return False
    if not any(w[0].islower() for w in words if len(w) > 2):
        return False
    if re.search(r"\b\d+[a-d](?:[-–—]\d+[a-d])?\b", title):
        return False
    return True


def find_chapter_starts(lines: list[str], volume_id: int = 0) -> list[tuple[int, int, str]]:
    candidates: dict[int, list[tuple[int, str]]] = {}
    # Pre-pass: join chapter headers split across two lines.
    # "Chapter 41" on line N, ": JUDGMENT" on line N+1 -> "Chapter 41: JUDGMENT".
    # We do this in-place to keep the rest of the code simple.
    joined: list[str] = []
    skip_next = False
    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
        if _CHAPTER_HEADER_SPLIT_RE.match(line) and i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if nxt.startswith(":") or nxt.startswith("."):
                joined.append(f"{line.rstrip()} {nxt}")
                skip_next = True
                continue
        joined.append(line)
    lines = joined
    for idx, line in enumerate(lines, start=1):
        m = CHAPTER_RE.search(line)
        if not m:
            continue
        raw = m.group(1)
        name = _clean_idea_name(m.group(2))
        # Per-line OCR fix on (raw_num, name) — e.g. "Chapter 3S: HONOR" → 35
        if (raw, name) in _CHAPTER_NUM_OCR_FIXES:
            num, name = _CHAPTER_NUM_OCR_FIXES[(raw, name)]
        elif raw.isdigit():
            num = int(raw)
        else:
            num = _roman_to_int(raw)
        if num is None:
            continue
        if not (1 <= num <= 102):
            continue
        if volume_id == 2 and num > 50:
            continue
        if volume_id == 3 and num < 51:
            continue
        candidates.setdefault(num, []).append((idx, name))

    chosen: dict[int, tuple[int, str]] = {}
    for num, occs in candidates.items():
        all_caps = [(i, n) for i, n in occs if n.upper() == n]
        if all_caps:
            chosen[num] = min(all_caps, key=lambda x: x[0])
        else:
            chosen[num] = min(occs, key=lambda x: x[0])
    return [(idx, num, name) for num, (idx, name) in sorted(chosen.items())]


# Pre-chapter section headers that mark the start of a distinct
# introductory section in the Syntopicon vol 2 front-matter (between
# CONTENTS and Chapter 1: ANGEL). These sections are surfaced as
# IntroSection rows in `ParsedSyntopicon.introductions` and rendered
# on the "Introdução" tab of the front-end.
_PRE_CHAPTER_HEADERS = (
    "PREFACE",
    "EXPLANATION OF REFERENCE STYLE",
    "SUGGESTIONS FOR USING THE SYNTOPICON",
    "THE GREAT IDEAS TODAY",
)


def _extract_front_matter(lines: list[str]) -> list[IntroSection]:
    """Walk the front-matter of vol 2 (lines 0..first Chapter header)
    and return IntroSection rows for each major section. The Syntopicon
    front-matter contains:

      PREFACE (L425)
      EXPLANATION OF REFERENCE STYLE (L1599)
      [optionally SUGGESTIONS FOR USING THE SYNTOPICON]
      [optionally THE GREAT IDEAS TODAY]

    All of these blocks have an all-caps header line followed by
    discursive text. The word "PREFACE" is reused at the top of every
    page in the vol 2 front-matter (it is a running head), so we look
    for *the first occurrence* of each section header and verify that
    the following text is the actual body, not a page header.

    The Syntopicon places the body of the Preface on different pages,
    separated by page-number artefacts and running headers; we treat
    everything between the first PREFACE header line and the first
    EXPLANATION OF REFERENCE STYLE header line as the Preface.
    """
    sections: list[IntroSection] = []

    def _slug(title: str) -> str:
        sl = title.lower().replace(" ", "-")
        for ch in ",.;:'\"?!()[]{}":
            sl = sl.replace(ch, "")
        return sl

    def _looks_like_chapter_header(line: str) -> bool:
        line = line.strip()
        return bool(re.match(r"^Chapter\s*\d", line)) or bool(re.match(r"^Chapteri?\s*[:\d]", line))

    def _is_textual_run(start_line: str) -> bool:
        """Return True if the line starting at `start_line` looks like
        body prose rather than a page-running-header artefact. The vol
        2 front-matter has running-head lines like "xii", "xiii", "THE
        GREAT IDEAS" between body paragraphs at every page boundary.
        A block following an all-caps section header is body text if
        it continues for several substantive lines.
        """
        return any(c.isalpha() and c.islower() for c in start_line) and len(start_line) >= 30

    # Locate *the first occurrence after the table of contents* of each
    # pre-chapter header. The TOC mentions these words but in title-
    # case, so we keep them as candidate and pick the first one whose
    # immediate next non-empty line is a body run.
    header_first_pos: list[tuple[int, str]] = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        for h in _PRE_CHAPTER_HEADERS:
            # Match the canonical header line OR a header plus a Roman
            # page number on the same line (e.g. "PREFACE xii").
            if stripped == h or (
                stripped.upper().startswith(h)
                and len(stripped) <= len(h) + 8
                and len(stripped) >= len(h)
            ):
                # Verify the next non-empty line(s) are body text.
                j = idx + 1
                lookahead = 0
                while j < len(lines) and lookahead < 5:
                    nxt = lines[j].strip()
                    if nxt and _is_textual_run(nxt):
                        header_first_pos.append((idx, h))
                        break
                    j += 1
                    lookahead += 1
                break
    # De-dup: keep only the first occurrence per header.
    seen = set()
    header_first_pos = [
        (p, h) for p, h in header_first_pos if h not in seen and not seen.add(h)
    ]

    for i, (start, header) in enumerate(header_first_pos):
        end = (
            header_first_pos[i + 1][0] if i + 1 < len(header_first_pos)
            else next(
                (j for j, ln in enumerate(lines[start:], start=start)
                 if _looks_like_chapter_header(ln)),
                len(lines),
            )
        )
        body_lines = list(lines[start:end])
        # Drop the header line itself from the body.
        body_lines = [
            ln for ln in body_lines
            if ln.strip() != header
            and not (
                ln.strip().upper().startswith(header)
                and len(ln.strip()) <= len(header) + 8
            )
        ]
        # Strip leading page-number artefacts.
        while body_lines and (
            body_lines[0].strip() in {"", "[PAGE 1]", "[PAGE 2]", "[PAGE 3]"}
            or (len(body_lines[0].strip()) <= 4 and body_lines[0].strip().isalnum())
        ):
            body_lines.pop(0)
        body_text = _join_paragraphs(_iter_page_text(body_lines)).strip()
        if not body_text:
            continue
        sections.append(
            IntroSection(
                key=_slug(header),
                title=header.title(),
                body=body_text,
            )
        )
    return sections


def _iter_page_text(lines: list[str]) -> "list[str]":
    """Filter the `[PAGE N]` markers and pure-number artefacts left
    behind by pymupdf so the body text reads as clean prose.
    """
    out: list[str] = []
    for ln in lines:
        s = ln.strip()
        if not s:
            out.append("")
            continue
        if s.startswith("[PAGE "):
            continue
        # Drop standalone page-number lines (1-4 chars, alphanumeric).
        if len(s) <= 4 and s.isalnum():
            continue
        # Drop repeated punctuation artefacts.
        if s in {"...", "....", ".", ",", ";", ":"}:
            continue
        out.append(ln)
    return out


def _join_paragraphs(raw_lines) -> str:
    """Group consecutive non-empty lines into single paragraphs
    separated by blank lines. The Syntopicon PDF emits one source line
    per visual line so paragraph boundaries are represented by a
    blank line; we honour that convention here.
    """
    paragraphs: list[str] = []
    buf: list[str] = []
    for ln in raw_lines:
        s = ln.strip()
        if not s:
            if buf:
                paragraphs.append(" ".join(buf))
                buf = []
        else:
            buf.append(ln.rstrip())
    if buf:
        paragraphs.append(" ".join(buf))
    return "\n\n".join(p for p in paragraphs if p)


def _collapse_page_artifacts(text: str) -> list[str]:
    """Break a body into paragraphs and drop artefacts that span across
    paragraphs in the source (e.g. "12", "Bible" floating on their
    own lines mid-sentence). Heavy OCR garble artefacts are left in
    place — cleaning them is out of scope here.
    """
    return [p for p in text.split("\n\n") if p.strip()]


def _next_chapter_is_different_than_current(line: str, current_chapter_num: int) -> bool:
    """Some PDFs duplicate the chapter-header line in the body of
    the chapter (a left-over running-head artefact); we must not let
    such a duplicate prematurely terminate the chapter, so we only
    treat the line as the next chapter header if its number does not
    match the chapter currently being extracted.
    """
    m = re.match(r"^Chapter\s*(\d+)\s*:?", line)
    if m is None:
        return False
    n = int(m.group(1))
    return n != current_chapter_num


# Match the chapter section headers OUTLINE OF TOPICS and REFERENCES.
# OCR sometimes embeds the header inside a sentence without a
# leading space ("is one everOUTLINE OF TOPICS"). We accept any
# non-letter boundary (whitespace, end-of-line, or punctuation)
# before the keyword.
_OUTLINE_HEADER_LINE_RE = re.compile(
    r"(?<![A-Za-z])OUTLINE\s+OF\s+TOPICS\b", re.IGNORECASE
)
_REFERENCES_HEADER_RE = re.compile(
    r"(?<![A-Za-z])REFERENCES\b\s*$", re.IGNORECASE
)
# OCR fuses the section header with a preceding word by dropping
# the space. Pre-process by inserting a space whenever we see a
# lowercase letter glued to "OUTLINE" or "REFERENCES" with no
# intervening whitespace — the broken-word "everOUTLINE" becomes
# "ever OUTLINE".
_OUTLINE_OCR_FUSE_RE = re.compile(
    r"([a-z]{3,})(OUTLINE\s+OF\s+TOPICS)", re.IGNORECASE
)
_REFERENCES_OCR_FUSE_RE = re.compile(
    r"([a-z]{3,})(REFERENCES\b)", re.IGNORECASE
)


def _de_ocr_fuse_headers(chunk: list[str]) -> list[str]:
    """Insert a space between an OCR-fused word and a section header.

    The Syntopicon OCR sometimes produces lines like
    "is one everOUTLINE OF TOPICS" — where the section header is
    glued to a preceding word. We rewrite such occurrences in-place
    so the header regexes can match them.
    """
    out: list[str] = []
    for ln in chunk:
        s = ln
        s = _OUTLINE_OCR_FUSE_RE.sub(r"\1 \2", s)
        s = _REFERENCES_OCR_FUSE_RE.sub(r"\1 \2", s)
        out.append(s)
    return out
_CROSSREF_HEADER_RE = re.compile(r"^CROSS[\s\-]REFERENCES?\s*$", re.IGNORECASE)
_ADDITIONAL_RE_READINGS_RE = re.compile(
    r"^ADDITIONAL\s+READINGS?\s*$",
    re.IGNORECASE,
)
_ADDITIONAL_READINGS_RE = re.compile(r"^ADDITIONAL\s+READING", re.IGNORECASE)


def _extract_idea_body(
    chapter_idea_number: int,
    lines: list[str],
    chapter_start: int,
    next_chapter_start: int | None,
    chapter_title: str,
) -> IdeaBody:
    """For one idea (cap N), extract:
      * `introduction`: the discursive essay preceding OUTLINE OF TOPICS.
        We pick the lines that follow the line "INTRODUCTION" or follow
        the chapter header directly (in some caps the chapter header is
        followed immediately by `OUTLINE OF TOPICS` with no introduc-
        tion at all).
      * `cross_references`: the section that follows REFERENCES (and
        possibly CROSS-REFERENCES) up until the next chapter header.
    """
    end = next_chapter_start or (len(lines) + 1)
    chunk = lines[chapter_start - 1 : end - 1]
    body = IdeaBody(idea_number=chapter_idea_number)

    # The next-chapter header may itself be at the start of the chunk
    # (rare). Skip it.
    chunk = _skip_leading_chapter_marker(chunk, chapter_idea_number)
    chunk = _de_ocr_fuse_headers(chunk)

    # Locate boundaries.
    intro_end = len(chunk)  # default = no outline found
    outline_pos = None
    refs_pos = None
    crossrefs_pos = None
    next_chap_pos = None
    for idx, line in enumerate(chunk):
        s = line.strip()
        if s.startswith("[PAGE ") and outline_pos is None:
            continue  # page markers between intro and outline
        if (
            outline_pos is None
            and _OUTLINE_HEADER_LINE_RE.search(s)
        ):
            outline_pos = idx
            continue
        if outline_pos is not None and refs_pos is None and _REFERENCES_HEADER_RE.search(s):
            refs_pos = idx
            continue
        if (
            refs_pos is not None
            and crossrefs_pos is None
            and _CROSSREF_HEADER_RE.match(s)
        ):
            crossrefs_pos = idx
            continue
        if (
            refs_pos is not None
            and crossrefs_pos is None
            and re.match(r"^Chapter\s*\d", s)
            and _next_chapter_is_different_than_current(s, chapter_idea_number)
        ):
            # Defensive: some PDFs emit the next chapter header inline
            # before the CROSS-REFERENCES header was emitted; treat that
            # as the end of the previous chapter.
            next_chap_pos = idx
            break

    # ----- Introduction text -----
    intro_text_lines: list[str] = []
    if outline_pos is not None:
        intro_end = outline_pos
        intro_slice = chunk[:intro_end]
    else:
        intro_slice = chunk
    # The intro slice may begin with a chapter header line and `INTRODUCTION`
    # marker. Drop both before collecting prose.
    for ln in intro_slice:
        s = ln.strip()
        if CHAPTER_RE.search(ln):
            continue
        if s == "INTRODUCTION":
            continue
        if _OUTLINE_HEADER_LINE_RE.search(s):
            continue
        intro_text_lines.append(ln)
    body.introduction = _join_paragraphs(_iter_page_text(intro_text_lines)).strip()

    # ----- Cross-references text -----
    if crossrefs_pos is not None:
        end_cross = next_chap_pos if next_chap_pos is not None else len(chunk)
        cr_slice = chunk[crossrefs_pos:end_cross]
    elif refs_pos is not None and outline_pos is not None:
        # Some chapters have references but skip the cross-references
        # section — fall back to using whatever lies between the
        # REFERENCES header and the next structural break (ADDITIONAL
        # READINGS or the next chapter header). When the chapter has no
        # CROSS-REFERENCES block at all, the body here is just the
        # References section and there is nothing cross-reference-y to
        # surface; in that case, do not emit cross_references.
        crossrefs_pos = refs_pos
        end_cross = next_chap_pos if next_chap_pos is not None else len(chunk)
        cr_slice = chunk[refs_pos:end_cross]
        # Trim cr_slice at the first ADDITIONAL READINGS header.
        for i, ln in enumerate(cr_slice):
            if _ADDITIONAL_READINGS_RE.match(ln.strip()):
                cr_slice = cr_slice[:i]
                break
        # When CROSS-REFERENCES was not actually found in the chapter,
        # the slice above is really the References section. Search the
        # chunk for a real CROSS-REFERENCES block; if there is one we
        # missed (e.g. OCR-garbled on its own line), treat it as the
        # cross_refs. Otherwise we leave the slice empty so the front-
        # end does not show garbled citations under "cross_references".
        has_real_cross = any(
            _CROSSREF_HEADER_RE.match(ln.strip()) for ln in cr_slice
        )
        if not has_real_cross:
            cr_slice = []
    else:
        cr_slice = []

    # In some chapters the cross-references are followed by an
    # ADDITIONAL READINGS appendix listing recommended works. Stop
    # the cross-references body at that header so the appendix is
    # not merged in (defensive — the fallback branch above already
    # does this, but the primary branch needs it too for chapters
    # that have both CROSS-REFERENCES and ADDITIONAL READINGS).
    if cr_slice:
        for i, ln in enumerate(cr_slice):
            if _ADDITIONAL_READINGS_RE.match(ln.strip()):
                cr_slice = cr_slice[:i]
                break

    # Strip the section-header lines themselves from the body.
    cr_text: list[str] = []
    for ln in cr_slice:
        s = ln.strip()
        if (
            _CROSSREF_HEADER_RE.search(s)
            or _REFERENCES_HEADER_RE.search(s)
            or _ADDITIONAL_RE_READINGS_RE.search(s)
        ):
            continue
        if CHAPTER_RE.search(ln):
            continue
        cr_text.append(ln)
    body.cross_references = _join_paragraphs(_iter_page_text(cr_text)).strip()

    return body


def _skip_leading_chapter_marker(chunk: list[str], chapter_idea_number: int) -> list[str]:
    """Drop the first few lines of a chapter chunk if they look like
    the chapter header (because the chunk is sliced on the line right
    after the matched header, sometimes nothing needs to be dropped).
    """
    out: list[str] = []
    skipping = True
    for ln in chunk:
        s = ln.strip()
        if skipping and (
            s.startswith("Chapter")
            or CHAPTER_RE.search(ln)
            or s == ""
        ):
            continue
        skipping = False
        out.append(ln)
    return out


def parse_volume(path: Path) -> ParsedSyntopicon:
    """Parse a single Syntopicon volume (vol 2 or vol 3)."""
    vol_id = _volume_id_from_path(path)
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    starts = find_chapter_starts(lines, volume_id=vol_id)

    # --- First pass: extract topics and citations without author
    # normalisation. We collect the (author_num, name) pairs from every
    # citation so we can compute the most-common (canonical) name per
    # author_num and use it as the definitive spelling in the final pass.
    result = ParsedSyntopicon()
    if vol_id == 2:
        # The vol-2 front-matter (PREFACE / EXPLANATION OF REFERENCE
        # STYLE) belongs to vol 2 only; vol 3 starts directly with its
        # first chapter.
        result.introductions = _extract_front_matter(lines)
    for i, (line_no, chapter_num, chapter_name) in enumerate(starts):
        next_line = starts[i + 1][0] if i + 1 < len(starts) else None
        result.ideas.append(
            Idea(
                number=chapter_num,
                name=chapter_name,
                volume_id=vol_id,
                outline_offset=line_no,
            )
        )
        topics = _extract_topics_for_chapter(lines, line_no, next_line)
        _OUTLINE_LABELS_PER_CHAPTER[chapter_num] = [t.label for t in topics]
        for t in topics:
            t.idea_number = chapter_num
            result.topics.append(t)
        result.citations.extend(
            _extract_citations_for_chapter(
                chapter_num, lines, line_no, next_line,
                outline_labels=[t.label for t in topics],
            )
        )
        # Body (intro essay + cross-references) — independent of the
        # citations, so it can run alongside the existing passes.
        result.idea_bodies[chapter_num] = _extract_idea_body(
            chapter_num, lines, line_no, next_line, chapter_name,
        )

    # --- Compute the canonical author name per (author_num) by majority
    # vote across all citations in this volume. The Syntopicon uses one
    # author number per author throughout, and the same author is cited
    # many times — the most-frequent spelling of "Plato", "Aquinas",
    # etc. is the canonical one. OCR variants ("Aqutnas", "MoNTiiSQUiEu")
    # get outvoted and rewritten.
    name_counter: dict[int, Counter] = {}
    for c in result.citations:
        if 1 <= c.author_number <= 54:
            name_counter.setdefault(c.author_number, Counter())[c.author_name] += 1
    canonical_author_name: dict[int, str] = {
        num: counter.most_common(1)[0][0] for num, counter in name_counter.items()
    }

    # --- Second pass: rewrite each citation's author_name to the
    # canonical form. We mutate the existing Citation objects in place.
    for c in result.citations:
        if c.author_number in canonical_author_name:
            c.author_name = canonical_author_name[c.author_number]

    return result


def parse_syntopicon(vol2_path: Path, vol3_path: Path) -> ParsedSyntopicon:
    parsed_v2 = parse_volume(vol2_path)
    parsed_v3 = parse_volume(vol3_path)
    merged = ParsedSyntopicon()
    merged.ideas = parsed_v2.ideas + parsed_v3.ideas
    merged.topics = parsed_v2.topics + parsed_v3.topics
    merged.citations = parsed_v2.citations + parsed_v3.citations
    merged.introductions = parsed_v2.introductions + parsed_v3.introductions
    # idea_bodies are keyed by idea_number, which is globally unique, so
    # both volumes contribute the same way.
    merged.idea_bodies.update(parsed_v2.idea_bodies)
    merged.idea_bodies.update(parsed_v3.idea_bodies)
    return merged