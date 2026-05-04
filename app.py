import json
import csv
import io
import os

import anthropic
import pdfplumber
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="CV Shortlisting Tool", page_icon="✨", layout="wide")

st.markdown("""
    <style>
    .score-high   { color: #059669; font-weight: 700; font-size: 1.5rem; }
    .score-mid    { color: #d97706; font-weight: 700; font-size: 1.5rem; }
    .score-low-m  { color: #ea580c; font-weight: 700; font-size: 1.5rem; }
    .score-low    { color: #dc2626; font-weight: 700; font-size: 1.5rem; }
    .tag { display:inline-block; padding:2px 10px; border-radius:999px; font-size:.75rem; font-weight:600; }
    </style>
""", unsafe_allow_html=True)


def extract_pdf_text(uploaded_file) -> str:
    with pdfplumber.open(uploaded_file) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages).strip()


def score_color_class(score: int) -> str:
    if score >= 80:
        return "score-high"
    if score >= 60:
        return "score-mid"
    if score >= 40:
        return "score-low-m"
    return "score-low"


def analyze_cv(client: anthropic.Anthropic, jd: str, cv_text: str) -> dict:
    prompt = f"""You are an expert recruiter. Analyze this candidate's CV against the job description and provide a matching assessment.

JOB DESCRIPTION:
{jd}

CANDIDATE CV:
{cv_text}

Evaluate based on:
- Required skills match
- Years and relevance of experience
- Education/qualifications fit
- Domain expertise
- Notable strengths beyond requirements

Respond with ONLY valid JSON, no markdown fences, no preamble. Use this exact structure:
{{"score": <integer 0-100>, "strengths": ["...", "..."], "gaps": ["...", "..."]}}

The score should reflect overall fit (0=no match, 100=perfect match). Provide 3-5 specific strengths and 2-4 specific gaps. Be concrete - reference actual skills, experiences, or requirements."""

    msg = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    parsed = json.loads(raw)
    return {
        "score": max(0, min(100, int(parsed.get("score", 0)))),
        "strengths": parsed.get("strengths", []),
        "gaps": parsed.get("gaps", []),
    }


def results_to_csv(results: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Rank", "Name", "Match Score (%)", "Strengths", "Gaps"])
    for i, r in enumerate(results, 1):
        writer.writerow([
            i,
            r["name"],
            r["score"],
            "; ".join(r.get("strengths", [])),
            "; ".join(r.get("gaps", [])),
        ])
    return buf.getvalue()


# ── Header ────────────────────────────────────────────────────────────────────

st.markdown(
    "<h1 style='text-align:center;'>✨ CV Shortlisting Tool</h1>"
    "<p style='text-align:center;color:#64748b;'>Match candidates to your job description with AI scoring</p>",
    unsafe_allow_html=True,
)

# ── API key ───────────────────────────────────────────────────────────────────

api_key = os.getenv("ANTHROPIC_API_KEY", "")
if not api_key:
    api_key = st.text_input("Anthropic API key", type="password",
                            help="Set ANTHROPIC_API_KEY in a .env file to avoid entering it each time.")

# ── Step 1: Job Description ───────────────────────────────────────────────────

st.subheader("Step 1 — Job Description")
jd_mode = st.radio("Input method", ["Paste text", "Upload PDF"], horizontal=True, label_visibility="collapsed")

jd_text = ""
if jd_mode == "Paste text":
    jd_text = st.text_area("Job description", height=200, placeholder="Paste the job description here…", label_visibility="collapsed")
else:
    jd_file = st.file_uploader("Upload JD PDF", type=["pdf"], label_visibility="collapsed")
    if jd_file:
        try:
            jd_text = extract_pdf_text(jd_file)
            st.success(f"Extracted {len(jd_text):,} characters from {jd_file.name}")
        except Exception as e:
            st.error(f"Failed to read PDF: {e}")

# ── Step 2: Candidate CVs ─────────────────────────────────────────────────────

st.subheader("Step 2 — Candidate CVs")

if "cvs" not in st.session_state:
    st.session_state.cvs = []  # list of {"name": str, "text": str}

cv_mode = st.radio("Input method", ["Upload PDFs", "Paste text"], horizontal=True,
                   key="cv_mode_radio", label_visibility="collapsed")

if cv_mode == "Upload PDFs":
    uploaded_cvs = st.file_uploader(
        "Upload CV PDFs (multiple allowed)", type=["pdf"], accept_multiple_files=True,
        label_visibility="collapsed",
    )
    if uploaded_cvs:
        existing_names = {c["name"] for c in st.session_state.cvs}
        added = 0
        for f in uploaded_cvs:
            name = f.name.removesuffix(".pdf")
            if name not in existing_names:
                try:
                    text = extract_pdf_text(f)
                    st.session_state.cvs.append({"name": name, "text": text})
                    existing_names.add(name)
                    added += 1
                except Exception as e:
                    st.error(f"Failed to read {f.name}: {e}")
        if added:
            st.success(f"Added {added} CV(s).")
else:
    col1, col2 = st.columns([1, 3])
    with col1:
        paste_name = st.text_input("Candidate name", key="paste_name")
    with col2:
        paste_text = st.text_area("CV text", height=120, key="paste_text",
                                  placeholder="Paste CV text here…", label_visibility="collapsed")
    if st.button("Add Candidate", disabled=not (paste_name.strip() and paste_text.strip())):
        st.session_state.cvs.append({"name": paste_name.strip(), "text": paste_text.strip()})
        st.rerun()

# Show added CVs with remove buttons
if st.session_state.cvs:
    st.markdown(f"**{len(st.session_state.cvs)} candidate(s) loaded**")
    to_remove = []
    for i, cv in enumerate(st.session_state.cvs):
        cols = st.columns([6, 1])
        cols[0].markdown(f"📄 **{cv['name']}** — {len(cv['text']):,} chars")
        if cols[1].button("✕", key=f"rm_{i}"):
            to_remove.append(i)
    for idx in reversed(to_remove):
        st.session_state.cvs.pop(idx)
    if to_remove:
        st.rerun()

# ── Run analysis ──────────────────────────────────────────────────────────────

st.divider()

run_disabled = not api_key or not jd_text.strip() or not st.session_state.cvs
if st.button("✨ Run Shortlisting", type="primary", disabled=run_disabled, use_container_width=True):
    client = anthropic.Anthropic(api_key=api_key)
    results = []
    bar = st.progress(0, text="Starting analysis…")
    total = len(st.session_state.cvs)

    for i, cv in enumerate(st.session_state.cvs):
        bar.progress((i) / total, text=f"Analysing {cv['name']} ({i+1}/{total})…")
        try:
            analysis = analyze_cv(client, jd_text, cv["text"])
            results.append({"name": cv["name"], **analysis})
        except Exception as e:
            results.append({"name": cv["name"], "score": 0, "strengths": [], "gaps": [],
                            "error": str(e)})

    bar.progress(1.0, text="Done!")
    results.sort(key=lambda r: r["score"], reverse=True)
    st.session_state.results = results

# ── Results ───────────────────────────────────────────────────────────────────

if st.session_state.get("results"):
    results = st.session_state.results
    st.subheader("Ranked Shortlist")

    csv_data = results_to_csv(results)
    st.download_button("⬇ Export CSV", data=csv_data, file_name="cv-shortlist.csv",
                       mime="text/csv")

    for i, r in enumerate(results):
        css_cls = score_color_class(r["score"])
        with st.expander(f"#{i+1}  {r['name']}", expanded=i == 0):
            if r.get("error"):
                st.error(r["error"])
            else:
                col_score, col_bar = st.columns([1, 4])
                col_score.markdown(f"<span class='{css_cls}'>{r['score']}%</span>",
                                   unsafe_allow_html=True)
                col_bar.progress(r["score"] / 100)

                left, right = st.columns(2)
                with left:
                    st.markdown("**✅ Strengths**")
                    for s in r["strengths"]:
                        st.markdown(f"- {s}")
                with right:
                    st.markdown("**⚠ Gaps**")
                    for g in r["gaps"]:
                        st.markdown(f"- {g}")

st.markdown(
    "<p style='text-align:center;color:#94a3b8;font-size:.75rem;margin-top:2rem;'>"
    "Powered by Claude · PDFs are processed locally and never stored</p>",
    unsafe_allow_html=True,
)
