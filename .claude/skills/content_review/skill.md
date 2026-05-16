---
name: content_review
description: >
  Workflow sábado 20min. Revisa drafts pendientes en content/drafts/, los modifica si hace falta, marca aprobados, sugiere copy final para IG/LinkedIn/X. NO activar entre semana.
---

## Before starting
Read .claude/skills/brand_context/voice.md y .claude/skills/brand_context/icp.md.

## Step 1 — Listar drafts
```
ls -la content/drafts/articles/
ls -la content/drafts/social/
```

## Step 2 — Por cada draft article
1. Abrir el .md.
2. Verificar contra voice.md: ¿hay anti-patrones? ¿el tono coincide?
3. Verificar contra icp.md: ¿le habla al dolor real?
4. Verificar SEO básico: ¿target keyword en H1, en primer párrafo, en URL slug?
5. Si OK → mover a `content/approved/articles/`. Si no → editar y volver a verificar.

## Step 3 — Por cada draft social
1. Verificar plataforma (IG / LinkedIn / X / TikTok).
2. Cumple regla de palabras (IG 80-150, LinkedIn 200-350, X thread 4-6 tweets, TikTok script 30-60s).
3. Hook fuerte en primera línea.
4. CTA claro al final.
5. Si OK → mover a `content/approved/social/`.

## Step 4 — Imprimir resumen para Camilo
```
APROBADOS:
- 1 artículo: <title> → publicar como blog post
- 4 social: IG=<title>, LinkedIn=<title>, X=<title>, TikTok=<script>

PASOS:
1. Copiar artículo a Astro: site/src/content/blog/<slug>.md (ya lo movió este skill)
2. Push a main → CF Pages despliega
3. Copiar manualmente cada social post a su plataforma
```

## After completing
Si surgieron correcciones recurrentes, append a `.claude/context/learnings.md` sección `content_review`.
