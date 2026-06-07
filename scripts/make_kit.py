#!/usr/bin/env python3
"""Orquestador del kit quincenal de Rutas de Crecimiento.

Toma el/los blog(s) más recientes y produce TODO listo para copiar-pegar:
  - 2 imágenes estáticas branded (PNG)
  - 1 carrusel branded (PNGs + caption)
  - 1 tiktokslide.mp4 (slides → video)
  - 1 video (Hailuo IA por default, o ffmpeg slideshow)
  - 3 threads de Twitter/X
  - 1 long post (LinkedIn + X)
  - README.md con instrucciones de publicación por red

Respeta MONTHLY_BUDGET_USD; si se excede a mitad, guarda lo hecho y marca 'partial'.

Usage:
  python scripts/make_kit.py --cycle              # 2 blogs más recientes
  python scripts/make_kit.py --topic "..."        # genera blog fresco + kit
  python scripts/make_kit.py --blog path.md       # kit desde un blog concreto
  python scripts/make_kit.py --cycle --video ffmpeg   # video gratis en vez de Hailuo
"""
import argparse
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from slugify import slugify

from _llm import MONTHLY_BUDGET, _month_cost, BudgetExceeded, log_run, now_iso
import content_gen as cg
import make_carousel as mc

ROOT = Path(__file__).resolve().parent.parent
DRAFTS_ART = ROOT / "content" / "drafts" / "articles"
BLOG_PUB = ROOT / "site" / "src" / "content" / "blog"
KITS_DIR = ROOT / "content" / "drafts" / "kits"
PY = sys.executable


def latest_blogs(n: int = 2) -> list[Path]:
    """Blogs más recientes: primero drafts/articles, luego los publicados."""
    arts = sorted(DRAFTS_ART.glob("*.md"), reverse=True) if DRAFTS_ART.exists() else []
    if len(arts) < n and BLOG_PUB.exists():
        arts += sorted(BLOG_PUB.glob("*.md"), reverse=True)
    # dedup por nombre preservando orden
    seen, out = set(), []
    for p in arts:
        if p.name not in seen:
            seen.add(p.name); out.append(p)
    return out[:n]


def run_video(kit_dir: Path, mode: str, engine: str = "ffmpeg") -> bool:
    cmd = [PY, str(ROOT / "scripts" / "make_video.py"), "--kit", kit_dir.name, "--mode", mode]
    if mode == "slideshow":
        cmd += ["--engine", engine]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ⚠️ make_video ({mode}/{engine}) falló:\n{r.stderr[-800:]}")
        return False
    print(f"  ✅ video {mode}/{engine if mode=='slideshow' else '-'} ok")
    return True


def write_readme(kit_dir: Path, title: str, blogs: list[Path]):
    blog_list = "\n".join(f"  - {b.name}" for b in blogs)
    (kit_dir / "README.md").write_text(f"""# Kit quincenal — {title}
Fecha: {datetime.now(timezone.utc):%Y-%m-%d}
Blogs fuente:
{blog_list}

## Qué hay aquí
- `static/*.png` — 2 imágenes estáticas branded
- `carousel/*.png` + `carousel/caption.md` — carrusel IG/FB
- `tiktokslide.mp4` (en content/videos/) — slides → video vertical
- `video.mp4` (en content/videos/) — video (Hailuo IA o slideshow)
- `threads.md` — 3 threads de Twitter/X
- `longpost.md` — long post para LinkedIn y X

## Dónde publicar (copiar-pegar)
| Asset | Red |
|---|---|
| static/*.png | Instagram (post), Facebook |
| carousel/*.png + caption | Instagram (carrusel), Facebook |
| tiktokslide.mp4 | TikTok, Reels, YouTube Shorts |
| video.mp4 | TikTok, Reels, YouTube Shorts |
| threads.md | Twitter/X (1 thread por día) |
| longpost.md | LinkedIn + X (long-form) |

## Publicar el blog
Aprueba en el Content Studio (Streamlit) → mueve el .md a site/src/content/blog/.
""", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--cycle", action="store_true", help="usa los 2 blogs más recientes (default)")
    g.add_argument("--topic", help="genera un blog fresco sobre este topic y arma el kit")
    g.add_argument("--blog", help="path a un blog .md concreto")
    ap.add_argument("--video", choices=["hailuo", "ffmpeg"], default="hailuo",
                    help="motor del video principal (default hailuo ~$0.45)")
    ap.add_argument("--no-video", action="store_true", help="omite el video principal")
    args = ap.parse_args()

    started = now_iso()
    total_cost = 0.0
    errors = []
    status = "ok"

    # 1. Determinar blog(s) fuente
    if args.topic:
        print(f"Generando blog fresco: '{args.topic}'")
        article, c, _, _ = cg.gen_cluster_article(args.topic)
        total_cost += c
        path = cg.save_article(article)
        if article.get("json_ld"):
            path.with_suffix(".schema.json").write_text(article["json_ld"], encoding="utf-8")
        blogs = [path]
        title, context = article["title"], article["body"]
    else:
        src = [Path(args.blog)] if args.blog else []
        blogs = src or latest_blogs(2)
        if not blogs:
            sys.exit("No hay blogs. Corre content_gen.py --blog o usa --topic.")
        title, context = mc._read_blog(blogs[0])

    kit_dir = KITS_DIR / f"{datetime.now(timezone.utc):%Y-%m-%d}-{slugify(title)[:55]}"
    kit_dir.mkdir(parents=True, exist_ok=True)
    print(f"Kit: {kit_dir.name}\nBlogs fuente: {[b.name for b in blogs]}")

    try:
        # 2. Carrusel (genera copy + bg images + render PNG)
        print("\n[1/6] Carrusel…")
        car = mc.build_carousel(title, context, kit_dir / "carousel")
        total_cost += car["cost"]
        bg_images = car["bg_images"]

        # 3. 2 imágenes estáticas branded (reciclan los slides hook + cta — costo $0)
        print("[2/6] Estáticas…")
        static_dir = kit_dir / "static"
        static_dir.mkdir(exist_ok=True)
        pngs = car["slides_png"]
        picks = [pngs[0]] + ([pngs[-1]] if len(pngs) > 1 else [])
        for i, p in enumerate(picks, 1):
            shutil.copy(p, static_dir / f"static_{i:02d}.png")
        print(f"  ✅ {len(picks)} estáticas")

        # 4. images/ para video Hailuo (seed) — reusa los bg del carrusel
        if bg_images:
            (kit_dir / "images").mkdir(exist_ok=True)
            for i, bg in enumerate(bg_images, 1):
                shutil.copy(bg, kit_dir / "images" / f"image_{i:02d}.webp")

        # 5. tiktokslide.mp4 (slides → video)
        print("[3/6] TikTokSlide mp4…")
        run_video(kit_dir, mode="tiktokslide")

        # 6. video principal (Hailuo IA con fallback automático a ffmpeg $0)
        if not args.no_video:
            print(f"[4/6] Video ({args.video})…")
            ok = run_video(kit_dir, mode="slideshow", engine=args.video)
            if ok and args.video == "hailuo":
                total_cost += 0.45
            elif not ok and args.video == "hailuo":
                print("  ↪ Hailuo no disponible (balance fal/budget). Fallback a ffmpeg ($0)…")
                if run_video(kit_dir, mode="slideshow", engine="ffmpeg"):
                    errors.append("hailuo_fallback_ffmpeg")

        # 7. threads + longpost
        print("[5/6] Threads…")
        threads, c, _, _ = cg.gen_threads(title, context, slugify(title)[:70], n=3)
        total_cost += c
        (kit_dir / "threads.md").write_text(f"# Threads — {title}\n\n{threads}\n", encoding="utf-8")

        print("[6/6] Long post…")
        longp, c, _, _ = cg.gen_longpost(title, context, slugify(title)[:70])
        total_cost += c
        (kit_dir / "longpost.md").write_text(f"# Long post (LinkedIn + X) — {title}\n\n{longp}\n", encoding="utf-8")

        write_readme(kit_dir, title, blogs)

    except BudgetExceeded as e:
        status = "partial"; errors.append(f"BUDGET: {e}")
    except Exception as e:
        status = "failed"; errors.append(str(e))
        log_run("make_kit", started, now_iso(), 0, 0, round(total_cost, 6), 0, status,
                "; ".join(errors)[:1000])
        raise

    log_run("make_kit", started, now_iso(), 0, 0, round(total_cost, 6), 1, status,
            "; ".join(errors)[:1000] if errors else "")
    print(f"\n{'='*48}\nKit listo: {kit_dir}\nCosto total: ~${total_cost:.3f} | "
          f"mes: ${_month_cost():.3f}/{MONTHLY_BUDGET:.0f} | status={status}")


if __name__ == "__main__":
    main()
