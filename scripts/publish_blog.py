#!/usr/bin/env python3
"""Publica drafts de artículos → site/src/content/blog/ (colección Astro).

El flujo semanal generaba drafts en content/drafts/articles/ pero nada los
movía al blog: el sitio se quedó con 1 post. Este script cierra ese gap.
El gate humano sigue siendo el Approve del workflow (environment 'aprobacion').

- Copia el draft a site/src/content/blog/<slug>.md sin el campo `status`,
  añadiendo `description` (primer párrafo, recortado) y el JSON-LD del
  .schema.json hermano si existe y es JSON válido.
- Marca el draft original como status: "published" (no se borra — historial).

Usage:
  python scripts/publish_blog.py --latest   # solo el draft más reciente (workflow)
  python scripts/publish_blog.py --all      # todos los pendientes (backfill)
  python scripts/publish_blog.py --dry-run --all
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRAFTS_DIR = ROOT / "content" / "drafts" / "articles"
BLOG_DIR = ROOT / "site" / "src" / "content" / "blog"


def parse_frontmatter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        raise ValueError("sin frontmatter")
    fm = {}
    for line in m.group(1).splitlines():
        kv = re.match(r"^(\w+):\s*(.*)$", line)
        if kv:
            fm[kv.group(1)] = kv.group(2).strip()
    return fm, m.group(2).strip()


def make_description(body: str, max_len: int = 160) -> str:
    for para in body.split("\n\n"):
        p = para.strip()
        if not p or p.startswith("#") or p.startswith("<!--"):
            continue
        # quitar markdown inline (links, énfasis)
        p = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", p)
        p = re.sub(r"[*_`]", "", p).strip()
        if len(p) > max_len:
            p = p[:max_len].rsplit(" ", 1)[0] + "…"
        return p
    return ""


def load_json_ld(draft_path: Path, slug: str) -> str | None:
    sidecar = draft_path.with_suffix(".schema.json")
    if not sidecar.exists():
        return None
    raw = sidecar.read_text(encoding="utf-8").strip()
    raw = raw.replace("[slug]", slug)
    try:
        return json.dumps(json.loads(raw), ensure_ascii=False)
    except json.JSONDecodeError:
        print(f"  ⚠ schema.json inválido, se omite: {sidecar.name}")
        return None


def publish(draft_path: Path, dry_run: bool) -> bool:
    text = draft_path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    if fm.get("status", "").strip('"') != "draft":
        return False
    slug = fm.get("slug", "").strip('"')
    if not slug:
        print(f"  ⚠ sin slug, se omite: {draft_path.name}")
        return False
    target = BLOG_DIR / f"{slug}.md"
    if target.exists():
        print(f"  ya publicado, se omite: {slug}")
        return False

    lines = ["---"]
    for k in ("title", "slug", "date", "target_keyword", "related_retreats"):
        if k in fm:
            lines.append(f"{k}: {fm[k]}")
    desc = make_description(body)
    if desc:
        lines.append(f'description: "{desc.replace(chr(34), chr(39))}"')
    json_ld = load_json_ld(draft_path, slug)
    if json_ld:
        lines.append("json_ld: |")
        lines.append(f"  {json_ld}")
    lines.append("---")
    content = "\n".join(lines) + "\n\n" + body + "\n"

    if dry_run:
        print(f"  [dry-run] publicaría: {slug}")
        return True
    BLOG_DIR.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    draft_path.write_text(text.replace('status: "draft"', 'status: "published"', 1), encoding="utf-8")
    print(f"  publicado: /blog/{slug}")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Publicar todos los drafts pendientes")
    parser.add_argument("--latest", action="store_true", help="Solo el draft más reciente")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    drafts = sorted(DRAFTS_DIR.glob("*.md"))
    if not drafts:
        print("Sin drafts en content/drafts/articles/")
        return
    if args.latest:
        drafts = drafts[-1:]
    elif not args.all:
        drafts = drafts[-1:]  # default seguro: solo el último

    published = sum(1 for d in drafts if publish(d, args.dry_run))
    print(f"\npublish_blog: {published} publicados de {len(drafts)} drafts revisados")


if __name__ == "__main__":
    main()
