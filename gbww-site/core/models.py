"""Data classes shared across the GBWW site."""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Volume:
    number: int
    display_name: str
    authors: list[str]
    works: list[str]
    txt_path: str
    is_syntopicon: bool = False


@dataclass
class Idea:
    number: int
    name: str
    volume_id: int
    outline_offset: int | None = None


@dataclass
class Topic:
    idea_number: int
    label: str
    title: str
    parent_label: str | None = None


@dataclass
class Citation:
    idea_number: int
    topic_label: str
    author_number: int
    author_name: str
    work_title: str           # normalized
    work_title_raw: str = ""  # raw, includes sub-spec ("Summa Theologica, part i, q 22")
    citation_text: str = ""
    page_start: str | None = None
    page_end: str | None = None


@dataclass
class IntroSection:
    """The 3 introductory texts at the start of the Syntopicon
    (vol 2): the editorial preface ("Explanatory Notes" / "Preface"),
    "Suggestions for Using the Syntopicon", and "The Great Ideas Today".
    Stored as plain text so the front-end can render them in a
    dedicated "Introdução" page of the site.
    """
    key: str           # slug ("preface" / "suggestions" / "today")
    title: str         # display title (already dedented)
    body: str          # body text, paragraphs separated by \n\n


@dataclass
class IdeaBody:
    """The discursive text (introduction + cross-references) attached
    to a single Syntopicon idea. Stored separately from `Idea` (the
    outline skeleton) so the parser can incrementally populate the
    outline first and the prose later.
    """
    idea_number: int
    introduction: str = ""      # free-form essay preceding OUTLINE OF TOPICS
    cross_references: str = ""  # "CROSS-REFERENCES" block following REFERENCES


@dataclass
class ParsedSyntopicon:
    ideas: list[Idea] = field(default_factory=list)
    topics: list[Topic] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    introductions: list[IntroSection] = field(default_factory=list)
    idea_bodies: dict[int, IdeaBody] = field(default_factory=dict)