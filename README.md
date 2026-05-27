# Great Books of the Western World — Text Extraction

Pipeline para baixar e extrair texto dos 54 volumes da coleção *Great Books of the Western World* (Encyclopædia Britannica, 1952) do [Internet Archive](https://archive.org/details/encyclopaediabritannicagreatbooksofthewesternworld), preservando referências alfanuméricas de página e coluna.

## Referências no texto extraído

Cada seção é prefixada com um marcador `[página+coluna]`:

| Marcador | Significado |
|----------|-------------|
| `[Xa]` | coluna esquerda da página X |
| `[Xb]` | coluna direita da página X |
| `[Xa]`…`[Xd]` | quadrantes sup-esq, inf-esq, sup-dir, inf-dir (flag `--quarters`) |

Volumes com layout de coluna única (ex: Pascal, Newton, Goethe, William James) produzem apenas `[Xa]` por página.

## Instalação

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
sudo apt install tesseract-ocr tesseract-ocr-eng
```

## Uso

```bash
# Verificar dependências
./venv/bin/python3 gbww_extract.py --check

# Baixar todos os 54 volumes (~XX GB)
./venv/bin/python3 gbww_download.py --output ./pdfs

# Listar volumes disponíveis
./venv/bin/python3 gbww_download.py --list

# Extrair um volume
./venv/bin/python3 gbww_extract.py pdfs/Volume\ 7\ -\ Plato.pdf

# Extrair todos os PDFs para txts/ (pula os já existentes)
./venv/bin/python3 gbww_extract.py ./pdfs/ --output ./txts/ --skip-existing

# Pipeline completo: baixar + extrair
./processar_tudo.sh

# Download e extração em paralelo (extrai à medida que baixa)
./venv/bin/python3 gbww_download.py --output ./pdfs &
./auto_extract.sh
```

### Opções do extrator

| Flag | Descrição |
|------|-----------|
| `--offset N` | ignora N páginas preliminares na numeração |
| `--lang eng+lat` | OCR com múltiplos idiomas Tesseract |
| `--quarters` | divide em 4 quadrantes por página |
| `--force-ocr` | força OCR mesmo em PDFs com texto nativo |
| `--skip-existing` | pula PDFs cujo TXT já existe |

## Dependências

- [PyMuPDF](https://pymupdf.readthedocs.io/) — leitura de PDFs e extração de texto nativo
- [Pillow](https://pillow.readthedocs.io/) — processamento de imagem para OCR
- [pytesseract](https://github.com/madmaze/pytesseract) + Tesseract OCR — OCR de páginas escaneadas
- [internetarchive](https://internetarchive.readthedocs.io/) — download do Internet Archive
- [tqdm](https://tqdm.github.io/) — barra de progresso
