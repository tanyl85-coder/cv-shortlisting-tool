import anthropic
import csv
import io
import json
import os

import pandas as pd
import pdfplumber
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="CV Shortlisting Tool",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 700; }
[data-testid="stMetricLabel"] { font-size: 0.8rem; color: #64748b; }
.stTabs [data-baseweb="tab"] { font-size: 0.9rem; font-weight: 600; padding: 10px 20px; }
div[data-testid="column"] > div { height: 100%; }
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_COMPETENCIES = ["Technical Competencies", "Relevance of Exp", "Leadership", "Overall Fit"]

PRESETS = {
    "🎓 Entry Level":   {"Technical Competencies": 30, "Relevance of Exp": 15, "Leadership": 5,  "Overall Fit": 50},
    "💼 Mid-career IC": {"Technical Competencies": 40, "Relevance of Exp": 35, "Leadership": 10, "Overall Fit": 15},
    "👔 Supervisory":   {"Technical Competencies": 20, "Relevance of Exp": 25, "Leadership": 40, "Overall Fit": 15},
}

REC_STYLE = {
    "Shortlist": ("#d1fae5", "#065f46", "#10b981", "🟢"),
    "Consider":  ("#fef9c3", "#92400e", "#f59e0b", "🟡"),
    "Pass":      ("#fee2e2", "#991b1b", "#ef4444", "🔴"),
}

SEV_STYLE = {
    "Critical": ("#fee2e2", "#991b1b", "🔴 Critical"),
    "Moderate": ("#ffedd5", "#9a3412", "🟠 Moderate"),
    "Minor":    ("#fef9c3", "#854d0e", "🟡 Minor"),
}

TAG_STYLE = {
    "Evidenced": ("#d1fae5", "#065f46", "✅ Evidenced"),
    "Exceeds":   ("#dbeafe", "#1e40af", "⭐ Exceeds"),
    "Inferred":  ("#f1f5f9", "#475569", "💡 Inferred"),
}

# ── Claude analysis ───────────────────────────────────────────────────────────

def real_analyze(client: anthropic.Anthropic, jd: str, cv_text: str,
                 name: str, competencies: list) -> dict:
    comp_list = "\n".join(f"- {c}" for c in competencies)
    comp_example = competencies[0] if competencies else "Technical Competencies"

    prompt = f"""You are a senior recruiter with 15+ years of hiring experience. Analyse the candidate's CV against the job description and return a structured JSON assessment.

JOB DESCRIPTION:
{jd}

CANDIDATE CV:
{cv_text}

Evaluate the candidate across these competency dimensions:
{comp_list}

Rules:
- Score each competency 0–100 (0 = no match, 100 = exceptional match)
- Strengths: 2–4 specific points per competency, each citing actual CV evidence.
  tag options: "Evidenced" (directly stated in CV), "Exceeds" (goes beyond the JD requirement), "Inferred" (implied or transferable)
- Gaps: 0–3 specific shortfalls per competency, grounded in the JD requirements only.
  severity options: "Critical" (must-have, missing), "Moderate" (important gap), "Minor" (nice-to-have)
- Each strength/gap must include a "req" field that names the specific JD requirement it refers to.
- Do NOT invent gaps for skills not mentioned in the JD.
- recommendation: "Shortlist" if overall weighted fit is strong (≥75), "Consider" if partial fit (50–74), "Pass" if poor fit (<50)
- summary: 2–3 sentence plain-English verdict.
- interview_focus: 1–2 sentence guidance on what to probe in the interview.

Respond with ONLY valid JSON — no markdown fences, no preamble:
{{
  "recommendation": "Shortlist",
  "summary": "...",
  "interview_focus": "...",
  "competencies": {{
    "{comp_example}": {{
      "score": 85,
      "strengths": [
        {{"text": "...", "tag": "Evidenced", "req": "specific JD requirement"}}
      ],
      "gaps": [
        {{"text": "...", "severity": "Moderate", "req": "specific JD requirement"}}
      ]
    }}
  }}
}}"""

    msg = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    parsed = json.loads(raw)

    result = {
        "name": name,
        "recommendation": parsed.get("recommendation", "Consider"),
        "summary": parsed.get("summary", ""),
        "interview_focus": parsed.get("interview_focus", ""),
        "competencies": {},
    }
    for comp in competencies:
        cd = parsed.get("competencies", {}).get(comp, {})
        result["competencies"][comp] = {
            "score": max(0, min(100, int(cd.get("score", 50)))),
            "strengths": [s for s in cd.get("strengths", []) if isinstance(s, dict)],
            "gaps":      [g for g in cd.get("gaps", [])      if isinstance(g, dict)],
        }
    return result


# ── Helper functions ──────────────────────────────────────────────────────────

def extract_pdf_text(f) -> str:
    with pdfplumber.open(f) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages).strip()


def get_weights() -> dict:
    return {c: st.session_state.weights.get(c, 0) for c in st.session_state.competencies}


def compute_weighted_score(comp_data: dict, weights: dict) -> int:
    total_w = sum(weights.values())
    if total_w == 0:
        return 0
    return round(sum(comp_data.get(c, {}).get("score", 0) * w for c, w in weights.items()) / total_w)


def generate_rationale(comp_data: dict, weights: dict) -> str:
    contribs = sorted(
        [(c, comp_data.get(c, {}).get("score", 0), w, comp_data.get(c, {}).get("score", 0) * w / 100)
         for c, w in weights.items() if w > 0],
        key=lambda x: x[3], reverse=True,
    )
    if not contribs:
        return "No weights configured."
    top, bottom = contribs[0], contribs[-1]
    lvl = lambda s: "strong" if s >= 80 else "moderate" if s >= 60 else "weak"
    text = f"Led by {lvl(top[1])} {top[0]} ({top[1]}pts × {top[2]}% = {top[3]:.0f}pts)."
    if len(contribs) > 1 and bottom[1] < 65 and bottom[2] > 0:
        text += f" Held back by {bottom[0]} ({bottom[1]}pts × {bottom[2]}%)."
    return text


def color_score(val):
    if not isinstance(val, (int, float)):
        return ""
    if val >= 80: return "background-color:#d1fae5;color:#065f46;font-weight:700"
    if val >= 60: return "background-color:#fef9c3;color:#92400e;font-weight:700"
    if val >= 40: return "background-color:#ffedd5;color:#9a3412;font-weight:700"
    return "background-color:#fee2e2;color:#991b1b;font-weight:700"


def badge(label, bg, fg):
    return (f'<span style="background:{bg};color:{fg};padding:3px 10px;'
            f'border-radius:999px;font-size:0.75rem;font-weight:700;'
            f'white-space:nowrap;">{label}</span>')


def rec_badge(rec):
    bg, fg, _, icon = REC_STYLE.get(rec, ("#f1f5f9", "#1e293b", "", ""))
    return badge(f"{icon} {rec}", bg, fg)


def sev_badge(sev):
    bg, fg, label = SEV_STYLE.get(sev, ("#f1f5f9", "#1e293b", sev))
    return badge(label, bg, fg)


def tag_badge(tag):
    bg, fg, label = TAG_STYLE.get(tag, ("#f1f5f9", "#475569", tag))
    return badge(label, bg, fg)


def results_to_csv(processed, weights):
    buf = io.StringIO()
    w = csv.writer(buf)
    comps = list(weights.keys())
    w.writerow(["Rank", "Candidate", "Weighted Score", "Recommendation"] + comps + ["Rationale"])
    for i, r in enumerate(processed, 1):
        w.writerow(
            [i, r["name"], r["weighted_score"], r["recommendation"]]
            + [r["competencies"].get(c, {}).get("score", "") for c in comps]
            + [r["rationale"]]
        )
    return buf.getvalue()


# ── Chart builders (pure HTML/CSS) ────────────────────────────────────────────

def _score_bar_color(score: int) -> str:
    if score >= 80: return "#10b981"
    if score >= 60: return "#f59e0b"
    if score >= 40: return "#f97316"
    return "#ef4444"


def render_ranking_bars(processed: list) -> str:
    rows = []
    for i, r in enumerate(processed):
        _, _, color, icon = REC_STYLE.get(r["recommendation"], ("", "", "#94a3b8", ""))
        score = r["weighted_score"]
        rows.append(
            f'<div style="margin-bottom:10px;">'
            f'  <div style="display:flex;justify-content:space-between;'
            f'       align-items:center;margin-bottom:3px;">'
            f'    <span style="font-size:0.88rem;font-weight:700;color:#0f172a;">'
            f'      #{i+1}&nbsp; {r["name"]}'
            f'    </span>'
            f'    <span style="font-size:0.75rem;font-weight:600;color:{color};">'
            f'      {icon} {r["recommendation"]}'
            f'    </span>'
            f'  </div>'
            f'  <div style="display:flex;align-items:center;gap:8px;">'
            f'    <div style="flex:1;background:#e2e8f0;border-radius:999px;height:22px;'
            f'         position:relative;overflow:hidden;">'
            f'      <div style="width:{score}%;background:{color};height:22px;'
            f'           border-radius:999px;transition:width 0.4s;">'
            f'      </div>'
            f'    </div>'
            f'    <span style="font-size:0.85rem;font-weight:800;color:{color};'
            f'         width:38px;text-align:right;">{score}%</span>'
            f'  </div>'
            f'</div>'
        )
    return (
        '<div style="background:#f8fafc;border-radius:10px;padding:16px;">'
        + "".join(rows)
        + "</div>"
    )


def render_heatmap_df(processed: list, competencies: list) -> pd.DataFrame:
    index = [f"#{i+1} {r['name']}" for i, r in enumerate(processed)]
    data = {
        comp: [r["competencies"].get(comp, {}).get("score", 0) for r in processed]
        for comp in competencies
    }
    return pd.DataFrame(data, index=index)


def render_individual_bars(candidate: dict, processed: list,
                           competencies: list, weights: dict) -> str:
    avgs = {
        c: round(sum(r["competencies"].get(c, {}).get("score", 0) for r in processed) / len(processed))
        for c in competencies
    }
    rows = []
    for comp in competencies:
        score = candidate["competencies"].get(comp, {}).get("score", 0)
        avg = avgs.get(comp, 0)
        w = weights.get(comp, 0)
        bar_color = _score_bar_color(score)
        diff = score - avg
        diff_str = (f'<span style="color:#10b981;">▲ {diff}</span>' if diff > 0
                    else f'<span style="color:#ef4444;">▼ {abs(diff)}</span>' if diff < 0
                    else '<span style="color:#94a3b8;">= avg</span>')
        rows.append(
            f'<div style="margin-bottom:14px;">'
            f'  <div style="display:flex;justify-content:space-between;margin-bottom:4px;">'
            f'    <span style="font-size:0.85rem;font-weight:700;color:#0f172a;">'
            f'      {comp} <span style="font-weight:400;color:#94a3b8;font-size:0.75rem;">· {w}% weight</span>'
            f'    </span>'
            f'    <span style="font-size:0.82rem;font-weight:700;color:{bar_color};">'
            f'      {score} &nbsp;{diff_str} vs avg ({avg})'
            f'    </span>'
            f'  </div>'
            f'  <div style="position:relative;background:#e2e8f0;border-radius:999px;height:18px;">'
            f'    <div style="position:absolute;left:{avg}%;top:-3px;width:3px;height:24px;'
            f'         background:#475569;border-radius:2px;z-index:2;" title="Group avg {avg}"></div>'
            f'    <div style="width:{score}%;background:{bar_color};height:18px;'
            f'         border-radius:999px;position:relative;z-index:1;"></div>'
            f'  </div>'
            f'</div>'
        )
    legend = (
        '<div style="font-size:0.72rem;color:#64748b;margin-top:8px;">'
        '  <span style="display:inline-block;width:10px;height:10px;background:#475569;'
        '       border-radius:2px;margin-right:4px;"></span>Grey bar = group average'
        '</div>'
    )
    return (
        '<div style="background:#f8fafc;border-radius:10px;padding:16px;">'
        + "".join(rows) + legend
        + "</div>"
    )


# ── Session state ─────────────────────────────────────────────────────────────

if "competencies" not in st.session_state:
    st.session_state.competencies = list(DEFAULT_COMPETENCIES)
if "weights" not in st.session_state:
    st.session_state.weights = {c: 25 for c in DEFAULT_COMPETENCIES}
if "slider_gen" not in st.session_state:
    st.session_state.slider_gen = 0
if "cvs" not in st.session_state:
    st.session_state.cvs = []   # list of {"name": str, "text": str, "chars": int}
if "jd_text" not in st.session_state:
    st.session_state.jd_text = ""
if "results" not in st.session_state:
    st.session_state.results = []

# Pending mutations (must run before any widgets render)
if st.session_state.get("_preset"):
    p = st.session_state.pop("_preset")
    st.session_state.competencies = list(DEFAULT_COMPETENCIES)
    st.session_state.weights = {c: PRESETS[p].get(c, 0) for c in DEFAULT_COMPETENCIES}
    st.session_state.slider_gen += 1
if st.session_state.get("_add_comp"):
    c = st.session_state.pop("_add_comp")
    if c and c not in st.session_state.competencies:
        st.session_state.competencies.append(c)
        st.session_state.weights[c] = 0
        st.session_state.slider_gen += 1
if st.session_state.get("_del_comp"):
    c = st.session_state.pop("_del_comp")
    if c in st.session_state.competencies:
        st.session_state.competencies.remove(c)
    st.session_state.weights.pop(c, None)
    st.session_state.slider_gen += 1

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("⚖️ Scoring Weights")
    st.caption("Adjust at any time — rankings update instantly.")

    st.markdown("**Role Presets**")
    for i, name in enumerate(PRESETS):
        if st.button(name, use_container_width=True, key=f"preset_{i}"):
            st.session_state["_preset"] = name
            st.rerun()

    st.divider()
    st.markdown("**Competencies**")
    if "comp_key" not in st.session_state:
        st.session_state.comp_key = 0
    new_c = st.text_input("Add competency",
                           key=f"new_comp_{st.session_state.comp_key}",
                           placeholder="e.g. Communication")
    if st.button("➕ Add", disabled=not (new_c or "").strip()):
        st.session_state["_add_comp"] = new_c.strip()
        st.session_state.comp_key += 1
        st.rerun()

    st.divider()
    total_w = 0
    gen = st.session_state.slider_gen
    for comp in list(st.session_state.competencies):
        h1, h2 = st.columns([5, 1])
        h1.markdown(f"**{comp}**")
        if h2.button("✕", key=f"del_{comp}_{gen}"):
            st.session_state["_del_comp"] = comp
            st.rerun()
        val = st.slider(
            " ", 0, 100, step=5,
            value=st.session_state.weights.get(comp, 0),
            key=f"w_{comp}_{gen}",
            label_visibility="collapsed",
        )
        st.session_state.weights[comp] = val
        total_w += val

    st.divider()
    rem = 100 - total_w
    if total_w == 100:
        st.success("✅ Total: 100% — ready")
    elif rem > 0:
        st.warning(f"⚠️ Total: {total_w}% — allocate {rem}% more")
    else:
        st.error(f"❌ Total: {total_w}% — reduce by {abs(rem)}%")

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown(
    "<h1 style='text-align:center;margin-bottom:4px;'>✨ CV Shortlisting Tool</h1>"
    "<p style='text-align:center;color:#64748b;margin-top:0;'>"
    "Weight competencies in the sidebar · Upload a JD + CVs · Run AI analysis · Adjust weights to re-rank instantly"
    "</p>",
    unsafe_allow_html=True,
)

# ── API key ───────────────────────────────────────────────────────────────────

try:
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
except Exception:
    api_key = ""
if not api_key:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
if not api_key:
    api_key = st.text_input(
        "🔑 Anthropic API Key",
        type="password",
        help="Set ANTHROPIC_API_KEY in Streamlit Cloud secrets or a local .env file to avoid entering it each run.",
    )

if not api_key:
    st.info("Enter your Anthropic API key above to enable AI analysis.")
    st.stop()

# ── Input steps ───────────────────────────────────────────────────────────────

collapsed = bool(st.session_state.results)

with st.expander("📋 Step 1 — Job Description", expanded=not collapsed):
    tab_paste, tab_pdf = st.tabs(["✏️ Paste", "📄 PDF"])
    with tab_paste:
        typed = st.text_area("JD text", height=140, value=st.session_state.jd_text,
                             label_visibility="collapsed", key="jd_textarea")
        st.session_state.jd_text = typed
    with tab_pdf:
        jd_file = st.file_uploader("Upload JD PDF", type=["pdf"],
                                    label_visibility="collapsed", key="jd_up")
        if jd_file:
            try:
                ex = extract_pdf_text(jd_file)
                st.session_state.jd_text = ex
                st.success(f"✅ {len(ex):,} chars extracted from {jd_file.name}")
                st.caption(ex[:300] + "…")
            except Exception as e:
                st.error(str(e))

with st.expander(f"👥 Step 2 — Candidate CVs ({len(st.session_state.cvs)} loaded)", expanded=not collapsed):
    uploads = st.file_uploader("CVs", type=["pdf"], accept_multiple_files=True,
                                label_visibility="collapsed", key="cv_up")
    if uploads:
        existing = {c["name"] for c in st.session_state.cvs}
        added = []
        for f in uploads:
            nm = f.name.removesuffix(".pdf")
            if nm in existing:
                continue
            try:
                txt = extract_pdf_text(f)
                st.session_state.cvs.append({"name": nm, "text": txt, "chars": len(txt)})
                existing.add(nm)
                added.append(nm)
            except Exception as e:
                st.error(f"{f.name}: {e}")
        if added:
            st.success(f"Added: {', '.join(added)}")

    if st.session_state.cvs:
        to_rm = []
        for i, cv in enumerate(st.session_state.cvs):
            c1, c2 = st.columns([7, 1])
            c1.markdown(f"📄 **{cv['name']}**  ·  {cv['chars']:,} chars")
            if c2.button("✕", key=f"rm_cv_{i}"):
                to_rm.append(i)
        for idx in reversed(to_rm):
            st.session_state.cvs.pop(idx)
        if to_rm:
            st.rerun()

# ── Run button ────────────────────────────────────────────────────────────────

st.divider()
weights = get_weights()
total_w = sum(weights.values())
run_ok = total_w == 100 and st.session_state.jd_text.strip() and st.session_state.cvs

if not run_ok and not st.session_state.results:
    if total_w != 100:
        st.warning(f"Weights total **{total_w}%** — must equal 100% to run. Adjust in the sidebar.")

if st.button("✨ Run Shortlisting", type="primary", use_container_width=True, disabled=not run_ok):
    client = anthropic.Anthropic(api_key=api_key)
    raw_results = []
    total = len(st.session_state.cvs)
    bar = st.progress(0, text="Starting analysis…")
    for i, cv in enumerate(st.session_state.cvs):
        bar.progress(i / total, text=f"Analysing {cv['name']} ({i+1}/{total})…")
        try:
            result = real_analyze(
                client,
                st.session_state.jd_text,
                cv["text"],
                cv["name"],
                st.session_state.competencies,
            )
            raw_results.append(result)
        except Exception as e:
            raw_results.append({
                "name": cv["name"],
                "recommendation": "Pass",
                "summary": f"Analysis failed: {e}",
                "interview_focus": "",
                "competencies": {
                    c: {"score": 0, "strengths": [], "gaps": []} for c in st.session_state.competencies
                },
            })
    bar.progress(1.0, text="Done!")
    st.session_state.results = raw_results
    st.rerun()

if not st.session_state.results:
    st.stop()

# ── Live results (re-computed on every render when weights change) ─────────────

weights = get_weights()
processed = sorted(
    [{**r,
      "weighted_score": compute_weighted_score(r["competencies"], weights),
      "rationale": generate_rationale(r["competencies"], weights)}
     for r in st.session_state.results],
    key=lambda x: x["weighted_score"], reverse=True,
)

# ── Active JD banner ──────────────────────────────────────────────────────────

st.markdown("---")
jd_preview = st.session_state.jd_text.strip()
jd_short = jd_preview[:300] + ("…" if len(jd_preview) > 300 else "")
st.markdown(
    f"""<div style="background:#f8fafc;border:1px solid #e2e8f0;border-left:4px solid #6366f1;
        border-radius:0 8px 8px 0;padding:12px 16px;margin-bottom:16px;">
      <div style="font-size:0.78rem;font-weight:700;color:#6366f1;
                  letter-spacing:0.05em;margin-bottom:4px;">📋 JOB DESCRIPTION USED FOR THIS ANALYSIS</div>
      <div style="font-size:0.83rem;color:#374151;line-height:1.6;">{jd_short}</div>
    </div>""",
    unsafe_allow_html=True,
)

# ── Metric cards ──────────────────────────────────────────────────────────────

m1, m2, m3, m4 = st.columns(4)
counts = {k: sum(1 for r in processed if r["recommendation"] == k) for k in REC_STYLE}
m1.metric("Total Candidates", len(processed))
m2.metric("🟢 Shortlist", counts["Shortlist"])
m3.metric("🟡 Consider", counts["Consider"])
m4.metric("🔴 Pass", counts["Pass"])

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_ov, tab_det = st.tabs(["📊 Overview", "👤 Candidate Detail"])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ════════════════════════════════════════════════════════════════════════════
with tab_ov:

    col_rank, col_heat = st.columns([1, 1], gap="large")

    with col_rank:
        st.markdown("#### Candidate Rankings")
        st.caption("Sorted by weighted score. Colour = recommendation.")
        st.markdown(render_ranking_bars(processed), unsafe_allow_html=True)

    with col_heat:
        st.markdown("#### Competency Heatmap")
        st.caption("Green = strong · Red = weak · Numbers = raw scores.")
        heatmap_df = render_heatmap_df(processed, st.session_state.competencies)
        st.dataframe(
            heatmap_df.style
                .background_gradient(cmap="RdYlGn", vmin=0, vmax=100)
                .format("{:.0f}"),
            use_container_width=True,
            height=60 + len(processed) * 38,
        )

    st.markdown("#### Summary Table")
    st.caption("Rankings re-sort automatically when you adjust weights in the sidebar.")

    rows = []
    for i, r in enumerate(processed, 1):
        _, _, _, icon = REC_STYLE.get(r["recommendation"], ("", "", "", ""))
        row = {
            "Rank": i,
            "Candidate": r["name"],
            "Weighted Score": r["weighted_score"],
            "Recommendation": f"{icon} {r['recommendation']}",
        }
        for comp in st.session_state.competencies:
            row[comp] = r["competencies"].get(comp, {}).get("score", "—")
        row["Score Rationale"] = r["rationale"]
        rows.append(row)

    df = pd.DataFrame(rows).set_index("Rank")
    sc = ["Weighted Score"] + [c for c in st.session_state.competencies if c in df.columns]
    styled = (
        df.style
        .map(color_score, subset=sc)
        .set_properties(subset=["Candidate"], **{"font-weight": "700"})
        .set_properties(subset=["Score Rationale"],
                        **{"font-size": "0.78rem", "color": "#475569"})
    )
    st.dataframe(
        styled,
        use_container_width=True,
        height=min(100 + len(processed) * 40, 500),
        column_config={
            "Score Rationale": st.column_config.TextColumn(width="large"),
            "Weighted Score": st.column_config.NumberColumn(format="%d%%"),
        },
    )

    dl_col, _ = st.columns([1, 5])
    dl_col.download_button("⬇ Export CSV", data=results_to_csv(processed, weights),
                           file_name="cv-shortlist.csv", mime="text/csv")

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — CANDIDATE DETAIL
# ════════════════════════════════════════════════════════════════════════════
with tab_det:

    # Legend shown once at the top
    st.markdown("**Legend**", help="Tags explain how each finding was determined")
    leg1, leg2, leg3, leg4, leg5, leg6, leg7, _ = st.columns([1, 1, 1, 0.2, 1, 1, 1, 1])
    leg1.markdown(badge("🔴 Critical", "#fee2e2", "#991b1b"), unsafe_allow_html=True)
    leg2.markdown(badge("🟠 Moderate", "#ffedd5", "#9a3412"), unsafe_allow_html=True)
    leg3.markdown(badge("🟡 Minor",    "#fef9c3", "#854d0e"), unsafe_allow_html=True)
    leg5.markdown(badge("✅ Evidenced", "#d1fae5", "#065f46"), unsafe_allow_html=True)
    leg6.markdown(badge("⭐ Exceeds",   "#dbeafe", "#1e40af"), unsafe_allow_html=True)
    leg7.markdown(badge("💡 Inferred",  "#f1f5f9", "#475569"), unsafe_allow_html=True)
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    for idx, r in enumerate(processed):
        bg, fg, bar_color, icon = REC_STYLE.get(r["recommendation"], ("#f8fafc", "#1e293b", "#94a3b8", ""))
        expander_label = (
            f"#{idx+1}  {r['name']}  ·  {r['weighted_score']}%  {icon} {r['recommendation']}"
        )

        with st.expander(expander_label, expanded=(idx == 0)):

            # ── Profile header card ────────────────────────────────────────
            st.markdown(
                f"""<div style="background:{bg};border-radius:10px;padding:16px 20px;
                    border-left:5px solid {bar_color};margin-bottom:1rem;">
                  <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                    <div style="flex:1;">
                      <div style="font-size:1.1rem;font-weight:800;color:{fg};">
                        {r['name']}
                      </div>
                      <div style="margin-top:5px;font-size:0.85rem;color:{fg};line-height:1.6;">
                        {r['summary']}
                      </div>
                    </div>
                    <div style="text-align:center;flex-shrink:0;margin-left:20px;">
                      <div style="font-size:2.2rem;font-weight:900;color:{fg};">{r['weighted_score']}%</div>
                      <div style="font-size:0.78rem;font-weight:700;color:{fg};">{icon} {r['recommendation']}</div>
                    </div>
                  </div>
                  <div style="margin-top:10px;padding:7px 12px;background:rgba(255,255,255,0.5);
                       border-radius:6px;font-size:0.8rem;color:{fg};">
                    <strong>Interview focus:</strong> {r.get('interview_focus', '—')}
                  </div>
                </div>""",
                unsafe_allow_html=True,
            )

            # ── Scores chart + breakdown table ─────────────────────────────
            col_chart, col_contrib = st.columns([3, 2], gap="large")

            with col_chart:
                st.markdown("**Competency Scores vs Group Average**")
                st.caption("Grey marker = group average · Coloured bar = this candidate")
                st.markdown(
                    render_individual_bars(r, processed, st.session_state.competencies, weights),
                    unsafe_allow_html=True,
                )

            with col_contrib:
                st.markdown("**Score Breakdown**")
                contrib_data = []
                for comp in st.session_state.competencies:
                    raw = r["competencies"].get(comp, {}).get("score", 0)
                    w = weights.get(comp, 0)
                    contrib_data.append({
                        "Competency": comp,
                        "Score": raw,
                        "Weight": f"{w}%",
                        "Points": round(raw * w / 100) if w else 0,
                    })
                cdf = pd.DataFrame(contrib_data).set_index("Competency")
                st.dataframe(
                    cdf.style.map(color_score, subset=["Score", "Points"]),
                    use_container_width=True,
                    height=60 + len(contrib_data) * 38,
                )
                st.caption(f"**Rationale:** {r['rationale']}")

            # ── Per-competency S&G ─────────────────────────────────────────
            st.markdown("---")
            st.markdown("**Detailed Strengths & Gaps by Competency**")

            for comp in st.session_state.competencies:
                data = r["competencies"].get(comp, {})
                score = data.get("score", 0)
                w = weights.get(comp, 0)
                pts = round(score * w / 100) if w else 0
                _, _, bar_c, _ = REC_STYLE.get(
                    "Shortlist" if score >= 80 else "Consider" if score >= 55 else "Pass",
                    ("", "", "#94a3b8", ""),
                )

                # Competency domain header
                st.markdown(
                    f"""<div style="background:#f1f5f9;border-left:5px solid {bar_c};
                        border-radius:0 8px 8px 0;padding:10px 16px;margin:16px 0 10px;">
                      <div style="display:flex;justify-content:space-between;align-items:center;">
                        <span style="font-size:1rem;font-weight:800;color:#0f172a;">{comp}</span>
                        <div style="display:flex;gap:16px;">
                          <span style="font-size:0.78rem;color:#64748b;">
                            Score&nbsp;<strong style="color:{bar_c};">{score}/100</strong>
                          </span>
                          <span style="font-size:0.78rem;color:#64748b;">
                            Weight&nbsp;<strong>{w}%</strong>
                          </span>
                          <span style="font-size:0.78rem;color:#64748b;">
                            Contributes&nbsp;<strong style="color:{bar_c};">{pts}&nbsp;pts</strong>
                          </span>
                        </div>
                      </div>
                      <div style="margin-top:8px;background:#e2e8f0;border-radius:999px;height:6px;">
                        <div style="width:{score}%;background:{bar_c};border-radius:999px;height:6px;"></div>
                      </div>
                    </div>""",
                    unsafe_allow_html=True,
                )

                left, right = st.columns(2, gap="medium")

                with left:
                    strengths = data.get("strengths", [])
                    st.markdown(
                        f"<p style='font-size:0.82rem;font-weight:700;color:#065f46;margin-bottom:6px;'>"
                        f"✅ Strengths"
                        f"{'&nbsp;<span style=\"font-weight:400;color:#94a3b8;\">— none noted</span>' if not strengths else ''}"
                        f"</p>",
                        unsafe_allow_html=True,
                    )
                    for s in strengths:
                        req = (f'<div style="font-size:0.7rem;color:#94a3b8;margin-top:2px;">↳ {s["req"]}</div>') if s.get("req") else ""
                        st.markdown(
                            f"""<div style="padding:8px 10px 8px 12px;border-left:3px solid #10b981;
                                background:#f0fdf4;border-radius:0 6px 6px 0;margin-bottom:7px;">
                              {tag_badge(s.get('tag', ''))}
                              <span style="font-size:0.84rem;color:#0f172a;margin-left:5px;">{s['text']}</span>
                              {req}
                            </div>""",
                            unsafe_allow_html=True,
                        )

                with right:
                    gaps = data.get("gaps", [])
                    st.markdown(
                        f"<p style='font-size:0.82rem;font-weight:700;color:#991b1b;margin-bottom:6px;'>"
                        f"⚠ Gaps"
                        f"{'&nbsp;<span style=\"font-weight:400;color:#94a3b8;\">— none identified</span>' if not gaps else ''}"
                        f"</p>",
                        unsafe_allow_html=True,
                    )
                    for g in gaps:
                        req = (f'<div style="font-size:0.7rem;color:#94a3b8;margin-top:2px;">↳ {g["req"]}</div>') if g.get("req") else ""
                        st.markdown(
                            f"""<div style="padding:8px 10px 8px 12px;border-left:3px solid #ef4444;
                                background:#fff7f7;border-radius:0 6px 6px 0;margin-bottom:7px;">
                              {sev_badge(g.get('severity', ''))}
                              <span style="font-size:0.84rem;color:#0f172a;margin-left:5px;">{g['text']}</span>
                              {req}
                            </div>""",
                            unsafe_allow_html=True,
                        )

        st.markdown("<hr style='border:none;border-top:1px solid #e2e8f0;margin:10px 0;'>",
                    unsafe_allow_html=True)

st.markdown(
    "<p style='text-align:center;color:#94a3b8;font-size:.75rem;margin-top:2rem;'>"
    "Powered by Claude · PDFs processed locally · No candidate data stored</p>",
    unsafe_allow_html=True,
)
