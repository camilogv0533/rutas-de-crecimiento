---
name: scraper_run
description: >
  Invocar scraper manual contra una URL específica de retiro. Útil cuando Camilo encuentra un retiro nuevo y quiere añadirlo sin esperar al cron del lunes. NO usar para masivo (eso es el cron).
---

## Before starting
Read .claude/skills/brand_context/positioning.md para validar que la URL califica.

## Step 1 — Validar la URL
- ¿Es un retiro? (no un curso online, no un evento corporativo, no un hotel).
- ¿Conecta lugar con habilidad? Si no es claro, anotar como warning pero seguir.
- ¿robots.txt permite scrape? `curl -s <dominio>/robots.txt`.

## Step 2 — Ejecutar
```
python scripts/scraper.py --url <URL>
```

## Step 3 — Validar resultado
```
sqlite3 data/retreats.db "SELECT title, location_country, price_usd_from FROM retreats WHERE source_url='<URL>'"
```

## Step 4 — Classify
```
python scripts/classify.py --slug <slug>
```

## Step 5 — Build + preview
```
python scripts/build_export.py --only <slug>
cd site && npm run dev
# abrir http://localhost:4321/retiros/<slug>
```

## After completing
Si la fuente es buena, añadir a `data/sources.json` para que el cron la vuelva a visitar.
