import csv
import io
import random

import pandas as pd
import pdfplumber
import streamlit as st

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

# ── Constants ────────────────────────────────────────────────────────────────

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

MOCK_CANDIDATES = [
    {
        "name": "Alice Tan",
        "recommendation": "Shortlist",
        "summary": "Exceptional all-round hire. Technically excellent, proven at senior level, and brings directly relevant fintech domain depth. No critical gaps — Kubernetes is the only notable miss and is learnable.",
        "interview_focus": "Confirm Kubernetes upskilling plan; explore startup adaptability; validate C-suite communication style.",
        "competencies": {
            "Technical Competencies": {
                "score": 95,
                "strengths": [
                    {"text": "Proficient in Python, SQL and Spark — all core stack requirements", "tag": "Evidenced", "req": "Core requirement: Python proficiency"},
                    {"text": "AWS Solutions Architect (Pro) + GCP Data Engineer certified", "tag": "Exceeds", "req": "Cloud infrastructure (AWS/GCP)"},
                    {"text": "Published NLP research directly applicable to AI platform roadmap", "tag": "Exceeds", "req": "Beyond JD scope — notable upside"},
                ],
                "gaps": [],
            },
            "Relevance of Exp": {
                "score": 92,
                "strengths": [
                    {"text": "8 years total, 5 in senior IC/lead roles — exceeds the 5-year bar", "tag": "Evidenced", "req": "Minimum 5 years"},
                    {"text": "Delivered 3 end-to-end platform migrations at 10M+ record scale", "tag": "Evidenced", "req": "Large-scale systems"},
                    {"text": "Production ML models in fintech — directly sector-relevant", "tag": "Evidenced", "req": "Domain alignment"},
                ],
                "gaps": [
                    {"text": "All experience at large corporates — startup-pace adaptability unproven", "severity": "Minor", "req": "Cultural fit"},
                ],
            },
            "Leadership": {
                "score": 88,
                "strengths": [
                    {"text": "Managed cross-functional team of 12 engineers across 2 time zones", "tag": "Evidenced", "req": "Team leadership"},
                    {"text": "Drove end-to-end hiring and onboarding for 4 junior engineers", "tag": "Evidenced", "req": "People development"},
                    {"text": "Presented technical roadmaps to C-suite quarterly", "tag": "Evidenced", "req": "Executive stakeholder management"},
                ],
                "gaps": [],
            },
            "Overall Fit": {
                "score": 86,
                "strengths": [
                    {"text": "3 years fintech — strong alignment with regulated industry context", "tag": "Evidenced", "req": "Domain fit"},
                    {"text": "MSc Computer Science, NUS — top regional programme", "tag": "Evidenced", "req": "Academic qualification"},
                    {"text": "Multiple professional certifications signal continuous development", "tag": "Exceeds", "req": "Credential depth"},
                ],
                "gaps": [
                    {"text": "No HR-tech or recruitment domain exposure", "severity": "Minor", "req": "Sector-specific knowledge"},
                ],
            },
        },
    },
    {
        "name": "Ben Lim",
        "recommendation": "Consider",
        "summary": "Solid mid-level engineer with good breadth and strong soft skills, but undershoots on seniority and lacks ML depth. Viable as a growth hire if the team can absorb a development curve.",
        "interview_focus": "Probe self-directed learning track record; assess ML upskilling appetite; gauge readiness for more complex system ownership.",
        "competencies": {
            "Technical Competencies": {
                "score": 72,
                "strengths": [
                    {"text": "Proficient in React and FastAPI — useful for internal tooling", "tag": "Evidenced", "req": "Full-stack capability"},
                    {"text": "Docker and basic CI/CD pipeline experience", "tag": "Evidenced", "req": "DevOps familiarity"},
                ],
                "gaps": [
                    {"text": "No machine learning or data engineering experience", "severity": "Critical", "req": "Core ML requirement"},
                    {"text": "No cloud certifications; AWS limited to personal side projects", "severity": "Moderate", "req": "Cloud platform requirement"},
                ],
            },
            "Relevance of Exp": {
                "score": 60,
                "strengths": [
                    {"text": "Shipped 4 production web applications end-to-end", "tag": "Evidenced", "req": "Delivery track record"},
                    {"text": "Participated in full SDLC including release management", "tag": "Evidenced", "req": "Engineering process maturity"},
                ],
                "gaps": [
                    {"text": "3 years professional experience vs 5-year minimum required", "severity": "Moderate", "req": "Minimum experience bar"},
                    {"text": "No experience on systems exceeding 100k concurrent users", "severity": "Moderate", "req": "Scale requirement"},
                ],
            },
            "Leadership": {
                "score": 75,
                "strengths": [
                    {"text": "Scrum master for a team of 6 — shows process and facilitation ownership", "tag": "Evidenced", "req": "Team coordination"},
                    {"text": "Mentored 2 interns; positive feedback cited in CV", "tag": "Evidenced", "req": "People development potential"},
                ],
                "gaps": [
                    {"text": "Has not managed direct reports — key gap for this seniority level", "severity": "Moderate", "req": "People management requirement"},
                ],
            },
            "Overall Fit": {
                "score": 68,
                "strengths": [
                    {"text": "B2B SaaS background — aligns with product-led engineering mindset", "tag": "Inferred", "req": "Culture alignment"},
                    {"text": "BEng Information Systems, NTU", "tag": "Evidenced", "req": "Academic baseline"},
                ],
                "gaps": [
                    {"text": "No fintech or regulated-industry experience", "severity": "Moderate", "req": "Sector alignment"},
                    {"text": "No professional certifications or postgraduate qualification", "severity": "Minor", "req": "Credential depth"},
                ],
            },
        },
    },
    {
        "name": "Carol Ng",
        "recommendation": "Consider",
        "summary": "Strong academic foundation but experience falls significantly short of the senior specification. Best suited for a junior or graduate-track variant. Shortlisting for this role as written is not recommended.",
        "interview_focus": "Only interview if a junior-level opening exists. Assess learning velocity, problem-solving approach, and ability to operate independently.",
        "competencies": {
            "Technical Competencies": {
                "score": 58,
                "strengths": [
                    {"text": "Python and SQL competent from coursework and internship", "tag": "Evidenced", "req": "Core language requirement"},
                    {"text": "Familiar with pandas and data visualisation libraries", "tag": "Evidenced", "req": "Data tooling familiarity"},
                ],
                "gaps": [
                    {"text": "No Docker, Kubernetes or CI/CD pipeline exposure", "severity": "Critical", "req": "DevOps requirement"},
                    {"text": "Zero cloud platform experience — local dev environment only", "severity": "Critical", "req": "Cloud platform requirement"},
                    {"text": "No production system or live deployment experience", "severity": "Critical", "req": "Production engineering"},
                ],
            },
            "Relevance of Exp": {
                "score": 40,
                "strengths": [
                    {"text": "6-month internship at a mid-size tech company with positive review", "tag": "Evidenced", "req": "Industry exposure"},
                    {"text": "Academic capstone involved real dataset and stakeholder deliverable", "tag": "Inferred", "req": "Project experience"},
                ],
                "gaps": [
                    {"text": "Under 1 year professional experience vs 5-year hard minimum", "severity": "Critical", "req": "Experience requirement"},
                    {"text": "No ownership of shipped features, products or on-call responsibilities", "severity": "Critical", "req": "Ownership & delivery track record"},
                ],
            },
            "Leadership": {
                "score": 48,
                "strengths": [
                    {"text": "Led 4-person university project groups to completion", "tag": "Evidenced", "req": "Basic team coordination"},
                    {"text": "Organised two faculty-level tech events end-to-end", "tag": "Evidenced", "req": "Initiative and execution"},
                ],
                "gaps": [
                    {"text": "No professional leadership or people management experience", "severity": "Critical", "req": "Leadership requirement"},
                    {"text": "No cross-functional stakeholder or executive engagement", "severity": "Moderate", "req": "Stakeholder management"},
                ],
            },
            "Overall Fit": {
                "score": 72,
                "strengths": [
                    {"text": "BComp (Hons) CS, NUS — Dean's List, strongest academic signal", "tag": "Exceeds", "req": "Academic qualification"},
                    {"text": "Electives in ML, Distributed Systems, Database Systems — directly relevant", "tag": "Evidenced", "req": "Technical foundation"},
                ],
                "gaps": [
                    {"text": "Very limited domain depth beyond academic context", "severity": "Moderate", "req": "Domain knowledge"},
                    {"text": "No regulatory, compliance or data governance awareness", "severity": "Minor", "req": "Regulated industry context"},
                ],
            },
        },
    },
    {
        "name": "David Ong",
        "recommendation": "Pass",
        "summary": "Fundamental mismatch — core software engineering skills are absent, the career gap is unexplained, and the background is not transferable to this role. Not recommended for progression without significant new information.",
        "interview_focus": "Only engage if the career gap is credibly explained and evidence of self-directed software upskilling is presented.",
        "competencies": {
            "Technical Competencies": {
                "score": 25,
                "strengths": [
                    {"text": "Basic MATLAB scripting from hardware engineering background", "tag": "Inferred", "req": "Adjacent technical exposure"},
                ],
                "gaps": [
                    {"text": "No Python, SQL or software engineering experience evidenced", "severity": "Critical", "req": "Core language requirement"},
                    {"text": "No cloud, DevOps or containerisation exposure", "severity": "Critical", "req": "Infrastructure requirement"},
                    {"text": "Technical profile is entirely hardware/embedded systems — non-transferable", "severity": "Critical", "req": "Domain alignment"},
                ],
            },
            "Relevance of Exp": {
                "score": 32,
                "strengths": [
                    {"text": "4 years professional employment — demonstrates workplace reliability", "tag": "Inferred", "req": "Professional track record"},
                ],
                "gaps": [
                    {"text": "2-year career gap with no explanation — significant red flag", "severity": "Critical", "req": "Career continuity"},
                    {"text": "Hardware engineering experience is not transferable to this role", "severity": "Critical", "req": "Relevant experience"},
                ],
            },
            "Leadership": {
                "score": 40,
                "strengths": [
                    {"text": "Project coordinator title — some evidence of team coordination", "tag": "Inferred", "req": "Coordination ability"},
                ],
                "gaps": [
                    {"text": "No formal people management or direct report ownership", "severity": "Moderate", "req": "People management"},
                    {"text": "No cross-functional or stakeholder leadership evidenced", "severity": "Moderate", "req": "Stakeholder management"},
                ],
            },
            "Overall Fit": {
                "score": 30,
                "strengths": [],
                "gaps": [
                    {"text": "Hardware engineering background has minimal overlap with this role", "severity": "Critical", "req": "Role alignment"},
                    {"text": "BEng Electrical Engineering — significant discipline mismatch", "severity": "Critical", "req": "Academic fit"},
                    {"text": "No software certifications or evidence of upskilling attempts", "severity": "Moderate", "req": "Development intent"},
                ],
            },
        },
    },
]

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


def mock_analyze(name: str, competencies: list) -> dict:
    match = next((c for c in MOCK_CANDIDATES if c["name"] == name), None)
    base = {**(match or {})}
    if not match:
        s = random.randint(35, 85)
        base = {
            "name": name,
            "recommendation": "Shortlist" if s >= 80 else "Consider" if s >= 55 else "Pass",
            "summary": "Uploaded candidate — mock scores generated. Use live API for real assessment.",
            "interview_focus": "Review CV in detail before determining interview focus areas.",
            "competencies": {},
        }
    for comp in competencies:
        if comp not in base.get("competencies", {}):
            s = random.randint(40, 78)
            base.setdefault("competencies", {})[comp] = {
                "score": s,
                "strengths": [{"text": "Relevant background noted (mock)", "tag": "Inferred", "req": ""}],
                "gaps": [{"text": "Further detail required (mock)", "severity": "Minor", "req": ""}],
            }
    return base


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


# ── Chart builders (pure HTML/CSS — no Altair) ───────────────────────────────

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
        avg_pct = avg  # avg is already 0-100
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
            # group average marker
            f'    <div style="position:absolute;left:{avg_pct}%;top:-3px;width:3px;height:24px;'
            f'         background:#475569;border-radius:2px;z-index:2;" title="Group avg {avg}"></div>'
            # candidate bar
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
    st.session_state.slider_gen = 0   # incremented to force fresh slider widgets
if "cvs" not in st.session_state:
    st.session_state.cvs = [{"name": c["name"], "chars": None} for c in MOCK_CANDIDATES]
if "jd_text" not in st.session_state:
    st.session_state.jd_text = (
        "Senior Software Engineer with 5+ years Python experience, "
        "cloud infrastructure (AWS/GCP), and team leadership skills."
    )
if "results" not in st.session_state:
    st.session_state.results = []

# Pending mutations
if st.session_state.get("_preset"):
    p = st.session_state.pop("_preset")
    st.session_state.competencies = list(DEFAULT_COMPETENCIES)
    st.session_state.weights = {c: PRESETS[p].get(c, 0) for c in DEFAULT_COMPETENCIES}
    st.session_state.slider_gen += 1   # new key → fresh sliders pick up new values
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
        st.session_state.comp_key += 1   # rotates key → fresh empty input next run
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
    "<p style='text-align:center;color:#64748b;margin-top:0;'>Weight competencies in the sidebar · Run analysis · Adjust to re-rank instantly</p>",
    unsafe_allow_html=True,
)
st.warning("🧪 **Mock mode** — scores and analysis are pre-scripted and do **not** update based on the JD you upload. To analyse against a real JD, add your API key and use `app.py`.")

# ── Input steps (collapsed when results exist) ────────────────────────────────

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
                st.caption(ex[:250] + "…")
            except Exception as e:
                st.error(str(e))

with st.expander(f"👥 Step 2 — Candidate CVs ({len(st.session_state.cvs)} loaded)", expanded=not collapsed):
    up_tab, name_tab = st.tabs(["📂 Upload PDFs", "✏️ Add by name"])
    with up_tab:
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
                    st.session_state.cvs.append({"name": nm, "chars": len(txt)})
                    existing.add(nm)
                    added.append(nm)
                except Exception as e:
                    st.error(f"{f.name}: {e}")
            if added:
                st.success(f"Added: {', '.join(added)}")
    with name_tab:
        nn = st.text_input("Name", key="new_cv_name")
        if st.button("Add", disabled=not nn.strip()):
            if nn.strip() not in {c["name"] for c in st.session_state.cvs}:
                st.session_state.cvs.append({"name": nn.strip(), "chars": None})
            st.rerun()

    if st.session_state.cvs:
        to_rm = []
        for i, cv in enumerate(st.session_state.cvs):
            c1, c2 = st.columns([7, 1])
            c1.markdown(f"📄 **{cv['name']}**" + (f"  ·  {cv['chars']:,} chars" if cv["chars"] else ""))
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
    raw = []
    bar = st.progress(0)
    for i, cv in enumerate(st.session_state.cvs):
        bar.progress((i + 1) / len(st.session_state.cvs), text=f"Analysing {cv['name']}…")
        raw.append(mock_analyze(cv["name"], st.session_state.competencies))
    st.session_state.results = raw
    st.rerun()

if not st.session_state.results:
    st.stop()

# ── Live results (re-computed on every render) ────────────────────────────────

weights = get_weights()
processed = sorted(
    [{**r,
      "weighted_score": compute_weighted_score(r["competencies"], weights),
      "rationale": generate_rationale(r["competencies"], weights)}
     for r in st.session_state.results],
    key=lambda x: x["weighted_score"], reverse=True,
)

# ── Active JD banner ─────────────────────────────────────────────────────────

st.markdown("---")
jd_preview = st.session_state.jd_text.strip()
jd_short = jd_preview[:300] + ("…" if len(jd_preview) > 300 else "")
st.markdown(
    f"""<div style="background:#f8fafc;border:1px solid #e2e8f0;border-left:4px solid #6366f1;
        border-radius:0 8px 8px 0;padding:12px 16px;margin-bottom:16px;">
      <div style="font-size:0.78rem;font-weight:700;color:#6366f1;
                  letter-spacing:0.05em;margin-bottom:4px;">📋 JOB DESCRIPTION IN USE</div>
      <div style="font-size:0.83rem;color:#374151;line-height:1.6;">{jd_short}</div>
      <div style="margin-top:8px;font-size:0.72rem;color:#f59e0b;font-weight:600;">
        ⚠ Mock mode: candidate scores and strengths/gaps below are pre-scripted and do
        not reflect this JD. Configure your API key in app.py for real JD-based analysis.
      </div>
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
    "Mock mode · No real data or API calls</p>",
    unsafe_allow_html=True,
)
