#!/usr/bin/env python3
"""Genera video 12-15s vertical (9:16) a partir de un kit quincenal.

Toma las imágenes del kit, aplica Ken-Burns (pan/zoom), quema captions
del video_script.md, añade música CC0 de fondo. Resultado: MP4 listo
para TikTok/Reels/Twitter.

Costo: <$0.05 (solo ffmpeg local, sin llamadas API externas).

Opcional: --engine hailuo → clip AI 10s via Hailuo-02 (~$0.45-0.70).
Requiere FAL_KEY en .env para ese modo.

Usage:
  python scripts/make_video.py --kit 2026-06-15-retiros-de-liderazgo
  python scripts/make_video.py --kit content/drafts/kits/2026-06-15-retiros
  python scripts/make_video.py --kit 2026-06-15-retiros --engine hailuo
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
KITS_DIR = ROOT / "content" / "drafts" / "kits"
OUT_DIR = ROOT / "content" / "videos"
MUSIC_DIR = Path(__file__).resolve().parent.parent.parent / "videocontentmachine" / "storage" / "music"
FALLBACK_MUSIC = list(MUSIC_DIR.glob("*.mp3"))[:1] if MUSIC_DIR.exists() else []

load_dotenv(ROOT / ".env")

VIDEO_W = 1080
VIDEO_H = 1920
VIDEO_DUR = 14  # seconds total


def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        sys.exit("ffmpeg no está instalado. Instala con: brew install ffmpeg")


def find_kit(kit_arg: str) -> Path:
    p = Path(kit_arg)
    if p.is_absolute() and p.exists():
        return p
    if (ROOT / kit_arg).exists():
        return ROOT / kit_arg
    matches = list(KITS_DIR.glob(f"*{kit_arg}*"))
    if matches:
        return sorted(matches)[-1]
    sys.exit(f"Kit no encontrado: {kit_arg}. Kits disponibles en {KITS_DIR}:\n" +
             "\n".join(f"  {k.name}" for k in sorted(KITS_DIR.iterdir()) if k.is_dir()))


def find_images(kit_dir: Path) -> list[Path]:
    imgs = sorted((kit_dir / "images").glob("*.webp")) if (kit_dir / "images").exists() else []
    if not imgs:
        imgs = sorted(kit_dir.glob("*.webp"))
    if not imgs:
        sys.exit(f"No hay imágenes .webp en {kit_dir}/images/")
    return imgs[:3]


def parse_captions(kit_dir: Path) -> list[str]:
    """Extrae las líneas de CAPTIONS del video_script.md."""
    script = kit_dir / "video_script.md"
    if not script.exists():
        return []
    text = script.read_text(encoding="utf-8")
    m = re.search(r"## CAPTIONS\n(.*?)(?:\n## |\Z)", text, re.DOTALL)
    if not m:
        return []
    lines = [l.strip() for l in m.group(1).strip().split("\n") if l.strip()]
    return lines


def has_drawtext() -> bool:
    """Check if ffmpeg was compiled with drawtext (libfreetype) support."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-filters"], capture_output=True, text=True
        )
        return "drawtext" in result.stdout
    except Exception:
        return False


def build_ffmpeg_cmd(
    images: list[Path],
    captions: list[str],
    music_path: Path | None,
    out_path: Path,
) -> list[str]:
    """Construye comando ffmpeg para slideshow Ken-Burns 9:16."""
    n = len(images)
    dur_per_img = VIDEO_DUR / n  # segundos por imagen
    use_captions = captions and has_drawtext()

    inputs = []
    filter_parts = []
    overlay_inputs = []

    for i, img in enumerate(images):
        inputs += ["-loop", "1", "-t", str(dur_per_img + 1), "-i", str(img)]
        filter_parts.append(
            f"[{i}:v]scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=increase,"
            f"crop={VIDEO_W}:{VIDEO_H},setsar=1,fps=25[v{i}]"
        )

    # xfade cross-dissolve entre imágenes (1s overlap al final de cada clip)
    if n == 1:
        filter_parts.append(f"[v0]trim=duration={VIDEO_DUR}[video_raw]")
    elif n == 2:
        offset = dur_per_img - 1
        filter_parts.append(
            f"[v0][v1]xfade=transition=fade:duration=1:offset={offset:.2f}[video_raw]"
        )
    else:
        # encadenar xfade progresivamente
        prev = "v0"
        for i in range(1, n):
            offset = (i * dur_per_img) - 1
            out = "video_raw" if i == n - 1 else f"xf{i}"
            filter_parts.append(
                f"[{prev}][v{i}]xfade=transition=fade:duration=1:offset={offset:.2f}[{out}]"
            )
            prev = out

    if use_captions:
        cap_filter = "[video_raw]"
        t_per_cap = VIDEO_DUR / len(captions)
        for j, cap in enumerate(captions):
            t_start = j * t_per_cap
            t_end = (j + 1) * t_per_cap
            safe_cap = cap.replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")
            draw = (
                f"drawtext=text='{safe_cap}':fontsize=52:fontcolor=white:"
                f"x=(w-text_w)/2:y=h*0.82-text_h/2:"
                f"box=1:boxcolor=black@0.55:boxborderw=12:"
                f"enable='between(t,{t_start:.2f},{t_end:.2f})'"
            )
            cap_filter += f"{draw},"
        cap_filter = cap_filter.rstrip(",")
        filter_parts.append(cap_filter + "[video_out]")
    else:
        filter_parts.append("[video_raw]copy[video_out]")

    filter_complex = ";".join(filter_parts)

    cmd = ["ffmpeg", "-y"]
    cmd += inputs

    audio_map = []
    if music_path and music_path.exists():
        cmd += ["-i", str(music_path)]
        audio_map = ["-map", f"{n}:a", "-af", f"afade=t=out:st={VIDEO_DUR-2}:d=2,volume=0.12", "-shortest"]

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[video_out]",
    ]
    cmd += audio_map
    cmd += [
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        "-r", "25",
        str(out_path),
    ]
    return cmd


def run_hailuo(images: list[Path], kit_dir: Path, out_path: Path):
    """Genera clip AI 10s con Hailuo-02 vía fal. Requiere FAL_KEY."""
    import os, base64, requests as rq, io
    from PIL import Image as PILImage

    fal_key = os.environ.get("FAL_KEY")
    if not fal_key:
        sys.exit("FAL_KEY no encontrada en .env. Necesaria para --engine hailuo.")

    print("  Convirtiendo imagen seed a base64…")
    img = PILImage.open(images[0]).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    b64 = base64.b64encode(buf.getvalue()).decode()
    image_data_uri = f"data:image/jpeg;base64,{b64}"

    captions = parse_captions(kit_dir)
    prompt_text = " ".join(captions[:2]) if captions else "editorial travel learning scene, cinematic"

    print(f"  Llamando Hailuo-02 (10s, ~$0.45)…")
    resp = rq.post(
        "https://fal.run/fal-ai/minimax/hailuo-02/standard/image-to-video",
        headers={"Authorization": f"Key {fal_key}", "Content-Type": "application/json"},
        json={
            "image_url": image_data_uri,
            "prompt": prompt_text,
            "duration": 10,
        },
        timeout=300,
    )
    resp.raise_for_status()
    data = resp.json()
    video_url = data.get("video", {}).get("url")
    if not video_url:
        sys.exit(f"Hailuo no devolvió URL de video: {data}")

    print(f"  Descargando video…")
    vr = rq.get(video_url, timeout=120)
    vr.raise_for_status()
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(vr.content)
        tmp_path = Path(tmp.name)

    # Convertir a 9:16 si hace falta
    print("  Post-procesando…")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(tmp_path),
        "-vf", f"scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=decrease,"
               f"pad={VIDEO_W}:{VIDEO_H}:(ow-iw)/2:(oh-ih)/2:color=black",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        str(out_path),
    ], check=True)
    tmp_path.unlink(missing_ok=True)
    print(f"  Costo estimado: ~$0.45 (10s × $0.045/s)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kit", required=True, help="Nombre o path del kit (ej: 2026-06-15-retiros)")
    parser.add_argument("--engine", choices=["ffmpeg", "hailuo"], default="ffmpeg",
                        help="ffmpeg = slideshow Ken-Burns gratuito (default) | hailuo = clip IA ~$0.45")
    args = parser.parse_args()

    check_ffmpeg()

    kit_dir = find_kit(args.kit)
    print(f"Kit: {kit_dir.name}")

    images = find_images(kit_dir)
    print(f"Imágenes: {[i.name for i in images]}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{kit_dir.name}.mp4"

    if args.engine == "hailuo":
        run_hailuo(images, kit_dir, out_path)
    else:
        captions = parse_captions(kit_dir)
        print(f"Captions: {len(captions)} líneas")

        music = FALLBACK_MUSIC[0] if FALLBACK_MUSIC else None
        if music:
            print(f"Música: {music.name}")
        else:
            print("Música: ninguna (instala música CC0 en videocontentmachine/storage/music/)")

        cmd = build_ffmpeg_cmd(images, captions, music, out_path)
        print(f"\nGenerando slideshow ffmpeg…")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print("ffmpeg error:")
            print(result.stderr[-2000:])
            sys.exit(1)

    print(f"\nVideo generado: {out_path}")
    print(f"Duración: ~{VIDEO_DUR}s | Resolución: {VIDEO_W}x{VIDEO_H} (9:16)")
    print(f"Costo: <$0.05 (ffmpeg local)" if args.engine == "ffmpeg" else "Costo: ~$0.45 (Hailuo-02)")


if __name__ == "__main__":
    main()
