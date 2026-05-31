#!/usr/bin/env python3
"""
Combina syntopicon_v18/ (intro + índice) com syntopicon-refs.txt (referências)
em ficheiros unificados por tópico, e gera CSVs para o Syntopicon-master.
"""

import re
import os
import csv
import json
from pathlib import Path

# Caminhos
REFS_FILE   = Path("/home/rodrigo/Downloads/syntopicon-refs.txt")
V18_DIR     = Path("/home/rodrigo/gbww/syntopicon_v18")
OUT_DIR     = Path("/home/rodrigo/gbww/syntopicon_combined")
CSV_DIR     = Path("/home/rodrigo/Downloads/Syntopicon-master/server/db/src/data/csv")

OUT_DIR.mkdir(exist_ok=True)
CSV_DIR.mkdir(parents=True, exist_ok=True)

# ── Mapeamento: nome do capítulo em refs.txt → nome do ficheiro em v18 ────────
CHAPTER_MAP = {
    "ANGEL":                     "Angels.txt",
    "ANIMAL":                    "Animals.txt",
    "ARISTOCRACY":               "Aristocracy.txt",
    "ART":                       "Art.txt",
    "ASTRONOMY":                 "Astronomy.txt",
    "BEAUTY":                    "Beauty.txt",
    "BEING":                     "Being.txt",
    "CAUSE":                     "Cause.txt",
    "CHANCE":                    "Chance.txt",
    "CHANGE":                    "Change.txt",
    "CITIZEN":                   "Citizen.txt",
    "CONSTITUTION":              "Constitution.txt",
    "COURAGE":                   "Courage.txt",
    "CUSTOM AND CONVENTION":     "Custom & Convention.txt",
    "DEFINITION":                "Definition.txt",
    "DEMOCRACY":                 "Democracy.txt",
    "DESIRE":                    "Desire.txt",
    "DIALECTIC":                 "Dialectic.txt",
    "DUTY":                      "Duty.txt",
    "EDUCATION":                 "Education.txt",
    "ELEMENT":                   "Element.txt",
    "EMOTION":                   "Emotion.txt",
    "ETERNITY":                  "Eternity.txt",
    "EVOLUTION":                 "Evolution.txt",
    "EXPERIENCE":                "Experience.txt",
    "FAMILY":                    "Family.txt",
    "FATE":                      "Fate.txt",
    "FORM":                      "Form.txt",
    "GOD":                       "God.txt",
    "GOOD AND EVIL":             "Good & Evil.txt",
    "GOVERNMENT":                "Government.txt",
    "HABIT":                     "Habit.txt",
    "HAPPINESS":                 "Happiness.txt",
    "HISTORY":                   "History.txt",
    "HONOR":                     "Honor.txt",
    "HYPOTHESIS":                "Hypothesis.txt",
    "IDEA":                      "Idea.txt",
    "IMMORTALITY":               "Immortality.txt",
    "INDUCTION":                 "Induction.txt",
    "INFINITY":                  "Infinity.txt",
    "JUDGEMENT":                 "Judgment.txt",
    "JUSTICE":                   "Justice.txt",
    "KNOWLEDGE":                 "Knowledge.txt",
    "LABOR":                     "Labor.txt",
    "LANGUAGE":                  "Language.txt",
    "LAW":                       "Law.txt",
    "LIBERTY":                   "Liberty.txt",
    "LIFE AND DEATH":            "Life & Death.txt",
    "LOGIC":                     "Logic.txt",
    "LOVE":                      "Love.txt",
    "MAN":                       "Man.txt",
    "MATHEMATICS":               "Mathematics.txt",
    "MATTER":                    "Matter.txt",
    "MECHANICS":                 "Mechanics.txt",
    "MEDICINE":                  "Medicine.txt",
    "MEMORY AND IMAGINATION":    "Memory & Imagination.txt",
    "METAPHYSICS":               "Metaphysics.txt",
    "MIND":                      "Mind.txt",
    "MONARCHY":                  "Monarchy.txt",
    "NATURE":                    "Nature.txt",
    "NECESSITY AND CONTINGENCY": "Necessity & Contingency.txt",
    "OLIGARCHY":                 "Oligarchy.txt",
    "ONE AND MANY":              "One & Many.txt",
    "OPINION":                   "Opinion.txt",
    "OPPOSITION":                "Opposition.txt",
    "PHILOSOPHY":                "Philosophy.txt",
    "PHYSICS":                   "Physics.txt",
    "PLEASURE AND PAIN":         "Pleasure & Pain.txt",
    "POETRY":                    "Poetry.txt",
    "PRINCIPLE":                 "Principle.txt",
    "PROGRESS":                  "Progress.txt",
    "PROPHECY":                  "Prophecy.txt",
    "PRUDENCE":                  "Prudence.txt",
    "PUNISHMENT":                "Punishment.txt",
    "QUALITY":                   "Quality.txt",
    "QUANTITY":                  "Quantity.txt",
    "REASONING":                 "Reasoning.txt",
    "RELATION":                  "Relation.txt",
    "RELIGION":                  "Religion.txt",
    "REVOLUTION":                "Revolution.txt",
    "RHETORIC":                  "Rhetoric.txt",
    "SAME AND OTHER":            "Same & Other.txt",
    "SCIENCE":                   "Science.txt",
    "SENSE":                     "Sense.txt",
    "SIGN AND SYMBOL":           "Sign & Symbol.txt",
    "SIN":                       "Sin.txt",
    "SLAVERY":                   "Slavery.txt",
    "SOUL":                      "Soul.txt",
    "SPACE":                     "Space.txt",
    "STATE":                     "State.txt",
    "TEMPERANCE":                "Temperance.txt",
    "THEOLOGY":                  "Theology.txt",
    "TIME":                      "Time.txt",
    "TRUTH":                     "Truth.txt",
    "TYRANNY":                   "Tyranny.txt",
    "UNIVERSAL AND PARTICULAR":  "Universal & Particular.txt",
    "VIRTUE AND VICE":           "Virtue & Vice.txt",
    "WAR AND PEACE":             "War & Peace.txt",
    "WEALTH":                    "Wealth.txt",
    "WILL":                      "Will.txt",
    "WISDOM":                    "Wisdom.txt",
    "WORLD":                     "World.txt",
}

# ── 1. Parse syntopicon-refs.txt ───────────────────────────────────────────────
def parse_refs(path):
    """
    Retorna:
      chapters = {chapter_num: {"name": str, "subtopics": [(id, desc, [ref_lines])]}
    """
    chapters = {}
    current_chapter_num  = None
    current_chapter_name = None
    current_sub_id   = None
    current_sub_desc = None
    current_refs     = []
    subtopics        = []

    chapter_re  = re.compile(r'^§==Chapter\s+(\d+)[:.  ]\s*(.+?)\s*==\s*$', re.IGNORECASE)
    subtopic_re = re.compile(r'^#(\S+)\.\s*(.*)')

    def flush_subtopic():
        if current_sub_id is not None:
            subtopics.append((current_sub_id, current_sub_desc, list(current_refs)))

    def flush_chapter():
        if current_chapter_num is not None:
            flush_subtopic()
            chapters[current_chapter_num] = {
                "name": current_chapter_name,
                "subtopics": list(subtopics),
            }

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip('\n')

            m = chapter_re.match(line)
            if m:
                flush_chapter()
                current_chapter_num  = int(m.group(1))
                current_chapter_name = m.group(2).strip().upper()
                current_sub_id = current_sub_desc = None
                current_refs = []
                subtopics = []
                continue

            m = subtopic_re.match(line)
            if m:
                flush_subtopic()
                current_sub_id   = m.group(1)
                current_sub_desc = m.group(2).strip()
                current_refs     = []
                continue

            # Reference line: starts with volume number or is continuation
            stripped = line.strip()
            if stripped and current_sub_id is not None:
                current_refs.append(stripped)

    flush_chapter()
    return chapters

# ── 2. Parse v18 ficheiro numa estrutura de secções ───────────────────────────
def parse_v18(path):
    """Divide o ficheiro v18 em: header, intro, outline, cross_refs, additional."""
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")

    # Secções standard no v18
    sections = {
        "header":     "",
        "intro":      "",
        "outline":    "",
        "cross_refs": "",
        "additional": "",
    }

    # Encontrar divisores
    outline_m    = re.search(r'\nOUTLINE OF TOPICS\s*\n', text, re.IGNORECASE)
    crossref_m   = re.search(r'\nCROSS-REFERENCES\s*\n', text, re.IGNORECASE)
    additional_m = re.search(r'\nADDITIONAL READINGS\s*\n', text, re.IGNORECASE)

    intro_start = 0
    outline_start = crossref_start = additional_start = len(text)

    if outline_m:
        outline_start = outline_m.start()
    if crossref_m:
        crossref_start = crossref_m.start()
    if additional_m:
        additional_start = additional_m.start()

    sections["intro"]      = text[intro_start:outline_start].strip()
    sections["outline"]    = text[outline_start:crossref_start].strip() if outline_m else ""
    sections["cross_refs"] = text[crossref_start:additional_start].strip() if crossref_m else ""
    sections["additional"] = text[additional_start:].strip() if additional_m else ""

    return sections

# ── 3. Construir ficheiro combinado ──────────────────────────────────────────
def build_combined(chapter_name, chapter_data, v18_sections):
    lines = []

    if v18_sections:
        lines.append(v18_sections["intro"])
        lines.append("")
        if v18_sections["outline"]:
            lines.append(v18_sections["outline"])
            lines.append("")
    else:
        lines.append(f"CHAPTER: {chapter_name.title()}\n")

    lines.append("REFERENCES")
    lines.append("=" * 60)
    lines.append("")

    for sub_id, sub_desc, refs in chapter_data["subtopics"]:
        # Cabeçalho do subtópico
        lines.append(f"{sub_id}. {sub_desc}")
        lines.append("")
        if refs:
            lines.extend(refs)
        else:
            lines.append("    [sem referências]")
        lines.append("")

    if v18_sections:
        if v18_sections["cross_refs"]:
            lines.append("")
            lines.append(v18_sections["cross_refs"])
        if v18_sections["additional"]:
            lines.append("")
            lines.append(v18_sections["additional"])

    return "\n".join(lines)

# ── 4. Gerar CSVs para Syntopicon-master ─────────────────────────────────────
def generate_csvs(chapters):
    # Estruturas para CSV
    authors   = {}   # last_name -> id
    works     = {}   # (author_id, title) -> id
    topics    = []
    subtopics = []
    references = []

    author_id_seq   = 1
    work_id_seq     = 1
    topic_id_seq    = 1
    subtopic_id_seq = 1
    ref_id_seq      = 1

    referrer_id = 1  # Mortimer Adler

    # Regex para linha de referência: "NN AUTHOR: Work, pages"
    ref_line_re = re.compile(
        r'^(\d+)\s+([A-Z][A-Z\s\-\'\.]+?):\s*(.+)$'
    )

    for ch_num in sorted(chapters.keys()):
        ch = chapters[ch_num]
        ch_name = ch["name"]
        topic_id = topic_id_seq
        topic_id_seq_val = topic_id

        subtopic_json = []
        for sub_id, sub_desc, _ in ch["subtopics"]:
            subtopic_json.append({"id": 0, "number": sub_id, "subtopic": sub_desc, "subtopics": []})

        topics.append({
            "id": topic_id,
            "referrer_id": referrer_id,
            "name": ch_name.title(),
            "subtopics": json.dumps(subtopic_json),
        })
        topic_id_seq += 1

        for sub_id, sub_desc, refs in ch["subtopics"]:
            subtopic_id = subtopic_id_seq
            subtopics.append({
                "id": subtopic_id,
                "topic_id": topic_id,
                "alt_id": sub_id,
                "referrer_id": referrer_id,
                "description": sub_desc[:299] if sub_desc else "(sem descrição)",
            })
            subtopic_id_seq += 1

            for ref_line in refs:
                m = ref_line_re.match(ref_line)
                if not m:
                    continue
                volume    = int(m.group(1))
                author_str = m.group(2).strip()
                rest      = m.group(3).strip()

                # Normalizar nome do autor
                author_key = author_str.upper()
                if author_key not in authors:
                    parts = author_str.title().split()
                    last  = parts[-1] if parts else author_str
                    first = " ".join(parts[:-1]) if len(parts) > 1 else None
                    authors[author_key] = {
                        "id": author_id_seq,
                        "last_name":  last,
                        "first_name": first,
                    }
                    author_id_seq += 1
                author_id = authors[author_key]["id"]

                # Tentar extrair título da obra e páginas
                work_title = rest.split(",")[0].strip() if "," in rest else rest[:80]
                pages_str  = rest[len(work_title):].strip().lstrip(",").strip()
                # Primeira página
                page_start = None
                page_end   = None
                page_m = re.search(r'(\d+[a-d]?)-?(\d+[a-d]?)?', pages_str)
                if page_m:
                    page_start = page_m.group(1)
                    page_end   = page_m.group(2)

                work_key = (author_id, work_title[:80])
                if work_key not in works:
                    works[work_key] = {
                        "id":        work_id_seq,
                        "volume_id": volume,
                        "author_id": author_id,
                        "author":    author_str.title(),
                        "title":     work_title[:99],
                        "translator": None,
                    }
                    work_id_seq += 1
                work_id = works[work_key]["id"]

                references.append({
                    "id":          ref_id_seq,
                    "topic_id":    topic_id,
                    "subtopic_id": subtopic_id,
                    "author_id":   author_id,
                    "work_id":     work_id,
                    "author":      author_str.title(),
                    "volume":      volume,
                    "page_start":  page_start or "",
                    "page_end":    page_end or "",
                    "notes":       pages_str[:299] if pages_str else "",
                    "summary_id":  ref_id_seq,
                    "excerpt_id":  ref_id_seq,
                    "referrer_id": referrer_id,
                    "upvotes":     0,
                    "downvotes":   0,
                })
                ref_id_seq += 1

    # Escrever CSVs
    def write_csv(filename, fieldnames, rows):
        out = CSV_DIR / filename
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
        print(f"  {out.name}: {len(rows)} linhas")

    # referrer.csv (só Adler)
    write_csv("referrer.csv", ["id","user_id","last_name","first_name"],
              [{"id":1,"user_id":1,"last_name":"Adler","first_name":"Mortimer"}])

    write_csv("author.csv", ["id","last_name","first_name"],
              [{"id": v["id"], "last_name": v["last_name"], "first_name": v["first_name"] or ""}
               for v in sorted(authors.values(), key=lambda x: x["id"])])

    work_rows = sorted(works.values(), key=lambda x: x["id"])
    write_csv("work.csv", ["id","volume_id","author_id","author","title","translator"],
              [{"id": w["id"], "volume_id": w["volume_id"], "author_id": w["author_id"],
                "author": w["author"], "title": w["title"], "translator": w["translator"] or ""}
               for w in work_rows])

    write_csv("topic.csv", ["id","referrer_id","name","subtopics"],
              topics)

    write_csv("subtopic.csv", ["id","topic_id","alt_id","referrer_id","description"],
              subtopics)

    # summary e excerpt: um registo vazio por referência (placeholder)
    write_csv("summary.csv", ["id","summary","alt_id"],
              [{"id": r["id"], "summary": "—", "alt_id": ""} for r in references])
    write_csv("excerpt.csv", ["id","alt_id","text","reference_id"],
              [{"id": r["id"], "alt_id": "", "text": "—", "reference_id": r["id"]} for r in references])

    write_csv("reference.csv",
              ["id","topic_id","subtopic_id","author_id","work_id","author","volume",
               "page_start","page_end","notes","summary_id","excerpt_id","referrer_id",
               "upvotes","downvotes"],
              references)

    print(f"\nTotais: {len(authors)} autores, {len(works)} obras, "
          f"{len(topics)} tópicos, {len(subtopics)} subtópicos, {len(references)} referências")


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("A fazer parse de syntopicon-refs.txt...")
    chapters = parse_refs(REFS_FILE)
    print(f"  {len(chapters)} capítulos lidos")

    print("\nA combinar com ficheiros v18 e a gerar ficheiros combinados...")
    matched = 0
    unmatched = []

    for ch_num in sorted(chapters.keys()):
        ch = chapters[ch_num]
        ch_name = ch["name"]

        filename = CHAPTER_MAP.get(ch_name)
        if not filename:
            unmatched.append(ch_name)
            filename = ch_name.title().replace(" And ", " & ") + ".txt"

        v18_path     = V18_DIR / filename
        v18_sections = parse_v18(v18_path)

        combined = build_combined(ch_name, ch, v18_sections)

        out_path = OUT_DIR / filename
        out_path.write_text(combined, encoding="utf-8")

        if v18_sections:
            matched += 1

    print(f"  {matched} ficheiros v18 combinados com sucesso")
    if unmatched:
        print(f"  Sem mapeamento (usou nome automático): {unmatched}")

    print("\nA gerar CSVs para Syntopicon-master...")
    generate_csvs(chapters)

    print("\nConcluído!")
    print(f"  Ficheiros combinados: {OUT_DIR}/")
    print(f"  CSVs: {CSV_DIR}/")


if __name__ == "__main__":
    main()
