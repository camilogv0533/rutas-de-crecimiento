#!/usr/bin/env python3
"""One-off: traduce campos narrativos de retiros a español en la DB.

Los primeros retiros se scrapearon con el prompt viejo ("original language"),
así que el texto quedó en inglés. El sitio es español → mezcla. Este script
traduce los campos human-facing al español editorial (voice.md) y actualiza la DB.
Después correr build_export.py para regenerar los .md.

Usage:
  python scripts/translate_es.py            # todos los activos con texto en inglés
  python scripts/translate_es.py --all      # fuerza re-traducción de todos
"""
import argparse
import json
import sqlite3
from pathlib import Path

from _llm import SONNET, call, cost_of, log_run, now_iso

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "retreats.db"
VOICE = (ROOT / ".claude" / "skills" / "brand_context" / "voice.md").read_text(encoding="utf-8")

# Campos narrativos human-facing a traducir. NO: title, host_name, códigos.
FIELDS = [
    "tagline", "intro", "what_unique", "who_for", "what_youll_learn",
    "sample_itinerary", "included", "not_included", "accommodation",
    "food", "travel_logistics", "accessibility", "certifications",
]

TOOL = {
    "name": "save_es",
    "description": "Devuelve los campos traducidos al español. Mantén null donde la entrada sea null. Preserva listas (una por línea) y nombres propios.",
    "input_schema": {
        "type": "object",
        "properties": {f: {"type": ["string", "null"]} for f in FIELDS},
        "required": FIELDS,
    },
}

SYSTEM = (
    "Eres el editor de Rutas de Crecimiento. Traduces texto de retiros al español "
    "natural y editorial, fiel a la voz de marca de abajo. Reglas:\n"
    "- Traduce el SIGNIFICADO, no palabra por palabra. Español de calidad publicable.\n"
    "- NO traduzcas nombres propios (lugares, hosts, marcas), pero el resto sí.\n"
    "- Si un campo ya está en español, devuélvelo tal cual.\n"
    "- Si un campo es null o vacío, devuelve null.\n"
    "- Preserva la estructura: si es una lista, una línea por ítem.\n"
    "- Sin emojis. Sin exclamaciones múltiples. Tono adulto profesional.\n\n"
    "--- VOICE.MD ---\n" + VOICE
)


def looks_spanish(text: str) -> bool:
    if not text:
        return True
    t = text.lower()
    es_markers = sum(w in t for w in (" el ", " la ", " los ", " las ", " para ", " con ", " una ", " que ", " del ", " y ", " en "))
    en_markers = sum(w in t for w in (" the ", " and ", " your ", " you ", " with ", " for ", " this ", " will ", " our "))
    return es_markers >= en_markers


def translate_row(row: dict) -> tuple[dict, object]:
    payload = {f: row.get(f) for f in FIELDS}
    user = (
        "Traduce al español estos campos de un retiro. Devuelve TODOS llamando save_es.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    resp = call(
        model=SONNET,
        system=SYSTEM,
        messages=[{"role": "user", "content": user}],
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "save_es"},
        max_tokens=4096,
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "save_es":
            return block.input, resp.usage
    raise RuntimeError("No save_es call")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="re-traduce todos, no solo los que parecen inglés")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM retreats WHERE status='active'")]

    started = now_iso()
    total_cost = 0.0
    tok_in = tok_out = 0
    updated = 0
    for r in rows:
        # Decide si necesita traducción: algún campo narrativo no-español.
        needs = args.all or any(
            (r.get(f) and not looks_spanish(str(r.get(f)))) for f in FIELDS
        )
        if not needs:
            print(f"  skip (ya español): {r['slug']}")
            continue
        es, usage = translate_row(r)
        sets, vals = [], []
        for f in FIELDS:
            if es.get(f) is not None and es.get(f) != r.get(f):
                sets.append(f"{f}=?")
                vals.append(es[f])
        if sets:
            vals.append(r["id"])
            conn.execute(f"UPDATE retreats SET {', '.join(sets)} WHERE id=?", vals)
            conn.commit()
            updated += 1
        c = cost_of(SONNET, usage)
        total_cost += c
        tok_in += getattr(usage, "input_tokens", 0)
        tok_out += getattr(usage, "output_tokens", 0)
        print(f"  ok: {r['slug']}  (${c:.4f})")

    log_run("translate_es", started, now_iso(), tok_in, tok_out, total_cost, updated, "success")
    print(f"\nTraducidos: {updated}/{len(rows)}  costo total: ${total_cost:.4f}")


if __name__ == "__main__":
    main()
