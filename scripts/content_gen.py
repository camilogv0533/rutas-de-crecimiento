#!/usr/bin/env python3
"""Generate content drafts (article + social posts) using Sonnet with brand voice.

Usage:
  python scripts/content_gen.py --type article --topic "retiros de liderazgo en Italia"
  python scripts/content_gen.py --type social --topic "claridad profesional"
  python scripts/content_gen.py --weekly  # picks 1 keyword + generates article + 4 social
"""
import argparse
import json
import random
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from slugify import slugify

from _llm import SONNET, HAIKU, call, cost_of, log_run, now_iso, BudgetExceeded

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "retreats.db"
VOICE = ROOT / ".claude" / "skills" / "brand_context" / "voice.md"
ICP = ROOT / ".claude" / "skills" / "brand_context" / "icp.md"
POSITIONING = ROOT / ".claude" / "skills" / "brand_context" / "positioning.md"
KEYWORDS = ROOT / "data" / "keywords_es.json"
DRAFTS_ART = ROOT / "content" / "drafts" / "articles"
DRAFTS_SOCIAL = ROOT / "content" / "drafts" / "social"


def brand_system() -> str:
    return "\n\n".join([
        "# BRAND VOICE\n" + VOICE.read_text(),
        "# ICP\n" + ICP.read_text(),
        "# POSITIONING\n" + POSITIONING.read_text(),
        "## Reglas duras:\n"
        "- Escribe SIEMPRE en español.\n"
        "- NO uses emojis en artículos largos. Máx 2 en social copy.\n"
        "- Cero exclamaciones múltiples, cero 'increíble experiencia transformadora', cero clichés.\n"
        "- Usa el tono editorial-personal de los ejemplos. Imagen sensorial sobre adjetivos.\n"
        "- Si citas fuente, usa una real reconocida (HBR, McKinsey, etc.) y de manera específica.\n"
        "- No prometas certezas absolutas.",
    ])


def fetch_related_retreats(topic: str, n: int = 3) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT slug, title, tagline, location_country, what_unique FROM retreats WHERE status='active' LIMIT ?",
        (n,)
    ).fetchall()
    conn.close()
    return [{"slug": r[0], "title": r[1], "tagline": r[2], "country": r[3], "unique": r[4]} for r in rows]


def gen_article(topic: str, target_keyword: str | None = None) -> tuple[dict, float, int, int]:
    related = fetch_related_retreats(topic, 3)
    related_block = "\n".join(
        f"- /retiros/{r['slug']} — {r['title']} ({r['country']}). {r['tagline'] or ''}" for r in related
    )
    target_keyword = target_keyword or topic
    user = (
        f"Escribe un artículo de blog para Rutas de Crecimiento sobre: {topic}\n"
        f"Target keyword principal: {target_keyword}\n"
        f"Longitud objetivo: 1500-2200 palabras.\n"
        f"Estructura: H1, lead, H2 ¿qué es esto?, H2 ¿por qué importa?, H2 cómo elegir, H2 ejemplos curados (linkea a 2-3 retiros), H2 cierre con CTA suave.\n"
        f"Retiros que puedes referenciar (linkea en markdown con su path):\n{related_block}\n\n"
        f"Reglas: usa el tono editorial-personal del brand voice. Markdown puro. Frontmatter NO — solo el contenido del artículo."
    )
    resp = call(SONNET, brand_system(), [{"role": "user", "content": user}], max_tokens=6000)
    body = "".join(b.text for b in resp.content if b.type == "text").strip()
    title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else topic.capitalize()
    if title_match:
        body = body[title_match.end():].lstrip()
    slug = slugify(title)[:70]
    out = {
        "title": title,
        "slug": slug,
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "target_keyword": target_keyword,
        "body": body,
        "related_retreats": [r["slug"] for r in related]
    }
    return out, cost_of(SONNET, resp.usage), resp.usage.input_tokens, resp.usage.output_tokens


SOCIAL_RULES = {
    "instagram": "Carrusel guion (5-7 slides). Por slide: 1 idea, 1-2 frases máx 20 palabras. Slide 1 = hook. Última = CTA suave (link en bio). Tono visual, sensorial. Devuélvelo como '## Slide N — <texto>'.",
    "linkedin": "200-350 palabras. Lead con un insight de liderazgo o L&D. Cuerpo: 2-3 párrafos cortos. Cierre con una pregunta abierta. 0-3 hashtags relevantes al final, sin spam.",
    "twitter": "Thread 4-6 tweets numerados (1/, 2/, etc.). Tweet 1 = hook fuerte sin emojis. Cada tweet ≤ 280 chars. Último tweet = CTA con link a una página del sitio.",
    "tiktok": "Guion 30-60 seg (≈ 90-180 palabras). Hook 0-3s, gancho contraintuitivo. Indicar shots con [B-ROLL: ...]. Cierre: 'sigue para más rutas de crecimiento'."
}


def gen_social(topic: str, platform: str) -> tuple[dict, float, int, int]:
    rules = SOCIAL_RULES[platform]
    related = fetch_related_retreats(topic, 1)
    rel = related[0] if related else {}
    user = (
        f"Escribe contenido para **{platform}** sobre: {topic}\n"
        f"Reglas de formato: {rules}\n"
        f"Si tiene sentido, referencia este retiro: {rel.get('title','')} — {rel.get('tagline','')} (URL: /retiros/{rel.get('slug','')})\n"
        f"Tono: brand voice. Cero 'increíble', cero 'imperdible'."
    )
    resp = call(SONNET, brand_system(), [{"role": "user", "content": user}], max_tokens=2000)
    body = "".join(b.text for b in resp.content if b.type == "text").strip()
    out = {
        "platform": platform,
        "topic": topic,
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "body": body,
        "related_retreat": rel.get("slug")
    }
    return out, cost_of(SONNET, resp.usage), resp.usage.input_tokens, resp.usage.output_tokens


def _yaml_str(v: str) -> str:
    return '"' + str(v).replace('\\', '\\\\').replace('"', "'").replace('\n', ' ') + '"'


def save_article(art: dict):
    DRAFTS_ART.mkdir(parents=True, exist_ok=True)
    fm_lines = [
        "---",
        f"title: {_yaml_str(art['title'])}",
        f"slug: {_yaml_str(art['slug'])}",
        f"date: {_yaml_str(art['date'])}",
        f"target_keyword: {_yaml_str(art['target_keyword'])}",
        f"related_retreats: {json.dumps(art['related_retreats'])}",
        'status: "draft"',
        "---",
        "",
    ]
    path = DRAFTS_ART / f"{art['date']}-{art['slug']}.md"
    path.write_text("\n".join(fm_lines) + "\n" + art["body"], encoding="utf-8")
    return path


def save_social(post: dict):
    DRAFTS_SOCIAL.mkdir(parents=True, exist_ok=True)
    slug = slugify(post["topic"])[:50]
    path = DRAFTS_SOCIAL / f"{post['date']}-{post['platform']}-{slug}.md"
    fm_lines = [
        "---",
        f"platform: {_yaml_str(post['platform'])}",
        f"topic: {_yaml_str(post['topic'])}",
        f"date: {_yaml_str(post['date'])}",
        f"related_retreat: {_yaml_str(post.get('related_retreat') or '')}",
        'status: "draft"',
        "---",
        "",
    ]
    path.write_text("\n".join(fm_lines) + "\n" + post["body"], encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=["article", "social", "weekly"])
    parser.add_argument("--topic")
    parser.add_argument("--platform", choices=list(SOCIAL_RULES.keys()))
    parser.add_argument("--weekly", action="store_true")
    args = parser.parse_args()

    if args.weekly or args.type == "weekly":
        kws = json.loads(KEYWORDS.read_text())
        topic = random.choice(kws["buckets"]["pillar_es"])
        social_topics = random.sample(kws["buckets"]["long_tail_es"], 4)
    else:
        topic = args.topic or "retiros de liderazgo"
        social_topics = [topic] * 4

    started = now_iso()
    total_cost = 0
    items = 0
    errors = []
    total_in = total_out = 0
    try:
        if args.weekly or args.type in ("article", "weekly"):
            art, c, ti, to = gen_article(topic)
            save_article(art)
            total_cost += c
            total_in += ti
            total_out += to
            items += 1
            print(f"Article saved: {art['slug']}")
        if args.weekly or args.type == "social":
            platforms = ["instagram", "linkedin", "twitter", "tiktok"] if args.weekly else [args.platform or "linkedin"]
            for i, p in enumerate(platforms):
                t = social_topics[i] if i < len(social_topics) else topic
                post, c, ti, to = gen_social(t, p)
                save_social(post)
                total_cost += c
                total_in += ti
                total_out += to
                items += 1
                print(f"Social saved: {p} on '{t[:50]}'")
        status = "ok"
    except BudgetExceeded as e:
        status = "partial"
        errors.append(f"BUDGET: {e}")
    except Exception as e:
        status = "failed"
        errors.append(str(e))

    log_run(
        agent_name="content_gen",
        started_at=started,
        finished_at=now_iso(),
        tokens_in=total_in,
        tokens_out=total_out,
        cost_usd=round(total_cost, 6),
        items_processed=items,
        status=status,
        errors="; ".join(errors)[:1000] if errors else ""
    )
    print(f"\ncontent_gen run: {items} items, ${total_cost:.4f}, status={status}")


if __name__ == "__main__":
    main()
