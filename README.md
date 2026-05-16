# Rutas de Crecimiento

Directorio curado de viajes que desarrollan habilidades. Auto-alimentado por agentes.

## Setup
```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # rellenar keys
python scripts/init_db.py
cd site && npm install && cd ..
```

## Operación semanal (Camilo, sábado ~20min)
1. `streamlit run admin/streamlit_admin.py`
2. Revisar tab "Drafts pendientes" → aprobar/editar
3. Copiar posts aprobados a IG / LinkedIn / X / TikTok
4. Cerrar

## Crons activos
- Lunes 6am UTC: scrape + classify
- Miércoles 8am UTC: generar artículo + 4 posts sociales
- Sábado 10am UTC: SEO/AEO audit
- On push main: deploy a Cloudflare Pages

## Costos esperados
~$4/mes. Hard cap en `.env` `MONTHLY_BUDGET_USD`.

## Stack
Astro static · Cloudflare Pages · SQLite · Anthropic Haiku/Sonnet · Tavily · GitHub Actions
