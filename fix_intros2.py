#!/usr/bin/env python3
"""
Complete re-extraction of syntopicon intros from PDFs using hardcoded page map.
Covers all 102 chapters found across both PDFs.
"""
import re, fitz
from pathlib import Path
try:
    import enchant as _enchant
    _dict = _enchant.Dict('en_US')
    _dict_ok = True
except Exception:
    _dict_ok = False

SYNT = Path('/home/rodrigo/gbww/syntopicon_v18')
PDF2 = "/home/rodrigo/gbww/pdfs/Encyclopædia Britannica - Great Books of the Western World, Volume 2 - The Great Ideas I.pdf"
PDF3 = "/home/rodrigo/gbww/pdfs/Encyclopædia Britannica - Great Books of the Western World, Volume 3 - The Great Ideas II.pdf"

# Hardcoded map: filename stem (lowercase) → (pdf_path, 0-based page index)
CHAPTER_MAP = {
    # Vol 2
    'angels':           (PDF2, 58),
    'animals':          (PDF2, 76),
    'aristocracy':      (PDF2, 107),
    'art':              (PDF2, 121),
    'astronomy':        (PDF2, 144),
    'beauty':           (PDF2, 169),
    'being':            (PDF2, 183),
    'cause':            (PDF2, 212),
    'chance':           (PDF2, 236),
    'change':           (PDF2, 250),
    'citizen':          (PDF2, 275),
    'constitution':     (PDF2, 290),
    'courage':          (PDF2, 309),
    'custom & convention':  (PDF2, 325),
    'definition':       (PDF2, 343),
    'democracy':        (PDF2, 360),
    'desire':           (PDF2, 380),
    'dialectic':        (PDF2, 402),
    'duty':             (PDF2, 415),
    'education':        (PDF2, 433),
    'element':          (PDF2, 457),
    'emotion':          (PDF2, 470),
    'eternity':         (PDF2, 494),
    'evolution':        (PDF2, 508),
    'experience':       (PDF2, 525),
    'family':           (PDF2, 543),
    'fate':             (PDF2, 572),
    'form':             (PDF2, 583),
    'god':              (PDF2, 600),
    'good & evil':      (PDF2, 662),
    'government':       (PDF2, 694),
    'habit':            (PDF2, 722),
    'happiness':        (PDF2, 741),
    'history':          (PDF2, 768),
    'honor':            (PDF2, 785),
    'hypothesis':       (PDF2, 806),
    'idea':             (PDF2, 818),
    'immortality':      (PDF2, 841),
    'induction':        (PDF2, 862),
    'infinity':         (PDF2, 873),
    'judgment':         (PDF2, 892),
    'justice':          (PDF2, 907),
    'knowledge':        (PDF2, 937),
    'labor':            (PDF2, 978),
    'language':         (PDF2, 998),
    'law':              (PDF2, 1019),
    'liberty':          (PDF2, 1048),
    'life & death':     (PDF2, 1070),
    'logic':            (PDF2, 1092),
    'love':             (PDF2, 1108),
    # Vol 3
    'man':              (PDF3, 34),
    'mathematics':      (PDF3, 75),
    'matter':           (PDF3, 96),
    'mechanics':        (PDF3, 113),
    'medicine':         (PDF3, 146),
    'memory & imagination': (PDF3, 166),
    'metaphysics':      (PDF3, 191),
    'mind':             (PDF3, 204),
    'monarchy':         (PDF3, 237),
    'nature':           (PDF3, 258),
    'necessity & contigency': (PDF3, 284),  # note: typo in filename
    'necessity & contingency': (PDF3, 284),
    'oligarchy':        (PDF3, 303),
    'one & many':       (PDF3, 315),
    'opinion':          (PDF3, 336),
    'opposition':       (PDF3, 356),
    'philosophy':       (PDF3, 375),
    'physics':          (PDF3, 396),
    'pleasure & pain':  (PDF3, 410),
    'poetry':           (PDF3, 433),
    'principle':        (PDF3, 453),
    'progress':         (PDF3, 470),
    'prophecy':         (PDF3, 487),
    'prudence':         (PDF3, 505),
    'punishment':       (PDF3, 521),
    'quality':          (PDF3, 546),
    'quantity':         (PDF3, 560),
    'reasoning':        (PDF3, 579),
    'relation':         (PDF3, 602),
    'religion':         (PDF3, 621),
    'revolution':       (PDF3, 659),
    'rhetoric':         (PDF3, 678),
    'same & other':     (PDF3, 698),
    'science':          (PDF3, 715),
    'sense':            (PDF3, 739),
    'sign & symbol':    (PDF3, 763),
    'sin':              (PDF3, 786),
    'slavery':          (PDF3, 807),
    'soul':             (PDF3, 824),
    'space':            (PDF3, 844),
    'state':            (PDF3, 859),
    'temperance':       (PDF3, 899),
    'theology':         (PDF3, 915),
    'time':             (PDF3, 929),
    'truth':            (PDF3, 948),
    'tyranny':          (PDF3, 972),
    'universal & particular': (PDF3, 990),
    'virtue & vice':    (PDF3, 1008),
    'war & peace':      (PDF3, 1043),
    'wealth':           (PDF3, 1071),
    'will':             (PDF3, 1104),
    'wisdom':           (PDF3, 1135),
    'world':            (PDF3, 1151),
}


def fix_words(text):
    """Apply word-level OCR corrections."""
    # v → w (old OCR: italic v misread as w-like)
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
    text = re.sub(r'\bot\b(?=\s+[a-z])', 'of', text)
    text = re.sub(r'\bhfe\b', 'life', text)
    text = re.sub(r'\bHfe\b', 'Life', text)
    text = re.sub(r'\bCHAFFER\b', 'CHAPTER', text)
    text = text.replace('SCHLEIERMACHFR', 'SCHLEIERMACHER')
    text = text.replace('Maimomdes', 'Maimonides')
    text = text.replace('m;»chine', 'machine')
    text = re.sub(r'\bC»<xl\b', 'God', text)
    text = re.sub(r'\bCi0ti\b|\bCiOti\b|\bC»\w+\b', 'God', text)
    text = re.sub(r'\bScotus Engena\b', 'Scotus Erigena', text)
    text = re.sub(r'\bJudaeoChristian\b', 'Judaeo-Christian', text)
    text = re.sub(r'\bsenseperception\b', 'sense-perception', text)
    text = re.sub(r'\bdocs\b(?!\s*\.)', 'does', text)
    text = re.sub(r'\btliat\b', 'that', text)
    text = re.sub(r'\bliave\b', 'have', text)
    text = re.sub(r'\bnianv\b', 'many', text)
    text = re.sub(r'\bjov\b', 'joy', text)
    text = re.sub(r'\bgocxl\b', 'good', text)
    text = re.sub(r'\bhojx\b', 'hope', text)
    text = re.sub(r'\bhappv\b', 'happy', text)
    text = re.sub(r'\bhappilv\b', 'happily', text)
    # T-ligature misread: 'I'he / I'he / i'hc → The/the
    text = re.sub(r"\bI'he\b", 'The', text)
    text = re.sub(r"\bi'hc\b", 'the', text)
    text = re.sub(r"'I'he\b", 'The', text)
    text = re.sub(r"'I'his\b", 'This', text)
    # Ix ligature: be/be-/In
    text = re.sub(r'\bIx\*(?!\w)', 'be', text)
    text = re.sub(r'\bIx:(?!\w)', 'be', text)
    text = re.sub(r'\bIx\^(\w+)', lambda m: 'be' + m.group(1), text)
    text = re.sub(r'\bIx-causc\b', 'because', text)
    text = re.sub(r'\bIx-twecn\b', 'between', text)
    text = re.sub(r'\bIx-holds\b', 'beholds', text)
    text = re.sub(r'\bIx-loved\b', 'beloved', text)
    text = re.sub(r'\bIx- (\w+)', lambda m: 'be ' + m.group(1), text)
    text = re.sub(r'\bIx-(\w+)', lambda m: 'be' + m.group(1), text)
    text = re.sub(r'\bIx\b(?=\s+[A-Z])', 'In', text)
    # Backslash replacing v (old-style italic v misrendered by PyMuPDF)
    text = re.sub(r'\bha\\e\b', 'have', text)
    text = re.sub(r'\bli\\e\b', 'live', text)
    text = re.sub(r'\blo\\e\b', 'love', text)
    text = re.sub(r'\bgi\\e\b', 'give', text)
    text = re.sub(r'\bgi\\en\b', 'given', text)
    text = re.sub(r'\bgi\\ing\b', 'giving', text)
    text = re.sub(r'\bmo\\e\b', 'move', text)
    text = re.sub(r'\bmo\\ement\b', 'movement', text)
    text = re.sub(r'\bne\\v\b', 'new', text)
    text = re.sub(r'\be\\en\b', 'even', text)
    text = re.sub(r'\be\\er\b', 'ever', text)
    text = re.sub(r'\be\\ery\b', 'every', text)
    text = re.sub(r'\bc\\cn\b', 'even', text)
    text = re.sub(r'\bdi\\ine\b', 'divine', text)
    text = re.sub(r'\bpri\\ate\b', 'private', text)
    text = re.sub(r'\bser\\e\b', 'serve', text)
    text = re.sub(r'\bser\\ed\b', 'served', text)
    text = re.sub(r'\bser\\ing\b', 'serving', text)
    text = re.sub(r'\bser\\ice', 'service', text)
    text = re.sub(r'\bobser\\e', 'observe', text)
    text = re.sub(r'\bpreser\\e', 'preserve', text)
    text = re.sub(r'\bcon\\ert', 'convert', text)
    text = re.sub(r'\bcon\\ince', 'convince', text)
    text = re.sub(r'\bin\\ol', 'invol', text)
    text = re.sub(r'\bre\\eal', 'reveal', text)
    text = re.sub(r'\bre\\olution', 'revolution', text)
    text = re.sub(r'\bbelie\\e', 'believe', text)
    # Words where v = \' (backslash + apostrophe) — PyMuPDF ligature artifact
    text = re.sub(r"\bde\\'eloped\b", 'developed', text)
    text = re.sub(r'\bde\\elop', 'develop', text)
    text = re.sub(r"\bdepri\\'ation\b", 'deprivation', text)
    text = re.sub(r'\bdepri\\ation\b', 'deprivation', text)
    text = re.sub(r"\be\\'ade\b", 'evade', text)
    text = re.sub(r'\be\\ade\b', 'evade', text)
    text = re.sub(r"\bli\\'ing\b", 'living', text)
    text = re.sub(r'\bli\\ing\b', 'living', text)
    text = re.sub(r'\bvegetati\\"e\b', 'vegetative', text)
    text = re.sub(r'\bvegetati\\e\b', 'vegetative', text)
    text = re.sub(r"\bcollecti\\'ely\b", 'collectively', text)
    text = re.sub(r'\bcollecti\\ely\b', 'collectively', text)
    text = re.sub(r"\bcollecti\\'e\b", 'collective', text)
    text = re.sub(r'\bcollecti\\e\b', 'collective', text)
    text = re.sub(r'\bse\\eral\b', 'several', text)
    text = re.sub(r'\bacti\\e\b', 'active', text)
    text = re.sub(r'\bacti\\ely\b', 'actively', text)
    text = re.sub(r'\bpro\\ide', 'provide', text)
    text = re.sub(r'\\arious\b', 'various', text)
    text = re.sub(r'\\alidate', 'validate', text)
    text = re.sub(r"\b\\'erbal\b", 'verbal', text)
    text = re.sub(r"\bE\\'OLUTION\b", 'EVOLUTION', text)
    text = re.sub(r"\bsophistr\\'(?!\w)", 'sophistry', text)
    text = re.sub(r"\btheor\\'(?!\w)", 'theory', text)
    text = re.sub(r"\bglor\\'?(?!\w)", 'glory', text)
    text = re.sub(r"\bPurgator\\'?-?(?!\w)", 'Purgatory', text)
    text = re.sub(r"\bfacult\\'?i?\b", 'faculty', text)
    text = re.sub(r"\bdisjunctit['\"]?e\\?['\"]?\b", 'disjunctive', text)
    # Backslash replacing k
    text = re.sub(r'\bwor\\s\b', 'works', text)
    text = re.sub(r'\bBoo\\s\b', 'Books', text)
    text = re.sub(r'\bBoo\\\b', 'Book', text)
    text = re.sub(r'\bDic\\\b', 'Dick', text)
    text = re.sub(r'\bbul\\\b', 'bulk', text)
    text = re.sub(r'\bloo\\not\b', 'look not', text)
    # Double-backslash (and \\' variant) replacing w — PyMuPDF ligature artifact
    text = re.sub(r"\\\\'hich\b", 'which', text)
    text = re.sub(r'\\\\hich\b', 'which', text)
    text = re.sub(r"\bpo\\\\'er\b", 'power', text)
    text = re.sub(r'\bpo\\\\er\b', 'power', text)
    text = re.sub(r"\bsho\\\\'ing\b", 'showing', text)
    text = re.sub(r'\bsho\\\\ing\b', 'showing', text)
    text = re.sub(r"\bgro\\\\'th\b", 'growth', text)
    text = re.sub(r'\bgro\\\\th\b', 'growth', text)
    text = re.sub(r'\bgro\\\\n\b', 'grown', text)
    text = re.sub(r"\bcommon\\\\\^?\s*ealth\b", 'commonwealth', text)
    # Backslash-caret (and \^' variant) replacing w
    text = re.sub(r"\\\^'orld\b", 'world', text)
    text = re.sub(r"\\\^orld\b", 'world', text)
    text = re.sub(r"\\\^'rites\b", 'writes', text)
    text = re.sub(r"\\\^ rites\b", 'writes', text)
    text = re.sub(r'\bma\^e\b', 'make', text)
    text = re.sub(r'\bspa\\esty\b', 'spakest', text)
    # \v → w (ne\v → new, Dar\vin → Darwin)
    text = re.sub(r'\bne\\v\b', 'new', text)
    # whate\-er → whatever
    text = re.sub(r'\bwhate\\-er\b', 'whatever', text)
    # A → x\ (capital A misrendered)
    text = re.sub(r'\bx\\ristotle\b', 'Aristotle', text)
    text = re.sub(r'\bx\\nimal\b', 'Animal', text)
    text = re.sub(r'\.ristotle\b', 'Aristotle', text)
    text = re.sub(r'\\ND\b', 'AND', text)
    # w' artifact
    text = re.sub(r"\bw'ith\b", 'with', text)
    text = re.sub(r"\bwdth\b", 'with', text)
    # \vc → we
    text = re.sub(r'\\vc\b', 'we', text)
    # ot → of (when before lowercase word, excluding 'ot' at start of sentence)
    # already covered above with \bot\b(?=\s+[a-z])
    def _fix_arc(m):
        pos = m.start()
        before = text[:pos]
        if re.search(r'\b(an|the|this|that|each|every|any|no|its|their|his|her|our|your|one)\s*$', before, re.I):
            return 'arc'
        return 'are'
    text = re.sub(r'\barc\b', _fix_arc, text)
    text = re.sub(r'\bof([A-Z][a-z]{2,})\b', r'of \1', text)
    text = re.sub(r'\bin([A-Z][a-z]{2,})\b', r'in \1', text)
    text = re.sub(r'\bto([A-Z][a-z]{2,})\b', r'to \1', text)
    text = re.sub(r'\bby([A-Z][a-z]{2,})\b', r'by \1', text)
    text = re.sub(r'\s+\d{3,4}\s+[A-Z]{3,}\s*\n', '\n', text)
    text = re.sub(r'\bDarw in\b', 'Darwin', text)
    text = re.sub(r"\bDarw in's\b", "Darwin's", text)
    text = re.sub(r"\bDar\\vin\b", 'Darwin', text)
    text = re.sub(r"\bDar\\vin's\b", "Darwin's", text)
    # Fix "m.atter" / "m.an" (OCR artifact: period in word)
    text = re.sub(r'\bm\.an\b', 'man', text)
    text = re.sub(r'\bm\.atter\b', 'matter', text)
    text = re.sub(r'\bam\.ong\b', 'among', text)
    text = re.sub(r'\bam\.ount\b', 'amount', text)
    # Specific garbled words from Dante/Aquinas passages in Honor
    text = re.sub(r'\bCitxl\b', 'God', text)
    text = re.sub(r'\bGixl\b', 'God', text)
    text = re.sub(r'\bGtxl\b', 'God', text)
    text = re.sub(r'\bSirints\b', 'Saints', text)
    # Terminal y → v OCR error (e.g. "onlv" → "only", "glorv" → "glory")
    if _dict_ok:
        def _fix_term_v(m):
            w = m.group()
            stem = w[:-1]
            y_form = stem + 'y'
            if not _dict.check(w) and _dict.check(y_form):
                return y_form
            return w
        text = re.sub(r'\b[a-zA-Z]{3,}v\b', _fix_term_v, text)
    # Fix double spaces
    text = re.sub(r'  +', ' ', text)
    return text


def extract_intro(doc, start_page_idx):
    """Extract intro text from PDF, from INTRODUCTION until OUTLINE OF TOPICS."""
    full_text = ""
    for i in range(start_page_idx, min(start_page_idx + 24, len(doc))):
        page_text = doc[i].get_text()
        full_text += page_text + "\n"
        if 'OUTLINE OF TOPICS' in page_text:
            break

    # Find INTRODUCTION marker (possibly "INTRODUCTION\n" or "INTRODUCTION ")
    m = re.search(r'INTRODUCTION\n', full_text)
    if not m:
        m = re.search(r'INTRODUCTION\s+', full_text)
    if not m:
        return None

    intro_text = full_text[m.end():]

    # Cut at OUTLINE OF TOPICS
    outline_pos = intro_text.find('OUTLINE OF TOPICS')
    if outline_pos != -1:
        intro_text = intro_text[:outline_pos]

    # Clean up PDF extraction artifacts
    intro_text = re.sub(r'(\w)-\n(\w)', r'\1\2', intro_text)       # dehyphenation
    intro_text = re.sub(r'\nChapter[\s\w:.\-]+\n', '\n', intro_text)  # running headers
    intro_text = re.sub(r'\nChai[»\w.:]+\s+\d+[:\s]+[A-Z &]+\n', '\n', intro_text)  # garbled headers
    intro_text = re.sub(r'\nTHE GREAT IDEAS\n', '\n', intro_text)
    intro_text = re.sub(r'^\d+\s*$', '', intro_text, flags=re.M)    # page numbers
    intro_text = re.sub(r'\n\d{3,4}\s*\n', '\n', intro_text)        # standalone page numbers
    intro_text = re.sub(r'\n[;»\s]{1,5}\n', '\n', intro_text)       # stray guillemets/punctuation
    intro_text = re.sub(r'\n{3,}', '\n\n', intro_text)
    intro_text = re.sub(r'[ \t]{2,}', ' ', intro_text)

    return intro_text.strip()


def process_file(txt_path, open_docs):
    name = txt_path.stem
    if name.startswith('#'):
        return False

    # Look up in map (case-insensitive)
    key = name.lower()
    entry = CHAPTER_MAP.get(key)

    # Try alternate keys
    if not entry:
        key2 = key.replace(' & ', ' and ')
        entry = CHAPTER_MAP.get(key2)
    if not entry:
        key3 = key.replace(' and ', ' & ')
        entry = CHAPTER_MAP.get(key3)

    if not entry:
        print(f"  ? No map entry for: {name}")
        return False

    pdf_path, page_idx = entry
    doc = open_docs[pdf_path]
    pdf_intro = extract_intro(doc, page_idx)

    if not pdf_intro or len(pdf_intro) < 200:
        print(f"  ! Empty PDF intro for: {name} (page {page_idx+1})")
        return False

    pdf_intro = fix_words(pdf_intro)

    # Read existing file to preserve OUTLINE + CROSS-REFS
    text = txt_path.read_text(encoding='utf-8', errors='replace')
    outline_pos = text.find('OUTLINE OF TOPICS')
    tail = text[outline_pos:] if outline_pos != -1 else ''

    new_text = f"CHAPTER: {name.upper()}\n\nINTRODUCTION\n\n{pdf_intro}\n\n{tail}"

    txt_path.write_text(new_text, encoding='utf-8')
    print(f"  ✓ {name} ({len(pdf_intro):,} chars)")
    return True


def main():
    # Open both PDFs once
    open_docs = {
        PDF2: fitz.open(PDF2),
        PDF3: fitz.open(PDF3),
    }

    files = sorted(SYNT.glob('*.txt'))
    n_ok = n_fail = 0

    for f in files:
        if f.name.startswith('#'):
            continue
        ok = process_file(f, open_docs)
        if ok:
            n_ok += 1
        else:
            n_fail += 1

    for doc in open_docs.values():
        doc.close()

    print(f"\nDone: {n_ok} updated, {n_fail} not found")


if __name__ == '__main__':
    main()
