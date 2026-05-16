#!/usr/bin/env python3
"""Seed skills table from data/skills_taxonomy.json. Idempotent."""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "retreats.db"
TAXONOMY = ROOT / "data" / "skills_taxonomy.json"


def main():
    data = json.loads(TAXONOMY.read_text())
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    inserted = updated = 0
    for s in data["skills"]:
        cur.execute("SELECT id FROM skills WHERE slug=?", (s["slug"],))
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE skills SET name_es=?, name_en=?, type=? WHERE slug=?",
                (s["name_es"], s.get("name_en"), s.get("type"), s["slug"]),
            )
            updated += 1
        else:
            cur.execute(
                "INSERT INTO skills (slug, name_es, name_en, type) VALUES (?,?,?,?)",
                (s["slug"], s["name_es"], s.get("name_en"), s.get("type")),
            )
            inserted += 1
    conn.commit()
    conn.close()
    print(f"Skills: {inserted} inserted, {updated} updated.")


if __name__ == "__main__":
    main()
