#!/usr/bin/env bash
# Processa automaticamente novos PDFs à medida que o download avança.
# Pula volumes 1, 2, 3. Encerra quando o download terminar.

cd "$(dirname "$0")"
SKIP_PATTERN="Volume 1 -\|Volume 2 -\|Volume 3 -"

echo "=== Auto-extração iniciada: $(date) ==="

while true; do
    for pdf in pdfs/*.pdf; do
        [ -f "$pdf" ] || continue

        # Pula volumes excluídos
        echo "$pdf" | grep -q "$SKIP_PATTERN" && continue

        txt="txts/$(basename "${pdf%.pdf}.txt")"

        # Pula se TXT já existe e não está vazio
        [ -s "$txt" ] && continue

        # Pula se o arquivo ainda está sendo escrito (download em andamento)
        lsof "$pdf" > /dev/null 2>&1 && continue

        # Pula se extração já está rodando para este arquivo
        pgrep -f "gbww_extract.*$(basename "$pdf" | cut -c1-30)" > /dev/null && continue

        echo ">>> Iniciando: $(basename "$pdf")"
        ./venv/bin/python3 gbww_extract.py "$pdf" --output "$txt"
        echo ">>> Salvo: $(basename "$txt") ($(du -h "$txt" | cut -f1))"
    done

    # Encerra quando o download terminar e não houver mais PDFs pendentes
    if ! pgrep -f "gbww_download.py" > /dev/null; then
        pending=$(for pdf in pdfs/*.pdf; do
            [ -f "$pdf" ] || continue
            echo "$pdf" | grep -q "$SKIP_PATTERN" && continue
            txt="txts/$(basename "${pdf%.pdf}.txt")"
            [ -s "$txt" ] || echo "$pdf"
        done)
        if [ -z "$pending" ]; then
            echo "=== Todos os volumes processados: $(date) ==="
            break
        fi
    fi

    sleep 30
done
