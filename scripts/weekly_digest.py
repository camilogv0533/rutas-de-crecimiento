#!/usr/bin/env python3
"""Resumen semanal — cada viernes te manda por Telegram qué publicar este fin de semana.

Lee social_ready/ y content/drafts/ generados esta semana.
Manda mensaje directo con copy listo para copiar-pegar.
"""
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOCIAL_DIR = ROOT / "data" / "social_ready"
DRAFTS_SOCIAL = ROOT / "content" / "drafts" / "social"
DRAFTS_ART = ROOT / "content" / "drafts" / "articles"

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

WEEK_AGO = datetime.utcnow() - timedelta(days=7)


def recent_files(directory: Path, suffix: str = ".md") -> list[Path]:
    if not directory.exists():
        return []
    files = []
    for f in directory.glob(f"*{suffix}"):
        try:
            if datetime.fromtimestamp(f.stat().st_mtime) > WEEK_AGO:
                files.append(f)
        except Exception:
            pass
    return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)


def extract_frontmatter_field(text: str, field: str) -> str:
    for line in text.splitlines():
        if line.startswith(f"{field}:"):
            return line.split(":", 1)[1].strip().strip('"')
    return ""


def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(url, data=data)
    urllib.request.urlopen(req, timeout=10)


def main():
    lines = [f"📋 Resumen semanal — {datetime.utcnow().strftime('%d %b %Y')}\n"]

    # Social copy listo
    social_files = recent_files(SOCIAL_DIR) + recent_files(DRAFTS_SOCIAL)
    if social_files:
        lines.append("📱 SOCIAL COPY LISTO PARA PUBLICAR:")
        for f in social_files[:4]:
            text = f.read_text(encoding="utf-8")
            platform = extract_frontmatter_field(text, "platform") or f.stem.split("-")[2] if "-" in f.stem else "social"
            topic = extract_frontmatter_field(text, "topic") or f.stem
            lines.append(f"  • {platform.upper()}: {topic[:60]}")
        lines.append(f"\nVer archivos: data/social_ready/ y content/drafts/social/")
    else:
        lines.append("📱 Sin social copy nuevo esta semana.")

    # Artículos pendientes de revisión
    art_files = recent_files(DRAFTS_ART)
    published = recent_files(ROOT / "site" / "src" / "content" / "blog")
    if art_files:
        lines.append(f"\n📝 ARTÍCULOS EN BORRADOR: {len(art_files)}")
        for f in art_files[:3]:
            text = f.read_text(encoding="utf-8")
            title = extract_frontmatter_field(text, "title") or f.stem
            lines.append(f"  • {title[:65]}")
        lines.append("El CEO Marketing los revisará el jueves — si quieres revisar antes: content/drafts/articles/")

    if published:
        lines.append(f"\n✅ Publicados esta semana: {len(published)} artículos en el sitio")

    lines.append("\n— Rutas Bot")

    msg = "\n".join(lines)
    send_telegram(msg)
    print("Digest enviado por Telegram.")


if __name__ == "__main__":
    main()
