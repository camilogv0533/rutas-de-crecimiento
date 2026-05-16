#!/usr/bin/env python3
"""SEO + AEO audit of built site. Writes findings to .claude/findings.md.

Run after `npm run build` in site/.
"""
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "site" / "dist"
FINDINGS = ROOT / ".claude" / "findings.md"


def severity(s: str) -> str:
    return {"P0": "🔴 P0", "P1": "🟡 P1", "P2": "🔵 P2"}.get(s, s)


def main():
    findings = []

    sitemap = DIST / "sitemap-index.xml"
    if not sitemap.exists():
        findings.append(("P0", "site/dist", "sitemap-index.xml ausente — verifica @astrojs/sitemap"))
    else:
        text = sitemap.read_text()
        if "<sitemap>" not in text:
            findings.append(("P0", "sitemap-index.xml", "sitemap vacío"))

    robots = DIST / "robots.txt"
    if not robots.exists():
        findings.append(("P0", "public/robots.txt", "falta"))
    else:
        if "Sitemap:" not in robots.read_text():
            findings.append(("P1", "robots.txt", "no apunta a sitemap"))

    llms = DIST / "llms.txt"
    if not llms.exists():
        findings.append(("P0", "llms.txt", "ausente — endpoint pages/llms.txt.ts no se generó"))
    else:
        body = llms.read_text()
        if len(body) < 200:
            findings.append(("P1", "llms.txt", f"contenido muy corto ({len(body)} chars)"))
        if "## Retiros" not in body:
            findings.append(("P1", "llms.txt", "falta sección Retiros"))

    retreat_pages = list((DIST / "retiros").glob("*/index.html"))
    schema_missing = []
    title_missing = []
    desc_missing = []
    for p in retreat_pages:
        html = p.read_text()
        if "application/ld+json" not in html:
            schema_missing.append(p.parent.name)
        if not re.search(r"<title>[^<]+</title>", html):
            title_missing.append(p.parent.name)
        if not re.search(r'<meta\s+name="description"', html):
            desc_missing.append(p.parent.name)
    if schema_missing:
        findings.append(("P1", "retiros/", f"JSON-LD ausente en: {', '.join(schema_missing[:5])}"))
    if title_missing:
        findings.append(("P0", "retiros/", f"<title> ausente en: {', '.join(title_missing[:5])}"))
    if desc_missing:
        findings.append(("P1", "retiros/", f"meta description ausente en: {', '.join(desc_missing[:5])}"))

    index = DIST / "index.html"
    if index.exists():
        html = index.read_text()
        if "<meta property=\"og:image\"" not in html:
            findings.append(("P2", "index.html", "og:image ausente"))
        if html.count("<a ") < 5:
            findings.append(("P2", "index.html", "pocos links internos en home"))

    FINDINGS.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# SEO + AEO findings",
        f"_Run at {datetime.utcnow().isoformat()}Z_",
        f"_Site built at: {DIST}_",
        "",
        f"Total findings: {len(findings)}",
        ""
    ]
    if not findings:
        lines.append("✅ No issues detected.")
    else:
        for sev, where, msg in sorted(findings):
            lines.append(f"- {severity(sev)} `{where}` — {msg}")
    FINDINGS.write_text("\n".join(lines), encoding="utf-8")
    print(FINDINGS.read_text())


if __name__ == "__main__":
    main()
