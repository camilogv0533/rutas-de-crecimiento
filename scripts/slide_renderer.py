"""Renderiza slides verticales 1080x1920 (PNG bytes) para carruseles y tiktokslides.

Estilo editorial Rutas de Crecimiento: foto a sangre + gradiente + texto.
Tipografía del design system global (Playfair display + IBM Plex Sans UI).
Sin logo (brand identity fuera de scope) — la marca es el nombre en texto + verde.

Portado de tiktokslidesmikefutia/services/slide_renderer.py, re-marcado.
"""
import io
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

CANVAS_W = 1080
CANVAS_H = 1920
SIDE_MARGIN = 90

FONT_DIR = Path(__file__).resolve().parent / "fonts"

# Design system global — accent del proyecto: verde
BRAND = {
    "primary": "#059669",   # accent-green
    "bg": "#FAFAF8",        # bg-primary
    "text": "#18181B",      # text-primary
    "accent": "#D97706",    # accent-warm
    "white": "#FFFFFF",
    "name": "Rutas de Crecimiento",
}


def _hex(color: str) -> tuple:
    h = color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _font_display(size: int) -> ImageFont.FreeTypeFont:
    """Playfair Display (titulares, hooks, CTA)."""
    f = ImageFont.truetype(str(FONT_DIR / "PlayfairDisplay.ttf"), size)
    try:
        f.set_variation_by_axes([700])
    except Exception:
        pass
    return f


def _font_ui(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    """IBM Plex Sans (cuerpo, labels)."""
    name = "IBMPlexSans-Bold.ttf" if bold else "IBMPlexSans-Regular.ttf"
    return ImageFont.truetype(str(FONT_DIR / name), size)


def _font_mono(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / "IBMPlexMono-Medium.ttf"), size)


def _draw_text_centered(draw, text, y, font, fill, max_chars=20, line_spacing=14, shadow=True):
    wrapped = textwrap.wrap(text, width=max_chars)
    cur_y = y
    for line in wrapped:
        bb = draw.textbbox((0, 0), line, font=font)
        lw, lh = bb[2] - bb[0], bb[3] - bb[1]
        x = max(SIDE_MARGIN, (CANVAS_W - lw) // 2)
        if shadow:
            draw.text((x + 3, cur_y + 3), line, font=font, fill=(0, 0, 0, 130))
        draw.text((x, cur_y), line, font=font, fill=fill)
        cur_y += lh + line_spacing
    return cur_y


def _blurred_bg(image_path: str, tint: str = None, strength: float = 0.32) -> Image.Image:
    src = Image.open(image_path).convert("RGB")
    scale = max(CANVAS_W / src.width, CANVAS_H / src.height)
    src = src.resize((int(src.width * scale), int(src.height * scale)), Image.LANCZOS)
    left = (src.width - CANVAS_W) // 2
    top = (src.height - CANVAS_H) // 2
    bg = src.crop((left, top, left + CANVAS_W, top + CANVAS_H))
    bg = bg.filter(ImageFilter.GaussianBlur(radius=18))
    tintc = Image.new("RGB", (CANVAS_W, CANVAS_H), _hex(tint or BRAND["text"]))
    return Image.blend(bg, tintc, strength).convert("RGBA")


def _gradient_bg(top: str, bottom: str) -> Image.Image:
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H))
    d = ImageDraw.Draw(img)
    c1, c2 = _hex(top), _hex(bottom)
    for y in range(CANVAS_H):
        t = y / CANVAS_H
        d.line([(0, y), (CANVAS_W, y)],
               fill=(int(c1[0] * (1 - t) + c2[0] * t),
                     int(c1[1] * (1 - t) + c2[1] * t),
                     int(c1[2] * (1 - t) + c2[2] * t), 255))
    return img


def _gradient_overlay(bg, y0, y1, color, a0, a1):
    ov = Image.new("RGBA", (CANVAS_W, y1 - y0), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for y in range(y1 - y0):
        t = y / max(1, y1 - y0)
        d.line([(0, y), (CANVAS_W, y)], fill=(*color, int(a0 * (1 - t) + a1 * t)))
    bg.paste(ov, (0, y0), ov)
    return bg


def _paste_photo(bg, image_path, hero_h, y_offset):
    try:
        src = Image.open(image_path).convert("RGBA")
        scale = CANVAS_W / src.width
        src = src.resize((CANVAS_W, int(src.height * scale)), Image.LANCZOS)
        crop_top = max(0, (src.height - hero_h) // 2)
        src = src.crop((0, crop_top, CANVAS_W, crop_top + min(hero_h, src.height)))
        bg.paste(src, (0, y_offset), src)
    except Exception:
        pass
    return bg


def _brand_label(draw, y=70, color=None):
    font = _font_mono(34)
    txt = BRAND["name"].upper()
    bb = draw.textbbox((0, 0), txt, font=font, features=["-kern"])
    x = (CANVAS_W - (bb[2] - bb[0])) // 2
    draw.text((x, y), txt, font=font, fill=(color or _hex(BRAND["white"])) + (235,))


def _kicker_bar(bg, y=130, h=8):
    bar = Image.new("RGBA", (160, h), (*_hex(BRAND["primary"]), 255))
    bg.paste(bar, ((CANVAS_W - 160) // 2, y), bar)
    return bg


def render_hook_slide(hook_text: str, image_path: str, theme: str = "clasico") -> bytes:
    bg = _blurred_bg(image_path, strength=0.20)
    bg = _paste_photo(bg, image_path, hero_h=1250, y_offset=240)
    bg = _gradient_overlay(bg, 0, 360, (0, 0, 0), 180, 0)
    bg = _gradient_overlay(bg, CANVAS_H - 900, CANVAS_H, _hex(BRAND["text"]), 0, 235)
    draw = ImageDraw.Draw(bg)
    _brand_label(draw, y=80)
    _kicker_bar(bg, y=140)
    draw = ImageDraw.Draw(bg)
    font = _font_display(96)
    n = max(1, len(textwrap.wrap(hook_text, width=18)))
    y = CANVAS_H - 360 - n * (96 + 14)
    _draw_text_centered(draw, hook_text, y, font, _hex(BRAND["white"]) + (255,), max_chars=18)
    return _to_bytes(bg)


def render_body_slide(body_text: str, image_path: str, theme: str = "clasico") -> bytes:
    bg = _blurred_bg(image_path, strength=0.20)
    bg = _paste_photo(bg, image_path, hero_h=1000, y_offset=180)
    bg = _gradient_overlay(bg, CANVAS_H - 1000, CANVAS_H, _hex(BRAND["text"]), 0, 245)
    draw = ImageDraw.Draw(bg)
    _brand_label(draw, y=80)
    font = _font_ui(70, bold=True)
    n = max(1, len(textwrap.wrap(body_text, width=22)))
    y = CANVAS_H - 280 - n * (70 + 16)
    _draw_text_centered(draw, body_text, y, font, _hex(BRAND["white"]) + (255,), max_chars=22)
    return _to_bytes(bg)


def render_cta_slide(cta_text: str, caption: str = "", image_path: str = None, theme: str = "gradiente") -> bytes:
    bg = _gradient_bg(BRAND["primary"], "#04734f")
    draw = ImageDraw.Draw(bg)
    _brand_label(draw, y=90, color=_hex(BRAND["white"]))
    _kicker_bar(bg, y=150)
    draw = ImageDraw.Draw(bg)
    font = _font_display(92)
    n = max(1, len(textwrap.wrap(cta_text, width=18)))
    y = (CANVAS_H - n * (92 + 14)) // 2 - 60
    end_y = _draw_text_centered(draw, cta_text, y, font, _hex(BRAND["white"]) + (255,),
                                max_chars=18, shadow=False)
    if caption:
        _draw_text_centered(draw, caption[:90], end_y + 60, _font_ui(42, bold=False),
                            _hex(BRAND["bg"]) + (220,), max_chars=32, shadow=False)
    # línea de cierre
    draw.line([(SIDE_MARGIN, CANVAS_H - 220), (CANVAS_W - SIDE_MARGIN, CANVAS_H - 220)],
              fill=_hex(BRAND["bg"]) + (140,), width=3)
    _draw_text_centered(draw, "rutasdecrecimiento.com", CANVAS_H - 180,
                        _font_mono(40), _hex(BRAND["bg"]) + (235,), max_chars=40, shadow=False)
    return _to_bytes(bg)


def _to_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def render_slides(slides: list[dict], image_paths: list[str], out_dir: Path) -> list[Path]:
    """slides: [{type:'hook'|'body'|'cta', text, caption?}]. Devuelve paths PNG escritos.

    image_paths se reciclan en orden para hook/body (CTA usa gradiente).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    img_i = 0
    imgs = image_paths or []
    for i, s in enumerate(slides, 1):
        kind = s.get("type", "body")
        img = imgs[img_i % len(imgs)] if imgs else None
        if kind == "hook":
            data = render_hook_slide(s["text"], img)
            img_i += 1
        elif kind == "cta":
            data = render_cta_slide(s["text"], s.get("caption", ""), img)
        else:
            data = render_body_slide(s["text"], img)
            img_i += 1
        p = out_dir / f"slide_{i:02d}.png"
        p.write_bytes(data)
        paths.append(p)
    return paths
