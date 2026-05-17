#!/usr/bin/env python3
"""CEO de Operaciones — evalúa calidad de retiros y enriquece datos faltantes.

Corre cada martes. Revisa retiros con reviewed_by_us=0, evalúa calidad,
aprueba los buenos automáticamente, enriquece what_unique/who_for si faltan.
Genera reporte en data/ops_report_YYYY-MM-DD.md

Usage:
  python scripts/ops_agent.py
  python scripts/ops_agent.py --dry-run
  python scripts/ops_agent.py --limit 5
"""
import argparse
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from _llm import HAIKU, SONNET, call, cost_of, log_run, now_iso, BudgetExceeded

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "retreats.db"
QUALITY_THRESHOLD = 65


def fetch_pending(conn: sqlite3.Connection, limit: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, slug, title, tagline, location_city, location_country, duration_days, "
        "price_usd_from, what_unique, who_for, skills_raw "
        "FROM retreats WHERE reviewed_by_us=0 AND status='active' "
        "ORDER BY scraped_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [
        {"id": r[0], "slug": r[1], "title": r[2], "tagline": r[3],
         "city": r[4], "country": r[5], "days": r[6], "price": r[7],
         "what_unique": r[8], "who_for": r[9], "skills_raw": r[10]}
        for r in rows
    ]


def evaluate_retreat(r: dict) -> tuple[int, str, float, int, int]:
    fields = {
        "title": r["title"],
        "tagline": r["tagline"],
        "location": f"{r['city']}, {r['country']}",
        "duration_days": r["days"],
        "price_usd": r["price"],
        "what_unique": (r["what_unique"] or "")[:400],
        "who_for": (r["who_for"] or "")[:300],
    }
    prompt = (
        f"Evalúa la calidad de estos datos de un retiro:\n{json.dumps(fields, ensure_ascii=False, indent=2)}\n\n"
        f"Devuelve SOLO JSON: {{\"score\": <0-100>, \"approve\": <true/false>, \"reason\": \"<15 palabras>\", "
        f"\"missing\": [\"campo1\", ...]}}\n"
        f"score >= {QUALITY_THRESHOLD} = approve. Criterios: datos completos (40%), diferenciación (35%), precio presente (25%)."
    )
    resp = call(HAIKU, "Eres un curador de retiros experienciales de alta calidad.", [
        {"role": "user", "content": prompt}
    ], max_tokens=300)
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    try:
        m = re.search(r'\{.*\}', text, re.DOTALL)
        data = json.loads(m.group()) if m else {}
        score = int(data.get("score", 0))
        approve = bool(data.get("approve", False))
        reason = data.get("reason", "")
    except Exception:
        score, approve, reason = 0, False, "parse error"
    return score, reason, cost_of(HAIKU, resp.usage), resp.usage.input_tokens, resp.usage.output_tokens


def enrich_retreat(r: dict) -> tuple[dict, float, int, int]:
    missing_fields = []
    if not r["what_unique"]:
        missing_fields.append("what_unique")
    if not r["who_for"]:
        missing_fields.append("who_for")
    if not missing_fields:
        return {}, 0.0, 0, 0

    prompt = (
        f"Retiro: {r['title']}\nUbicación: {r['city']}, {r['country']}\n"
        f"Duración: {r['days']} días\nPrecio: ${r['price']} USD\n"
        f"Tagline: {r['tagline'] or 'N/A'}\n\n"
        f"Genera estos campos faltantes en JSON:\n"
        + ("- what_unique: 2-3 frases describiendo qué hace único este retiro vs otros similares. Específico, sin clichés.\n" if "what_unique" in missing_fields else "")
        + ("- who_for: 1-2 frases describiendo el perfil ideal del participante. Concreto (ej: 'Líderes de equipos +10 personas...').\n" if "who_for" in missing_fields else "")
        + "\nDevuelve SOLO el JSON con los campos generados."
    )
    resp = call(SONNET, "Eres un curador de retiros experienciales. Escribe en español, tono editorial-personal, cero clichés.", [
        {"role": "user", "content": prompt}
    ], max_tokens=600)
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    try:
        m = re.search(r'\{.*\}', text, re.DOTALL)
        enriched = json.loads(m.group()) if m else {}
    except Exception:
        enriched = {}
    return enriched, cost_of(SONNET, resp.usage), resp.usage.input_tokens, resp.usage.output_tokens


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    dry_run = args.dry_run

    started = now_iso()
    total_cost = 0.0
    total_in = total_out = 0
    items = 0
    errors = []
    report_lines = [f"# Ops Report — {datetime.utcnow().strftime('%Y-%m-%d')}\n"]

    conn = sqlite3.connect(DB_PATH)
    try:
        pending = fetch_pending(conn, args.limit)
        print(f"Retiros pendientes de revisión: {len(pending)}")
        report_lines.append(f"Revisados: {len(pending)}\n")

        approved = []
        enriched_count = 0

        for r in pending:
            try:
                score, reason, c, ti, to = evaluate_retreat(r)
                total_cost += c; total_in += ti; total_out += to
                print(f"  [{score}/100] {r['title'][:55]} — {reason}")

                if score >= QUALITY_THRESHOLD:
                    if not dry_run:
                        conn.execute("UPDATE retreats SET reviewed_by_us=1 WHERE id=?", (r["id"],))
                    approved.append(r["title"])
                    items += 1

                    enriched, c2, ti2, to2 = enrich_retreat(r)
                    if enriched:
                        total_cost += c2; total_in += ti2; total_out += to2
                        updates = []
                        vals = []
                        for field in ("what_unique", "who_for"):
                            if field in enriched and enriched[field]:
                                updates.append(f"{field}=?")
                                vals.append(enriched[field])
                        if updates and not dry_run:
                            vals.append(r["id"])
                            conn.execute(f"UPDATE retreats SET {', '.join(updates)} WHERE id=?", vals)
                        enriched_count += 1
                        print(f"    → enriquecido: {list(enriched.keys())}")
                else:
                    report_lines.append(f"- BAJA CALIDAD ({score}): {r['title'][:60]} — {reason}\n")

            except BudgetExceeded as e:
                errors.append(f"BUDGET: {e}")
                break
            except Exception as e:
                errors.append(f"retreat {r['id']}: {e}")

        if not dry_run:
            conn.commit()

        report_lines.append(f"\n## Aprobados ({len(approved)})\n")
        for t in approved:
            report_lines.append(f"- {t}\n")
        report_lines.append(f"\nEnriquecidos: {enriched_count}\nCosto: ${total_cost:.4f}\n")

        report_path = ROOT / "data" / f"ops_report_{datetime.utcnow().strftime('%Y-%m-%d')}.md"
        if not dry_run:
            report_path.write_text("".join(report_lines), encoding="utf-8")
            print(f"Reporte: {report_path}")

        status = "ok" if not errors else ("partial" if items > 0 else "failed")
    except Exception as e:
        status = "failed"
        errors.append(str(e))
    finally:
        conn.close()

    if not dry_run:
        log_run("ops_agent", started, now_iso(), total_in, total_out,
                round(total_cost, 6), items, status, "; ".join(errors)[:1000])
    print(f"\nops_agent: {items} aprobados, ${total_cost:.4f}, status={status}")
    if dry_run:
        print("[DRY RUN — no se escribió nada]")


if __name__ == "__main__":
    main()
