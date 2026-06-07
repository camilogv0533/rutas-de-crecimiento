#!/usr/bin/env python3
"""Generate content drafts (article + social posts) using Sonnet with brand voice.

Usage:
  python scripts/content_gen.py --type article --topic "retiros de liderazgo en Italia"
  python scripts/content_gen.py --type social --topic "claridad profesional"
  python scripts/content_gen.py --weekly  # picks 1 keyword + generates article + 4 social
  python scripts/content_gen.py --cluster  # quincenal: pillar blog + 5 tweets + LinkedIn + 2-3 imgs
  python scripts/content_gen.py --cluster --topic "retiros de burnout ejecutivo"
"""
import argparse
import json
import os
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
DRAFTS_KITS = ROOT / "content" / "drafts" / "kits"


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


def gen_cluster_article(topic: str) -> tuple[dict, float, int, int]:
    """Blog pillar AEO/SEO/GEO optimizado: respuesta directa front-loaded, FAQ, JSON-LD."""
    related = fetch_related_retreats(topic, 4)
    related_block = "\n".join(
        f"- /retiros/{r['slug']} — {r['title']} ({r['country']}). {r['tagline'] or ''}" for r in related
    )
    user = (
        f"Escribe un artículo pillar para Rutas de Crecimiento sobre: **{topic}**\n\n"
        f"OPTIMIZACIÓN AEO/SEO/GEO (Answer Engine + Search + Generative):\n"
        f"- Párrafo 1 (≤60 palabras): respuesta directa y definitoria a '¿qué es {topic}?' "
        f"  (los answer engines extraen el primer párrafo — hazlo dense en valor).\n"
        f"- H1 debe contener la keyword exacta.\n"
        f"- Usa H2 con preguntas naturales (ej. '¿Por qué los líderes eligen retiros en lugar de coaching?').\n"
        f"- Incluye una sección H2 'Preguntas frecuentes' con 4-5 Q&A en formato markdown (### Pregunta? \\n Respuesta).\n"
        f"- Entidades nombradas: cita 2-3 destinos específicos con nombre real (ciudad/país).\n"
        f"- Longitud: 1800-2500 palabras.\n"
        f"- Cierre con CTA suave a ver retiros (/retiros).\n\n"
        f"Retiros para referenciar con links internos:\n{related_block}\n\n"
        f"IMPORTANTE: Devuelve SOLO el cuerpo del artículo en Markdown (sin frontmatter). "
        f"Al final, añade una sección especial delimitada así:\n"
        f"<!-- JSON-LD-START -->\n[JSON-LD Article + FAQPage como JSON puro]\n<!-- JSON-LD-END -->\n"
        f"El JSON-LD debe tener '@type': 'Article' + 'FAQPage' (dos entidades en array). "
        f"Usa url ficticia https://rutasdecrecimiento.com/blog/[slug]. "
        f"Incluye las 4-5 preguntas del FAQ como 'mainEntity' del FAQPage."
    )
    resp = call(SONNET, brand_system(), [{"role": "user", "content": user}], max_tokens=8000)
    raw = "".join(b.text for b in resp.content if b.type == "text").strip()

    # Separar JSON-LD del cuerpo
    json_ld = ""
    body = raw
    jld_match = re.search(r"<!-- JSON-LD-START -->(.*?)<!-- JSON-LD-END -->", raw, re.DOTALL)
    if jld_match:
        json_ld = jld_match.group(1).strip()
        body = raw[:jld_match.start()].strip()

    title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else topic.capitalize()
    if title_match:
        body = body[title_match.end():].lstrip()
    slug = slugify(title)[:70]
    out = {
        "title": title,
        "slug": slug,
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "target_keyword": topic,
        "body": body,
        "json_ld": json_ld,
        "related_retreats": [r["slug"] for r in related],
    }
    return out, cost_of(SONNET, resp.usage), resp.usage.input_tokens, resp.usage.output_tokens


def gen_cluster_tweets(article_title: str, article_body: str, blog_slug: str) -> tuple[str, float, int, int]:
    """5 tweets standalone desde el artículo. Cada uno = ángulo distinto. Último con link."""
    user = (
        f"Basado en este artículo de blog, escribe 5 tweets STANDALONE para Twitter/X.\n\n"
        f"Artículo: **{article_title}**\n\n"
        f"--- EXTRACTO ---\n{article_body[:3000]}\n--- FIN EXTRACTO ---\n\n"
        f"Reglas:\n"
        f"- Cada tweet = ángulo/insight distinto del artículo (no repitas el mismo punto).\n"
        f"- ≤280 caracteres por tweet.\n"
        f"- Sin emojis en tweets 1-3. Máx 1 emoji en tweets 4-5.\n"
        f"- Tweet 5: termina con 'Más en rutasdecrecimiento.com/blog/{blog_slug}'.\n"
        f"- Tono: observación inteligente, no motivacional. Sin exclamaciones.\n"
        f"- Formato de salida: cada tweet en bloque separado por línea vacía, precedido por '**Tweet N:**'.\n"
        f"- Escribe SOLO los tweets, sin explicaciones."
    )
    resp = call(SONNET, brand_system(), [{"role": "user", "content": user}], max_tokens=1500)
    body = "".join(b.text for b in resp.content if b.type == "text").strip()
    return body, cost_of(SONNET, resp.usage), resp.usage.input_tokens, resp.usage.output_tokens


def gen_cluster_linkedin(article_title: str, article_body: str, blog_slug: str) -> tuple[str, float, int, int]:
    """Long-form LinkedIn post (blog largo para LinkedIn). 300-600 palabras."""
    user = (
        f"Basado en este artículo de blog, escribe un post largo para LinkedIn.\n\n"
        f"Artículo: **{article_title}**\n\n"
        f"--- EXTRACTO ---\n{article_body[:4000]}\n--- FIN EXTRACTO ---\n\n"
        f"Reglas de formato LinkedIn:\n"
        f"- 300-600 palabras.\n"
        f"- Primera línea: gancho que corta el scroll (observación contraintuitiva o dato concreto).\n"
        f"- Párrafos cortos (2-3 líneas máximo). Mucho espacio blanco — es LinkedIn, no un blog.\n"
        f"- 1 idea central desarrollada en 3-4 puntos. No lista con bullets — prosa corta.\n"
        f"- Cierre: pregunta abierta a la audiencia.\n"
        f"- 2-3 hashtags relevantes al final (solo los necesarios, sin spam).\n"
        f"- Incluye al final en una línea separada: 'Artículo completo → rutasdecrecimiento.com/blog/{blog_slug}'\n"
        f"- Tono: editorial, profesional de alto nivel, cero clichés de LinkedIn ('soy un apasionado de...', etc.).\n"
        f"- Máx 1 emoji visible si encaja naturalmente.\n"
        f"- Escribe SOLO el post, sin explicaciones."
    )
    resp = call(SONNET, brand_system(), [{"role": "user", "content": user}], max_tokens=2000)
    body = "".join(b.text for b in resp.content if b.type == "text").strip()
    return body, cost_of(SONNET, resp.usage), resp.usage.input_tokens, resp.usage.output_tokens


def gen_threads(article_title: str, article_body: str, blog_slug: str, n: int = 3) -> tuple[str, float, int, int]:
    """N threads de Twitter/X (4-6 tweets numerados c/u), ángulos distintos."""
    user = (
        f"Basado en este artículo, escribe {n} THREADS independientes para Twitter/X.\n\n"
        f"Artículo: **{article_title}**\n\n"
        f"--- EXTRACTO ---\n{article_body[:3500]}\n--- FIN EXTRACTO ---\n\n"
        f"Reglas:\n"
        f"- Cada thread = un ángulo/tesis DISTINTA del artículo (no repitas el mismo punto entre threads).\n"
        f"- Cada thread tiene 4-6 tweets numerados (formato '1/', '2/', …).\n"
        f"- Tweet 1 de cada thread = hook fuerte sin emojis, que corte el scroll.\n"
        f"- ≤280 caracteres por tweet. Cero exclamaciones múltiples, cero clichés motivacionales.\n"
        f"- Último tweet de cada thread: CTA suave con 'rutasdecrecimiento.com/blog/{blog_slug}'.\n"
        f"- Tono: observación inteligente, editorial.\n"
        f"- Formato de salida: separa cada thread con un encabezado '### Thread N — <título corto>' "
        f"y debajo los tweets, uno por línea. Solo el contenido, sin explicaciones."
    )
    resp = call(SONNET, brand_system(), [{"role": "user", "content": user}], max_tokens=2500)
    body = "".join(b.text for b in resp.content if b.type == "text").strip()
    return body, cost_of(SONNET, resp.usage), resp.usage.input_tokens, resp.usage.output_tokens


def gen_longpost(article_title: str, article_body: str, blog_slug: str) -> tuple[str, float, int, int]:
    """1 long post servible para LinkedIn Y para Twitter/X (long-form). 350-600 palabras."""
    user = (
        f"Basado en este artículo, escribe UN post largo (long-form) que sirva tanto para LinkedIn "
        f"como para un tweet largo de X.\n\n"
        f"Artículo: **{article_title}**\n\n"
        f"--- EXTRACTO ---\n{article_body[:4000]}\n--- FIN EXTRACTO ---\n\n"
        f"Reglas:\n"
        f"- 350-600 palabras.\n"
        f"- Primera línea: gancho que corta el scroll (observación contraintuitiva o dato concreto).\n"
        f"- Párrafos cortos (2-3 líneas), mucho espacio en blanco.\n"
        f"- 1 idea central desarrollada; prosa, no bullets.\n"
        f"- Cierre con una pregunta abierta a la audiencia.\n"
        f"- Última línea: 'Artículo completo → rutasdecrecimiento.com/blog/{blog_slug}'.\n"
        f"- Tono editorial de alto nivel, cero clichés de LinkedIn. Máx 1 emoji si encaja.\n"
        f"- Al final, en una sección '### Hashtags', sugiere 3 hashtags relevantes (para añadir manual).\n"
        f"- Escribe SOLO el post, sin explicaciones."
    )
    resp = call(SONNET, brand_system(), [{"role": "user", "content": user}], max_tokens=2000)
    body = "".join(b.text for b in resp.content if b.type == "text").strip()
    return body, cost_of(SONNET, resp.usage), resp.usage.input_tokens, resp.usage.output_tokens


def gen_cluster_image_prompts(article_title: str, article_body: str) -> tuple[list[str], float, int, int]:
    """Genera 2-3 prompts de imagen fotográfica editorial para el kit."""
    user = (
        f"Artículo: **{article_title}**\n\n"
        f"Resumen del tema: {article_body[:1000]}\n\n"
        f"Genera 3 prompts fotográficos EN INGLÉS para imágenes editoriales que ilustren este artículo.\n"
        f"Cada prompt: escena concreta, destino/ambiente específico, luz cinematográfica, "
        f"presencia humana difusa/de espaldas, sin texto/logos, estilo Magnum Photos, 16:9.\n"
        f"Formato: una línea por prompt, precedida por 'PROMPT 1:', 'PROMPT 2:', 'PROMPT 3:'.\n"
        f"Solo los prompts, sin explicaciones."
    )
    resp = call(HAIKU, brand_system(), [{"role": "user", "content": user}], max_tokens=600)
    raw = "".join(b.text for b in resp.content if b.type == "text").strip()
    prompts = []
    for line in raw.split("\n"):
        m = re.match(r"PROMPT \d+:\s*(.+)", line.strip())
        if m:
            prompts.append(m.group(1).strip())
    return prompts[:3], cost_of(HAIKU, resp.usage), resp.usage.input_tokens, resp.usage.output_tokens


def gen_video_script(article_title: str, article_body: str) -> tuple[str, float, int, int]:
    """Guion 12-15s para video vertical (para que Camilo lo grabe/genere manualmente)."""
    user = (
        f"Artículo: **{article_title}**\n\n"
        f"Tema: {article_body[:800]}\n\n"
        f"Escribe un guion para video vertical de 12-15 segundos (≈40-50 palabras spoken).\n"
        f"Formato:\n"
        f"## GUION VIDEO 12-15s\n"
        f"**Hook (0-3s):** [gancho contraintuitivo — una frase]\n"
        f"**Cuerpo (3-10s):** [desarrollo — 2 frases]\n"
        f"**Cierre (10-15s):** [CTA suave o pregunta]\n\n"
        f"## CAPTIONS\n"
        f"[El texto completo partido en 3-4 líneas para quemarlas en el video]\n\n"
        f"## NOTAS DE PRODUCCIÓN\n"
        f"- B-roll sugerido: [1-2 tipos de plano]\n"
        f"- Música: ambient instrumental (ninguna canción específica)\n\n"
        f"Costo de producción si usas make_video.py: <$0.05 (slideshow ffmpeg)\n"
        f"Escribe SOLO el guion estructurado, en español, sin introducción."
    )
    resp = call(HAIKU, brand_system(), [{"role": "user", "content": user}], max_tokens=500)
    body = "".join(b.text for b in resp.content if b.type == "text").strip()
    return body, cost_of(HAIKU, resp.usage), resp.usage.input_tokens, resp.usage.output_tokens


def save_cluster_kit(
    topic: str,
    article: dict,
    tweets: str,
    linkedin: str,
    video_script: str,
    image_paths: list[Path],
) -> Path:
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    kit_dir = DRAFTS_KITS / f"{date_str}-{article['slug']}"
    kit_dir.mkdir(parents=True, exist_ok=True)

    # blog.md con JSON-LD en schema.json
    fm_lines = [
        "---",
        f'title: "{article["title"]}"',
        f'slug: "{article["slug"]}"',
        f'date: "{article["date"]}"',
        f'target_keyword: "{article["target_keyword"]}"',
        f'related_retreats: {json.dumps(article["related_retreats"])}',
        'status: "draft"',
        "---",
        "",
    ]
    (kit_dir / "blog.md").write_text("\n".join(fm_lines) + "\n" + article["body"], encoding="utf-8")

    if article.get("json_ld"):
        (kit_dir / "schema.json").write_text(article["json_ld"], encoding="utf-8")

    (kit_dir / "tweets.md").write_text(
        f"# Tweets — {article['title']}\n\n{tweets}\n", encoding="utf-8"
    )
    (kit_dir / "linkedin.md").write_text(
        f"# LinkedIn — {article['title']}\n\n{linkedin}\n", encoding="utf-8"
    )
    (kit_dir / "video_script.md").write_text(
        f"# Video 12-15s — {article['title']}\n\n{video_script}\n", encoding="utf-8"
    )

    # README del kit
    readme = [
        f"# Kit quincenal — {article['title']}",
        f"Fecha: {date_str} | Topic: {topic}",
        "",
        "## Archivos",
        "- `blog.md` — artículo pillar AEO/SEO/GEO (publicar en sitio)",
        "- `schema.json` — JSON-LD Article + FAQPage (añadir al <head> de la página)",
        "- `tweets.md` — 5 tweets standalone para publicar 1/día",
        "- `linkedin.md` — post largo LinkedIn",
        "- `video_script.md` — guion 12-15s + notas producción",
        "- `images/*.webp` — imágenes editoriales IA",
        "",
        "## Flujo de publicación (finde de semana)",
        "1. Revisar blog.md y aprobarlo en content_review",
        "2. Añadir blog.md a site/src/content/blog/ para publicar",
        "3. Copiar schema.json al layout de la página del blog",
        "4. Publicar tweets 1 por día (lunes a viernes)",
        "5. Publicar linkedin.md el lunes siguiente",
        "6. Generar video: `python scripts/make_video.py --kit {kit_dir.name}`",
    ]
    (kit_dir / "README.md").write_text("\n".join(readme), encoding="utf-8")

    return kit_dir


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
    parser.add_argument("--cluster", action="store_true",
                        help="Modo quincenal: 1 blog pillar AEO + 5 tweets + LinkedIn + 2-3 imgs → kit/")
    parser.add_argument("--blog", action="store_true",
                        help="Modo semanal: 1 blog pillar AEO/SEO/GEO → content/drafts/articles/")
    parser.add_argument("--no-images", action="store_true", help="Skip image generation in cluster mode")
    args = parser.parse_args()

    if args.blog:
        _run_blog(args)
        return

    if args.cluster:
        _run_cluster(args)
        return

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
        errors = [f"BUDGET: {e}"]
    except Exception as e:
        status = "failed"
        errors = [str(e)]

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


def _run_blog(args):
    """Genera 1 blog pillar AEO/SEO/GEO semanal → content/drafts/articles/{date}-{slug}.md"""
    kws = json.loads(KEYWORDS.read_text())
    topic = args.topic or random.choice(kws["buckets"]["pillar_es"])
    print(f"Blog semanal: '{topic}'")
    started = now_iso()
    total_cost = total_in = total_out = 0
    errors = []
    status = "ok"
    try:
        article, c, ti, to = gen_cluster_article(topic)
        total_cost += c; total_in += ti; total_out += to
        DRAFTS_ART.mkdir(parents=True, exist_ok=True)
        path = save_article(article)
        if article.get("json_ld"):
            path.with_suffix(".schema.json").write_text(article["json_ld"], encoding="utf-8")
        print(f"  Blog guardado: {path.name} (${c:.4f})")
    except BudgetExceeded as e:
        status = "partial"; errors.append(f"BUDGET: {e}")
    except Exception as e:
        status = "failed"; errors.append(str(e)); raise
    finally:
        log_run("content_blog", started, now_iso(), total_in, total_out,
                round(total_cost, 6), 1, status, "; ".join(errors)[:1000])
    print(f"Blog run: ${total_cost:.4f}, status={status}")


def _run_cluster(args):
    from image_gen import IMG_COST, generate_to_path

    kws = json.loads(KEYWORDS.read_text())
    if args.topic:
        topic = args.topic
    else:
        topic = random.choice(kws["buckets"]["pillar_es"])

    print(f"Cluster: '{topic}'")
    started = now_iso()
    total_cost = 0.0
    total_in = total_out = 0
    errors = []
    image_paths: list[Path] = []

    try:
        # 1. Blog pillar AEO/SEO/GEO
        print("  Generando blog pillar…")
        article, c, ti, to = gen_cluster_article(topic)
        total_cost += c; total_in += ti; total_out += to
        print(f"  Blog: '{article['title']}' (${c:.4f})")

        # 2. 5 Tweets standalone
        print("  Generando tweets…")
        tweets, c, ti, to = gen_cluster_tweets(article["title"], article["body"], article["slug"])
        total_cost += c; total_in += ti; total_out += to
        print(f"  Tweets (${c:.4f})")

        # 3. LinkedIn largo
        print("  Generando LinkedIn…")
        linkedin, c, ti, to = gen_cluster_linkedin(article["title"], article["body"], article["slug"])
        total_cost += c; total_in += ti; total_out += to
        print(f"  LinkedIn (${c:.4f})")

        # 4. Guion de video
        print("  Generando guion video…")
        video_script, c, ti, to = gen_video_script(article["title"], article["body"])
        total_cost += c; total_in += ti; total_out += to

        # 5. Imágenes IA vía Gemini (opcional, requiere GEMINI_API_KEY)
        if not args.no_images and os.environ.get("GEMINI_API_KEY"):
            print("  Generando prompts de imagen…")
            img_prompts, c, ti, to = gen_cluster_image_prompts(article["title"], article["body"])
            total_cost += c; total_in += ti; total_out += to

            kit_img_dir = DRAFTS_KITS / f"{article['date']}-{article['slug']}" / "images"
            for i, prompt in enumerate(img_prompts, 1):
                from _llm import _month_cost, MONTHLY_BUDGET
                if _month_cost() + IMG_COST >= MONTHLY_BUDGET:
                    print(f"  Budget alcanzado, saltando imágenes restantes.")
                    break
                print(f"  Imagen {i}/{len(img_prompts)}: {prompt[:60]}…")
                out_path = kit_img_dir / f"image_{i:02d}.webp"
                try:
                    generate_to_path(prompt, out_path)
                    image_paths.append(out_path)
                    total_cost += IMG_COST
                    print(f"  ✅ image_{i:02d}.webp (~${IMG_COST:.3f})")
                except Exception as e:
                    errors.append(f"img_{i}: {e}")
                    print(f"  ⚠️  Imagen {i} falló: {e}")
        elif not os.environ.get("GEMINI_API_KEY"):
            print("  (Sin GEMINI_API_KEY — salteando imágenes. Usa --no-images para suprimir este aviso.)")

        # 6. Guardar kit
        kit_dir = save_cluster_kit(topic, article, tweets, linkedin, video_script, image_paths)
        print(f"\nKit guardado: {kit_dir}")
        print(f"  blog.md, tweets.md, linkedin.md, video_script.md, schema.json, {len(image_paths)} imgs")

        status = "ok" if not errors else "partial"
    except BudgetExceeded as e:
        status = "partial"
        errors.append(f"BUDGET: {e}")
    except Exception as e:
        status = "failed"
        errors.append(str(e))
        raise

    log_run(
        agent_name="content_cluster",
        started_at=started,
        finished_at=now_iso(),
        tokens_in=total_in,
        tokens_out=total_out,
        cost_usd=round(total_cost, 6),
        items_processed=1 + len(image_paths),
        status=status,
        errors="; ".join(errors)[:1000] if errors else ""
    )
    print(f"\nCluster run: ${total_cost:.4f}, status={status}")


if __name__ == "__main__":
    main()
