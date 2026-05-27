#!/usr/bin/env python3
"""
gbww_download.py
Baixa os volumes da coleção Great Books of the Western World (1952)
do Internet Archive em formato PDF.

Uso:
    python gbww_download.py --list                 # lista volumes disponíveis
    python gbww_download.py --output ./pdfs        # baixa todos os 54 volumes
    python gbww_download.py --volumes 7 8 9        # baixa volumes específicos
"""

import re
import sys
import argparse
from pathlib import Path

try:
    import internetarchive as ia
except ImportError:
    print("Instale: pip install internetarchive")
    sys.exit(1)

MAIN_ID = "encyclopaediabritannicagreatbooksofthewesternworld"

# Regex para extrair número do volume do nome do arquivo
# Ex: "...Volume 8 - Aristotle I.pdf" → 8
VOL_RE = re.compile(r'Volume\s+(\d+)', re.IGNORECASE)


def parse_volume_number(filename):
    """Extrai o número do volume do nome do arquivo. Retorna None se não encontrar."""
    m = VOL_RE.search(filename)
    return int(m.group(1)) if m else None


def get_pdf_list(identifier=MAIN_ID):
    """Retorna lista de dicts {vol, name, size} para todos os PDFs do item."""
    try:
        item = ia.get_item(identifier)
    except Exception as e:
        print(f"Erro ao acessar {identifier}: {e}")
        sys.exit(1)

    pdfs = []
    for f in item.files:
        name = f.get("name", "")
        if not name.lower().endswith(".pdf"):
            continue
        vol = parse_volume_number(name)
        size = int(f.get("size", 0))
        pdfs.append({"vol": vol, "name": name, "size": size})

    # Ordena por número de volume (None vai para o fim)
    pdfs.sort(key=lambda x: (x["vol"] is None, x["vol"] or 0))
    return pdfs


def list_available():
    """Imprime tabela com todos os PDFs disponíveis."""
    pdfs = get_pdf_list()
    if not pdfs:
        print("Nenhum PDF encontrado.")
        return

    print(f"\n{'Vol':<5} {'Arquivo':<72} {'Tamanho':>10}")
    print("-" * 90)
    total_bytes = 0
    for f in pdfs:
        vol_label = str(f["vol"]) if f["vol"] else "?"
        size_mb = f"{f['size'] / 1_048_576:.1f} MB" if f["size"] else "?"
        total_bytes += f["size"]
        print(f"{vol_label:<5} {f['name']:<72} {size_mb:>10}")

    total_gb = total_bytes / 1_073_741_824
    print(f"\nTotal: {len(pdfs)} volumes  |  {total_gb:.1f} GB")


def download_volumes(output_dir, volume_filter=None):
    """
    Baixa os PDFs para output_dir.
    volume_filter: conjunto de ints com os volumes desejados, ou None para todos.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pdfs = get_pdf_list()

    if volume_filter:
        selected = [f for f in pdfs if f["vol"] in volume_filter]
        missing = volume_filter - {f["vol"] for f in selected}
        if missing:
            print(f"Aviso: volumes não encontrados no item: {sorted(missing)}")
    else:
        selected = pdfs

    if not selected:
        print("Nenhum volume para baixar.")
        return

    total_gb = sum(f["size"] for f in selected) / 1_073_741_824
    print(f"\nDiretório de saída: {output_dir.resolve()}")
    print(f"Volumes a baixar: {len(selected)}  |  {total_gb:.1f} GB\n")

    for i, f in enumerate(selected, 1):
        name = f["name"]
        dest = output_dir / name
        vol_label = f"Vol {f['vol']}" if f["vol"] else name

        if dest.exists():
            print(f"[{i}/{len(selected)}] {vol_label}: já existe, pulando.")
            continue

        size_mb = f"{f['size'] / 1_048_576:.1f} MB" if f["size"] else "?"
        print(f"[{i}/{len(selected)}] {vol_label} ({size_mb}) ...", flush=True)
        try:
            ia.download(
                MAIN_ID,
                files=[name],
                destdir=str(output_dir),
                no_directory=True,
                verbose=False,
            )
            print(f"           Salvo: {dest.name}")
        except Exception as e:
            print(f"           Erro: {e}")

    print("\nConcluído.")


def main():
    parser = argparse.ArgumentParser(
        description="Baixa os PDFs da coleção Great Books of the Western World do Internet Archive.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python gbww_download.py --list
  python gbww_download.py --output ./pdfs
  python gbww_download.py --output ./pdfs --volumes 7 8 9
        """
    )
    parser.add_argument(
        "--list", action="store_true",
        help="Lista os volumes disponíveis sem baixar"
    )
    parser.add_argument(
        "--volumes", nargs="+", type=int, metavar="N",
        help="Números dos volumes a baixar (ex: 7 8 9). Sem este flag, baixa todos."
    )
    parser.add_argument(
        "--output", default="./pdfs",
        help="Diretório de saída (padrão: ./pdfs)"
    )

    args = parser.parse_args()

    if args.list:
        list_available()
    else:
        download_volumes(
            args.output,
            volume_filter=set(args.volumes) if args.volumes else None,
        )


if __name__ == "__main__":
    main()
