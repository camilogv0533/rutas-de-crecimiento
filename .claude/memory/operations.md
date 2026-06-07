# Operations — rutas-de-crecimiento

## Budget cap (updated 2026-06-06)
- `MONTHLY_BUDGET_USD=4.00` (bajado desde 6.50 → kill switch actualizado)
- Kill switch en `scripts/_llm.py::_check_budget()` — aborta calls si mes excede.
- Kill switch también cubre `gpt-image-1` / Gemini image calls vía `_month_cost()` check ANTES de cada llamada (no solo LLM wrapper).
- Motor de imágenes: **Gemini 2.5 Flash Image** (~$0.039/img). OpenAI gpt-image-1 eliminado.
- Gasto estimado real: ~$2.5/mes (margen ~$1.5).

## Schedule actual (todos 9am Ecuador / UTC-5 = cron 14 UTC)
- **scrape-weekly**: Lunes
- **mastermind-weekly**: Miércoles (NUEVO 2026-06-06) — busca masterminds con viaje
- **content-quincenal**: días 1 y 15 de cada mes (`cron: '45 15 1,15 * *'`) — genera kit completo: blog AEO + 5 tweets + LinkedIn + 3 imágenes + video script
- **ops-agent**: Martes
- **marketing-agent**: Jueves
- **weekly-digest**: Viernes
- **seo-audit**: Sábado
- **ux-agent**: Domingo

Todos tienen `environment: aprobacion` (approval gate antes de commit/push).

## URLs del sitio
- **Cloudflare Pages auto**: `https://rutas-de-crecimiento.pages.dev`
- **Custom domain**: `https://rutasdecrecimiento.com` — ✅ LIVE (2026-06-01). DNS en Cloudflare (NS apollo/lindsey.ns.cloudflare.com), HTTPS 200.

## Deploy automático
- `deploy.yml` usa `workflow_run` trigger (NO `push` — GitHub bloquea push del bot).
- Cubre: "Scrape weekly", "Content quincenal", "Mastermind weekly" + todos los CEO agents.
- Guard: `if: github.event.workflow_run.conclusion == 'success'` — no despliega si el workflow upstream falló.

## Telegram notification pattern
Bloque en cada workflow:
```yaml
- name: Notificacion Telegram
  if: always()
  env:
    BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
    CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
    RUN_URL: https://github.com/${{ github.repository }}/actions/runs/${{ github.run_id }}
    JOB_STATUS: ${{ job.status }}
```

## DB estado (2026-06-06)
- 14 retiros activos. Columna `categories` en retreats (CSV: "retiro,mastermind").
- Columna `image_url TEXT` en destinations table.
- 30 skills en DB. 17 con retiros → solo esas se exportan a `site/src/content/skills/`.
- `retreat_skills` tabla: clasificación con Haiku (confianza 0-1).

## Skills module (2026-06-06)
- `build_export.py::export_skills()` filtra `COUNT(rs.retreat_id) > 0` — solo 17 exported.
- `content.config.ts` incluye campo `retreat_count: z.number().default(0)`.
- Ciclo classify: si retiro → 0 skills, segunda llamada Haiku propone nuevas (confidence ≥ 0.7) → añade a DB + skills_taxonomy.json automáticamente.
- Iconos por habilidad: emoji map en `habilidades/index.astro` (sin deps externas).

## Verificación post-cambio
GitHub → Actions tab → workflow → ver schedules listados. Manual run via "Run workflow" button para probar antes del cron real.
