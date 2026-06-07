"""Rutas de Crecimiento — Admin dashboard (local only).

Run:  streamlit run admin/streamlit_admin.py
"""
import json
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "retreats.db"
DRAFTS = ROOT / "content" / "drafts"
APPROVED = ROOT / "content" / "approved"
ARTICLES_OUT = ROOT / "site" / "src" / "content" / "blog"
MONTHLY_BUDGET = float(os.getenv("MONTHLY_BUDGET_USD", "5"))

st.set_page_config(page_title="Rutas Admin", page_icon="🌿", layout="wide")
st.title("Rutas de Crecimiento — Admin")


def conn():
    return sqlite3.connect(DB)


def list_drafts(kind: str):
    folder = DRAFTS / ("articles" if kind == "article" else "social")
    if not folder.exists():
        return []
    return sorted(folder.glob("*.md"), reverse=True)


def parse_frontmatter(path: Path):
    text = path.read_text()
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm, parts[2].strip()


KITS = DRAFTS / "kits"
VIDEOS = ROOT / "content" / "videos"

tab_studio, tab_drafts, tab_retreats, tab_costs, tab_logs, tab_findings = st.tabs(
    ["🎬 Content Studio", "Drafts pendientes", "Retiros DB", "Costos", "Logs agentes", "Findings SEO"]
)


with tab_studio:
    import subprocess
    PY = (ROOT / ".venv" / "bin" / "python")
    PY = str(PY if PY.exists() else "python3")

    st.subheader("Generar kit quincenal")
    st.caption("1 carrusel + 2 estáticas + tiktokslide.mp4 + video + 3 threads + long post. "
               "Costo ~$0.18 (ffmpeg) / ~$0.63 (Hailuo).")
    cgen1, cgen2, cgen3 = st.columns([2, 2, 1])
    with cgen1:
        src = st.radio("Fuente", ["Ciclo (2 blogs recientes)", "Topic nuevo"], horizontal=False)
        topic = st.text_input("Topic", placeholder="retiros de liderazgo en los Andes") if src == "Topic nuevo" else None
    with cgen2:
        engine = st.radio("Motor de video", ["ffmpeg ($0)", "hailuo (~$0.45)"], horizontal=False)
        eng = "hailuo" if engine.startswith("hailuo") else "ffmpeg"
    with cgen3:
        st.write("")
        st.write("")
        go = st.button("⚙️ Generar kit", type="primary")
    if go:
        cmd = [PY, str(ROOT / "scripts" / "make_kit.py"), "--video", eng]
        if src == "Topic nuevo" and topic:
            cmd += ["--topic", topic]
        else:
            cmd += ["--cycle"]
        with st.spinner("Generando kit… (puede tardar 1-2 min)"):
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        st.code((r.stdout or "") + ("\n" + r.stderr[-1500:] if r.returncode else ""))
        if r.returncode == 0:
            st.success("Kit generado. Selecciónalo abajo."); st.rerun()
        else:
            st.error("Falló — revisa el log arriba.")

    st.divider()
    st.subheader("Kits existentes")
    kits = sorted([d for d in KITS.glob("*") if d.is_dir()], reverse=True) if KITS.exists() else []
    if not kits:
        st.info("Sin kits aún. Genera uno arriba.")
    else:
        kit = st.selectbox("Kit", kits, format_func=lambda p: p.name)
        rd = kit / "README.md"
        if rd.exists():
            with st.expander("README / instrucciones de publicación"):
                st.markdown(rd.read_text())

        st.markdown("**Imágenes estáticas** (Instagram / Facebook)")
        statics = sorted((kit / "static").glob("*.png")) if (kit / "static").exists() else []
        if statics:
            cols = st.columns(len(statics))
            for col, p in zip(cols, statics):
                col.image(str(p), use_container_width=True)

        st.markdown("**Carrusel** (swipe IG / FB)")
        cslides = sorted((kit / "carousel").glob("slide_*.png"))
        if cslides:
            cols = st.columns(min(4, len(cslides)))
            for i, p in enumerate(cslides):
                cols[i % len(cols)].image(str(p), use_container_width=True)
        cap = kit / "carousel" / "caption.md"
        if cap.exists():
            st.text_area("Caption del carrusel (copiar)", cap.read_text(), height=160)

        st.markdown("**Videos** (TikTok / Reels / Shorts)")
        vcol1, vcol2 = st.columns(2)
        tiktok = VIDEOS / f"{kit.name}-tiktokslide.mp4"
        video = VIDEOS / f"{kit.name}.mp4"
        if tiktok.exists():
            vcol1.caption("TikTokSlide"); vcol1.video(str(tiktok))
        if video.exists():
            vcol2.caption("Video"); vcol2.video(str(video))

        tcol1, tcol2 = st.columns(2)
        th = kit / "threads.md"
        lp = kit / "longpost.md"
        if th.exists():
            tcol1.text_area("Threads — Twitter/X (copiar)", th.read_text(), height=320)
        if lp.exists():
            tcol2.text_area("Long post — LinkedIn + X (copiar)", lp.read_text(), height=320)


with tab_drafts:
    st.subheader("Drafts pendientes")
    articles = list_drafts("article")
    socials = list_drafts("social")
    col_a, col_b = st.columns([1, 2])
    with col_a:
        st.metric("Artículos pendientes", len(articles))
        st.metric("Posts sociales pendientes", len(socials))
        st.divider()
        kind = st.radio("Tipo:", ["Artículo", "Social"], horizontal=True)
        files = articles if kind == "Artículo" else socials
        if files:
            labels = [f.name for f in files]
            chosen = st.selectbox("Selecciona:", labels)
            chosen_path = next(f for f in files if f.name == chosen)
        else:
            chosen_path = None
            st.info("No hay drafts pendientes.")
    with col_b:
        if chosen_path:
            fm, body = parse_frontmatter(chosen_path)
            st.caption(", ".join(f"**{k}**: {v}" for k, v in fm.items()))
            edited = st.text_area("Cuerpo (editable)", value=body, height=600)
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("Guardar cambios"):
                    fm_lines = ["---"] + [f"{k}: \"{v}\"" for k, v in fm.items()] + ["---", ""]
                    chosen_path.write_text("\n".join(fm_lines) + "\n" + edited)
                    st.success("Guardado.")
            with c2:
                if st.button("Aprobar y mover"):
                    target_folder = APPROVED / chosen_path.parent.name
                    target_folder.mkdir(parents=True, exist_ok=True)
                    target = target_folder / chosen_path.name
                    shutil.move(str(chosen_path), str(target))
                    # if article: also copy to site/src/content/blog/ for next deploy
                    if chosen_path.parent.name == "articles":
                        ARTICLES_OUT.mkdir(parents=True, exist_ok=True)
                        site_target = ARTICLES_OUT / fm.get("slug", chosen_path.stem).replace(" ", "-").lower()
                        site_target = site_target.with_suffix(".md")
                        shutil.copy(str(target), str(site_target))
                        st.success(f"Aprobado y copiado a {site_target.relative_to(ROOT)}. Haz push para deploy.")
                    else:
                        st.success(f"Aprobado → {target.relative_to(ROOT)}. Copia el texto a la plataforma manualmente.")
                    st.rerun()
            with c3:
                if st.button("Descartar"):
                    chosen_path.unlink()
                    st.warning("Descartado.")
                    st.rerun()


with tab_retreats:
    st.subheader("Retiros en directorio")
    c = conn()
    rows = c.execute(
        "SELECT slug, title, location_country, duration_days, price_usd_from, reviewed_by_us, status FROM retreats ORDER BY scraped_at DESC"
    ).fetchall()
    c.close()
    if not rows:
        st.info("Sin retiros aún. Corre scraper.py.")
    else:
        st.write(f"Total: {len(rows)}")
        st.dataframe(
            [
                {"slug": r[0], "title": r[1], "país": r[2], "días": r[3],
                 "USD": r[4], "revisado": bool(r[5]), "status": r[6]}
                for r in rows
            ],
            use_container_width=True
        )


with tab_costs:
    st.subheader("Costos por agente — mes actual")
    c = conn()
    spent = c.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM agent_runs WHERE strftime('%Y-%m', started_at) = strftime('%Y-%m','now')"
    ).fetchone()[0]
    st.metric("Mes a la fecha", f"${spent:.3f}", f"Budget: ${MONTHLY_BUDGET:.2f}")
    pct = min(100, int(spent / MONTHLY_BUDGET * 100)) if MONTHLY_BUDGET else 0
    st.progress(pct, text=f"{pct}% del budget mensual")
    breakdown = c.execute(
        "SELECT agent_name, ROUND(SUM(cost_usd), 4), SUM(items_processed) FROM agent_runs "
        "WHERE strftime('%Y-%m', started_at) = strftime('%Y-%m','now') GROUP BY agent_name"
    ).fetchall()
    c.close()
    if breakdown:
        st.table({"Agente": [b[0] for b in breakdown],
                  "Costo USD": [b[1] for b in breakdown],
                  "Items": [b[2] for b in breakdown]})


with tab_logs:
    st.subheader("Últimas 30 runs")
    c = conn()
    logs = c.execute(
        "SELECT started_at, agent_name, status, items_processed, ROUND(cost_usd, 4), errors "
        "FROM agent_runs ORDER BY started_at DESC LIMIT 30"
    ).fetchall()
    c.close()
    if logs:
        st.dataframe(
            [{"when": l[0], "agent": l[1], "status": l[2], "items": l[3], "USD": l[4], "errors": (l[5] or "")[:100]} for l in logs],
            use_container_width=True
        )
    else:
        st.info("Sin runs aún.")


with tab_findings:
    st.subheader("Hallazgos SEO/AEO")
    f = ROOT / ".claude" / "findings.md"
    if f.exists():
        st.markdown(f.read_text())
    else:
        st.info("Sin findings. Corre: `python scripts/seo_audit.py`")
