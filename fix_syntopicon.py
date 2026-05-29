#!/usr/bin/env python3
"""
Fix syntopicon_v18 TXT files:
1. Extract clean intro texts from Vol 2 & 3 PDFs
2. Apply regex corrections for OCR/ligature errors
3. Write corrected files back
"""
import re, fitz
from pathlib import Path

SYNT = Path('/home/rodrigo/gbww/syntopicon_v18')
PDF2 = Path('/home/rodrigo/gbww/pdfs/Encyclopædia Britannica - Great Books of the Western World, Volume 2 - The Great Ideas I.pdf')
PDF3 = Path('/home/rodrigo/gbww/pdfs/Encyclopædia Britannica - Great Books of the Western World, Volume 3 - The Great Ideas II.pdf')

# ── Regex corrections ──────────────────────────────────────────────────────────

def apply_corrections(text):
    """Apply systematic OCR/ligature corrections to text."""

    # Ligature: 'f' sequences
    # fi→ fi (normal), fl→fl, ff→ff — sometimes appear as single chars
    # Specific known ligature errors from native PDF text layer:
    text = re.sub(r'\bvhole\b', 'whole', text)
    text = re.sub(r'\bVhole\b', 'Whole', text)
    text = re.sub(r'\bvhich\b', 'which', text)
    text = re.sub(r'\bVhich\b', 'Which', text)
    text = re.sub(r'\bvith\b', 'with', text)
    text = re.sub(r'\bWith\b', 'With', text)  # intentional cap
    text = re.sub(r'\bvould\b', 'would', text)
    text = re.sub(r'\bVould\b', 'Would', text)
    text = re.sub(r'\bvork\b', 'work', text)
    text = re.sub(r'\bVork\b', 'Work', text)
    text = re.sub(r'\bvorld\b', 'world', text)
    text = re.sub(r'\bVorld\b', 'World', text)
    text = re.sub(r'\bvhen\b', 'when', text)
    text = re.sub(r'\bVhen\b', 'When', text)
    text = re.sub(r'\bvere\b', 'were', text)
    text = re.sub(r'\bVere\b', 'Were', text)
    text = re.sub(r'\bvay\b', 'way', text)
    text = re.sub(r'\bvill\b', 'will', text)  # only lowercase, 'Will' is a name/concept
    text = re.sub(r'\bvast\b', 'vast', text)

    # ' arc ' → ' are ' — in philosophical texts, standalone "arc" is almost always "are"
    # Preserve "arc" only when preceded by article/determiner (geometric usage)
    def _fix_arc(m):
        before = text[:m.start()].rstrip()
        # If the word before is an article/possessive, this "arc" is a real arc
        if re.search(r'\b(an|the|this|that|each|every|any|no|its|their|his|her|our|your|one)\s*$', before, re.I):
            return 'arc'
        return 'are'
    text = re.sub(r'\barc\b', _fix_arc, text)

    # docs → does (not "documents" — but "docs" alone always means "does" in this corpus)
    text = re.sub(r'\bdocs\b(?!\s*\.)', 'does', text)

    # lias → has
    text = re.sub(r'\blias\b', 'has', text)
    text = re.sub(r'\bLias\b', 'Has', text)

    # tlie → the
    text = re.sub(r'\btlie\b', 'the', text)
    text = re.sub(r'\bTlie\b', 'The', text)

    # llie → the
    text = re.sub(r'\bllie\b', 'the', text)

    # niatter → matter
    text = re.sub(r'\bniatter\b', 'matter', text)
    text = re.sub(r'\bNiatter\b', 'Matter', text)

    # oi/ol as 'of' in specific patterns (e.g., "assertion oi a", "principle ol conduct")
    text = re.sub(r'\boi\b(?=\s+[a-z])', 'of', text)
    text = re.sub(r'\bol\b(?=\s+[a-z])', 'of', text)

    # Missing spaces before capital words (e.g., "ofGod" → "of God", "andThe" → "and The")
    # This handles cases like "ofMorals", "ofBoethius", "inThe", etc.
    text = re.sub(r'\b(of|in|for|to|and|the|a|an|or|by|with|from|on|at|as)\b([A-Z][a-z])',
                  r'\1 \2', text)

    # Chapteri: → Chapter 1:
    text = re.sub(r'\bChapteri\b', 'Chapter 1', text)
    text = re.sub(r'\bChapter i\b', 'Chapter 1', text)
    text = re.sub(r'\bChapter ir\b', 'Chapter 11', text)  # 'ir' OCR for '11'

    # Fix em-dash issues: "word— " and "—word" (normalize)
    # Some places have stray numbers from page headers inserted in text
    # Pattern like "with- 515 FATE" → "with-" (page header artifact)
    text = re.sub(r'\s+\d{3,4}\s+[A-Z]{3,}\s*\n', '\n', text)

    # Fix "SCHLEIERMACHFR" → "SCHLEIERMACHER"
    text = text.replace('SCHLEIERMACHFR', 'SCHLEIERMACHER')

    # Fix "Maimomdes" → "Maimonides"
    text = text.replace('Maimomdes', 'Maimonides')

    # Fix "Engena" → "Erigena"
    text = re.sub(r'\bScotus Engena\b', 'Scotus Erigena', text)

    # Fix "JudaeoChristian" → "Judaeo-Christian"
    text = re.sub(r'\bJudaeoChristian\b', 'Judaeo-Christian', text)
    text = re.sub(r'\bJudaeo-christian\b', 'Judaeo-Christian', text)

    # Fix "senseperception" → "sense-perception"
    text = re.sub(r'\bsenseperception\b', 'sense-perception', text)
    text = re.sub(r'\bSenseperception\b', 'Sense-perception', text)

    # Fix "CHAFFER" → "CHAPTER"
    text = re.sub(r'\bCHAFFER\b', 'CHAPTER', text)

    # Fix common joined prepositions with words (lowercase only, to avoid name issues)
    text = re.sub(r'\bof([A-Z][a-z]{2,})\b', r'of \1', text)
    text = re.sub(r'\bin([A-Z][a-z]{2,})\b', r'in \1', text)
    text = re.sub(r'\bto([A-Z][a-z]{2,})\b', r'to \1', text)
    text = re.sub(r'\bby([A-Z][a-z]{2,})\b', r'by \1', text)
    text = re.sub(r'\bas([A-Z][a-z]{2,})\b', r'as \1', text)

    # Fix "raisedby" → "raised by" etc. (lowercase joined)
    text = re.sub(r'([a-z]{3,})(by|of|in|to|for|with|from)\b', r'\1 \2', text)

    # Fix double spaces
    text = re.sub(r'  +', ' ', text)

    # Fix "inan" → "in an" or "man" context
    text = re.sub(r'\biiian\b', 'man', text)

    # "doc s" → "does"
    text = re.sub(r'\bdoc s\b', 'does', text)

    # Fix "hfe" → "life"
    text = re.sub(r'\bhfe\b', 'life', text)
    text = re.sub(r'\bHfe\b', 'Life', text)

    # Fix "demi-gods" variants
    text = re.sub(r'\bdemi-\s+gods\b', 'demi-gods', text)

    return text


# ── Extract intro from PDF ─────────────────────────────────────────────────────

def extract_intro_from_pdf(doc, start_page_idx):
    """Extract intro text from PDF starting at a chapter's intro page.
    Returns clean text from after INTRODUCTION until OUTLINE OF TOPICS."""

    full_text = ""
    for i in range(start_page_idx, min(start_page_idx + 20, len(doc))):
        page_text = doc[i].get_text()
        full_text += page_text + "\n"
        if 'OUTLINE OF TOPICS' in page_text:
            break

    # Find INTRODUCTION marker
    intro_pos = full_text.find('INTRODUCTION\n')
    if intro_pos == -1:
        intro_pos = full_text.find('INTRODUCTION ')
    if intro_pos == -1:
        return None

    intro_text = full_text[intro_pos + len('INTRODUCTION'):]

    # Cut at OUTLINE OF TOPICS
    outline_pos = intro_text.find('OUTLINE OF TOPICS')
    if outline_pos != -1:
        intro_text = intro_text[:outline_pos]

    # Clean up PDF extraction artifacts
    # Remove hyphenation at line breaks
    intro_text = re.sub(r'(\w)-\n(\w)', r'\1\2', intro_text)
    # Remove running headers: "Chapter N: TOPIC" and "THE GREAT IDEAS" lines
    intro_text = re.sub(r'\nChapter[\w\s:]+\n', '\n', intro_text)
    intro_text = re.sub(r'\nTHE GREAT IDEAS\n', '\n', intro_text)
    # Remove page numbers (lines that are just digits)
    intro_text = re.sub(r'^\d+\s*$', '', intro_text, flags=re.M)
    # Normalize whitespace
    intro_text = re.sub(r'\n{3,}', '\n\n', intro_text)
    intro_text = re.sub(r'  +', ' ', intro_text)

    return intro_text.strip()


# ── Build chapter map from both PDFs ──────────────────────────────────────────

def build_chapter_map():
    """Find all chapter intro pages in Vol 2 and 3 PDFs."""
    result = {}  # normalized_topic_name → (pdf_path, page_idx)

    pat = re.compile(r'^Chapter[\w\s]*:\s*([A-Z][A-Z &]+)\s*\nINTRODUCTION', re.M)

    for pdf_path in [PDF2, PDF3]:
        doc = fitz.open(str(pdf_path))
        for i in range(len(doc)):
            text = doc[i].get_text()
            m = pat.search(text[:600])
            if m:
                topic_name = m.group(1).strip()
                # Normalize: "CUSTOM AND CONVENTION" → "custom-and-convention"
                normalized = topic_name.lower().replace(' and ', ' & ').replace(' ', '-')
                result[normalized] = (str(pdf_path), i)
        doc.close()

    return result


# ── Normalize TXT filename to lookup key ──────────────────────────────────────

def normalize_name(name):
    """Normalize a topic name for matching."""
    return name.lower().replace(' & ', ' & ').replace(' ', '-').replace('&', 'and').replace('--', '-')


# ── Main processing ───────────────────────────────────────────────────────────

def process_file(txt_path, chapter_map, stats):
    """Process one syntopicon TXT file: fix errors and optionally update intro from PDF."""

    name = txt_path.stem  # e.g. "Angels", "Custom & Convention"
    text = txt_path.read_text(encoding='utf-8', errors='replace')
    original = text

    # 1. Apply word-level corrections
    text = apply_corrections(text)

    # 2. Try to get better intro from PDF
    # Normalize name for PDF map lookup
    def _norm_key(s):
        """Normalize to match chapter_map keys: lower, keep &, hyphenate."""
        s = s.lower().strip().replace(' ', '-')
        return s

    def _norm_key_singular(s):
        """Also try stripping trailing 's' (plural → singular)."""
        k = _norm_key(s)
        # Strip trailing 's' from each word
        k = re.sub(r's(?=-|$)', '', k)
        return k

    lookup = _norm_key(name)
    pdf_entry = chapter_map.get(lookup) or chapter_map.get(_norm_key_singular(name))

    if not pdf_entry:
        # Try "and" ↔ "&" swap
        lookup_and = lookup.replace('-&-', '-and-')
        lookup_amp = lookup.replace('-and-', '-&-')
        pdf_entry = chapter_map.get(lookup_and) or chapter_map.get(lookup_amp)

    if not pdf_entry:
        # Fuzzy word-set match
        name_words = set(re.split(r'[-& ]+', name.lower()))
        name_words.discard('')
        for k, v in chapter_map.items():
            k_words = set(re.split(r'[-& ]+', k.lower()))
            k_words.discard('')
            # Also try singular forms
            k_words_sing = {re.sub(r's$', '', w) for w in k_words}
            name_words_sing = {re.sub(r's$', '', w) for w in name_words}
            if name_words == k_words or name_words_sing == k_words_sing:
                pdf_entry = v
                break

    if pdf_entry:
        pdf_path, page_idx = pdf_entry
        doc = fitz.open(pdf_path)
        pdf_intro = extract_intro_from_pdf(doc, page_idx)
        doc.close()

        if pdf_intro and len(pdf_intro) > 500:
            # Compare lengths: if PDF intro is significantly longer, use it
            # Find the intro section in our TXT file
            outline_pos = text.find('OUTLINE OF TOPICS')
            if outline_pos == -1:
                outline_pos = len(text)

            # Find what's before outline in TXT (the intro section)
            intro_end_in_txt = text[:outline_pos]
            # Remove the Chapter header and INTRODUCTION lines
            header_end = 0
            for line in intro_end_in_txt.splitlines():
                if re.match(r'^INTRODUCTION\s*$', line, re.I):
                    header_end = intro_end_in_txt.find(line) + len(line)
                    break

            txt_intro_len = len(intro_end_in_txt) - header_end
            pdf_intro_cleaned = apply_corrections(pdf_intro)

            if len(pdf_intro_cleaned) > txt_intro_len * 1.05:  # PDF has 5%+ more content
                # Replace intro section
                after_outline = text[outline_pos:] if outline_pos < len(text) else ''
                # Rebuild the file with PDF intro
                chapter_header = f"CHAPTER {name.upper()}\n\nINTRODUCTION\n\n"
                text = chapter_header + pdf_intro_cleaned + '\n\n' + after_outline
                stats['pdf_updated'] += 1
                print(f"  ✓ PDF intro used for {name} (PDF:{len(pdf_intro_cleaned)} vs TXT:{txt_intro_len})")
            else:
                stats['kept_txt'] += 1
        else:
            stats['pdf_no_intro'] += 1
    else:
        stats['no_pdf_map'] += 1

    if text != original:
        txt_path.write_text(text, encoding='utf-8')
        stats['corrected'] += 1
        return True
    return False


def main():
    print("Building chapter map from PDFs...")
    chapter_map = build_chapter_map()
    print(f"Found {len(chapter_map)} chapters in PDFs:")
    for k in sorted(chapter_map.keys()):
        print(f"  {k}")

    print("\nProcessing syntopicon_v18 files...")
    stats = {'corrected': 0, 'pdf_updated': 0, 'kept_txt': 0,
             'pdf_no_intro': 0, 'no_pdf_map': 0}

    files = sorted(SYNT.glob('*.txt'))
    files = [f for f in files if not f.name.startswith('#')]

    for f in files:
        process_file(f, chapter_map, stats)

    print(f"\nDone:")
    print(f"  Files modified: {stats['corrected']}")
    print(f"  Intro from PDF: {stats['pdf_updated']}")
    print(f"  Kept TXT intro: {stats['kept_txt']}")
    print(f"  No PDF match:   {stats['no_pdf_map']}")


if __name__ == '__main__':
    main()
