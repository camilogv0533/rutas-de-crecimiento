---
name: add_source
description: >
  Añadir fuente nueva (URL base o sitemap) a data/sources.json para que el cron la scrape semanalmente. Invocar después de scraping-mastery global. NO usar para una URL one-off (usa scraper_run).
---

## Before starting
Apply skill: scraping-mastery (global) primero para validar la fuente.

## Step 1 — Categorizar
- ¿Es un agregador (BookRetreats, BlackTomato)? Marca `type: "aggregator"`.
- ¿Es un retreat host individual (alptitu.de)? `type: "host"`.
- ¿Tiene sitemap o feed? Anotar URL.

## Step 2 — Añadir entry a data/sources.json
```json
{
  "url": "https://example.com",
  "type": "host",
  "sitemap": "https://example.com/sitemap.xml",
  "language": "en",
  "added_at": "2026-05-16",
  "notes": "Hosts inmersivos en Italia, foco liderazgo"
}
```

## Step 3 — Test
```
python scripts/scraper.py --source <url> --limit 1 --dry-run
```

## Step 4 — Aprobar
Si dry-run extrae bien → quitar `--dry-run` y procesar 1 retiro como test.

## After completing
Append a `~/.claude/skills/scraping-mastery/references/source_library.md` con la fuente nueva y observaciones de extracción.
