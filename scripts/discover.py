#!/usr/bin/env python3
"""Discover new retreat URLs via Tavily search. Appends candidates to data/discovered_urls.json.

Does NOT auto-add to sources.json — that's manual via add_source skill so brand context decides.

Usage:
  python scripts/discover.py
  python scripts/discover.py --limit 5
"""
import argparse
import json
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from tavily import TavilyClient

from _llm import now_iso, log_run

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
DB_PATH = ROOT / "data" / "retreats.db"
SOURCES = ROOT / "data" / "sources.json"
DISCOVERED = ROOT / "data" / "discovered_urls.json"
KEYWORDS = ROOT / "data" / "keywords_es.json"

SEARCH_TERMS_EN = [
    "immersive learning retreat 2026",
    "leadership retreat europe 2026",
    "purpose retreat for executives 2026",
    "creativity retreat for founders",
    "skills tourism retreat",
    "transformational travel skill development",
    "executive burnout retreat 2026",
    "mastermind retreat for entrepreneurs"
]

MASTERMIND_SEARCH_TERMS = [
    "mastermind retreat presencial viaje 2026",
    "mastermind group in-person destination 2026",
    "mastermind retreat entrepreneurs travel Europe",
    "mastermind retreat leadership destination 2026",
    "peer mastermind group retreat founders 2026",
]


def existing_hosts() -> set:
    sources = json.loads(SOURCES.read_text())["sources"]
    return {s["url"].rstrip("/") for s in sources}


def already_scraped_hosts() -> set:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT DISTINCT source_url FROM retreats").fetchall()
    conn.close()
    from urllib.parse import urlparse
    hosts = set()
    for (u,) in rows:
        p = urlparse(u)
        hosts.add(f"{p.scheme}://{p.netloc}")
    return hosts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=3, help="Number of queries to issue")
    parser.add_argument("--query-override", help="Use mastermind-specific search terms instead of default")
    args = parser.parse_args()

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        print("TAVILY_API_KEY missing; skipping discover.")
        return

    client = TavilyClient(api_key=api_key)
    seen = existing_hosts() | already_scraped_hosts()
    discovered = []
    if DISCOVERED.exists():
        discovered = json.loads(DISCOVERED.read_text())
    discovered_urls = {d["url"] for d in discovered}

    # Choose search terms: mastermind-specific or default
    if args.query_override and "mastermind" in args.query_override.lower():
        terms = MASTERMIND_SEARCH_TERMS
    else:
        terms = SEARCH_TERMS_EN

    started = now_iso()
    new_count = 0
    for term in terms[: args.limit]:
        try:
            res = client.search(query=term, max_results=10, search_depth="basic")
            for item in res.get("results", []):
                url = item.get("url", "").rstrip("/")
                if not url or url in seen or url in discovered_urls:
                    continue
                from urllib.parse import urlparse
                host = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
                if host in seen:
                    continue
                discovered.append({
                    "url": url,
                    "host": host,
                    "title": item.get("title"),
                    "snippet": item.get("content", "")[:300],
                    "found_at": now_iso(),
                    "found_via": term
                })
                discovered_urls.add(url)
                new_count += 1
        except Exception as e:
            print(f"Tavily error for '{term}': {e}")

    DISCOVERED.parent.mkdir(parents=True, exist_ok=True)
    DISCOVERED.write_text(json.dumps(discovered, indent=2, ensure_ascii=False))
    log_run(
        agent_name="discover",
        started_at=started,
        finished_at=now_iso(),
        tokens_in=0, tokens_out=0, cost_usd=0,
        items_processed=new_count, status="ok"
    )
    print(f"Discover: {new_count} new candidates → {DISCOVERED.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
