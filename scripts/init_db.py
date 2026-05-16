#!/usr/bin/env python3
"""Initialize SQLite schema for Rutas de Crecimiento.

Idempotent — safe to run multiple times. Won't drop existing data.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "retreats.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS retreats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    source_url TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    tagline TEXT,
    intro TEXT,
    location_city TEXT,
    location_country TEXT,
    location_region TEXT,
    lat REAL,
    lng REAL,
    duration_days INTEGER,
    next_date TEXT,
    recurring TEXT,
    price_usd_from REAL,
    currency_original TEXT,
    price_original REAL,
    language TEXT,
    group_size_min INTEGER,
    group_size_max INTEGER,
    what_unique TEXT,
    who_for TEXT,
    sample_itinerary TEXT,
    what_youll_learn TEXT,
    included TEXT,
    not_included TEXT,
    accommodation TEXT,
    food TEXT,
    travel_logistics TEXT,
    accessibility TEXT,
    certifications TEXT,
    host_name TEXT,
    host_url TEXT,
    social_instagram TEXT,
    social_linkedin TEXT,
    image_urls TEXT,
    faq TEXT,
    categories TEXT,
    review_score REAL,
    scraped_at TEXT,
    last_seen_at TEXT,
    status TEXT DEFAULT 'active',
    reviewed_by_us INTEGER DEFAULT 0,
    seal_certified INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name_es TEXT NOT NULL,
    name_en TEXT,
    type TEXT,
    description_es TEXT,
    description_en TEXT,
    parent_id INTEGER REFERENCES skills(id)
);

CREATE TABLE IF NOT EXISTS retreat_skills (
    retreat_id INTEGER REFERENCES retreats(id) ON DELETE CASCADE,
    skill_id INTEGER REFERENCES skills(id) ON DELETE CASCADE,
    confidence REAL,
    PRIMARY KEY (retreat_id, skill_id)
);

CREATE TABLE IF NOT EXISTS destinations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    country TEXT,
    region TEXT,
    narrative_hook TEXT,
    unique_skills_associated TEXT
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    items_processed INTEGER DEFAULT 0,
    status TEXT,
    errors TEXT
);

CREATE TABLE IF NOT EXISTS content_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    platform TEXT,
    target_keyword TEXT,
    title TEXT,
    slug TEXT,
    body_md TEXT,
    suggested_image_prompt TEXT,
    related_retreat_slugs TEXT,
    refs TEXT,
    status TEXT DEFAULT 'draft',
    created_at TEXT NOT NULL,
    approved_at TEXT,
    published_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_retreats_status ON retreats(status);
CREATE INDEX IF NOT EXISTS idx_retreats_country ON retreats(location_country);
CREATE INDEX IF NOT EXISTS idx_agent_runs_month ON agent_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON content_drafts(status);
"""


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    print(f"DB ready: {DB_PATH}")
    print(f"Tables: {', '.join(t[0] for t in tables)}")
    conn.close()


if __name__ == "__main__":
    main()
