#!/usr/bin/env python3
"""
Re-extract clean intro texts from Vol 2 & 3 PDFs and update syntopicon_v18 files.
Fixes garbled headers and corrupted first paragraphs.
"""
import re, fitz
from pathlib import Path

SYNT = Path('/home/rodrigo/gbww/syntopicon_v18')
PDF2 = "/home/rodrigo/gbww/pdfs/Encyclopædia Britannica - Great Books of the Western World, Volume 2 - The Great Ideas I.pdf"
PDF3 = "/home/rodrigo/gbww/pdfs/Encyclopædia Britannica - Great Books of the Western World, Volume 3 - The Great Ideas II.pdf"

# ── Apply word-level corrections ──────────────────────────────────────────────

def fix_words(text):
    text = re.sub(r'\bvhole\b', 'whole', text)
    text = re.sub(r'\bvhich\b', 'which', text)
    text = re.sub(r'\bvith\b', 'with', text)
    text = re.sub(r'\bvould\b', 'would', text)
    text = re.sub(r'\bvork\b', 'work', text)
    text = re.sub(r'\bvorld\b', 'world', text)
    text = re.sub(r'\bvhen\b', 'when', text)
    text = re.sub(r'\bvere\b', 'were', text)
    text = re.sub(r'\bvay\b', 'way', text)
    text = re.sub(r'\bvill\b', 'will', text)
    text = re.sub(r'\bvast\b', 'vast', text)
    text = re.sub(r'\blias\b', 'has', text)
    text = re.sub(r'\btlie\b', 'the', text)
    text = re.sub(r'\bllie\b', 'the', text)
    text = re.sub(r'\bniatter\b', 'matter', text)
    text = re.sub(r'\boi\b(?=\s+[a-z])', 'of', text)
    text = re.sub(r'\bol\b(?=\s+[a-z])', 'of', text)
    text = re.sub(r'\bhfe\b', 'life', text)
    text = re.sub(r'\bHfe\b', 'Life', text)
    text = re.sub(r'\bCHAFFER\b', 'CHAPTER', text)
    text = text.replace('SCHLEIERMACHFR', 'SCHLEIERMACHER')
    text = text.replace('Maimomdes', 'Maimonides')
    text = re.sub(r'\bScotus Engena\b', 'Scotus Erigena', text)
    text = re.sub(r'\bJudaeoChristian\b', 'Judaeo-Christian', text)
    text = re.sub(r'\bsenseperception\b', 'sense-perception', text)
    # docs → does (standalone)
    text = re.sub(r'\bdocs\b(?!\s*\.)', 'does', text)
    # arc → are (when not preceded by article suggesting geometric arc)
    def _fix_arc(m):
        pos = m.start()
        before = text[:pos]
        if re.search(r'\b(an|the|this|that|each|every|any|no|its|their|his|her|our|your|one)\s*$', before, re.I):
            return 'arc'
        return 'are'
    text = re.sub(r'\barc\b', _fix_arc, text)
    # Missing spaces: "ofGod" → "of God" etc.
    text = re.sub(r'\bof([A-Z][a-z]{2,})\b', r'of \1', text)
    text = re.sub(r'\bin([A-Z][a-z]{2,})\b', r'in \1', text)
    text = re.sub(r'\bto([A-Z][a-z]{2,})\b', r'to \1', text)
    text = re.sub(r'\bby([A-Z][a-z]{2,})\b', r'by \1', text)
    # Page header artifacts: "515 FATE" etc.
    text = re.sub(r'\s+\d{3,4}\s+[A-Z]{3,}\s*\n', '\n', text)
    # Fix "Darw in" → "Darwin"
    text = re.sub(r'\bDarw in\b', 'Darwin', text)
    # Fix "Darw in's" → "Darwin's"
    text = re.sub(r"\bDarw in's\b", "Darwin's", text)
    # Fix double spaces
    text = re.sub(r'  +', ' ', text)
    return text


# ── Extract intro from PDF ────────────────────────────────────────────────────

def extract_intro(doc, start_page_idx):
    full_text = ""
    for i in range(start_page_idx, min(start_page_idx + 22, len(doc))):
        page_text = doc[i].get_text()
        full_text += page_text + "\n"
        if 'OUTLINE OF TOPICS' in page_text:
            break

    m = re.search(r'INTRODUCTION\n', full_text)
    if not m:
        return None
    intro_text = full_text[m.end():]

    outline_pos = intro_text.find('OUTLINE OF TOPICS')
    if outline_pos != -1:
        intro_text = intro_text[:outline_pos]

    # Remove hyphenation at line breaks
    intro_text = re.sub(r'(\w)-\n(\w)', r'\1\2', intro_text)
    # Remove running headers and page numbers
    intro_text = re.sub(r'\nChapter[\s\w:]+\n', '\n', intro_text)
    intro_text = re.sub(r'\nTHE GREAT IDEAS\n', '\n', intro_text)
    intro_text = re.sub(r'^\d+\s*$', '', intro_text, flags=re.M)
    # Clean up
    intro_text = re.sub(r'\n{3,}', '\n\n', intro_text)
    intro_text = re.sub(r'  +', ' ', intro_text)

    return intro_text.strip()


# ── Build chapter map ─────────────────────────────────────────────────────────

def build_chapter_map():
    result = {}  # normalized_name → (pdf_path, page_idx, raw_topic_name)
    pat = re.compile(r'^Chapter[\w\s]*:\s*([A-Z][A-Z &]+)\s*\nINTRODUCTION', re.M)

    for pdf_path in [PDF2, PDF3]:
        doc = fitz.open(pdf_path)
        for i in range(len(doc)):
            text = doc[i].get_text()
            m = pat.search(text[:600])
            if m:
                topic_raw = m.group(1).strip()
                # Normalize: lower, spaces→hyphen
                norm = topic_raw.lower().replace(' ', '-')
                if norm not in result:
                    result[norm] = (pdf_path, i, topic_raw)
        doc.close()
    return result


def find_pdf_entry(name, chapter_map):
    """Find the best PDF entry for a given TXT filename stem."""
    # Try several normalizations
    candidates = [
        name.lower().replace(' & ', '-&-').replace(' ', '-'),
        name.lower().replace(' & ', '-and-').replace(' ', '-'),
        name.lower().replace('&', 'and').replace(' ', '-'),
    ]
    # Also singular: strip trailing 's'
    candidates += [re.sub(r's(?=-|$)', '', c) for c in candidates]

    for c in candidates:
        if c in chapter_map:
            return chapter_map[c]

    # Fuzzy: word-set match
    name_words = set(re.split(r'[-& ]+', name.lower()) )
    name_words.discard('')
    name_sing = {re.sub(r's$', '', w) for w in name_words}

    for k, v in chapter_map.items():
        k_words = set(k.split('-'))
        k_words.discard('')
        k_sing = {re.sub(r's$', '', w) for w in k_words}
        if name_words == k_words or name_sing == k_sing:
            return v
    return None


# ── Process each file ─────────────────────────────────────────────────────────

def process_file(txt_path, chapter_map):
    name = txt_path.stem
    if name.startswith('#'):
        return False

    text = txt_path.read_text(encoding='utf-8', errors='replace')
    original = text

    # Find OUTLINE OF TOPICS and CROSS-REFERENCES sections to preserve
    outline_pos = text.find('OUTLINE OF TOPICS')
    crossref_pos = text.find('CROSS-REFERENCES')
    addread_pos = text.find('ADDITIONAL READINGS')

    # Preserve the non-intro sections
    if outline_pos != -1:
        tail = text[outline_pos:]
    else:
        tail = ''

    # Try to get PDF intro
    entry = find_pdf_entry(name, chapter_map)
    if entry:
        pdf_path, page_idx, raw_topic = entry
        doc = fitz.open(pdf_path)
        pdf_intro = extract_intro(doc, page_idx)
        doc.close()

        if pdf_intro and len(pdf_intro) > 300:
            pdf_intro = fix_words(pdf_intro)
            # Rebuild file
            new_text = f"Chapter: {raw_topic}\n\nINTRODUCTION\n\n{pdf_intro}\n\n{tail}"
            if new_text != original:
                txt_path.write_text(new_text, encoding='utf-8')
                print(f"  ✓ {name} — intro from PDF ({len(pdf_intro)} chars)")
                return True
            return False

    # No PDF match — just apply word corrections to existing text
    fixed = fix_words(text)
    if fixed != text:
        txt_path.write_text(fixed, encoding='utf-8')
        print(f"  ~ {name} — word corrections only")
        return True
    return False


def main():
    print("Building chapter map...")
    chapter_map = build_chapter_map()
    print(f"Found {len(chapter_map)} chapters in PDFs\n")

    files = sorted(SYNT.glob('*.txt'))
    n_pdf = n_words = n_skip = 0

    for f in files:
        if f.name.startswith('#'):
            continue
        result = process_file(f, chapter_map)
        if result is True:
            n_pdf += 1
        else:
            n_skip += 1

    print(f"\nDone: {n_pdf} files updated, {n_skip} unchanged")


if __name__ == '__main__':
    main()
