# CLAUDE.md — Rutas de Crecimiento

> Hereda global `~/.claude/CLAUDE.md`. Aquí solo lo único de este proyecto.

## Qué es
Directorio público de viajes/retiros curados que desarrollan habilidades (turismo para el desarrollo de habilidades). Stack: Astro estático + Cloudflare Pages + SQLite versionada + agentes Python en GitHub Actions.

## Dominio
Comprado en **SiteGround** (Camilo localiza fecha/email). DNS se reapunta a Cloudflare Pages.

## Restricción de costo
≤ $5/mes ideal, ≤ $10/mes máximo. Hard kill switch en `MONTHLY_BUDGET_USD`.

## Modelos
- Haiku 4.5 (`claude-haiku-4-5-20251001`): scraping, classify, dedupe.
- Sonnet 4.6 (`claude-sonnet-4-6`): contenido (artículos, social), auditoría, copy curado.
- Nunca Opus.

## Accent color del proyecto
Verde `#059669` (`--accent-green` del design system global). Crecimiento, naturaleza, rutas.

## Idioma
Español primero. Inglés se considera fase 6 (>500 visitas/mes orgánico).

## Comandos clave
- `python scripts/scraper.py --url <URL>` — scrape un retiro
- `python scripts/build_export.py` — DB → MD para Astro
- `python scripts/content_gen.py --topic <X> --type article|social` — draft contenido
- `cd site && npm run dev` — sitio local
- `streamlit run admin/streamlit_admin.py` — admin local

## Tono (voice)
Curaduría editorial seria pero personal. Lee `.claude/skills/brand_context/voice.md` antes de cualquier draft.

## Reglas de scope
- Mecánica masiva (scrape, classify): Haiku.
- Texto humano-facing: Sonnet con voice.md como system prompt.
- Drafts a `content/drafts/`. Nunca auto-publicar a redes.
- Cada agent_run loguea cost_usd en SQLite. Abortar si excede budget mensual.

## Skill triggers obligatorios
- Antes de añadir fuente nueva: `Apply skill: scraping-mastery` (global) + `add_source` (local).
- Revisar drafts sábado: `Apply skill: content_review`.
- Auditoría SEO/AEO manual: `Apply skill: seo_aeo_pass`.
