#!/usr/bin/env python3
"""CEO de UX — analiza gaps del catálogo y mejora copy de habilidades/destinos.

Corre cada domingo. Detecta habilidades sin retiros, destinos vacíos,
genera lista de wishlist de retiros faltantes y enriquece descriptions.
Escribe reporte a data/ux_report_YYYY-MM-DD.md

Usage:
  python scripts/ux_agent.py
  python scripts/ux_agent.py --dry-run
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
WISHLIST_PATH = ROOT / "data" / "wishlist.md"


def analyze_gaps(conn: sqlite3.Connection) -> dict:
    skills_no_retreats = conn.execute(
        "SELECT s.slug, s.name_es FROM skills s "
        "LEFT JOIN retreat_skills rs ON s.id=rs.skill_id "
        "WHERE rs.skill_id IS NULL"
    ).fetchall()

    destinations_low = conn.execute(
        "SELECT d.slug, d.name, COUNT(rd.retreat_id) as cnt "
        "FROM destinations d "
        "LEFT JOIN (SELECT DISTINCT r.id as retreat_id, jd.value as dest_slug "
        "           FROM retreats r, json_each(r.destinations) jd) rd ON rd.dest_slug=d.slug "
        "GROUP BY d.id HAVING cnt < 2 ORDER BY cnt"
    ).fetchall()

    skills_no_desc = conn.execute(
        "SELECT id, slug, name_es FROM skills WHERE description_es IS NULL OR description_es=''"
    ).fetchall()

    active_retreats = conn.execute("SELECT COUNT(*) FROM retreats WHERE status='active'").fetchone()[0]
    reviewed = conn.execute("SELECT COUNT(*) FROM retreats WHERE reviewed_by_us=1").fetchone()[0]

    recent_errors = conn.execute(
        "SELECT agent_name, errors FROM agent_runs WHERE errors!='' AND errors IS NOT NULL "
        "ORDER BY started_at DESC LIMIT 10"
    ).fetchall()

    return {
        "skills_no_retreats": skills_no_retreats,
        "destinations_low": destinations_low,
        "skills_no_desc": skills_no_desc,
        "active_retreats": active_retreats,
        "reviewed": reviewed,
        "recent_errors": recent_errors,
    }


def gen_wishlist(gaps: dict) -> tuple[str, float, int, int]:
    skill_names = [r[1] for r in gaps["skills_no_retreats"][:10]]
    dest_names = [r[1] for r in gaps["destinations_low"][:8]]

    prompt = (
        f"Eres el curador de Rutas de Crecimiento. Tienes gaps en el catálogo:\n"
        f"Habilidades sin retiros: {skill_names}\n"
        f"Destinos con < 2 retiros: {dest_names}\n\n"
        f"Genera una lista de 8-12 retiros concretos que DEBERÍAN existir para cubrir estos gaps.\n"
        f"Por cada uno: nombre sugerido, habilidad que enseña, país ideal, por qué ese país, precio estimado.\n"
        f"Formato markdown: ## Nombre del retiro\n- Habilidad: X\n- País: Y\n- Por qué: Z\n- Precio: $N USD\n"
        f"Sé específico: 'Retiro de escritura narrativa en Oaxaca' no 'retiro creativo en México'."
    )
    resp = call(SONNET, "Experto en turismo experiencial y desarrollo de habilidades.", [
        {"role": "user", "content": prompt}
    ], max_tokens=2000)
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    return text, cost_of(SONNET, resp.usage), resp.usage.input_tokens, resp.usage.output_tokens


def enrich_skill_descriptions(conn: sqlite3.Connection, skills: list, dry_run: bool) -> tuple[int, float, int, int]:
    if not skills:
        return 0, 0.0, 0, 0

    total_cost = 0.0; total_in = total_out = 0; enriched = 0
    names = [f"{s[1]} ({s[2]})" for s in skills[:8]]
    prompt = (
        f"Genera descriptions_es cortas (20-35 palabras) para estas habilidades de viaje experiencial:\n"
        f"{json.dumps(names, ensure_ascii=False)}\n\n"
        f"Devuelve JSON: {{\"slug\": \"descripcion...\", ...}}\n"
        f"Tono editorial, sin clichés. Enfócate en qué desarrolla la habilidad en la práctica real."
    )
    resp = call(HAIKU, "Especialista en desarrollo de habilidades y educación experiencial.", [
        {"role": "user", "content": prompt}
    ], max_tokens=1200)
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    total_cost += cost_of(HAIKU, resp.usage)
    total_in += resp.usage.input_tokens; total_out += resp.usage.output_tokens

    try:
        m = re.search(r'\{.*\}', text, re.DOTALL)
        data = json.loads(m.group()) if m else {}
        for skill in skills[:8]:
            slug = skill[1]
            desc = data.get(slug)
            if desc and not dry_run:
                conn.execute("UPDATE skills SET description_es=? WHERE id=?", (desc, skill[0]))
                enriched += 1
        if not dry_run:
            conn.commit()
    except Exception:
        pass

    return enriched, total_cost, total_in, total_out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run

    started = now_iso()
    total_cost = 0.0
    total_in = total_out = 0
    items = 0
    errors = []

    conn = sqlite3.connect(DB_PATH)
    try:
        gaps = analyze_gaps(conn)
        today = datetime.utcnow().strftime("%Y-%m-%d")

        report = [
            f"# UX Report — {today}\n",
            f"**Catálogo:** {gaps['active_retreats']} retiros activos, {gaps['reviewed']} curados\n",
            f"**Habilidades sin retiros:** {len(gaps['skills_no_retreats'])}\n",
            f"**Destinos con < 2 retiros:** {len(gaps['destinations_low'])}\n",
            f"**Habilidades sin descripción:** {len(gaps['skills_no_desc'])}\n\n",
        ]

        # Wishlist
        wishlist, c, ti, to = gen_wishlist(gaps)
        total_cost += c; total_in += ti; total_out += to; items += 1
        report.append("## Retiros wishlist\n")
        report.append(wishlist + "\n\n")
        if not dry_run:
            WISHLIST_PATH.write_text(f"# Wishlist — {today}\n\n{wishlist}", encoding="utf-8")
            print(f"Wishlist: {WISHLIST_PATH}")

        # Enrich skill descriptions
        enriched, c2, ti2, to2 = enrich_skill_descriptions(conn, gaps["skills_no_desc"], dry_run)
        total_cost += c2; total_in += ti2; total_out += to2
        report.append(f"## Skills enriquecidas\n{enriched} de {len(gaps['skills_no_desc'])} procesadas.\n\n")
        items += enriched

        # Recent errors summary
        if gaps["recent_errors"]:
            report.append("## Errores recientes en agentes\n")
            for agent, err in gaps["recent_errors"]:
                report.append(f"- **{agent}:** {(err or '')[:120]}\n")

        report_path = ROOT / "data" / f"ux_report_{today}.md"
        if not dry_run:
            report_path.write_text("".join(report), encoding="utf-8")
            print(f"Reporte: {report_path}")

        # Also update findings.md if there are critical gaps
        critical = len(gaps["skills_no_retreats"]) > 5 or len(gaps["destinations_low"]) > 3
        if critical and not dry_run:
            findings_path = ROOT / ".claude" / "findings.md"
            existing = findings_path.read_text() if findings_path.exists() else ""
            entry = (
                f"\n## UX gaps — {today}\n"
                f"- {len(gaps['skills_no_retreats'])} habilidades sin retiros\n"
                f"- {len(gaps['destinations_low'])} destinos con < 2 retiros\n"
                f"- Ver wishlist: data/wishlist.md\n"
            )
            findings_path.write_text(existing + entry, encoding="utf-8")

        status = "ok" if not errors else ("partial" if items > 0 else "failed")
    except BudgetExceeded as e:
        status = "partial"
        errors.append(f"BUDGET: {e}")
    except Exception as e:
        status = "failed"
        errors.append(str(e))
    finally:
        conn.close()

    if not dry_run:
        log_run("ux_agent", started, now_iso(), total_in, total_out,
                round(total_cost, 6), items, status, "; ".join(errors)[:1000])
    print(f"\nux_agent: {items} items, ${total_cost:.4f}, status={status}")
    if dry_run:
        print("[DRY RUN — no se escribió nada]")


if __name__ == "__main__":
    main()
