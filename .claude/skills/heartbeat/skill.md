---
name: heartbeat
description: >
  Ejecutar al inicio de cada sesión en este proyecto. Reporta: drafts pendientes en content/drafts/, últimos agent_runs en DB, costo del mes, próximo cron. NO activar para preguntas conceptuales.
---

## Before starting
Read .claude/context/learnings.md (sección heartbeat).

## Step 1 — Listar drafts pendientes
```
ls content/drafts/articles/ 2>/dev/null | wc -l
ls content/drafts/social/ 2>/dev/null | wc -l
```

## Step 2 — Últimos agent_runs
```
sqlite3 data/retreats.db "SELECT agent_name, started_at, items_processed, cost_usd, status FROM agent_runs ORDER BY started_at DESC LIMIT 5;"
```

## Step 3 — Costo del mes acumulado
```
sqlite3 data/retreats.db "SELECT ROUND(SUM(cost_usd),3) FROM agent_runs WHERE strftime('%Y-%m', started_at) = strftime('%Y-%m','now');"
```

## Step 4 — Reportar
Imprimir en bloque tipo:
```
DRAFTS:    X articles | Y social posts pending
AGENT RUNS: último <agent_name> a <hora>, status=<status>
COSTO MES: $X.XX / $5.00
PRÓXIMO:   <lunes 6am UTC = scrape>
```

## After completing
Si drafts > 0, sugerir: `streamlit run admin/streamlit_admin.py`.
