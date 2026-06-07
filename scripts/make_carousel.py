#!/usr/bin/env python3
"""Genera un carrusel branded (PNG 1080x1920) desde un blog o topic.

Flujo:
  1. Haiku escribe copy de 5-7 slides + caption IG/FB + 3 prompts de imagen (1 call, tool-use).
  2. Gemini genera 3 imágenes de fondo editoriales (con guard de budget).
  3. slide_renderer renderiza los PNG branded.
  4. Escribe caption.md.

Costo: ~$0.001 (Haiku) + ~$0.12 (3 imgs Gemini) ≈ $0.12.

Usage:
  python scripts/make_carousel.py --topic "retiros de liderazgo"
  python scripts/make_carousel.py --blog content/drafts/articles/2026-06-07-x.md
  python scripts/make_carousel.py --topic "..." --out content/drafts/kits/x/carousel
"""
import argparse
import json
import re
from pathlib import Path

from _llm import HAIKU, MONTHLY_BUDGET, _month_cost, call, cost_of, log_run, now_iso
from content_gen import brand_system
import slide_renderer as sr

ROOT = Path(__file__).resolve().parent.parent

COPY_TOOL = {
    "name": "save_carousel",
    "description": "Copy de un carrusel de Instagram/Facebook para Rutas de Crecimiento.",
    "input_schema": {
        "type": "object",
        "properties": {
            "slides": {
                "type": "array",
                "description": "5-7 slides en orden: 1 hook, 3-5 body, 1 cta.",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["hook", "body", "cta"]},
                        "text": {"type": "string", "description": "≤14 palabras, 1 idea."},
                        "caption": {"type": "string", "description": "solo para cta: subtítulo corto"},
                    },
                    "required": ["type", "text"],
                },
            },
            "caption": {"type": "string", "description": "Caption del post IG/FB, 60-120 palabras + CTA + 3-5 hashtags."},
            "image_prompts": {
                "type": "array",
                "description": "3 prompts fotográficos EN INGLÉS, escena editorial de viaje, sin texto/logos, vertical.",
                "items": {"type": "string"},
            },
        },
        "required": ["slides", "caption", "image_prompts"],
    },
}


def gen_carousel_copy(title: str, context: str) -> tuple[dict, float, int, int]:
    user = (
        f"Crea un carrusel para Instagram/Facebook sobre: **{title}**\n\n"
        f"Contexto:\n{context[:2500]}\n\n"
        f"Reglas:\n"
        f"- 5-7 slides: slide 1 = hook que corta el scroll; 3-5 slides body (1 idea c/u, ≤14 palabras); "
        f"último slide = cta suave.\n"
        f"- Tono editorial-personal del brand voice, imagen sensorial, cero clichés ('cambiará tu vida', etc.).\n"
        f"- caption: 60-120 palabras + CTA suave + 3-5 hashtags relevantes en español.\n"
        f"- image_prompts: 3 escenas fotográficas en inglés (destino/ambiente concreto, luz cinematográfica, "
        f"presencia humana difusa, sin texto/logos), formato vertical 9:16.\n"
        f"Llama save_carousel."
    )
    resp = call(HAIKU, brand_system(), [{"role": "user", "content": user}],
                tools=[COPY_TOOL], tool_choice={"type": "tool", "name": "save_carousel"},
                max_tokens=1500)
    data = {}
    for b in resp.content:
        if b.type == "tool_use":
            data = b.input
            break
    return data, cost_of(HAIKU, resp.usage), resp.usage.input_tokens, resp.usage.output_tokens


def gen_bg_images(prompts: list[str], out_dir: Path, max_imgs: int = 3) -> list[Path]:
    """Gemini backgrounds con guard de budget. Devuelve paths .webp."""
    from image_gen import IMG_COST, generate_to_path
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, p in enumerate(prompts[:max_imgs], 1):
        if _month_cost() + IMG_COST >= MONTHLY_BUDGET:
            print(f"  🛑 Budget alcanzado, {len(paths)} bg generadas.")
            break
        try:
            out = generate_to_path(p, out_dir / f"bg_{i:02d}.webp")
            paths.append(out)
            log_run("make_carousel_img", now_iso(), now_iso(), 0, 0, IMG_COST, 1, "success")
            print(f"  ✅ bg_{i:02d}.webp (~${IMG_COST:.3f})")
        except Exception as e:
            print(f"  ⚠️ bg_{i} falló: {e}")
    return paths


def build_carousel(title: str, context: str, out_dir: Path, bg_images: list[Path] | None = None) -> dict:
    """Orquesta copy + bg + render. Devuelve {slides_png, caption, cost}."""
    started = now_iso()
    total_cost = total_in = total_out = 0
    data, c, ti, to = gen_carousel_copy(title, context)
    total_cost += c; total_in += ti; total_out += to
    slides = data.get("slides", [])
    if not slides:
        raise RuntimeError("Haiku no devolvió slides.")

    if bg_images is None:
        bg_images = gen_bg_images(data.get("image_prompts", []), out_dir / "bg")
        total_cost += len(bg_images) * 0.039
    bg_strs = [str(p) for p in bg_images]

    png_paths = sr.render_slides(slides, bg_strs, out_dir)
    (out_dir / "caption.md").write_text(
        f"# Carrusel — {title}\n\n{data.get('caption', '')}\n", encoding="utf-8")

    log_run("make_carousel", started, now_iso(), total_in, total_out,
            round(total_cost, 6), len(png_paths), "success")
    return {"slides_png": png_paths, "caption": data.get("caption", ""),
            "bg_images": bg_images, "cost": total_cost}


def _read_blog(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    m = re.search(r'title:\s*"?(.+?)"?\s*$', text, re.MULTILINE)
    title = m.group(1) if m else path.stem
    body = text.split("---", 2)[-1] if text.startswith("---") else text
    return title, body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic")
    ap.add_argument("--blog", help="path a un blog .md para basar el carrusel")
    ap.add_argument("--out", default=None, help="dir de salida (default: content/drafts/carousels/<slug>)")
    args = ap.parse_args()

    if args.blog:
        title, context = _read_blog(Path(args.blog))
    elif args.topic:
        title, context = args.topic, args.topic
    else:
        ap.error("Da --topic o --blog")

    from slugify import slugify
    out_dir = Path(args.out) if args.out else ROOT / "content" / "drafts" / "carousels" / slugify(title)[:60]
    print(f"Carrusel: '{title}' → {out_dir}")
    res = build_carousel(title, context, out_dir)
    print(f"\n{len(res['slides_png'])} slides, caption ok. Costo ~${res['cost']:.3f}")
    print(f"PNG en: {out_dir}")


if __name__ == "__main__":
    main()
