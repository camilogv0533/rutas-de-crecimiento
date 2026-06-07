#!/usr/bin/env python3
"""Export SQLite → MD frontmatter para Astro content collections.

Genera:
  site/src/content/retreats/<slug>.md
  site/src/content/skills/<slug>.md
  site/src/content/destinations/<slug>.md

(blog/ se escribe directamente por content_gen.py)
"""
import argparse
import json
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "retreats.db"
SITE_CONTENT = ROOT / "site" / "src" / "content"


def yaml_value(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        items = ", ".join(json.dumps(x, ensure_ascii=False) for x in v)
        return f"[{items}]"
    s = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{s}"'


def write_md(path: Path, frontmatter: dict, body: str = ""):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for k, v in frontmatter.items():
        lines.append(f"{k}: {yaml_value(v)}")
    lines.append("---")
    lines.append("")
    if body:
        lines.append(body)
    path.write_text("\n".join(lines), encoding="utf-8")


def export_retreats(conn, only_slug: str | None = None):
    out_dir = SITE_CONTENT / "retreats"
    if not only_slug and out_dir.exists():
        shutil.rmtree(out_dir)
    cur = conn.cursor()
    if only_slug:
        cur.execute("SELECT * FROM retreats WHERE slug=? AND status='active'", (only_slug,))
    else:
        cur.execute("SELECT * FROM retreats WHERE status='active'")
    cols = [d[0] for d in cur.description]
    n = 0
    for row in cur.fetchall():
        r = dict(zip(cols, row))
        rid = r["id"]
        skill_rows = conn.execute(
            "SELECT s.slug FROM skills s JOIN retreat_skills rs ON s.id=rs.skill_id WHERE rs.retreat_id=?",
            (rid,)
        ).fetchall()
        skills = [s[0] for s in skill_rows]
        destinations = []
        if r.get("location_country"):
            dest_rows = conn.execute(
                "SELECT slug FROM destinations WHERE country=?", (r["location_country"],)
            ).fetchall()
            destinations = [d[0] for d in dest_rows]
        fm = {
            "slug": r["slug"],
            "title": r["title"],
            "tagline": r.get("tagline") or "",
            "source_url": r["source_url"],
            "host_name": r.get("host_name") or "",
            "host_url": r.get("host_url") or "",
            "location_city": r.get("location_city") or "",
            "location_country": r.get("location_country") or "",
            "location_region": r.get("location_region") or "",
            "duration_days": r.get("duration_days"),
            "recurring": r.get("recurring") or "",
            "price_usd_from": r.get("price_usd_from"),
            "currency_original": r.get("currency_original") or "",
            "price_original": r.get("price_original"),
            "language": r.get("language") or "",
            "group_size_max": r.get("group_size_max"),
            "what_unique": r.get("what_unique") or "",
            "who_for": r.get("who_for") or "",
            "skills": skills,
            "destinations": destinations,
            "reviewed_by_us": bool(r.get("reviewed_by_us")),
            "image_urls": json.loads(r["image_urls"]) if r.get("image_urls") else [],
            "categories": [c.strip() for c in (r.get("categories") or "retiro").split(",") if c.strip()],
        }
        for k in ("title", "tagline", "host_name", "host_url", "location_city",
                  "location_country", "location_region", "recurring",
                  "currency_original", "language", "what_unique", "who_for"):
            if fm.get(k) == "":
                del fm[k]
        for k in ("duration_days", "price_usd_from", "price_original", "group_size_max"):
            if fm.get(k) is None:
                del fm[k]
        body = (r.get("intro") or "").strip()
        write_md(out_dir / f"{r['slug']}.md", fm, body)
        n += 1
    print(f"Retreats exported: {n} → {out_dir}")


def export_skills(conn):
    out_dir = SITE_CONTENT / "skills"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    # Only export skills with at least one linked retreat
    cur = conn.execute(
        "SELECT s.slug, s.name_es, s.name_en, s.type, s.description_es, COUNT(rs.retreat_id) as cnt "
        "FROM skills s JOIN retreat_skills rs ON s.id=rs.skill_id "
        "GROUP BY s.id HAVING cnt > 0 ORDER BY cnt DESC"
    )
    n = 0
    for slug, name_es, name_en, stype, desc, cnt in cur.fetchall():
        fm = {"slug": slug, "name_es": name_es, "retreat_count": cnt}
        if name_en:
            fm["name_en"] = name_en
        if stype:
            fm["type"] = stype
        if desc:
            fm["description_es"] = desc
        write_md(out_dir / f"{slug}.md", fm)
        n += 1
    print(f"Skills exported: {n} (with retreats)")


def export_destinations(conn):
    out_dir = SITE_CONTENT / "destinations"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    # Only export destinations with at least one active retreat
    cur = conn.execute(
        "SELECT d.slug, d.name, d.country, d.region, d.narrative_hook, d.unique_skills_associated, d.image_url "
        "FROM destinations d "
        "WHERE EXISTS ("
        "  SELECT 1 FROM retreats r WHERE r.location_country = d.country AND r.status='active'"
        ") ORDER BY d.name"
    )
    n = 0
    for row in cur.fetchall():
        slug, name, country, region, hook, skills_json, image_url = row
        skills = json.loads(skills_json) if skills_json else []
        fm = {"slug": slug, "name": name}
        if country:
            fm["country"] = country
        if region:
            fm["region"] = region
        if hook:
            fm["narrative_hook"] = hook
        fm["skills"] = skills
        if image_url:
            fm["image_url"] = image_url
        write_md(out_dir / f"{slug}.md", fm)
        n += 1
    print(f"Destinations exported: {n} (with retreats)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="Export only a single retreat slug")
    args = parser.parse_args()
    conn = sqlite3.connect(DB_PATH)
    if args.only:
        export_retreats(conn, only_slug=args.only)
    else:
        export_retreats(conn)
        export_skills(conn)
        export_destinations(conn)
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
