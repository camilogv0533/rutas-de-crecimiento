# Setup — Próximos pasos manuales

Lo que YA quedó listo en código (corre solo cuando arranque el cron):
- Estructura de proyecto, CLAUDE.md, skills, .env.example, requirements.txt
- SQLite con schema, 30 habilidades, 12 destinos, 3 retiros semilla
- Sitio Astro estático: 50 páginas (home, retiros, habilidades, destinos, blog, llms.txt, sitemap, robots)
- Agentes Python: scraper, classify, content_gen, discover, seo_audit, build_export, _llm wrapper con budget kill
- 4 workflows GitHub Actions: scrape (lun 6am UTC), content (mié 8am UTC), seo audit (sáb 10am UTC), deploy on push
- Streamlit admin local con 5 tabs (drafts, retiros, costos, logs, findings)

Lo que necesita Camilo hacer (orden recomendado, ~45 min):

## 1. Dominio + Cloudflare (15 min)

1. Entra a SiteGround y localiza el dominio (probablemente `rutasdecrecimiento.com`).
2. Si está activo: déjalo registrado allí o transfiérelo a Cloudflare Registrar a costo (~$10/año). Recomiendo dejarlo en SiteGround si ya pagaste el año.
3. Crea cuenta gratis en https://cloudflare.com.
4. En Cloudflare → Add Site → entra el dominio. Elige plan **Free**.
5. Cloudflare te dará 2 nameservers. Cópialos.
6. En SiteGround → DNS / Domain → Nameservers → cambia a los de Cloudflare. (Toma 1–24h propagar.)
7. Cuando esté propagado: Cloudflare → Pages → Create project → "Direct Upload" o conecta GitHub. Project name: `rutas-de-crecimiento`.

## 2. GitHub (5 min)

```bash
cd ~/Desktop/AI\ Tools/rutas-de-crecimiento
git init
git add -A
git commit -m "init: rutas de crecimiento scaffold"
```

1. Crear repo `rutas-de-crecimiento` en https://github.com/new (público para tener 2000min CI gratis).
2. `git remote add origin git@github.com:<usuario>/rutas-de-crecimiento.git`
3. `git push -u origin main`

## 3. Secrets en GitHub (5 min)

GitHub repo → Settings → Secrets and variables → Actions → New secret:

- `ANTHROPIC_API_KEY` — desde https://console.anthropic.com (necesita ~$5 de crédito inicial)
- `TAVILY_API_KEY` — desde https://tavily.com (free tier 1000 búsquedas/mes)
- `CLOUDFLARE_API_TOKEN` — desde Cloudflare dashboard → My Profile → API Tokens → Create Token → "Edit Cloudflare Pages" template
- `CLOUDFLARE_ACCOUNT_ID` — Cloudflare dashboard, sidebar derecho

## 4. Primer setup local (10 min)

```bash
cd ~/Desktop/AI\ Tools/rutas-de-crecimiento
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Editar .env con ANTHROPIC_API_KEY y TAVILY_API_KEY reales

python scripts/init_db.py
python scripts/seed_skills.py
python scripts/seed_destinations.py
python scripts/seed_retreats_initial.py
python scripts/build_export.py

cd site && npm install && npm run dev
# Abrir http://localhost:4321
```

## 5. Probar scraper contra una URL (5 min · ~$0.01)

```bash
# dry-run (no escribe DB)
python scripts/scraper.py --url https://alptitu.de --dry-run

# real
python scripts/scraper.py --url https://alptitu.de
python scripts/classify.py --slug $(sqlite3 data/retreats.db "SELECT slug FROM retreats WHERE source_url='https://alptitu.de'")
python scripts/build_export.py
```

## 6. Probar admin (2 min)

```bash
streamlit run admin/streamlit_admin.py
# Abrir http://localhost:8501
```

## 7. Push y deploy (5 min)

```bash
git add -A && git commit -m "first deploy" && git push
# Cloudflare Pages auto-despliega en <60s
```

## 8. Trigger primer cron manual

GitHub repo → Actions → "Content weekly" → Run workflow.
Espera 5 min. Revisa `content/drafts/` — debería haber 1 artículo + 4 posts sociales.

---

## Cómo opera el sistema cada semana (sin Camilo)

- **Lunes 6am UTC** → scrape-weekly.yml descubre 3 búsquedas Tavily + scrapea 10 URLs nuevas + clasifica skills + commit + push → CF Pages despliega
- **Miércoles 8am UTC** → content-weekly.yml genera 1 artículo + 4 posts sociales en `content/drafts/` + commit + push
- **Sábado 10am UTC** → seo-audit-weekly.yml audita el build, escribe `.claude/findings.md` + commit + push

## Lo que Camilo hace los sábados (~20 min)

```bash
streamlit run admin/streamlit_admin.py
```
1. Tab "Drafts pendientes" → leer cada draft, aprobar o editar
2. Aprobar artículo → se copia auto a `site/src/content/blog/` → próximo push lo despliega
3. Aprobar social → leer texto y copiar a IG / LinkedIn / X / TikTok
4. Tab "Costos" → confirmar que vamos por debajo de $5/mes
5. Tab "Findings SEO" → si hay P0 abrirlos como issues
6. Cerrar

## Budget guards activos

- `.env` → `MONTHLY_BUDGET_USD=5` (hard cap, todo script aborta si excede)
- Cada `agent_runs` row loguea cost_usd
- Sonnet solo para content_gen (4 artículos/mes + 16 social = ~$2/mes)
- Haiku para scrape + classify (~120 retiros/mes = ~$1/mes)
- Total esperado: ~$3-4/mes

## Si algo falla

- GitHub Actions fallidos → email a Camilo automático
- Build de Astro falla → CF Pages reporta en email
- Budget excedido → script aborta con `BudgetExceeded` exception, run queda con status='partial'
- Para diagnosticar: `streamlit run admin/streamlit_admin.py` → tab Logs
