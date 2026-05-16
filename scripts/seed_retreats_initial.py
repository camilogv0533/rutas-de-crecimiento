#!/usr/bin/env python3
"""Seed 3 retreats curados manualmente desde docs del usuario.
Datos serán enriquecidos/sobrescritos por scraper.py cuando corra.
Idempotente.
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "retreats.db"

NOW = datetime.utcnow().isoformat() + "Z"

RETREATS = [
    {
        "slug": "alptitude-alpes-franceses",
        "source_url": "https://alptitu.de",
        "title": "Alptitude — Liderazgo en los Alpes franceses",
        "tagline": "Cinco días de coaching de liderazgo entre cumbres alpinas.",
        "intro": "Alptitude reúne a líderes de alto desempeño en los Alpes franceses para una semana de reflexión, caminatas guiadas y coaching ejecutivo. La premisa: el aire delgado, el silencio de la montaña y la fatiga compartida revelan patrones de decisión que la oficina esconde.",
        "location_city": "Chamonix",
        "location_country": "FR",
        "location_region": "Auvergne-Rhône-Alpes",
        "duration_days": 5,
        "recurring": "2 cohortes al año",
        "price_usd_from": 4500,
        "currency_original": "EUR",
        "price_original": 4200,
        "language": "EN",
        "group_size_max": 12,
        "what_unique": "El programa combina caminatas técnicas con sesiones de coaching individual y grupal. Cada actividad outdoor refleja un dilema de liderazgo: la cuerda compartida en una vía ferrata enseña delegación; la decisión de retroceder ante el clima practica el juicio bajo presión.",
        "who_for": "Líderes senior, founders y ejecutivos C-level que sienten que la rutina diaria erosiona su criterio estratégico.",
        "what_youll_learn": ["liderazgo", "toma-decisiones", "resiliencia"],
        "host_name": "Alptitude",
        "host_url": "https://alptitu.de",
        "destinations": ["alpes-franceses"]
    },
    {
        "slug": "epic-leadership-kripalu",
        "source_url": "https://epicleadership.org/kripalu-2023/",
        "title": "Epic Leadership at Kripalu — Liderazgo y mindfulness",
        "tagline": "Liderazgo, presencia y propósito en el centro Kripalu de Massachusetts.",
        "intro": "Epic Leadership trae su programa intensivo de liderazgo al campus boscoso de Kripalu en los Berkshires. La metodología combina prácticas contemplativas con simulaciones de liderazgo organizacional, integrando cuerpo y estrategia.",
        "location_city": "Stockbridge",
        "location_country": "US",
        "location_region": "Berkshires, Massachusetts",
        "duration_days": 4,
        "recurring": "Anual",
        "price_usd_from": 3200,
        "currency_original": "USD",
        "price_original": 3200,
        "language": "EN",
        "group_size_max": 24,
        "what_unique": "Kripalu es uno de los centros de retreats de bienestar más serios de Norteamérica. Epic Leadership aprovecha el ecosistema (yoga, alimentación, naturaleza) para integrar prácticas que sostienen el liderazgo a largo plazo — no como descanso, sino como tecnología de presencia.",
        "who_for": "Ejecutivos, directores de L&D y founders interesados en integrar mindfulness con práctica de liderazgo organizacional.",
        "what_youll_learn": ["liderazgo", "mindfulness", "inteligencia-emocional"],
        "host_name": "Epic Leadership",
        "host_url": "https://epicleadership.org",
        "destinations": []
    },
    {
        "slug": "wanderlearn-ischia",
        "source_url": "https://www.wanderlearnretreats.com/ischia2024",
        "title": "WanderLearn Ischia — Creatividad y reset ejecutivo",
        "tagline": "Una semana en la isla termal italiana para creadores en busca de claridad.",
        "intro": "WanderLearn Ischia mezcla la tradición termal de la isla con sesiones de escritura, exploración cultural y coaching individual. La isla es pequeña, lenta, y profundamente sensorial — el contraste con la vida ejecutiva acelera el descubrimiento de ritmos creativos sostenibles.",
        "location_city": "Ischia",
        "location_country": "IT",
        "location_region": "Campania",
        "duration_days": 7,
        "recurring": "1 cohorte al año",
        "price_usd_from": 3900,
        "currency_original": "USD",
        "price_original": 3900,
        "language": "EN",
        "group_size_max": 10,
        "what_unique": "El programa está construido alrededor de tres anclas: prácticas creativas matutinas, exploración cultural curada, y reflexión nocturna en grupo. La pequeña escala y la geografía de la isla obligan a un encuentro humano denso — improbable en retiros de 50 personas.",
        "who_for": "Creadores, escritores, founders early-stage y profesionales senior con un proyecto creativo aplazado.",
        "what_youll_learn": ["creatividad", "proposito", "escritura"],
        "host_name": "WanderLearn Retreats",
        "host_url": "https://www.wanderlearnretreats.com",
        "destinations": ["italia-ischia"]
    }
]


def upsert_retreat(cur, r):
    cur.execute("SELECT id FROM retreats WHERE slug=?", (r["slug"],))
    row = cur.fetchone()
    fields = {
        "slug": r["slug"],
        "source_url": r["source_url"],
        "title": r["title"],
        "tagline": r["tagline"],
        "intro": r["intro"],
        "location_city": r.get("location_city"),
        "location_country": r.get("location_country"),
        "location_region": r.get("location_region"),
        "duration_days": r.get("duration_days"),
        "recurring": r.get("recurring"),
        "price_usd_from": r.get("price_usd_from"),
        "currency_original": r.get("currency_original"),
        "price_original": r.get("price_original"),
        "language": r.get("language"),
        "group_size_max": r.get("group_size_max"),
        "what_unique": r.get("what_unique"),
        "who_for": r.get("who_for"),
        "host_name": r.get("host_name"),
        "host_url": r.get("host_url"),
        "scraped_at": NOW,
        "last_seen_at": NOW,
        "status": "active",
        "reviewed_by_us": 1
    }
    if row:
        retreat_id = row[0]
        keys = [k for k in fields if k != "slug"]
        cur.execute(
            f"UPDATE retreats SET {', '.join(f'{k}=?' for k in keys)} WHERE slug=?",
            tuple(fields[k] for k in keys) + (r["slug"],),
        )
    else:
        keys = list(fields.keys())
        cur.execute(
            f"INSERT INTO retreats ({', '.join(keys)}) VALUES ({', '.join('?' for _ in keys)})",
            tuple(fields[k] for k in keys),
        )
        retreat_id = cur.lastrowid
    cur.execute("DELETE FROM retreat_skills WHERE retreat_id=?", (retreat_id,))
    for skill_slug in r.get("what_youll_learn", []):
        cur.execute("SELECT id FROM skills WHERE slug=?", (skill_slug,))
        sk = cur.fetchone()
        if sk:
            cur.execute(
                "INSERT INTO retreat_skills (retreat_id, skill_id, confidence) VALUES (?, ?, 1.0)",
                (retreat_id, sk[0]),
            )


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for r in RETREATS:
        upsert_retreat(cur, r)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM retreats").fetchone()[0]
    nrs = conn.execute("SELECT COUNT(*) FROM retreat_skills").fetchone()[0]
    conn.close()
    print(f"Retreats: {n} total. Retreat-skill links: {nrs}.")


if __name__ == "__main__":
    main()
