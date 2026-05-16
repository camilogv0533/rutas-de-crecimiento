#!/usr/bin/env python3
"""Classify a retreat into skills from skills_taxonomy.json. Idempotent.

Usage:
  python scripts/classify.py --slug alptitude-alpes-franceses
  python scripts/classify.py --all  # all retreats lacking skill links
"""
import argparse
import json
import sqlite3
from pathlib import Path

from _llm import HAIKU, call, cost_of, log_run, now_iso, BudgetExceeded

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "retreats.db"
TAXONOMY = ROOT / "data" / "skills_taxonomy.json"


TOOL = {
    "name": "save_skills",
    "description": "Save up to 5 skill slugs that the retreat develops. Confidence 0-1.",
    "input_schema": {
        "type": "object",
        "properties": {
            "skills": {
                "type": "array",
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string"},
                        "confidence": {"type": "number"}
                    },
                    "required": ["slug", "confidence"]
                }
            }
        },
        "required": ["skills"]
    }
}


def get_retreat(conn, slug: str | None):
    if slug:
        rows = conn.execute(
            "SELECT id, slug, title, tagline, intro, what_unique, who_for, what_youll_learn FROM retreats WHERE slug=?",
            (slug,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, slug, title, tagline, intro, what_unique, who_for, what_youll_learn FROM retreats r "
            "WHERE NOT EXISTS (SELECT 1 FROM retreat_skills rs WHERE rs.retreat_id=r.id)"
        ).fetchall()
    return rows


def classify_one(rid: int, retreat_text: str, valid_slugs: set, taxonomy_block: str):
    system = (
        "You map retreats to a fixed taxonomy of skills. Return up to 5 most relevant skill slugs. "
        "Use ONLY slugs from the provided list. Do not invent slugs. Confidence reflects how central "
        "that skill is to the retreat's stated outcome (1 = explicitly trained; 0.5 = adjacent)."
    )
    user = f"TAXONOMY (use these slugs only):\n{taxonomy_block}\n\nRETREAT:\n{retreat_text}\n\nCall save_skills now."
    resp = call(
        model=HAIKU,
        system=system,
        messages=[{"role": "user", "content": user}],
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "save_skills"},
        max_tokens=1024,
    )
    payload = None
    for b in resp.content:
        if b.type == "tool_use" and b.name == "save_skills":
            payload = b.input
            break
    if not payload:
        return [], resp.usage
    cleaned = [s for s in payload.get("skills", []) if s["slug"] in valid_slugs]
    return cleaned, resp.usage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if not args.slug and not args.all:
        parser.error("Pass --slug or --all")

    tax = json.loads(TAXONOMY.read_text())["skills"]
    slug_to_id = {}
    valid_slugs = set()
    taxonomy_lines = []
    for s in tax:
        valid_slugs.add(s["slug"])
        syn = ", ".join(s.get("synonyms_es", []) + s.get("synonyms_en", []))
        taxonomy_lines.append(f"- {s['slug']}: {s['name_es']} / {s.get('name_en','')} — {syn}")
    taxonomy_block = "\n".join(taxonomy_lines)

    conn = sqlite3.connect(DB_PATH)
    for slug_, _, _, *_  in conn.execute("SELECT slug, id, slug, slug, slug, slug, slug, slug FROM skills WHERE 1=0"):
        pass
    for sid, sslug in conn.execute("SELECT id, slug FROM skills"):
        slug_to_id[sslug] = sid

    rows = get_retreat(conn, args.slug if args.slug else None)
    started = now_iso()
    items = 0
    total_cost = 0
    total_in = total_out = 0
    errors = []
    try:
        for rid, slug, title, tagline, intro, what_unique, who_for, learn in rows:
            text = "\n".join(filter(None, [title, tagline or "", intro or "", what_unique or "", who_for or "", learn or ""]))
            try:
                skills, usage = classify_one(rid, text, valid_slugs, taxonomy_block)
                conn.execute("DELETE FROM retreat_skills WHERE retreat_id=?", (rid,))
                for s in skills:
                    sid = slug_to_id.get(s["slug"])
                    if sid:
                        conn.execute(
                            "INSERT OR REPLACE INTO retreat_skills (retreat_id, skill_id, confidence) VALUES (?,?,?)",
                            (rid, sid, float(s["confidence"]))
                        )
                conn.commit()
                items += 1
                total_cost += cost_of(HAIKU, usage)
                total_in += usage.input_tokens
                total_out += usage.output_tokens
                print(f"  classified {slug}: {[s['slug'] for s in skills]}")
            except BudgetExceeded as e:
                errors.append(f"BUDGET: {e}")
                break
        status = "ok" if not errors else "partial"
    except Exception as e:
        status = "failed"
        errors.append(str(e))
    conn.close()
    log_run(
        agent_name="classifier",
        started_at=started,
        finished_at=now_iso(),
        tokens_in=total_in,
        tokens_out=total_out,
        cost_usd=round(total_cost, 6),
        items_processed=items,
        status=status,
        errors="; ".join(errors)[:1000] if errors else ""
    )
    print(f"\nClassifier run: {items} retreats, ${total_cost:.4f}, status={status}")


if __name__ == "__main__":
    main()
