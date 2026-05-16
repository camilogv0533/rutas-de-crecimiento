#!/usr/bin/env python3
"""Seed destinations table with curated narrative hooks. Idempotent."""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "retreats.db"

# Hooks curados manualmente: lugar -> habilidad asociada por narrativa.
DESTINATIONS = [
    {"slug": "turquia", "name": "Turquía", "country": "TR", "region": "Anatolia",
     "narrative_hook": "Alejandro Magno y el liderazgo en territorios desconocidos.",
     "skills": ["liderazgo", "estrategia", "toma-decisiones"]},
    {"slug": "italia-toscana", "name": "Toscana", "country": "IT", "region": "Toscana",
     "narrative_hook": "Renacimiento, mecenazgo y liderazgo de la creatividad.",
     "skills": ["liderazgo", "creatividad", "innovacion"]},
    {"slug": "italia-ischia", "name": "Ischia", "country": "IT", "region": "Campania",
     "narrative_hook": "Isla de aguas termales para reflexión profunda y reset ejecutivo.",
     "skills": ["proposito", "manejo-burnout", "mindfulness"]},
    {"slug": "alpes-franceses", "name": "Alpes Franceses", "country": "FR", "region": "Auvergne-Rhône-Alpes",
     "narrative_hook": "Cima y caminatas — toma de decisiones bajo incertidumbre.",
     "skills": ["liderazgo", "resiliencia", "toma-decisiones"]},
    {"slug": "japon-kyoto", "name": "Kyoto", "country": "JP", "region": "Kansai",
     "narrative_hook": "Filosofía de los cinco elementos y maestría artesanal.",
     "skills": ["mindfulness", "observacion-consciente", "creatividad"]},
    {"slug": "bali", "name": "Bali", "country": "ID", "region": "Bali",
     "narrative_hook": "Ritmo de vida lento — desintoxicación digital y sueño reparador.",
     "skills": ["habitos-sueno", "longevidad", "manejo-burnout"]},
    {"slug": "marruecos", "name": "Marruecos", "country": "MA", "region": "Atlas / Sahara",
     "narrative_hook": "Hospitalidad bereber y negociación en zocos — leer al otro.",
     "skills": ["negociacion", "comunicacion", "inteligencia-emocional"]},
    {"slug": "mongolia", "name": "Mongolia", "country": "MN", "region": "Estepa",
     "narrative_hook": "Liderazgo nómada — Gengis Kan, escala y autoridad ligera.",
     "skills": ["liderazgo", "estrategia", "resiliencia"]},
    {"slug": "espana-camino-santiago", "name": "Camino de Santiago", "country": "ES", "region": "Galicia",
     "narrative_hook": "Caminar como práctica de propósito y simplicidad.",
     "skills": ["proposito", "resiliencia", "mindfulness"]},
    {"slug": "islandia", "name": "Islandia", "country": "IS", "region": "Atlántico Norte",
     "narrative_hook": "Naturaleza extrema — toma de decisiones en condiciones cambiantes.",
     "skills": ["toma-decisiones", "resiliencia", "supervivencia-outdoor"]},
    {"slug": "kenia-tanzania-safari", "name": "Safari África Oriental", "country": "KE", "region": "Maasai Mara / Serengeti",
     "narrative_hook": "Observación, paciencia y conservación como liderazgo regenerativo.",
     "skills": ["observacion-consciente", "sostenibilidad", "liderazgo"]},
    {"slug": "patagonia", "name": "Patagonia", "country": "AR", "region": "Andes Sur",
     "narrative_hook": "Aislamiento productivo — claridad de pensamiento estratégico.",
     "skills": ["estrategia", "proposito", "resiliencia"]}
]


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    n = 0
    for d in DESTINATIONS:
        skills_json = json.dumps(d["skills"], ensure_ascii=False)
        cur.execute("SELECT id FROM destinations WHERE slug=?", (d["slug"],))
        if cur.fetchone():
            cur.execute(
                "UPDATE destinations SET name=?, country=?, region=?, narrative_hook=?, unique_skills_associated=? WHERE slug=?",
                (d["name"], d["country"], d["region"], d["narrative_hook"], skills_json, d["slug"]),
            )
        else:
            cur.execute(
                "INSERT INTO destinations (slug, name, country, region, narrative_hook, unique_skills_associated) VALUES (?,?,?,?,?,?)",
                (d["slug"], d["name"], d["country"], d["region"], d["narrative_hook"], skills_json),
            )
            n += 1
    conn.commit()
    conn.close()
    print(f"Destinations seeded: {n} new (total {len(DESTINATIONS)}).")


if __name__ == "__main__":
    main()
