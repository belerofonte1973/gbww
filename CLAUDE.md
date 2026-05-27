# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: GBWW Text Extraction

The main active project is `/home/rodrigo/gbww/` — a pipeline to download and extract text from the 54-volume *Great Books of the Western World* (1952 Encyclopædia Britannica edition) sourced from the Internet Archive.

### Directory layout

```
gbww/
  gbww_download.py    # downloads PDFs from Internet Archive
  gbww_extract.py     # extracts text with column-reference markers
  auto_extract.sh     # watches for new PDFs and extracts as downloads arrive
  processar_tudo.sh   # one-shot: download all + extract all
  requirements.txt
  venv/               # Python virtualenv
  pdfs/               # 54 downloaded PDFs
  txts/               # extracted TXTs (54 volumes complete)
```

### Running the scripts

Always use the venv:

```bash
# Verify dependencies
./venv/bin/python3 gbww_extract.py --check

# Extract a single PDF
./venv/bin/python3 gbww_extract.py pdfs/<volume>.pdf

# Extract all PDFs to txts/ (skipping already done)
./venv/bin/python3 gbww_extract.py ./pdfs/ --output ./txts/ --skip-existing

# Download missing PDFs then extract all
./processar_tudo.sh

# Download PDFs and auto-extract as files arrive
./venv/bin/python3 gbww_download.py --output ./pdfs &
./auto_extract.sh
```

Install dependencies:

```bash
pip install -r requirements.txt
sudo apt install tesseract-ocr tesseract-ocr-eng
```

### Reference system in output TXTs

Each extracted section is prefixed with an alphanumeric page+column marker:

- `[Xa]` / `[Xb]` — left/right columns of page X (default, 2 columns)
- `[Xa]` / `[Xb]` / `[Xc]` / `[Xd]` — four quadrants of page X (`--quarters` flag)

Use `--offset N` when a PDF has N unnumbered preliminary pages before the book's page 1.

### PDF types and OCR logic

`gbww_extract.py` auto-detects whether a page has native embedded text (≥ 80 chars) and falls back to Tesseract OCR for scanned pages. Key constants:

- `DPI = 400` — render resolution for OCR
- `GUTTER_RATIO = 0.02` — fraction of page width ignored at the center spine
- `MIN_TEXT_LEN = 80` — threshold for native-text detection
- `MIN_LONG_WORD_RATIO = 0.20` — below this, an OCR result is treated as a decorative/illustration page

### Single-column detection

Some volumes (33 Pascal, 34 Newton/Huygens, 47 Goethe, 53 William James) use a single-column layout instead of the two-column standard. Without detection, their text blocks — centered at the midpoint — fall in the gutter and are discarded, losing 30–84% of the text.

The fix (in `_is_single_column`): if >40% of a page's text blocks have their horizontal center within the gutter zone, the page is treated as single-column and all blocks are extracted into column `[Xa]` without splitting. Two-column pages produce `[Xa]` and `[Xb]` as usual.

### Internet Archive source

Internet Archive identifier: `encyclopaediabritannicagreatbooksofthewesternworld`

Volumes 2 and 3 are intentionally skipped in the batch scripts (`auto_extract.sh`, `processar_tudo.sh`) — they are the Syntopicon index volumes and were extracted manually. Volume 1 was also extracted manually and exists under a short filename (`vol1-great-conversation.txt`) in addition to the full-name TXT.
