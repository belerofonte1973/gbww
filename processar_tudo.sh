#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
LOG="processar_tudo.log"
exec > >(tee -a "$LOG") 2>&1

echo "=== Início: $(date) ==="

echo ""
echo "--- Baixando volumes ausentes ---"
./venv/bin/python3 gbww_download.py --output ./pdfs

echo ""
echo "--- Extraindo texto de todos os PDFs ---"
ls ./pdfs/*.pdf | grep -v "Volume 1 \|Volume 2 \|Volume 3 " | tr '\n' '\0' | xargs -0 ./venv/bin/python3 gbww_extract.py --output ./txts/ --skip-existing

echo ""
echo "=== Concluído: $(date) ==="
echo "TXTs gerados:"
ls ./txts/*.txt | wc -l
