---
name: seo_aeo_pass
description: >
  Auditoría manual SEO + AEO (Answer Engine Optimization para AI crawlers). Activar después de cambios mayores al sitio o si tracking orgánico cae. NO ejecutar en cada commit.
---

## Before starting
Build el sitio primero: `cd site && npm run build`.

## Step 1 — SEO técnico
- `sitemap.xml` válido y completo? `curl -s https://<dominio>/sitemap-index.xml`
- `robots.txt` permite crawl? `curl -s https://<dominio>/robots.txt`
- Cada retiro tiene `<title>`, `<meta name="description">`, OG tags?
- `hreflang` solo si hay variantes idioma (no aplica fase 1).

## Step 2 — Schema JSON-LD
- Cada retiro tiene `<script type="application/ld+json">` con tipo `TouristTrip` o `EducationEvent`?
- Pillar de habilidad tiene `WebPage` + `BreadcrumbList`?
- Validar en https://validator.schema.org/

## Step 3 — AEO (AI crawlers)
- `llms.txt` existe en raíz con índice estructurado?
- Markdown crudo accesible? (Astro genera HTML; agregar endpoint `/retiros/<slug>.md` si no existe).
- Contenido respondible: cada página responde una pregunta clara en H1?

## Step 4 — Performance
- Lighthouse SEO score > 95.
- LCP < 2s, CLS < 0.1.
- Imágenes lazy + WebP.

## Step 5 — Internal linking
- Cada retiro enlaza a su skill page y destination page (debe ser auto en template).
- Cada blog post enlaza a 3+ retiros relacionados.
- Pillar pages (skills) listan todos sus retiros sin pagination en primera página.

## Step 6 — Logear issues
Append a `.claude/findings.md` con lista de issues priorizada (P0/P1/P2) y archivo a tocar.

## After completing
Si issues P0 → crear tareas TaskCreate. Si solo P2 → dejar para próximo pass.
