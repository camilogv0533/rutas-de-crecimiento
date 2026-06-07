#!/usr/bin/env python3
"""IA fallback: genera UNA imagen ilustrativa para retiros sin foto real.

Solo se usa cuando images.py no encontró imagen en la fuente. La imagen es
ILUSTRATIVA del lugar/habilidad (paisaje real del destino + mood), NUNCA finge
ser el venue específico — honestidad editorial (voice.md).

Flujo:
  1. Haiku escribe un prompt fotográfico desde los datos del retiro (~$0.001)
  2. Gemini 2.5 Flash Image genera la imagen (~$0.039)
  3. Guarda como webp en site/public/img/retreats/<slug>.webp (versionado)
  4. image_urls = ["/img/retreats/<slug>.webp"]

Requiere GEMINI_API_KEY. Usage:
  python scripts/image_gen.py --slug wanderlearn-ischia
  python scripts/image_gen.py            # todos los activos sin imagen propia
  python scripts/image_gen.py --all      # regenera todos (reemplaza existentes)
"""
import argparse
import base64
import io
import json
import os
import sqlite3
from pathlib import Path

import requests
from PIL import Image

from _llm import HAIKU, MONTHLY_BUDGET, _month_cost, call, cost_of, log_run, now_iso

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "retreats.db"
OUT_DIR = ROOT / "site" / "public" / "img" / "retreats"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Gemini 2.5 Flash Image ≈ $0.039/imagen (estimado conservador)
IMG_COST = 0.039

PROMPT_TOOL = {
    "name": "save_prompt",
    "description": "Prompt fotográfico en inglés para un generador de imágenes.",
    "input_schema": {
        "type": "object",
        "properties": {"prompt": {"type": "string"}},
        "required": ["prompt"],
    },
}

PROMPT_SYS = (
    "Escribes prompts fotográficos para un generador de imágenes de viaje editorial. "
    "Crea UNA escena fotográfica específica que ilustre el lugar y el ambiente de aprendizaje del retiro. "
    "Reglas de calidad: "
    "(1) Detalle arquitectónico o paisajístico MUY específico del destino (ej: tejados terracota toscanos, fiordo noruego al amanecer, adobe nuevo-mexicano). "
    "(2) Presencia humana difusa/de espaldas permitida — sin rostros reconocibles. "
    "(3) Luz cinematográfica: hora dorada, contraluz suave o luz de ventana interior. "
    "(4) Lente 35mm f/2.0, profundidad de campo visible, bokeh suave en fondo. "
    "(5) Sin texto, sin logos, sin marcas. "
    "(6) NO menciones 'retreat' ni 'workshop' — solo escena del lugar. "
    "Estilo: fotografía documental de viaje, Magnum Photos, formato horizontal 16:9. "
    "Devuelve el prompt EN INGLÉS llamando save_prompt (máx 200 palabras)."
)


def make_prompt(r: dict) -> tuple[str, object]:
    desc = (
        f"Retiro: {r['title']}\nLugar: {r.get('location_city')}, {r.get('location_region')}, "
        f"{r.get('location_country')}\nQué lo hace único: {r.get('what_unique')}\n"
        f"Para quién: {r.get('who_for')}"
    )
    resp = call(
        model=HAIKU, system=PROMPT_SYS,
        messages=[{"role": "user", "content": desc}],
        tools=[PROMPT_TOOL], tool_choice={"type": "tool", "name": "save_prompt"},
        max_tokens=512,
    )
    for b in resp.content:
        if b.type == "tool_use":
            return b.input["prompt"], resp.usage
    raise RuntimeError("no prompt")


def generate(prompt: str, slug: str) -> Path:
    key = os.environ["GEMINI_API_KEY"]
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key={key}",
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        },
        timeout=180,
    )
    r.raise_for_status()
    candidates = r.json().get("candidates", [])
    b64_data = None
    for candidate in candidates:
        for part in candidate.get("content", {}).get("parts", []):
            if "inlineData" in part:
                b64_data = part["inlineData"]["data"]
                break
        if b64_data:
            break
    if not b64_data:
        raise RuntimeError(f"Gemini no devolvió imagen. Response: {r.text[:500]}")
    # PNG crudo → webp comprimido (~150KB), ancho máx 1200px.
    img = Image.open(io.BytesIO(base64.b64decode(b64_data))).convert("RGB")
    if img.width > 1200:
        img = img.resize((1200, round(img.height * 1200 / img.width)), Image.LANCZOS)
    path = OUT_DIR / f"{slug}.webp"
    img.save(path, "WEBP", quality=82, method=6)
    return path


def generate_to_path(prompt: str, out_path: Path) -> Path:
    """Generate image from prompt and save to specified path (webp)."""
    key = os.environ["GEMINI_API_KEY"]
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key={key}",
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        },
        timeout=180,
    )
    r.raise_for_status()
    b64_data = None
    for candidate in r.json().get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            if "inlineData" in part:
                b64_data = part["inlineData"]["data"]
                break
        if b64_data:
            break
    if not b64_data:
        raise RuntimeError(f"Gemini no devolvió imagen: {r.text[:400]}")
    img = Image.open(io.BytesIO(base64.b64decode(b64_data))).convert("RGB")
    if img.width > 1200:
        img = img.resize((1200, round(img.height * 1200 / img.width)), Image.LANCZOS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "WEBP", quality=82, method=6)
    return out_path


def generate_hero() -> Path:
    """Genera imagen hero para la portada del sitio."""
    hero_prompt = (
        "Editorial travel photograph. A person silhouetted against dramatic Andean mountain peaks at golden hour, "
        "sitting on stone steps of an ancient terraced landscape, writing in a journal. "
        "Warm ochre and deep green tones, cinematic depth of field, 35mm f/2.0 lens, "
        "Magnum Photos style, horizontal 16:9, no text, no logos."
    )
    out_dir = ROOT / "site" / "public" / "img"
    out_dir.mkdir(parents=True, exist_ok=True)
    key = os.environ["GEMINI_API_KEY"]
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key={key}",
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": hero_prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        },
        timeout=180,
    )
    r.raise_for_status()
    candidates = r.json().get("candidates", [])
    b64_data = None
    for candidate in candidates:
        for part in candidate.get("content", {}).get("parts", []):
            if "inlineData" in part:
                b64_data = part["inlineData"]["data"]
                break
        if b64_data:
            break
    if not b64_data:
        raise RuntimeError(f"Gemini hero: no imagen. Response: {r.text[:500]}")
    img = Image.open(io.BytesIO(base64.b64decode(b64_data))).convert("RGB")
    if img.width > 1400:
        img = img.resize((1400, round(img.height * 1400 / img.width)), Image.LANCZOS)
    path = out_dir / "hero.webp"
    img.save(path, "WEBP", quality=85, method=6)
    return path


DEST_OUT_DIR = ROOT / "site" / "public" / "img" / "destinations"
DEST_OUT_DIR.mkdir(parents=True, exist_ok=True)


def generate_destination_image(dest_slug: str, dest_name: str, country: str | None) -> Path:
    """Generate an evocative landscape image for a destination."""
    country_hint = f" in {country}" if country else ""
    prompt = (
        f"Editorial travel photograph of {dest_name}{country_hint}. "
        "Iconic landscape that captures the spirit of this place: natural light, golden hour or blue hour, "
        "architectural or natural landmark recognizable but not branded, diffuse human presence (silhouette, backs), "
        "35mm lens, cinematic depth of field, no text, no logos, no watermarks. "
        "Colors authentic to the location's climate and culture."
    )
    path = DEST_OUT_DIR / f"{dest_slug}.webp"
    return generate_to_path(prompt, path)


def run_destinations(only_slug: str | None = None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if only_slug:
        rows = conn.execute(
            "SELECT slug, name, country FROM destinations WHERE slug=?", (only_slug,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT d.slug, d.name, d.country FROM destinations d "
            "WHERE NOT EXISTS (SELECT 1 FROM retreats r WHERE r.location_country=d.country AND r.status='active') IS NOT 1 "
            "AND (d.image_url IS NULL OR d.image_url = '')"
        ).fetchall()
    conn.close()
    if not rows:
        print("Todos los destinos ya tienen imagen.")
        return

    est = len(rows) * IMG_COST
    print(f"Generar {len(rows)} imagen(es) destino — costo estimado: ${est:.3f}")
    for row in rows:
        if _month_cost() + IMG_COST >= MONTHLY_BUDGET:
            print("🛑 Budget alcanzado.")
            break
        slug = row["slug"]
        print(f"  {slug}...")
        path = generate_destination_image(slug, row["name"], row["country"])
        rel = f"/img/destinations/{slug}.webp"
        c2 = sqlite3.connect(DB_PATH)
        c2.execute("UPDATE destinations SET image_url=? WHERE slug=?", (rel, slug))
        c2.commit()
        c2.close()
        log_run("image_gen_dest", now_iso(), now_iso(), 0, 0, IMG_COST, 1, "success")
        print(f"    ✅ {path.name}  (~${IMG_COST:.3f})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug")
    ap.add_argument("--all", action="store_true", help="regenera TODOS los activos con IA (reemplaza fotos hotlink)")
    ap.add_argument("--hero", action="store_true", help="genera solo la imagen hero de portada")
    ap.add_argument("--destinations", action="store_true", help="genera imágenes para destinos sin imagen")
    ap.add_argument("--destination-slug", help="genera imagen para un destino específico")
    args = ap.parse_args()

    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("Falta GEMINI_API_KEY en el entorno.")

    if args.hero:
        path = generate_hero()
        print(f"Hero generado: {path}  (~${IMG_COST:.3f})")
        return

    if args.destinations or args.destination_slug:
        run_destinations(only_slug=args.destination_slug)
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    q = "SELECT * FROM retreats WHERE status='active'"
    params = ()
    if args.slug:
        q += " AND slug=?"
        params = (args.slug,)
    rows = [dict(r) for r in conn.execute(q, params)]

    targets = []
    for r in rows:
        iu = r.get("image_urls")
        has = bool(iu and iu not in ("[]", "null") and json.loads(iu))
        # Solo IA: regenera si no tiene imagen IA propia (/img/retreats/...).
        own_ia = has and "/img/retreats/" in (iu or "")
        if args.all or args.slug or not own_ia:
            targets.append(r)

    if not targets:
        print("Nada que generar — todos tienen imagen.")
        return

    est = len(targets) * IMG_COST
    print(f"Generar {len(targets)} imagen(es) IA — costo estimado: ${est:.3f}")

    started = now_iso()
    tcost = ti = to = 0
    done = 0
    for r in targets:
        # Kill switch: la imagen NO pasa por _llm.call, así que la chequeamos aquí.
        # Si el gasto del mes + esta imagen supera el budget, paramos.
        if _month_cost() + IMG_COST >= MONTHLY_BUDGET:
            print(f"\n🛑 Budget ${MONTHLY_BUDGET:.2f} alcanzado (mes: ${_month_cost():.3f}). "
                  f"Detenido. Faltaron {len(targets) - done} imagen(es).")
            break
        prompt, usage = make_prompt(r)
        tcost += cost_of(HAIKU, usage)
        ti += getattr(usage, "input_tokens", 0)
        to += getattr(usage, "output_tokens", 0)
        print(f"  {r['slug']}\n    prompt: {prompt[:80]}...")
        path = generate(prompt, r["slug"])
        rel = f"/img/retreats/{r['slug']}.webp"
        conn.execute("UPDATE retreats SET image_urls=? WHERE id=?",
                     (json.dumps([rel]), r["id"]))
        conn.commit()
        tcost += IMG_COST
        done += 1
        # Loguea incremental para que _month_cost refleje el gasto de imagen en tiempo real.
        log_run("image_gen", started, now_iso(), ti, to, IMG_COST + cost_of(HAIKU, usage),
                1, "success")
        print(f"    ✅ {path.name}  (~${IMG_COST:.3f})")

    print(f"\nGeneradas: {done}/{len(targets)}  costo total: ~${tcost:.3f}")


if __name__ == "__main__":
    main()
