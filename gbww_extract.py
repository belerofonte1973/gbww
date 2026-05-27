#!/usr/bin/env python3
"""
gbww_extract.py
Extrai texto dos PDFs da coleção Great Books of the Western World (1952)
preservando as referências alfanuméricas de página+coluna.

Sistema de referências:
  Modo padrão (2 colunas por página):
    [Xa] = coluna esquerda da página X
    [Xb] = coluna direita da página X

  Modo --quarters (4 quadrantes por página, referências tipo '157a-158c'):
    [Xa] = quadrante superior-esquerdo da página X
    [Xb] = quadrante inferior-esquerdo da página X
    [Xc] = quadrante superior-direito da página X
    [Xd] = quadrante inferior-direito da página X

Uso:
    python gbww_extract.py arquivo.pdf
    python gbww_extract.py ./pdfs/ --output ./txts/
    python gbww_extract.py arquivo.pdf --quarters
    python gbww_extract.py arquivo.pdf --offset 8 --lang eng+lat
    python gbww_extract.py arquivo.pdf --force-ocr
"""

import sys
import io
import re
import argparse
from pathlib import Path

try:
    import fitz  # pymupdf
except ImportError:
    print("Erro: pymupdf não encontrado. Instale: pip install pymupdf")
    sys.exit(1)

try:
    from PIL import Image, ImageFilter, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False


DPI = 400
GUTTER_RATIO = 0.02  # 2% da largura ignorado no centro (evita borda entre colunas)
MIN_TEXT_LEN = 80     # mínimo de caracteres para considerar página como texto nativo
MIN_LONG_WORD_RATIO = 0.20  # abaixo disso, OCR result é considerado página decorativa


def render_page(page, dpi=DPI):
    """Renderiza uma página PDF como imagem PIL."""
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
    img_bytes = pix.tobytes("png")
    return Image.open(io.BytesIO(img_bytes))


def split_image(img, quarters=False):
    """
    Divide a imagem em regiões para OCR.
    Retorna lista de (label_suffix, imagem_recortada).

    2 colunas: [('a', col_esq), ('b', col_dir)]
    4 quadrantes: [('a', sup_esq), ('b', inf_esq), ('c', sup_dir), ('d', inf_dir)]
    """
    w, h = img.size
    gutter = int(w * GUTTER_RATIO)
    mid_x = w // 2

    col_left  = img.crop((0,           0, mid_x - gutter, h))
    col_right = img.crop((mid_x + gutter, 0, w,           h))

    if not quarters:
        return [("a", col_left), ("b", col_right)]

    mid_y = h // 2
    return [
        ("a", col_left.crop((0, 0,     col_left.width,  mid_y))),
        ("b", col_left.crop((0, mid_y, col_left.width,  h))),
        ("c", col_right.crop((0, 0,    col_right.width, mid_y))),
        ("d", col_right.crop((0, mid_y, col_right.width, h))),
    ]


def clean_text(text):
    """
    Limpa artefatos comuns de OCR e formatação de colunas impressas:
    - Remove prefixo '_ ' de parágrafos (artefato OCR de indentação)
    - Junta hifenização de linha: 'pala-\nvra' → 'palavra'
    - Remove linhas com lixo OCR (≥ 60% de caracteres não-alfanuméricos,
      exceto linhas muito curtas que podem ser legítimas)
    """
    # Remove prefixo '_ ' ou '_\n' usado como indentação escaneada
    text = re.sub(r'(?m)^_\s+', '', text)

    # Junta hifenização: palavra- + quebra de linha + minúscula → palavra
    text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)

    # Remove linhas com lixo OCR: > 60% não-alfanumérico e comprimento > 8
    def is_garbage(line):
        stripped = line.strip()
        if len(stripped) <= 8:
            return False
        alnum = sum(c.isalnum() or c.isspace() for c in stripped)
        return alnum / len(stripped) < 0.4

    lines = text.splitlines()
    lines = [l for l in lines if not is_garbage(l)]
    return "\n".join(lines)


def preprocess_for_ocr(img):
    """
    Melhora a qualidade da imagem antes do OCR:
    - Denoising com filtro mediano (remove pontos isolados)
    - Auto-contraste (normaliza histograma)
    - Sharpening (afia bordas dos caracteres)
    """
    img = img.convert("L")
    img = img.filter(ImageFilter.MedianFilter(size=3))
    img = ImageOps.autocontrast(img, cutoff=2)
    img = img.filter(ImageFilter.SHARPEN)
    return img


def is_decorative_ocr(text):
    """
    Detecta páginas decorativas/ilustradas pelo padrão do resultado OCR.
    Páginas decorativas produzem fragmentos curtos; páginas com texto real
    produzem palavras longas mesmo com erros de OCR.
    Considera decorativa se < 30% das 'palavras' têm 4+ caracteres alpha.
    """
    words = re.findall(r'[a-zA-Z]+', text)
    if len(words) < 8:
        return True
    long_words = [w for w in words if len(w) >= 4]
    return len(long_words) / len(words) < MIN_LONG_WORD_RATIO


def ocr_image(img, lang="eng"):
    """Executa OCR numa imagem PIL e retorna o texto limpo."""
    if not HAS_TESSERACT:
        return "[OCR não disponível — instale pytesseract e tesseract]"
    img = preprocess_for_ocr(img)
    # --psm 4: coluna única de texto (adequado para colunas já recortadas)
    config = "--psm 4 --oem 1"
    text = pytesseract.image_to_string(img, lang=lang, config=config)
    text = clean_text(text.strip())
    if is_decorative_ocr(text):
        return "[página ilustrada]"
    return text


def is_text_pdf(page):
    """Retorna True se a página tem texto nativo suficiente para não precisar de OCR."""
    return len(page.get_text().strip()) >= MIN_TEXT_LEN


def _is_single_column(blocks, w):
    """
    Retorna True se a página parece ser de coluna única.
    Critério: > 40% dos blocos de texto têm centro horizontal dentro da
    zona de gutter (±2% em torno do meio da página), o que indica que
    os blocos se estendem pela largura total e não há duas colunas reais.
    """
    gutter = w * GUTTER_RATIO
    mid_x = w / 2
    text_blocks = [(x0, x1) for x0, y0, x1, y1, text, _, btype in blocks
                   if btype == 0 and text.strip()]
    if not text_blocks:
        return False
    in_gutter = sum(1 for x0, x1 in text_blocks
                    if mid_x - gutter <= (x0 + x1) / 2 <= mid_x + gutter)
    return in_gutter / len(text_blocks) > 0.40


def extract_text_columns_native(page, quarters=False):
    """
    Extrai texto de uma página com texto nativo (PDF não-escaneado)
    dividindo os blocos por posição x.
    Retorna lista de (label_suffix, texto).

    Detecta automaticamente páginas de coluna única: se > 40% dos blocos
    tiver centro no gutter, trata a página inteira como coluna 'a'.
    """
    w = page.rect.width
    h = page.rect.height
    gutter = w * GUTTER_RATIO
    mid_x = w / 2

    blocks = page.get_text("blocks", sort=True)
    # blocks: (x0, y0, x1, y1, text, block_no, block_type)

    # Página de coluna única: coloca tudo em 'a', ignora split
    if _is_single_column(blocks, w):
        items = [(y0, text.strip()) for x0, y0, x1, y1, text, _, btype in blocks
                 if btype == 0 and text.strip()]
        items.sort(key=lambda x: x[0])
        return [("a", clean_text("\n".join(t for _, t in items)))]

    buckets = {"a": [], "b": [], "c": [], "d": []} if quarters else {"a": [], "b": []}

    for x0, y0, x1, y1, text, _, btype in blocks:
        if btype != 0 or not text.strip():
            continue
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2

        if cx < mid_x - gutter:
            col = "left"
        elif cx > mid_x + gutter:
            col = "right"
        else:
            continue  # bloco na margem central — ignora

        if not quarters:
            key = "a" if col == "left" else "b"
            buckets[key].append((y0, text.strip()))
        else:
            mid_y = h / 2
            if col == "left":
                key = "a" if cy < mid_y else "b"
            else:
                key = "c" if cy < mid_y else "d"
            buckets[key].append((y0, text.strip()))

    result = []
    for key in (["a", "b", "c", "d"] if quarters else ["a", "b"]):
        items = sorted(buckets[key], key=lambda x: x[0])
        result.append((key, clean_text("\n".join(t for _, t in items))))
    return result


def process_page(page, book_page, lang="eng", quarters=False, force_ocr=False):
    """
    Processa uma página e retorna string formatada com marcadores de referência.
    Formato: [Xa]\ntexto\n\n[Xb]\ntexto\n...
    """
    use_ocr = force_ocr or not is_text_pdf(page)

    if use_ocr:
        if not HAS_PIL:
            return f"[{book_page}a]\n[Pillow não instalado]\n"
        img = render_page(page)
        regions = split_image(img, quarters=quarters)
        sections = [(label, ocr_image(img_region, lang=lang))
                    for label, img_region in regions]
    else:
        sections = extract_text_columns_native(page, quarters=quarters)

    parts = []
    for label, text in sections:
        marker = f"[{book_page}{label}]"
        parts.append(f"{marker}\n{text}")
    return "\n\n".join(parts)


def process_pdf(pdf_path, output_path=None, page_offset=0,
                lang="eng", quarters=False, force_ocr=False, verbose=True):
    """
    Processa um PDF inteiro e grava arquivo TXT com referências alfanuméricas.
    page_offset: número de páginas preliminares do PDF sem numeração de livro
                 (ex: 8 → página 1 do PDF = página 1+0 do livro, PDF página 9 = livro 1)
    """
    pdf_path = Path(pdf_path)
    if output_path is None:
        txts_dir = pdf_path.parent.parent / "txts"
        if txts_dir.is_dir():
            output_path = txts_dir / pdf_path.with_suffix(".txt").name
        else:
            output_path = pdf_path.with_suffix(".txt")
    output_path = Path(output_path)

    if verbose:
        print(f"\nProcessando: {pdf_path.name}")

    doc = fitz.open(str(pdf_path))
    total = len(doc)
    parts = []

    iterator = range(total)
    if HAS_TQDM and verbose:
        iterator = tqdm(iterator, desc="Páginas", unit="pág")

    for i in iterator:
        page = doc[i]
        book_page = i + 1 - page_offset
        if book_page < 1:
            # Página preliminar — extrai sem marcador ou pula
            continue
        section = process_page(page, book_page, lang=lang,
                                quarters=quarters, force_ocr=force_ocr)
        parts.append(section)

    doc.close()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n\n".join(parts), encoding="utf-8")

    if verbose:
        print(f"Salvo: {output_path}  ({len(parts)} seções)")
    return output_path


def check_dependencies():
    """Verifica e reporta dependências disponíveis."""
    print("=== Verificação de dependências ===")
    ok = True

    print(f"  pymupdf (fitz):    {'OK' if 'fitz' in sys.modules else 'FALTANDO — pip install pymupdf'}")

    if HAS_PIL:
        print("  Pillow:            OK")
    else:
        print("  Pillow:            FALTANDO — pip install Pillow")
        ok = False

    if HAS_TESSERACT:
        try:
            ver = pytesseract.get_tesseract_version()
            print(f"  pytesseract:       OK (Tesseract {ver})")
            langs = pytesseract.get_languages()
            print(f"  Idiomas Tesseract: {', '.join(langs)}")
        except Exception as e:
            print(f"  pytesseract:       Instalado mas Tesseract não encontrado ({e})")
            ok = False
    else:
        print("  pytesseract:       FALTANDO — pip install pytesseract")
        print("  Tesseract OCR:     instale com: sudo apt install tesseract-ocr tesseract-ocr-eng")
        ok = False

    if not ok:
        print("\nAlgumas dependências estão faltando. OCR pode não funcionar.")
        print("Instale tudo com: pip install -r requirements.txt")
        print("                  sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-por")
    else:
        print("\nTodas as dependências OK.")
    return ok


def main():
    parser = argparse.ArgumentParser(
        description="Extrai texto dos PDFs da coleção Great Books of the Western World "
                    "com marcadores de referência alfanumérica (ex: [157a], [157b]).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python gbww_extract.py vol07.pdf
  python gbww_extract.py ./pdfs/ --output ./txts/ --lang eng
  python gbww_extract.py vol08.pdf --quarters           # referências a/b/c/d por página
  python gbww_extract.py vol08.pdf --offset 10          # ignora 10 páginas preliminares
  python gbww_extract.py vol08.pdf --lang eng+lat+grc   # OCR com múltiplos idiomas
  python gbww_extract.py --check                        # verifica dependências instaladas
        """
    )
    parser.add_argument("input", nargs="*", help="PDF(s) ou diretório com PDFs")
    parser.add_argument("-o", "--output", help="Arquivo TXT de saída ou diretório")
    parser.add_argument(
        "--offset", type=int, default=0,
        help="Páginas PDF preliminares a ignorar na numeração (padrão: 0)"
    )
    parser.add_argument(
        "--lang", default="eng",
        help="Idioma(s) para OCR no formato Tesseract (padrão: eng). "
             "Ex: eng+lat, por+eng, grc"
    )
    parser.add_argument(
        "--quarters", action="store_true",
        help="Divide cada página em 4 quadrantes (a/b/c/d) em vez de 2 colunas (a/b)"
    )
    parser.add_argument(
        "--force-ocr", action="store_true",
        help="Forçar OCR mesmo em PDFs com texto nativo embutido"
    )
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="Pula PDFs cujo TXT de saída já existe"
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Verifica as dependências instaladas e sai"
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suprime saída de progresso"
    )

    args = parser.parse_args()

    if args.check:
        check_dependencies()
        return

    if not args.input:
        parser.print_help()
        return

    # Coleta PDFs
    pdfs = []
    for inp in args.input:
        p = Path(inp)
        if p.is_dir():
            pdfs.extend(sorted(p.glob("*.pdf")))
        elif p.suffix.lower() == ".pdf":
            pdfs.append(p)
        else:
            print(f"Ignorando (não é PDF): {inp}")

    if not pdfs:
        print("Nenhum PDF encontrado.")
        sys.exit(1)

    output_is_dir = args.output and (Path(args.output).is_dir() or len(pdfs) > 1)

    for pdf in pdfs:
        if output_is_dir:
            out = Path(args.output) / pdf.with_suffix(".txt").name
        elif args.output:
            out = Path(args.output)
        else:
            out = None

        if args.skip_existing:
            check = out if out else (
                (pdf.parent.parent / "txts" / pdf.with_suffix(".txt").name)
                if (pdf.parent.parent / "txts").is_dir()
                else pdf.with_suffix(".txt")
            )
            if check.exists():
                print(f"Pulando (já existe): {check.name}")
                continue

        process_pdf(
            pdf,
            output_path=out,
            page_offset=args.offset,
            lang=args.lang,
            quarters=args.quarters,
            force_ocr=args.force_ocr,
            verbose=not args.quiet,
        )

    print("\nConcluído.")


if __name__ == "__main__":
    main()
