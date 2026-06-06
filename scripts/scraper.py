#!/usr/bin/env python3
"""Scrape a retreat URL → structured JSON via Haiku tool-use → SQLite upsert.

Usage:
  python scripts/scraper.py --url https://alptitu.de
  python scripts/scraper.py --url https://example.com --dry-run
  python scripts/scraper.py --batch  # process all sources from data/sources.json
"""
import argparse
import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from slugify import slugify

from _llm import HAIKU, call, cost_of, log_run, now_iso, BudgetExceeded

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "retreats.db"
SOURCES_PATH = ROOT / "data" / "sources.json"
DISCOVERED_PATH = ROOT / "data" / "discovered_urls.json"

MAX_HTML_CHARS = 60_000  # tighten input; Haiku can re-read sub-sections if needed

EXTRACTION_TOOL = {
    "name": "save_retreat",
    "description": "Save structured retreat data. Use null when info isn't on the page — do not invent.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "tagline": {"type": ["string", "null"]},
            "intro": {"type": ["string", "null"], "description": "1-3 paragraph intro EN ESPAÑOL (traducido si la fuente está en otro idioma)."},
            "location_city": {"type": ["string", "null"]},
            "location_country": {"type": ["string", "null"], "description": "ISO 2-letter country code."},
            "location_region": {"type": ["string", "null"]},
            "duration_days": {"type": ["integer", "null"]},
            "next_date": {"type": ["string", "null"], "description": "ISO date YYYY-MM-DD of next cohort if visible."},
            "recurring": {"type": ["string", "null"], "description": "How often (e.g. 'monthly', '2x year')."},
            "price_original": {"type": ["number", "null"]},
            "currency_original": {"type": ["string", "null"], "description": "ISO 3-letter currency code."},
            "language": {"type": ["string", "null"], "description": "Language of the retreat itself."},
            "group_size_min": {"type": ["integer", "null"]},
            "group_size_max": {"type": ["integer", "null"]},
            "what_unique": {"type": ["string", "null"]},
            "who_for": {"type": ["string", "null"]},
            "sample_itinerary": {"type": ["string", "null"]},
            "what_youll_learn": {"type": ["string", "null"], "description": "Free text — classifier maps to skill taxonomy later."},
            "included": {"type": ["string", "null"]},
            "not_included": {"type": ["string", "null"]},
            "accommodation": {"type": ["string", "null"]},
            "food": {"type": ["string", "null"]},
            "host_name": {"type": ["string", "null"]},
            "host_url": {"type": ["string", "null"]},
            "social_instagram": {"type": ["string", "null"]},
            "image_urls": {"type": "array", "items": {"type": "string"}, "default": []},
            "is_actually_a_retreat": {"type": "boolean", "description": "True if the page is an immersive multi-day in-person learning experience that requires travel to a destination. This includes: retreats, residencies, and MASTERMINDS with a physical travel component. False if it is: an online course, a hotel listing without curated programming, a blog post, a hardware product, or a pure conference without travel/lodging component."},
            "categories": {"type": "array", "items": {"type": "string"}, "description": "Tags describing the format. Always include one of: 'retiro', 'mastermind', 'residencia', 'inmersion'. Add others if clearly applicable (e.g. 'liderazgo', 'escritura'). Must include 'mastermind' if the page uses that word or clearly describes a peer mastermind group format.", "default": ["retiro"]}
        },
        "required": ["title", "is_actually_a_retreat"]
    }
}


def fetch_html(url: str) -> str:
    headers = {"User-Agent": "RutasDeCrecimientoBot/0.1 (+https://rutasdecrecimiento.com)"}
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    return r.text


def strip_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:MAX_HTML_CHARS]


def usd_from(price: float | None, currency: str | None) -> float | None:
    if price is None:
        return None
    rates = {"USD": 1, "EUR": 1.08, "GBP": 1.27, "CHF": 1.12, "JPY": 0.0066, "MXN": 0.057, "COP": 0.00025}
    return round(price * rates.get((currency or "USD").upper(), 1), 2)


def extract(url: str, text: str) -> tuple[dict, dict]:
    system = (
        "You extract structured retreat data from web pages. "
        "Strictness: do NOT invent. If a field is not visible, use null. "
        "Set is_actually_a_retreat=false if the page is a hotel listing, online course, "
        "blog article, agency homepage, or anything that is not an immersive multi-day learning retreat with a defined cohort. "
        "IDIOMA: el sitio publica en español. Traduce SIEMPRE al español natural y editorial estos campos narrativos: "
        "tagline, intro, what_unique, who_for, what_youll_learn — aunque la página original esté en inglés u otro idioma. "
        "NO traduzcas: title (nombre propio del retiro), host_name, ni códigos (país, moneda). "
        "Return all fields by calling the save_retreat tool."
    )
    user = f"URL: {url}\n\n--- PAGE TEXT ---\n{text}\n--- END ---\nExtract the retreat info now by calling save_retreat."
    resp = call(
        model=HAIKU,
        system=system,
        messages=[{"role": "user", "content": user}],
        tools=[EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "save_retreat"},
        max_tokens=4096,
    )
    payload = None
    for block in resp.content:
        if block.type == "tool_use" and block.name == "save_retreat":
            payload = block.input
            break
    if not payload:
        raise RuntimeError("Model did not call save_retreat.")
    return payload, resp.usage


def upsert(data: dict, source_url: str) -> str:
    slug = slugify(data["title"])[:80] or slugify(urlparse(source_url).netloc)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id FROM retreats WHERE source_url=?", (source_url,))
    existing = cur.fetchone()
    if existing:
        cur.execute("SELECT slug FROM retreats WHERE id=?", (existing[0],))
        slug = cur.fetchone()[0]
    fields = {
        "slug": slug,
        "source_url": source_url,
        "title": data["title"],
        "tagline": data.get("tagline"),
        "intro": data.get("intro"),
        "location_city": data.get("location_city"),
        "location_country": data.get("location_country"),
        "location_region": data.get("location_region"),
        "duration_days": data.get("duration_days"),
        "next_date": data.get("next_date"),
        "recurring": data.get("recurring"),
        "price_original": data.get("price_original"),
        "currency_original": data.get("currency_original"),
        "price_usd_from": usd_from(data.get("price_original"), data.get("currency_original")),
        "language": data.get("language"),
        "group_size_min": data.get("group_size_min"),
        "group_size_max": data.get("group_size_max"),
        "what_unique": data.get("what_unique"),
        "who_for": data.get("who_for"),
        "sample_itinerary": data.get("sample_itinerary"),
        "what_youll_learn": data.get("what_youll_learn"),
        "included": data.get("included"),
        "not_included": data.get("not_included"),
        "accommodation": data.get("accommodation"),
        "food": data.get("food"),
        "host_name": data.get("host_name"),
        "host_url": data.get("host_url"),
        "social_instagram": data.get("social_instagram"),
        "image_urls": json.dumps(data.get("image_urls", []), ensure_ascii=False),
        "categories": ",".join(data.get("categories") or ["retiro"]),
        "scraped_at": now_iso(),
        "last_seen_at": now_iso(),
        "status": "active"
    }
    if existing:
        keys = [k for k in fields if k != "source_url"]
        cur.execute(
            f"UPDATE retreats SET {', '.join(f'{k}=?' for k in keys)} WHERE source_url=?",
            tuple(fields[k] for k in keys) + (source_url,)
        )
    else:
        keys = list(fields.keys())
        cur.execute(
            f"INSERT INTO retreats ({', '.join(keys)}) VALUES ({', '.join('?' for _ in keys)})",
            tuple(fields[k] for k in keys)
        )
    conn.commit()
    conn.close()
    return slug


def process_url(url: str, dry_run: bool = False) -> dict:
    html = fetch_html(url)
    text = strip_to_text(html)
    data, usage = extract(url, text)
    if not data.get("is_actually_a_retreat", True):
        return {"url": url, "skipped": True, "reason": "not a retreat", "cost": cost_of(HAIKU, usage)}
    if dry_run:
        return {"url": url, "dry_run": True, "data": data, "cost": cost_of(HAIKU, usage)}
    slug = upsert(data, url)
    return {"url": url, "slug": slug, "cost": cost_of(HAIKU, usage), "tokens_in": usage.input_tokens, "tokens_out": usage.output_tokens}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="Single URL to scrape")
    parser.add_argument("--batch", action="store_true", help="Process all sources from data/sources.json")
    parser.add_argument("--include-discovered", action="store_true",
                        help="Also process new URLs from data/discovered_urls.json (filtered, deduped)")
    parser.add_argument("--limit", type=int, default=0, help="Limit batch size")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    started = now_iso()
    total_cost = 0
    total_in = total_out = 0
    items = 0
    errors = []

    try:
        if args.url:
            urls = [args.url]
        elif args.batch:
            sources = json.loads(SOURCES_PATH.read_text())["sources"]
            urls = [s["url"] for s in sources if s["type"] == "host"]
            if args.include_discovered and DISCOVERED_PATH.exists():
                # bridge discover -> scrape; dedupe vs already-scraped + sources before spending LLM
                conn = sqlite3.connect(DB_PATH)
                scraped = {r[0].rstrip("/") for r in conn.execute("SELECT source_url FROM retreats")}
                conn.close()
                known = scraped | {u.rstrip("/") for u in urls}
                discovered = json.loads(DISCOVERED_PATH.read_text())
                for d in discovered:
                    du = d.get("url", "").rstrip("/")
                    if du and du not in known:
                        urls.append(du)
                        known.add(du)
            if args.limit:
                urls = urls[: args.limit]
        else:
            parser.error("Pass --url or --batch")
            return
        for u in urls:
            try:
                r = process_url(u, dry_run=args.dry_run)
                items += 1
                total_cost += r.get("cost", 0)
                total_in += r.get("tokens_in", 0)
                total_out += r.get("tokens_out", 0)
                print(json.dumps(r, ensure_ascii=False)[:500])
            except BudgetExceeded as e:
                errors.append(f"BUDGET: {e}")
                break
            except Exception as e:
                errors.append(f"{u}: {e}")
                print(f"ERROR {u}: {e}")
        status = "ok" if not errors else "partial"
    except Exception as e:
        status = "failed"
        errors.append(str(e))

    log_run(
        agent_name="scraper",
        started_at=started,
        finished_at=now_iso(),
        tokens_in=total_in,
        tokens_out=total_out,
        cost_usd=round(total_cost, 6),
        items_processed=items,
        status=status,
        errors="; ".join(errors)[:1000] if errors else ""
    )
    print(f"\nScraper run: {items} items, ${total_cost:.4f}, status={status}")


if __name__ == "__main__":
    main()
