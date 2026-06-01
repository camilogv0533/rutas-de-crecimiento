#!/usr/bin/env python3
"""IA fallback: genera UNA imagen ilustrativa para retiros sin foto real.

Solo se usa cuando images.py no encontró imagen en la fuente. La imagen es
ILUSTRATIVA del lugar/habilidad (paisaje real del destino + mood), NUNCA finge
ser el venue específico — honestidad editorial (voice.md).

Flujo:
  1. Haiku escribe un prompt fotográfico desde los datos del retiro (~$0.001)
  2. gpt-image-1 genera 1536x1024 calidad media (~$0.06)
  3. Guarda PNG en site/public/img/retreats/<slug>.png (versionado, no hotlink)
  4. image_urls = ["/img/retreats/<slug>.png"]

Requiere OPENAI_API_KEY. Usage:
  python scripts/image_gen.py --slug wanderlearn-ischia
  python scripts/image_gen.py            # todos los activos sin imagen
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

from _llm import HAIKU, call, cost_of, log_run, now_iso

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "retreats.db"
OUT_DIR = ROOT / "site" / "public" / "img" / "retreats"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# gpt-image-1, 1536x1024 medium ≈ 1568 tokens × $40/1M ≈ $0.063
IMG_COST = 0.063

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
    "Escribes prompts para un generador de imágenes. Genera UNA escena fotográfica, "
    "editorial, realista, que ILUSTRE el lugar y el ambiente de aprendizaje de un retiro. "
    "Reglas: paisaje/entorno real del destino + luz natural cálida; sin texto, sin logos, "
    "sin personas reconocibles, sin marcas; NO inventes un edificio específico — evoca el "
    "lugar y la habilidad. Estilo: fotografía documental de viaje, formato horizontal. "
    "Devuelve el prompt EN INGLÉS llamando save_prompt."
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
    key = os.environ["OPENAI_API_KEY"]
    r = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": "gpt-image-1", "prompt": prompt, "size": "1536x1024",
              "quality": "medium", "n": 1},
        timeout=180,
    )
    r.raise_for_status()
    b64 = r.json()["data"][0]["b64_json"]
    # PNG crudo (~2.7MB) → webp comprimido (~150KB), ancho máx 1200px.
    img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    if img.width > 1200:
        img = img.resize((1200, round(img.height * 1200 / img.width)), Image.LANCZOS)
    path = OUT_DIR / f"{slug}.webp"
    img.save(path, "WEBP", quality=82, method=6)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug")
    ap.add_argument("--all", action="store_true", help="regenera TODOS los activos con IA (reemplaza fotos hotlink)")
    args = ap.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Falta OPENAI_API_KEY en el entorno.")

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
    for r in targets:
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
        print(f"    ✅ {path.name}  (~${IMG_COST:.3f})")

    log_run("image_gen", started, now_iso(), ti, to, tcost, len(targets), "success")
    print(f"\nGeneradas: {len(targets)}  costo total: ~${tcost:.3f}")


if __name__ == "__main__":
    main()
