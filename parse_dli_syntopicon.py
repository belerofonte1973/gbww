#!/usr/bin/env python3
"""
parse_dli_syntopicon.py

Parses DLI (Digital Library of India) DJVU TXT files of the Syntopicon
(The Great Ideas, vols I and II, ABBYY FineReader 11.0) and produces:

  gbww/syntopicon_dli/   -- 102 chapter files in syntopicon_v18 format
  gbww/mapa_dli/         -- 2 Mapa files compatible with parse_mapa_refs()

Usage:
  python3 parse_dli_syntopicon.py [--vol1 PATH] [--vol2 PATH] [--out-dir DIR]

Defaults:
  --vol1  /tmp/syntopicon_vol1_dli.txt
  --vol2  /tmp/syntopicon_vol2_dli.txt
  --out-dir  /home/rodrigo/gbww
"""

import re
import sys
import argparse
from pathlib import Path

# ── Chapter mapping: number → (DLI full name, output filename stem) ──────────
# Output stem matches existing syntopicon_v18/ filenames so build_db.py works
# unchanged.
CHAPTERS = {
     1: ('ANGEL',                    'Angels'),
     2: ('ANIMAL',                   'Animals'),
     3: ('ARISTOCRACY',              'Aristocracy'),
     4: ('ART',                      'Art'),
     5: ('ASTRONOMY',                'Astronomy'),
     6: ('BEAUTY',                   'Beauty'),
     7: ('BEING',                    'Being'),
     8: ('CAUSE',                    'Cause'),
     9: ('CHANCE',                   'Chance'),
    10: ('CHANGE',                   'Change'),
    11: ('CITIZEN',                  'Citizen'),
    12: ('CONSTITUTION',             'Constitution'),
    13: ('COURAGE',                  'Courage'),
    14: ('CUSTOM AND CONVENTION',    'Custom & Convention'),
    15: ('DEFINITION',               'Definition'),
    16: ('DEMOCRACY',                'Democracy'),
    17: ('DESIRE',                   'Desire'),
    18: ('DIALECTIC',                'Dialectic'),
    19: ('DUTY',                     'Duty'),
    20: ('EDUCATION',                'Education'),
    21: ('ELEMENT',                  'Element'),
    22: ('EMOTION',                  'Emotion'),
    23: ('ETERNITY',                 'Eternity'),
    24: ('EVOLUTION',                'Evolution'),
    25: ('EXPERIENCE',               'Experience'),
    26: ('FAMILY',                   'Family'),
    27: ('FATE',                     'Fate'),
    28: ('FORM',                     'Form'),
    29: ('GOD',                      'God'),
    30: ('GOOD AND EVIL',            'Good & Evil'),
    31: ('GOVERNMENT',               'Government'),
    32: ('HABIT',                    'Habit'),
    33: ('HAPPINESS',                'Happiness'),
    34: ('HISTORY',                  'History'),
    35: ('HONOR',                    'Honor'),
    36: ('HYPOTHESIS',               'Hypothesis'),
    37: ('IDEA',                     'Idea'),
    38: ('IMMORTALITY',              'Immortality'),
    39: ('INDUCTION',                'Induction'),
    40: ('INFINITY',                 'Infinity'),
    41: ('JUDGMENT',                 'Judgment'),
    42: ('JUSTICE',                  'Justice'),
    43: ('KNOWLEDGE',                'Knowledge'),
    44: ('LABOR',                    'Labor'),
    45: ('LANGUAGE',                 'Language'),
    46: ('LAW',                      'Law'),
    47: ('LIBERTY',                  'Liberty'),
    48: ('LIFE AND DEATH',           'Life & Death'),
    49: ('LOGIC',                    'Logic'),
    50: ('LOVE',                     'Love'),
    51: ('MAN',                      'Man'),
    52: ('MATHEMATICS',              'Mathematics'),
    53: ('MATTER',                   'Matter'),
    54: ('MECHANICS',                'Mechanics'),
    55: ('MEDICINE',                 'Medicine'),
    56: ('MEMORY AND IMAGINATION',   'Memory & Imagination'),
    57: ('METAPHYSICS',              'Metaphysics'),
    58: ('MIND',                     'Mind'),
    59: ('MONARCHY',                 'Monarchy'),
    60: ('NATURE',                   'Nature'),
    61: ('NECESSITY',                'Necessity & Contingency'),
    62: ('OLIGARCHY',                'Oligarchy'),
    63: ('ONE AND MANY',             'One & Many'),
    64: ('OPINION',                  'Opinion'),
    65: ('OPPOSITION',               'Opposition'),
    66: ('PHILOSOPHY',               'Philosophy'),
    67: ('PHYSICS',                  'Physics'),
    68: ('PLEASURE AND PAIN',        'Pleasure & Pain'),
    69: ('POETRY',                   'Poetry'),
    70: ('PRINCIPLE',                'Principle'),
    71: ('PROGRESS',                 'Progress'),
    72: ('PROPHECY',                 'Prophecy'),
    73: ('PRUDENCE',                 'Prudence'),
    74: ('PUNISHMENT',               'Punishment'),
    75: ('QUALITY',                  'Quality'),
    76: ('QUANTITY',                 'Quantity'),
    77: ('REASONING',                'Reasoning'),
    78: ('RELATION',                 'Relation'),
    79: ('RELIGION',                 'Religion'),
    80: ('REVOLUTION',               'Revolution'),
    81: ('RHETORIC',                 'Rhetoric'),
    82: ('SAME AND OTHER',           'Same & Other'),
    83: ('SCIENCE',                  'Science'),
    84: ('SENSE',                    'Sense'),
    85: ('SIGN AND SYMBOL',          'Sign & Symbol'),
    86: ('SIN',                      'Sin'),
    87: ('SLAVERY',                  'Slavery'),
    88: ('SOUL',                     'Soul'),
    89: ('SPACE',                    'Space'),
    90: ('STATE',                    'State'),
    91: ('TEMPERANCE',               'Temperance'),
    92: ('THEOLOGY',                 'Theology'),
    93: ('TIME',                     'Time'),
    94: ('TRUTH',                    'Truth'),
    95: ('TYRANNY',                  'Tyranny'),
    96: ('UNIVERSAL AND PARTICULAR', 'Universal & Particular'),
    97: ('VIRTUE AND VICE',          'Virtue & Vice'),
    98: ('WAR AND PEACE',            'War & Peace'),
    99: ('WEALTH',                   'Wealth'),
   100: ('WILL',                     'Will'),
   101: ('WISDOM',                   'Wisdom'),
   102: ('WORLD',                    'World'),
}

# ── OCR corrections for subtopic codes ───────────────────────────────────────
# Applied only to lines that look like subtopic headings in the outline/refs.
# Pattern: leading code like "Sb.", "ja.", "3(7.", "3^.", "3/.", "41-." etc.
# We fix these systematically.

def fix_subtopic_code(line):
    """Fix common OCR substitutions in subtopic code at start of line."""
    # Handle "N . " (space between digit and period) → "N."
    line = re.sub(r'^(\s*\d+)\s+\.\s', lambda m: m.group(1) + '. ', line)
    # Handle "Na . " → "Na."
    line = re.sub(r'^(\s*\d+[a-z])\s+\.\s', lambda m: m.group(1) + '. ', line)

    # Handle "N A " or "N B " pattern (digit + space + uppercase = OCR for Na, Nb)
    # e.g. "3 A The explanation..." → "3b. The explanation..." (uppercase → lower)
    # Note: when digit already has 'a' in prev line, the next uppercase is likely 'b'
    line = re.sub(
        r'^(\s*)(\d+)\s+([A-Z])\s+',
        lambda m: m.group(1) + m.group(2) + m.group(3).lower() + '. ',
        line
    )
    # Handle "NflTEXT" or "Nfl." → OCR "fl" ligature = 'a'; "fi" = 'a' too
    line = re.sub(r'^(\s*\d+)fl\.?\s', lambda m: m.group(1) + 'a. ', line)
    line = re.sub(r'^(\s*\d+)fi\.?\s', lambda m: m.group(1) + 'a. ', line)

    # Only process lines that start with a potential subtopic code (digit then . or letter)
    m = re.match(r'^(\s*)(\S+?\.)(\s+.+)', line)
    if not m:
        return line
    indent, code, rest = m.group(1), m.group(2), m.group(3)

    # Remove trailing period for processing, add back later
    code_body = code.rstrip('.')

    # Fix leading-character OCR errors
    code_body = re.sub(r'^S(?=\d)', '5', code_body)
    code_body = re.sub(r'^I(?=\d)', '1', code_body)
    code_body = re.sub(r'^O(?=\d)', '0', code_body)
    code_body = re.sub(r'^j(?=\d)', '7', code_body)
    code_body = re.sub(r'^l(?=\d)', '1', code_body)

    # Fix sub-letter OCR
    code_body = re.sub(r'\(7$', 'a', code_body)   # 3(7 → 3a
    code_body = re.sub(r'\^$',  'b', code_body)   # 3^ → 3b
    code_body = re.sub(r'\($',  '',  code_body)   # trailing ( → remove
    code_body = re.sub(r'/$',   'f', code_body)   # 3/ → 3f
    code_body = re.sub(r'\\$',  'f', code_body)   # 3\ → 3f
    code_body = re.sub(r'(\d)1-$', r'\1b', code_body)
    code_body = re.sub(r'(\d)I-$', r'\1b', code_body)
    code_body = re.sub(r'-$', '', code_body)

    return indent + code_body + '.' + rest


# ── Running header patterns ───────────────────────────────────────────────────

# Matches "Chapter N [;:.-] NAME" (possibly with trailing dash or page num)
CHAPTER_HDR = re.compile(
    r'^Chapter\s+\d+\s*[;:.\-]+\s*[A-Z][A-Z &\-]*\s*[\-]?\s*$',
    re.MULTILINE
)

# "THE GREAT IDEAS" or "THE GREAT IDEAS   N" recto running header
GREAT_IDEAS_HDR = re.compile(r'^THE GREAT IDEAS\s*\d*\s*$', re.MULTILINE)

# Isolated page-number lines (just a number, possibly with spaces)
PAGE_NUM_LINE = re.compile(r'^\s*\d{1,4}\s*$', re.MULTILINE)

# "PAGB N N N ..." or "PAGE N N N" or "PACE" — page number table in outline header
PAGE_TABLE = re.compile(r'^PAC?G[BE]?\s*[\d\s]*$', re.MULTILINE)

# Running header "Xa to Xb Chapter N:" or "Xa to Xb  N" mid references
RANGE_HDR = re.compile(
    r'^\s*\d+[a-zA-Z()\d]*\s+to\s+\d+[a-zA-Z()\d]*\s+Chapter\s+\d+\s*:?\s*$',
    re.MULTILINE
)
# Also "Na to Nb  N" without "Chapter"
RANGE_HDR2 = re.compile(
    r'^\s*\d+[a-z]\s+to\s+\d+[a-z]\s+\d+\s*$',
    re.MULTILINE
)

# References boilerplate (the "how to use references" explanation)
REFS_BOILERPLATE = re.compile(
    r'To find the passages cited.*?consult the Preface\.',
    re.DOTALL
)


def strip_running_headers(text):
    """Remove DJVU running headers, page numbers and artifacts from text."""
    text = CHAPTER_HDR.sub('', text)
    text = GREAT_IDEAS_HDR.sub('', text)
    text = PAGE_NUM_LINE.sub('', text)
    text = PAGE_TABLE.sub('', text)
    text = RANGE_HDR.sub('', text)
    text = RANGE_HDR2.sub('', text)
    # Collapse multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def strip_refs_boilerplate(text):
    """Remove the standard references explanation paragraph."""
    return REFS_BOILERPLATE.sub('', text).strip()


# ── Chapter extraction ────────────────────────────────────────────────────────

def _looks_like_refs_page(text, pos, window=600):
    """
    Return True if position pos starts inside a REFERENCES or OUTLINE section
    without preceding intro text — i.e. we seem to have missed the intro.
    """
    snippet = text[pos:pos+window]
    # Clear refs indicators
    if re.search(r'REFERENCES|To find the passages cited|^\d{1,2} \w+:', snippet, re.I | re.M):
        return True
    # Outline-page indicator: page number on line 2 (after chapter header),
    # followed immediately by numbered outline items (no intro prose)
    # Pattern: header\nPAGE_NUM\n...\nN. Topic or N^/7. Topic
    if re.search(r'^\s*\d{2,4}\s*$', snippet[:200], re.M):
        # Has a page number line → likely outline or refs page
        return True
    return False


def _search_for_intro(text, from_pos, to_pos, name_prefix):
    """
    Find the LAST 'INTRODUCTION' in [from_pos, to_pos) that is preceded
    (within 400 chars) by the chapter name prefix.  Using the LAST match
    avoids picking up the previous chapter's INTRODUCTION.

    Returns start-of-block position, or -1 if not found.
    """
    # Use at least 4 chars of name as anchor to reduce false matches
    anchor = re.escape(name_prefix[:4]) if len(name_prefix) >= 4 else re.escape(name_prefix)
    pat = re.compile(
        r'\b' + anchor + r'\S*.{0,400}INTRODUCTION\b',
        re.I | re.DOTALL
    )
    # Find all matches, take the rightmost one
    matches = list(pat.finditer(text, from_pos, to_pos))
    if not matches:
        return -1
    m = matches[-1]  # last (rightmost) match
    # Walk back to start of block (double-newline or from_pos)
    start = max(from_pos, m.start() - 50)
    block_start = text.rfind('\n\n', start, m.start())
    return block_start + 2 if block_start != -1 else m.start()


def find_chapter_boundaries(text, chapters_in_vol):
    """
    Return dict: chapter_num → start position in text.

    Strategy (applied in order for each chapter):
    1. "Chapter N [;:.] NAME_PREFIX" — canonical DJVU running header.
    2. "NAME_PREFIX[...] INTRODUCTION" — some short chapters have the chapter
       name as the only running header on intro pages (no chapter number).
    3. "Chapter N" without name — last resort.

    All candidates are searched forward from the previous chapter's start
    to skip false matches in the Table of Contents.  If candidate 1 finds
    a REFERENCES page (the intro pages were missed), we try candidate 2
    to recover an earlier true start.
    """
    boundaries = {}
    min_pos = 0

    for num in sorted(chapters_in_vol):
        dli_name, stem = CHAPTERS[num]
        name_prefix = re.escape(dli_name[:4])

        # --- Candidate 1: standard header ---
        # Allow up to 3 non-alphanumeric chars between "Chapter" and number
        # (handles OCR variants like "Chapter' 75", "Chaper 10", etc.)
        pat1 = re.compile(
            r'Chapter\W{0,3}' + str(num) + r'\s*[;:.\-,\']+\s*' + name_prefix,
            re.IGNORECASE
        )
        m1 = pat1.search(text, min_pos)

        # --- Candidate 2: NAME INTRODUCTION (no chapter number) ---
        # Match "NAME_START ... INTRODUCTION" within ~50 chars, after min_pos
        pat2 = re.compile(
            r'\b' + re.escape(dli_name[:5]) + r'.{0,50}INTRODUCTION\b',
            re.IGNORECASE | re.DOTALL
        )
        m2 = pat2.search(text, min_pos)

        # Pick the best candidate
        chosen = None
        if m1 and m2:
            # If m1 is a refs page AND m2 is earlier → prefer m2
            if _looks_like_refs_page(text, m1.start()) and m2.start() < m1.start():
                chosen = m2.start()
                print(f'  [INFO] Ch {num} ({stem}): intro-header at {chosen} '
                      f'preferred over refs-header at {m1.start()}', file=sys.stderr)
            else:
                chosen = min(m1.start(), m2.start())
        elif m1:
            chosen = m1.start()
        elif m2:
            chosen = m2.start()
            print(f'  [WARN] Ch {num} ({stem}): using NAME+INTRO fallback at {chosen}',
                  file=sys.stderr)
        else:
            # Last resort: Chapter N with any name
            pat3 = re.compile(
                r'Chapter\s+' + str(num) + r'\s*[;:.\-,]+\s*[A-Z]',
                re.IGNORECASE
            )
            m3 = pat3.search(text, min_pos)
            if m3:
                chosen = m3.start()
                print(f'  [WARN] Ch {num} ({stem}): last-resort match at {chosen}',
                      file=sys.stderr)
            else:
                print(f'  [ERROR] Ch {num} ({stem}): not found (min_pos={min_pos})',
                      file=sys.stderr)

        if chosen is not None:
            # Post-check: if the chosen start looks like an outline/refs page,
            # try to find an earlier INTRODUCTION within the lookback window
            # (handles chapters whose intro pages lack a clear Chapter N header)
            if _looks_like_refs_page(text, chosen, 400):
                prev_start = boundaries.get(num - 1, 0) if num > sorted(chapters_in_vol)[0] else 0
                intro_pos = _search_for_intro(text, prev_start, chosen, dli_name[:3])
                if intro_pos != -1 and intro_pos > prev_start:
                    print(f'  [INFO] Ch {num} ({stem}): moved start from {chosen} '
                          f'to intro at {intro_pos}', file=sys.stderr)
                    chosen = intro_pos

            boundaries[num] = chosen
            min_pos = chosen + 1

    return boundaries


def extract_chapters(text, chapters_in_vol):
    """Extract raw text for each chapter in a volume."""
    boundaries = find_chapter_boundaries(text, chapters_in_vol)
    sorted_nums = sorted(boundaries.keys())
    result = {}
    for i, num in enumerate(sorted_nums):
        start = boundaries[num]
        end = boundaries[sorted_nums[i+1]] if i+1 < len(sorted_nums) else len(text)
        result[num] = text[start:end]
    return result


# ── Section parsing ───────────────────────────────────────────────────────────

SECTION_MARKERS = {
    # Case-insensitive; handle OCR variants:
    # "OUTLINE OF TOPICS", "outline of topics", "OUTLINE 'OP 'TOPICS",
    # "OUTLINE'OF TOPICS", "OUTLINE :0F- TOPICS" → match OUTLINE + noise + TOPICS
    'outline':    re.compile(r"OUTLINE\W{0,15}\w{1,3}\W{0,10}TOPICS|OUTLINE\W{0,5}TOPICS", re.I),
    # "REFERENCES" (not preceded by CROSS, not followed by "For:" or topic-code)
    # Handle lowercase "references'" OCR variant
    'references': re.compile(
        r"(?<!CROSS[-\s])REFERENCES['']?\b(?!\s+For:)(?!\s+\d+[a-z])",
        re.I
    ),
    'crossrefs':  re.compile(r'\bCROSS[-\s]REFERENCES\b', re.I),
    'additional': re.compile(r'\bADDITIONAL\s+READINGS\b', re.I),
}


def find_section(text, key):
    """Return (start_idx, end_of_marker_idx) or (-1, -1) if not found."""
    m = SECTION_MARKERS[key].search(text)
    if m:
        return m.start(), m.end()
    return -1, -1


def parse_chapter_text(raw, chapter_num, stem):
    """
    Split raw chapter text into (intro, outline, refs, crossrefs) strings.
    Returns strings already stripped of running headers.
    """
    outline_pos, outline_end   = find_section(raw, 'outline')
    refs_pos,    refs_end      = find_section(raw, 'references')
    cross_pos,   cross_end     = find_section(raw, 'crossrefs')
    add_pos,     _             = find_section(raw, 'additional')

    # Determine section boundaries
    if outline_pos == -1:
        intro_raw   = raw
        outline_raw = ''
        refs_raw    = ''
        cross_raw   = ''
    else:
        intro_raw = raw[:outline_pos]
        if refs_pos != -1 and refs_pos > outline_pos:
            outline_raw = raw[outline_pos:refs_pos]
            if cross_pos != -1 and cross_pos > refs_pos:
                refs_raw  = raw[refs_pos:cross_pos]
                end_cross = add_pos if add_pos != -1 else len(raw)
                cross_raw = raw[cross_pos:end_cross]
            else:
                refs_raw  = raw[refs_pos:]
                cross_raw = ''
        elif cross_pos != -1 and cross_pos > outline_pos:
            outline_raw = raw[outline_pos:cross_pos]
            refs_raw    = ''
            end_cross   = add_pos if add_pos != -1 else len(raw)
            cross_raw   = raw[cross_pos:end_cross]
        else:
            outline_raw = raw[outline_pos:]
            refs_raw    = ''
            cross_raw   = ''

    # Clean each section
    intro  = strip_running_headers(intro_raw)
    outline = strip_running_headers(outline_raw)
    refs    = strip_running_headers(strip_refs_boilerplate(refs_raw))
    crossrefs = strip_running_headers(cross_raw)

    # Apply subtopic code fixes to outline and refs
    outline  = fix_outline_codes(outline)
    refs     = fix_outline_codes(refs)

    return intro, outline, refs, crossrefs


def fix_outline_codes(text):
    """Apply OCR corrections to subtopic code lines."""
    lines = text.splitlines()
    fixed = []
    for line in lines:
        # Match lines that look like subtopic codes, including OCR variants:
        # "1. TEXT", "1a. TEXT", "Sb. TEXT" (period after code)
        # "1 . TEXT" (space before period)
        # "3 A TEXT" or "4A TEXT" (uppercase letter instead of lowercase+period)
        if re.match(r'^\s{0,6}(?:[0-9SIjlO]\S{0,4}\.\s|[0-9]\s+\.\s|[0-9]\s+[A-Z]\s|[0-9][A-Z]\s)', line):
            line = fix_subtopic_code(line)
        fixed.append(line)
    return '\n'.join(fixed)


# ── Output formatting ─────────────────────────────────────────────────────────

def format_synt_file(chapter_num, stem, intro, outline, refs, crossrefs):
    """Produce the syntopicon_dli file content."""
    parts = [f'CHAPTER: {stem}\n']
    parts.append('INTRODUCTION\n')
    if intro:
        parts.append(intro + '\n')
    if outline:
        parts.append('\n' + outline + '\n')
    if refs:
        parts.append('\nREFERENCES\n')
        parts.append(refs + '\n')
    if crossrefs:
        parts.append('\n' + crossrefs + '\n')
    return '\n'.join(parts)


def format_mapa_chapter(chapter_num, stem, dli_name, refs):
    """Produce a chapter block for the Mapa file."""
    if not refs:
        return ''
    return f'Chapter {chapter_num}: {dli_name}\n\n{refs}\n'


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vol1', default='/tmp/syntopicon_vol1_dli.txt')
    ap.add_argument('--vol2', default='/tmp/syntopicon_vol2_dli.txt')
    ap.add_argument('--out-dir', default='/home/rodrigo/gbww')
    ap.add_argument('--no-mapa', action='store_true',
                    help='Skip generating mapa_dli/ files')
    ap.add_argument('--fallback-dir', default=None,
                    help='syntopicon_v18 dir to use as fallback for missing outlines')
    args = ap.parse_args()

    out_dir  = Path(args.out_dir)
    synt_dir = out_dir / 'syntopicon_dli'
    mapa_dir = out_dir / 'mapa_dli'
    fallback_dir = Path(args.fallback_dir) if args.fallback_dir else (out_dir / 'syntopicon_v18')
    synt_dir.mkdir(exist_ok=True)
    if not args.no_mapa:
        mapa_dir.mkdir(exist_ok=True)

    vol1_text = Path(args.vol1).read_text(encoding='utf-8', errors='replace')
    vol2_text = Path(args.vol2).read_text(encoding='utf-8', errors='replace')

    print('Extracting chapters...')

    vols = [
        (vol1_text, list(range(1,  51))),
        (vol2_text, list(range(51, 103))),
    ]

    stats = {'ok': 0, 'missing_outline': 0, 'missing_refs': 0}
    mapa_parts = {1: [], 2: []}

    for vol_idx, (text, chap_list) in enumerate(vols, start=1):
        print(f'  Volume {vol_idx} ({len(chap_list)} chapters)...')
        chapters = extract_chapters(text, chap_list)

        for num in chap_list:
            dli_name, stem = CHAPTERS[num]
            if num not in chapters:
                print(f'    [SKIP] Ch {num} {stem}: not found', file=sys.stderr)
                continue

            raw = chapters[num]
            intro, outline, refs, crossrefs = parse_chapter_text(raw, num, stem)

            if not outline:
                # Fallback: use outline from syntopicon_v18 for this chapter
                fallback_file = fallback_dir / f'{stem}.txt'
                if fallback_file.exists():
                    fb_text = fallback_file.read_text(encoding='utf-8', errors='replace')
                    fb_start = fb_text.find('OUTLINE OF TOPICS')
                    fb_end   = fb_text.find('CROSS-REFERENCES')
                    if fb_start != -1:
                        fb_end = fb_end if fb_end != -1 else len(fb_text)
                        outline = fb_text[fb_start:fb_end].strip()
                        print(f'    [INFO] Ch {num} {stem}: outline from syntopicon_v18 fallback')
                    else:
                        stats['missing_outline'] += 1
                        print(f'    [WARN] Ch {num} {stem}: no outline in DLI or fallback')
                else:
                    stats['missing_outline'] += 1
                    print(f'    [WARN] Ch {num} {stem}: no OUTLINE OF TOPICS found')
            if not refs:
                stats['missing_refs'] += 1

            content = format_synt_file(num, stem, intro, outline, refs, crossrefs)
            out_file = synt_dir / f'{stem}.txt'
            out_file.write_text(content, encoding='utf-8')
            stats['ok'] += 1

            if not args.no_mapa and refs:
                mapa_parts[vol_idx].append(format_mapa_chapter(num, stem, dli_name, refs))

    # Write Mapa files
    if not args.no_mapa:
        for vol_idx, parts in mapa_parts.items():
            mapa_file = mapa_dir / f'syntopicon_mapa_vol{vol_idx}.txt'
            mapa_file.write_text('\n\n'.join(parts), encoding='utf-8')
            print(f'  Mapa vol{vol_idx}: {len(parts)} chapters → {mapa_file}')

    print(f'\nDone: {stats["ok"]} files written to {synt_dir}')
    if stats['missing_outline']:
        print(f'  WARNING: {stats["missing_outline"]} chapters missing outline')
    if stats['missing_refs']:
        print(f'  NOTE: {stats["missing_refs"]} chapters without explicit REFERENCES section')


if __name__ == '__main__':
    main()
