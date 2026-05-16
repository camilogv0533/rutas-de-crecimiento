---
name: wrap_up
description: >
  Ejecutar al final de sesión cuando usuario escribe "wrap up". Extrae learnings y los clasifica en CLAUDE.md global / .claude/context/learnings.md / .claude/memory/. Append-only.
---

## Before starting
Identificar tipo de cosas aprendidas en esta sesión.

## Step 1 — Clasificar learnings
- Patrones universales (aplican a todos los proyectos) → `~/.claude/CLAUDE.md`
- Específicos de una skill → `.claude/context/learnings.md` sección de esa skill
- Específicos del proyecto Rutas → `.claude/memory/`

## Step 2 — Append, nunca sobrescribir
Si la sección ya existe, agregar bullet con fecha (`YYYY-MM-DD`).

## Step 3 — Listar cambios al usuario
"Guardé learnings en: <archivos>"

## After completing
No invocar otras skills.
