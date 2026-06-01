# Operations — rutas-de-crecimiento

## Budget cap
- `MONTHLY_BUDGET_USD=6.50` (subido desde 5.00 el 2026-05-18 al duplicar scrape+content).
- Kill switch en `scripts/_llm.py::_check_budget()` — aborta calls si mes excede.
- Hardcoded en 5 workflows: scrape, content, marketing, ops, ux.
- Costo proyectado real: ~$5.85/mes (margen $0.65).

## Schedule actual (todos 9am Ecuador / UTC-5 = cron 14 UTC)
- **scrape-weekly**: Lun + Jue (2x/sem)
- **content-weekly**: Mié + Sáb (2x/sem)
- **ops-agent**: Mar
- **marketing-agent**: Jue
- **weekly-digest**: Vie
- **seo-audit**: Sáb
- **ux-agent**: Dom

Razón duplicación: scrape captura retiros nuevos más fresh, content da más drafts para publicar. Resto no escala con frecuencia.

## URLs del sitio
- **Cloudflare Pages auto**: `https://rutas-de-crecimiento.pages.dev` — funciona apenas deploy corre.
- **Custom domain**: `https://rutasdecrecimiento.com` — ✅ LIVE (2026-06-01). DNS ya en Cloudflare (NS apollo/lindsey.ns.cloudflare.com), resuelve a IPs CF, HTTPS 200, sirve la prod de Pages. La migración SiteGround→CF ya está hecha.
- Notificaciones Telegram aún apuntan a pages.dev URL (cosmético; ambas sirven el mismo deploy).

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
Format MSG: icon + agent label + estado + RUN_URL + `Sitio: https://rutas-de-crecimiento.pages.dev`.

`weekly-digest.yml` tiene formato propio (digest semanal), no usa este pattern.

## Verificación post-cambio
GitHub → Actions tab → workflow → ver schedules listados. Manual run via "Run workflow" button para probar antes del cron real.
