#!/usr/bin/env python3
"""CEO de Marketing — publica drafts aprobados y genera copy social listo para usar.

Corre cada jueves. Lee content_drafts con status='draft', puntúa con Haiku,
los que pasan score >= 70 se mueven a site/src/content/blog/ y se marcan 'published'.
Genera variantes de posts Twitter + LinkedIn para cada artículo publicado.

Usage:
  python scripts/marketing_agent.py
  python scripts/marketing_agent.py --dry-run
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
BLOG_DIR = ROOT / "site" / "src" / "content" / "blog"
SOCIAL_OUT = ROOT / "data" / "social_ready"
SCORE_THRESHOLD = 70


def _yaml_str(v: str) -> str:
    return '"' + str(v).replace('\\', '\\\\').replace('"', "'").replace('\n', ' ') + '"'


def fetch_drafts(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, type, platform, target_keyword, title, slug, body_md, related_retreat_slugs "
        "FROM content_drafts WHERE status='draft' AND type='article' ORDER BY created_at LIMIT 10"
    ).fetchall()
    return [
        {"id": r[0], "type": r[1], "platform": r[2], "keyword": r[3],
         "title": r[4], "slug": r[5], "body": r[6], "related": r[7]}
        for r in rows
    ]


def score_draft(draft: dict) -> tuple[int, float, int, int]:
    prompt = (
        f"Evalúa este borrador de artículo para un blog de turismo experiencial en español.\n"
        f"Título: {draft['title']}\n"
        f"Keyword objetivo: {draft['keyword']}\n"
        f"Primeros 800 chars del body:\n{(draft['body'] or '')[:800]}\n\n"
        f"Devuelve SOLO un JSON: {{\"score\": <0-100>, \"reason\": \"<max 20 palabras>\"}}\n"
        f"Criterios: claridad (30%), SEO fit (30%), tono editorial sin clichés (40%)."
    )
    resp = call(HAIKU, "Eres un editor de contenido experto en SEO para turismo.", [
        {"role": "user", "content": prompt}
    ], max_tokens=200)
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    try:
        m = re.search(r'\{.*\}', text, re.DOTALL)
        data = json.loads(m.group()) if m else {}
        score = int(data.get("score", 0))
    except Exception:
        score = 0
    return score, cost_of(HAIKU, resp.usage), resp.usage.input_tokens, resp.usage.output_tokens


def publish_article(draft: dict, dry_run: bool) -> str | None:
    BLOG_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    slug = draft["slug"] or re.sub(r'[^a-z0-9-]', '-', (draft["title"] or "sin-titulo").lower())[:70]
    related = []
    if draft["related"]:
        try:
            related = json.loads(draft["related"])
        except Exception:
            pass
    fm = [
        "---",
        f"title: {_yaml_str(draft['title'] or '')}",
        f"slug: {_yaml_str(slug)}",
        f"date: {_yaml_str(today)}",
        f"description: {_yaml_str(draft['keyword'] or '')}",
        f"target_keyword: {_yaml_str(draft['keyword'] or '')}",
        f"related_retreats: {json.dumps(related)}",
        "---",
        "",
    ]
    filename = f"{today}-{slug}.md"
    dest = BLOG_DIR / filename
    if not dry_run:
        dest.write_text("\n".join(fm) + "\n" + (draft["body"] or ""), encoding="utf-8")
    return str(dest)


def gen_social_copy(draft: dict, dry_run: bool) -> tuple[float, int, int]:
    prompt = (
        f"Artículo publicado en Rutas de Crecimiento:\nTítulo: {draft['title']}\nKeyword: {draft['keyword']}\n"
        f"Primeros 400 chars:\n{(draft['body'] or '')[:400]}\n\n"
        f"Genera 2 variantes:\n"
        f"1. TWITTER THREAD (3 tweets numerados, ≤280 chars c/u, último con link /blog/{draft['slug']})\n"
        f"2. LINKEDIN (180-220 palabras, insight + pregunta al final)\n"
        f"Formato: ## Twitter\n<tweets>\n## LinkedIn\n<post>\nCero emojis en LinkedIn. Máx 2 en Twitter."
    )
    resp = call(SONNET, "Eres redactor experto en marketing de contenidos B2C para viajes experienciales en español.", [
        {"role": "user", "content": prompt}
    ], max_tokens=1200)
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not dry_run:
        SOCIAL_OUT.mkdir(parents=True, exist_ok=True)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        out_path = SOCIAL_OUT / f"{today}-{draft['slug'][:50]}.md"
        out_path.write_text(f"# Social copy: {draft['title']}\n\n{text}", encoding="utf-8")
    return cost_of(SONNET, resp.usage), resp.usage.input_tokens, resp.usage.output_tokens


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="No escribe a DB ni a disco")
    args = parser.parse_args()
    dry_run = args.dry_run

    started = now_iso()
    total_cost = 0.0
    total_in = total_out = 0
    items = 0
    errors = []

    conn = sqlite3.connect(DB_PATH)
    try:
        drafts = fetch_drafts(conn)
        print(f"Drafts encontrados: {len(drafts)}")

        for draft in drafts:
            try:
                score, c, ti, to = score_draft(draft)
                total_cost += c; total_in += ti; total_out += to
                print(f"  [{score}/100] {draft['title'][:60]}")

                if score >= SCORE_THRESHOLD:
                    path = publish_article(draft, dry_run)
                    print(f"    → publicado: {path}")
                    c2, ti2, to2 = gen_social_copy(draft, dry_run)
                    total_cost += c2; total_in += ti2; total_out += to2
                    if not dry_run:
                        conn.execute("UPDATE content_drafts SET status='published' WHERE id=?", (draft["id"],))
                        conn.commit()
                    items += 1
                else:
                    print(f"    → score bajo, omitido")
            except BudgetExceeded as e:
                errors.append(f"BUDGET: {e}")
                break
            except Exception as e:
                errors.append(f"draft {draft['id']}: {e}")

        status = "ok" if not errors else ("partial" if items > 0 else "failed")
    except Exception as e:
        status = "failed"
        errors.append(str(e))
    finally:
        conn.close()

    if not dry_run:
        log_run("marketing_agent", started, now_iso(), total_in, total_out,
                round(total_cost, 6), items, status, "; ".join(errors)[:1000])
    print(f"\nmarketing_agent: {items} publicados, ${total_cost:.4f}, status={status}")
    if dry_run:
        print("[DRY RUN — no se escribió nada]")


if __name__ == "__main__":
    main()
