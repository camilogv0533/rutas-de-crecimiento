#!/usr/bin/env python3
"""Extrae imágenes REALES de la página fuente de cada retiro ($0, sin LLM).

Estrategia (en orden de preferencia):
  1. og:image / twitter:image (suele ser el hero/cover real del retiro)
  2. link rel=image_src
  3. <img> grandes del contenido (filtra logos/iconos/avatares/sprites)

Valida que cada URL cargue y sea imagen real (>15KB). Guarda hasta 3 en
retreats.image_urls (JSON). Los que queden sin imagen → candidatos a IA fallback.

Usage:
  python scripts/images.py            # solo retiros activos sin imagen
  python scripts/images.py --all      # re-extrae todos
  python scripts/images.py --slug X   # uno
"""
import argparse
import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "retreats.db"
HEADERS = {"User-Agent": "RutasDeCrecimientoBot/0.1 (+https://rutasdecrecimiento.com)"}

# Patrones que descartan un <img> (no son foto del retiro).
BAD = re.compile(r"(logo|icon|favicon|sprite|avatar|badge|placeholder|spinner|"
                 r"pixel|tracking|1x1|blank|spacer|flag|payment|stripe|paypal|"
                 r"wp-content/plugins|gravatar|emoji|button)", re.I)
MIN_BYTES = 15_000  # <15KB suele ser logo/icono
WANT = 3


def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text


def candidates(html: str, base: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()

    def add(u):
        if not u:
            return
        u = urljoin(base, u.strip())
        if not u.startswith("http") or u in seen or BAD.search(u):
            return
        if urlparse(u).path.lower().endswith((".svg", ".gif")):
            return
        seen.add(u)
        out.append(u)

    # 1. meta og/twitter (hero real, prioridad)
    for prop in ("og:image", "og:image:url", "twitter:image", "twitter:image:src"):
        for m in soup.find_all("meta", attrs={"property": prop}) + soup.find_all("meta", attrs={"name": prop}):
            add(m.get("content"))
    for l in soup.find_all("link", rel="image_src"):
        add(l.get("href"))
    # 2. <img> del contenido (lazy-load incluido)
    for img in soup.find_all("img"):
        for attr in ("src", "data-src", "data-lazy-src", "data-original"):
            add(img.get(attr))
        srcset = img.get("srcset") or img.get("data-srcset")
        if srcset:
            add(srcset.split(",")[-1].strip().split(" ")[0])
    return out


def is_real_image(url: str) -> bool:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, stream=True)
        if r.status_code != 200:
            return False
        ct = r.headers.get("content-type", "")
        if not ct.startswith("image/") or "svg" in ct:
            return False
        cl = r.headers.get("content-length")
        if cl and int(cl) < MIN_BYTES:
            return False
        if not cl:  # sin header → leer un cacho
            chunk = next(r.iter_content(MIN_BYTES), b"")
            if len(chunk) < MIN_BYTES:
                return False
        return True
    except Exception:
        return False


def pick(url: str) -> list[str]:
    try:
        html = fetch(url)
    except Exception as e:
        print(f"    fetch fail: {e}")
        return []
    good = []
    for c in candidates(html, url):
        if is_real_image(c):
            good.append(c)
        if len(good) >= WANT:
            break
    return good


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--slug")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    q = "SELECT id,slug,source_url,image_urls FROM retreats WHERE status='active'"
    params = ()
    if args.slug:
        q += " AND slug=?"
        params = (args.slug,)
    rows = conn.execute(q, params).fetchall()

    found = nwith = 0
    no_image = []
    for r in rows:
        cur = r["image_urls"]
        has = bool(cur and cur not in ("[]", "null") and json.loads(cur))
        if has and not args.all:
            print(f"  skip (ya tiene): {r['slug']}")
            nwith += 1 if False else 0
            continue
        print(f"  buscando: {r['slug']}")
        imgs = pick(r["source_url"])
        if imgs:
            conn.execute("UPDATE retreats SET image_urls=? WHERE id=?",
                         (json.dumps(imgs), r["id"]))
            conn.commit()
            found += 1
            print(f"    ✅ {len(imgs)} imagen(es)")
        else:
            no_image.append(r["slug"])
            print(f"    ❌ sin imagen real")

    print(f"\nCon imagen nueva: {found}/{len(rows)}")
    if no_image:
        print(f"Sin imagen (candidatos IA fallback): {', '.join(no_image)}")


if __name__ == "__main__":
    main()
