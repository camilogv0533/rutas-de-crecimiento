# Kit quincenal — Retiros de liderazgo en los Andes: qué son, para quién y por qué importa el lugar
Fecha: 2026-06-06 | Topic: retiros de liderazgo en los Andes

## Archivos
- `blog.md` — artículo pillar AEO/SEO/GEO (publicar en sitio)
- `schema.json` — JSON-LD Article + FAQPage (añadir al <head> de la página)
- `tweets.md` — 5 tweets standalone para publicar 1/día
- `linkedin.md` — post largo LinkedIn
- `video_script.md` — guion 12-15s + notas producción
- `images/*.webp` — imágenes editoriales IA

## Flujo de publicación (finde de semana)
1. Revisar blog.md y aprobarlo en content_review
2. Añadir blog.md a site/src/content/blog/ para publicar
3. Copiar schema.json al layout de la página del blog
4. Publicar tweets 1 por día (lunes a viernes)
5. Publicar linkedin.md el lunes siguiente
6. Generar video: `python scripts/make_video.py --kit {kit_dir.name}`