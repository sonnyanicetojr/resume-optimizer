import os
import json
import tempfile
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from resume_parser import extract_text, extract_styles, parse_resume
from llm_tailor import tailor_resume
from cv_generator import generate_docx, convert_to_pdf
from prompts import TAILORING_TIPS

load_dotenv()

st.set_page_config(
    page_title="CV Tailor",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Session State
# ---------------------------------------------------------------------------
for key, default in {
    "tailored_cv": None,
    "output_docx": None,
    "output_pdf": None,
    "original_text": None,
    "step": 1,
    "resume_text": "",
    "resume_styles": {},
    "resume_loaded": False,
    "resume_source": "",
    "jd_text": "",
    "jd_loaded": False,
    "jd_source_name": "",
    "generating": False,
    "gen_elapsed": 0.0,
    "theme": "light",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def go_to(step):
    st.session_state.step = step


def save_outputs(tailored_cv):
    """Write the DOCX (and PDF if conversion works) and record them in session state."""
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    docx_path = str(output_dir / f"tailored_cv_{ts}.docx")
    pdf_path = str(output_dir / f"tailored_cv_{ts}.pdf")

    generate_docx(tailored_cv, st.session_state.resume_styles, docx_path)
    try:
        convert_to_pdf(docx_path, pdf_path)
        st.session_state.output_pdf = pdf_path
    except Exception:
        st.session_state.output_pdf = None

    st.session_state.tailored_cv = tailored_cv
    st.session_state.output_docx = docx_path


def toggle_theme():
    st.session_state.theme = "dark" if st.session_state.theme == "light" else "light"


is_dark = st.session_state.theme == "dark"

# ---------------------------------------------------------------------------
# Modernist design system — tokens from the claude.ai/design "Modernist"
# project (styles.css / theme.json). Light is the system as designed; dark is
# derived from the same tonal ramps (accent-400 on a dark ground, per its guide).
# ---------------------------------------------------------------------------
LIGHT_TOKENS = {
    "bg": "#f2f4f7",
    "surface": "#e6eaf0",
    "text": "#0e1830",
    "accent": "#1c3170",
    "accent-hover": "#3a5ba8",   # accent-600
    "accent-press": "#273f88",   # accent-700
    "accent-ink": "#273f88",     # accent-700 — accent-coloured body text
    "on-accent": "#f2f4f7",
    "tag-bg": "#eef3fc",         # accent-100
    "tag-text": "#1c2f68",       # accent-800
    "danger": "#b3261e",
    "divider": "color-mix(in srgb, #0e1830 40%, transparent)",
}
DARK_TOKENS = {
    "bg": "#0b1226",
    "surface": "#131f44",        # accent-900
    "text": "#eef3fc",
    "accent": "#8fa9dc",         # accent-400
    "accent-hover": "#bccdee",   # accent-300
    "accent-press": "#dae4f6",   # accent-200
    "accent-ink": "#bccdee",
    "on-accent": "#0e1830",
    "tag-bg": "#1c2f68",         # accent-800
    "tag-text": "#dae4f6",
    "danger": "#f2b8b5",
    "divider": "color-mix(in srgb, #eef3fc 35%, transparent)",
}

tokens = DARK_TOKENS if is_dark else LIGHT_TOKENS
token_css = "\n".join(f"    --color-{k}: {v};" for k, v in tokens.items())

MODERNIST_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;800&display=swap');

:root {
__TOKENS__
    --color-muted: color-mix(in srgb, var(--color-text) 55%, transparent);
    --color-soft: color-mix(in srgb, var(--color-text) 72%, transparent);
    --color-hover: color-mix(in srgb, var(--color-text) 7%, transparent);
    --color-press: color-mix(in srgb, var(--color-text) 14%, transparent);
    --font-heading: "Archivo", system-ui, sans-serif;
    --font-heading-weight: 800;
    --font-body: "Archivo", system-ui, sans-serif;
    --space-1: 4px;
    --space-2: 8px;
    --space-3: 12px;
    --space-4: 16px;
    --space-6: 24px;
    --space-8: 32px;
    --radius: 0px;
}

/* ── Base ── */
html, body, [data-testid="stApp"], [data-testid="stAppViewContainer"] {
    background: var(--color-bg) !important;
    color: var(--color-text) !important;
    font-family: var(--font-body) !important;
}
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stDecoration"],
[data-testid="collapsedControl"],
[data-testid="stSidebar"] { display: none !important; }
[data-testid="stBottomBlockContainer"] { background: transparent !important; }
[data-testid="stMainBlockContainer"], .block-container {
    max-width: 960px !important; padding-top: 2.5rem !important;
}
p, label, li, input, textarea, button, [data-testid="stMarkdownContainer"] {
    font-family: var(--font-body) !important;
}
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li { color: var(--color-text); }
h1, h2, h3, h4, h5, h6 {
    font-family: var(--font-heading) !important;
    font-weight: var(--font-heading-weight) !important;
    color: var(--color-text) !important;
    letter-spacing: -0.015em !important;
}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: var(--color-muted) !important; }
::selection { background: color-mix(in srgb, var(--color-accent) 30%, transparent); }
:focus-visible { outline: 2px solid var(--color-accent) !important; outline-offset: 2px; }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--color-divider); border-radius: 0; }
hr, [data-testid="stDivider"] { border-color: var(--color-divider) !important; }

/* ── Nav ── */
.nav { display: flex; align-items: baseline; gap: var(--space-3); }
.nav-brand {
    font-family: var(--font-heading); font-weight: var(--font-heading-weight);
    font-size: 22px; letter-spacing: -0.02em; color: var(--color-text);
}
.nav-sub {
    font-size: 11px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase;
    color: var(--color-muted);
}

/* ── Stepper: a four-cell grid ── */
.stepper {
    display: grid; grid-template-columns: repeat(4, 1fr);
    margin: var(--space-4) 0 var(--space-8);
}
.step { padding: var(--space-3) var(--space-3) var(--space-3) 0; border-top: 2px solid var(--color-divider); }
.step + .step { padding-left: var(--space-3); border-left: 1px solid var(--color-divider); }
.step-num {
    font-size: 11px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase;
    color: var(--color-muted);
}
.step-name {
    font-family: var(--font-heading); font-weight: var(--font-heading-weight);
    font-size: 15px; margin-top: 2px; color: var(--color-muted);
}
.step.done { border-top-color: var(--color-text); }
.step.done .step-num, .step.done .step-name { color: var(--color-text); }
.step.active { border-top: 4px solid var(--color-accent); padding-top: calc(var(--space-3) - 2px); }
.step.active .step-num { color: var(--color-accent-ink); }
.step.active .step-name { color: var(--color-text); }

/* ── Step intro ── */
.intro {
    padding-bottom: var(--space-6); margin-bottom: var(--space-6);
    border-bottom: 2px solid var(--color-divider);
}
.kicker {
    display: block; margin-bottom: var(--space-2);
    font-size: 11px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase;
    color: var(--color-accent-ink);
}
.intro-title {
    font-family: var(--font-heading); font-weight: var(--font-heading-weight);
    font-size: 40px; line-height: 1.08; letter-spacing: -0.02em;
    color: var(--color-text); margin: 0 0 var(--space-3);
}
.intro-desc { font-size: 15px; line-height: 1.55; color: var(--color-soft); max-width: 560px; margin: 0; }

/* ── Cards ── */
.card-grid {
    display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--space-2);
    margin: 0 0 var(--space-6);
}
.card {
    display: flex; flex-direction: column; gap: var(--space-2);
    padding: var(--space-4); background: var(--color-surface); border-radius: var(--radius);
    margin-bottom: var(--space-2);
}
.card-grid .card { margin-bottom: 0; }
.card-kicker {
    font-size: 10px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase;
    color: var(--color-accent-ink);
}
.card-title {
    font-family: var(--font-heading); font-weight: var(--font-heading-weight);
    font-size: 17px; line-height: 1.2; color: var(--color-text); overflow-wrap: anywhere;
}
.card-body { margin: 0; font-size: 13px; color: var(--color-soft); }
.card-meta { font-size: 11px; color: var(--color-muted); }

/* ── Results: CV preview ── */
.cv-head { padding: var(--space-4) 0 var(--space-2); }
.cv-name {
    font-family: var(--font-heading); font-weight: var(--font-heading-weight);
    font-size: 42px; line-height: 1.08; letter-spacing: -0.02em; color: var(--color-text);
}
.cv-contact { font-size: 13px; color: var(--color-soft); margin-top: var(--space-2); }
.section { margin-top: var(--space-8); }
.section-head {
    display: flex; align-items: baseline; gap: var(--space-3);
    padding-bottom: var(--space-2); margin-bottom: var(--space-2);
    border-bottom: 2px solid var(--color-divider);
}
.section-num { font-size: 11px; font-weight: 600; letter-spacing: 0.1em; color: var(--color-accent-ink); }
.section-title {
    font-family: var(--font-heading); font-weight: var(--font-heading-weight);
    font-size: 20px; letter-spacing: -0.01em; color: var(--color-text);
}
.section-text { font-size: 15px; line-height: 1.65; color: var(--color-text); margin: var(--space-3) 0 0; max-width: 720px; }

.skill-row {
    display: grid; grid-template-columns: 200px 1fr; gap: var(--space-4);
    padding: var(--space-3) 0; border-bottom: 1px solid var(--color-divider);
}
.skill-row:last-child { border-bottom: none; }
.skill-cat {
    font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--color-muted); padding-top: 4px;
}
.tags { display: flex; flex-wrap: wrap; gap: var(--space-1); }
.tag {
    display: inline-flex; align-items: center; font-size: 12px; letter-spacing: 0.02em;
    padding: 3px 10px; border-radius: var(--radius);
    background: var(--color-tag-bg); color: var(--color-tag-text);
}

.exp {
    display: grid; grid-template-columns: 1fr 200px; gap: var(--space-1) var(--space-4);
    padding: var(--space-4) 0; border-bottom: 1px solid var(--color-divider);
}
.exp:last-child { border-bottom: none; }
.exp-title {
    font-family: var(--font-heading); font-weight: var(--font-heading-weight);
    font-size: 16px; color: var(--color-text);
}
.exp-company { font-size: 14px; font-weight: 600; color: var(--color-accent-ink); }
.exp-meta { font-size: 12px; line-height: 1.5; color: var(--color-muted); }
.points { grid-column: 1 / -1; list-style: none; padding: 0; margin: var(--space-2) 0 0; }
.points li {
    position: relative; padding-left: var(--space-4); margin-bottom: var(--space-1);
    font-size: 14px; line-height: 1.6; color: var(--color-text);
}
.points li::before { content: '–'; position: absolute; left: 0; color: var(--color-accent-ink); }

.table { width: 100%; border-collapse: collapse; font-size: 14px; color: var(--color-text); }
.table th {
    text-align: left; font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--color-muted); padding: var(--space-2) var(--space-2) var(--space-2) 0;
    border-bottom: 2px solid var(--color-divider);
}
.table td { padding: var(--space-2) var(--space-2) var(--space-2) 0; border-bottom: 1px solid var(--color-divider); vertical-align: top; }
.table, .table th, .table td { border-top: none !important; border-left: none !important; border-right: none !important; background: transparent !important; }
.table tbody tr:hover { background: var(--color-hover); }
.table td.strong { font-weight: 600; }

/* ── Footer ── */
.footer {
    margin-top: 3rem; padding-top: var(--space-3);
    border-top: 2px solid var(--color-divider);
    font-size: 12px; color: var(--color-muted);
}
.footer b { color: var(--color-text); font-weight: var(--font-heading-weight); }

/* ── Buttons: square, heavy, labels flush left ── */
[data-testid^="stBaseButton"] {
    border-radius: var(--radius) !important; min-height: 40px !important;
    padding: var(--space-2) 14px !important;
    justify-content: flex-start !important; text-align: left !important;
    box-shadow: none !important; transition: background 0.12s ease, border-color 0.12s ease !important;
}
[data-testid^="stBaseButton"] > div {
    width: 100% !important; justify-content: flex-start !important; text-align: left !important;
}
[data-testid^="stBaseButton"] p {
    font-family: var(--font-heading) !important; font-weight: var(--font-heading-weight) !important;
    font-size: 14px !important; text-align: left !important;
}
[data-testid="stBaseButton-primary"] {
    background: var(--color-accent) !important; border: 1px solid var(--color-accent) !important;
    color: var(--color-on-accent) !important;
}
[data-testid="stBaseButton-primary"] p { color: var(--color-on-accent) !important; }
[data-testid="stBaseButton-primary"]:hover:not(:disabled) {
    background: var(--color-accent-hover) !important; border-color: var(--color-accent-hover) !important;
}
[data-testid="stBaseButton-primary"]:active:not(:disabled) {
    background: var(--color-accent-press) !important; border-color: var(--color-accent-press) !important;
}
[data-testid="stBaseButton-secondary"] {
    background: transparent !important; border: 1px solid var(--color-divider) !important;
    color: var(--color-text) !important;
}
[data-testid="stBaseButton-secondary"] p { color: var(--color-text) !important; }
[data-testid="stBaseButton-secondary"]:hover:not(:disabled) { background: var(--color-hover) !important; }
[data-testid="stBaseButton-secondary"]:active:not(:disabled) { background: var(--color-press) !important; }
[data-testid^="stBaseButton"]:disabled { opacity: 0.45 !important; cursor: not-allowed !important; }

/* ── Form fields ── */
[data-testid="stWidgetLabel"] p {
    font-size: 12px !important; font-weight: 400 !important; color: var(--color-soft) !important;
}
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {
    background: var(--color-surface) !important;
    border: 1px solid var(--color-divider) !important; border-radius: var(--radius) !important;
}
[data-baseweb="input"]:hover, [data-baseweb="textarea"]:hover, [data-baseweb="select"] > div:hover {
    border-color: color-mix(in srgb, var(--color-text) 55%, transparent) !important;
}
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within, [data-baseweb="select"] > div:focus-within {
    border-color: var(--color-accent) !important;
}
[data-baseweb="base-input"], [data-baseweb="input"] input, [data-baseweb="textarea"] textarea {
    background: transparent !important; color: var(--color-text) !important;
    font-size: 14px !important; caret-color: var(--color-accent);
}
[data-baseweb="select"] * { color: var(--color-text) !important; }
[data-baseweb="popover"] > div, [data-baseweb="menu"], [data-baseweb="popover"] ul {
    background: var(--color-surface) !important; border-radius: var(--radius) !important;
}
[data-baseweb="popover"] li { color: var(--color-text) !important; }
[data-baseweb="popover"] li[aria-selected="true"] { background: var(--color-tag-bg) !important; }
[data-baseweb="popover"] li:hover { background: var(--color-hover) !important; }

/* Radio → segmented control */
[data-testid="stRadio"] [role="radiogroup"] {
    display: inline-flex !important; flex-direction: row !important; flex-wrap: nowrap !important;
    gap: 0 !important; border: 1px solid var(--color-divider);
}
[data-testid="stRadio"] label[data-baseweb="radio"] {
    margin: 0 !important; padding: 7px 14px !important; cursor: pointer;
    background: transparent; transition: background 0.12s ease;
}
[data-testid="stRadio"] label[data-baseweb="radio"] + label[data-baseweb="radio"] {
    border-left: 1px solid var(--color-divider);
}
[data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child {
    position: absolute !important; width: 0 !important; height: 0 !important;
    margin: 0 !important; border: 0 !important; overflow: hidden !important; opacity: 0 !important;
}
[data-testid="stRadio"] label[data-baseweb="radio"] p { font-size: 13px !important; font-weight: 600 !important; }
[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) { background: var(--color-accent) !important; }
[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) p { color: var(--color-on-accent) !important; }
[data-testid="stRadio"] label[data-baseweb="radio"]:not(:has(input:checked)):hover { background: var(--color-hover); }
[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:focus-visible) {
    outline: 2px solid var(--color-accent); outline-offset: -2px;
}

/* Checkbox */
[data-testid="stCheckbox"] label[data-baseweb="checkbox"] > span:first-child {
    border-radius: var(--radius) !important; border-color: var(--color-divider) !important;
    background-color: var(--color-surface) !important;
}
[data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked) > span:first-child {
    background-color: var(--color-accent) !important; border-color: var(--color-accent) !important;
}
[data-testid="stCheckbox"] p { font-size: 14px !important; color: var(--color-text) !important; }

/* File uploader */
[data-testid="stFileUploaderDropzone"] {
    background: var(--color-surface) !important; border: 1px solid var(--color-divider) !important;
    border-radius: var(--radius) !important;
}
[data-testid="stFileUploaderDropzone"] * { color: var(--color-soft); }

/* ── Alerts: surface with a strong accent edge ── */
[data-testid="stAlertContainer"] {
    background: var(--color-surface) !important; color: var(--color-text) !important;
    border: 0 !important; border-left: 4px solid var(--color-accent) !important;
    border-radius: var(--radius) !important;
}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) { border-left-color: var(--color-danger) !important; }
[data-testid="stAlertContainer"] p { color: var(--color-text) !important; font-size: 14px !important; }
[data-testid="stAlertContainer"] svg { color: var(--color-accent) !important; fill: var(--color-accent) !important; }

/* ── Tabs: underline on a 2px rule ── */
[data-baseweb="tab-list"] {
    gap: var(--space-6) !important; background: transparent !important;
    border-bottom: 2px solid var(--color-divider) !important;
}
[data-baseweb="tab"] {
    background: transparent !important; padding: var(--space-2) 0 !important; border-radius: var(--radius) !important;
}
[data-baseweb="tab"] p {
    font-family: var(--font-heading) !important; font-weight: var(--font-heading-weight) !important;
    font-size: 14px !important; color: var(--color-muted) !important;
}
[data-baseweb="tab"][aria-selected="true"] p, [data-baseweb="tab"]:hover p { color: var(--color-text) !important; }
[data-baseweb="tab-highlight"] { background: var(--color-accent) !important; }
[data-baseweb="tab-border"] { display: none !important; }

/* ── Progress, JSON, code ── */
[data-testid="stProgress"] [role="progressbar"] > div { border-radius: var(--radius) !important; }
[data-testid="stProgress"] [role="progressbar"] > div > div { background-color: var(--color-accent) !important; border-radius: var(--radius) !important; }
[data-testid="stJson"] { background: var(--color-surface) !important; border-radius: var(--radius) !important; padding: var(--space-3); }

@media (max-width: 640px) {
    .stepper { grid-template-columns: repeat(2, 1fr); }
    .step:nth-child(3) { border-left: none; padding-left: 0; }
    .intro-title, .cv-name { font-size: 30px; }
    .card-grid { grid-template-columns: 1fr; }
    .skill-row, .exp { grid-template-columns: 1fr; gap: var(--space-1); }
}
"""

st.markdown(
    "<style>" + MODERNIST_CSS.replace("__TOKENS__", token_css) + "</style>",
    unsafe_allow_html=True,
)


def intro(kicker, title, desc):
    """Step header: accent kicker, display title, flush-left lede, 2px rule below."""
    st.markdown(
        f"""<div class="intro">
    <span class="kicker">{kicker}</span>
    <div class="intro-title">{title}</div>
    <p class="intro-desc">{desc}</p>
</div>""",
        unsafe_allow_html=True,
    )


def section_head(num, title):
    num_html = f'<span class="section-num">{num:02d}</span>' if num is not None else ""
    return f"""<div class="section-head">
    {num_html}
    <span class="section-title">{title}</span>
</div>"""


# ---------------------------------------------------------------------------
# NAVBAR
# ---------------------------------------------------------------------------
nav_left, nav_right = st.columns([4, 1], vertical_alignment="bottom")
with nav_left:
    st.markdown(
        """
    <div class="nav">
        <span class="nav-brand">CV Tailor</span>
        <span class="nav-sub">Resume tailoring</span>
    </div>
    """,
        unsafe_allow_html=True,
    )
with nav_right:
    st.button(
        "Light mode" if is_dark else "Dark mode",
        on_click=toggle_theme,
        type="secondary",
        use_container_width=True,
    )

# ---------------------------------------------------------------------------
# Determine effective step & readiness
# ---------------------------------------------------------------------------
has_results = st.session_state.tailored_cv is not None
current_step = st.session_state.step

# Clamp step
if has_results and current_step < 4:
    current_step = 4

s1_done = st.session_state.resume_loaded
s2_done = st.session_state.jd_loaded
s3_done = has_results

# ---------------------------------------------------------------------------
# STEPPER
# ---------------------------------------------------------------------------
def step_class(n, label=False):
    if has_results and n <= 3:
        return "done"
    if n < current_step:
        return "done"
    if n == current_step:
        return "active"
    return ""

step_cells = "".join(
    f'<div class="step {step_class(n)}">'
    f'<div class="step-num">{n:02d}{" — Done" if step_class(n) == "done" else ""}</div>'
    f'<div class="step-name">{name}</div></div>'
    for n, name in enumerate(["Resume", "Job description", "Generate", "Results"], 1)
)
st.markdown(f'<div class="stepper">{step_cells}</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# STEP 1 — RESUME
# ═══════════════════════════════════════════════════════════════════════════
if current_step == 1:
    intro(
        "Step 01 / 03",
        "Upload your resume",
        "Provide your current resume. We'll extract and preserve its structure for tailoring.",
    )

    uploaded_resume = st.file_uploader(
        "Upload your resume (DOCX)",
        type=["docx"],
        help="Upload your existing resume in DOCX format",
    )

    resume_text = ""
    resume_styles = {}
    resume_ok = False
    resume_src = ""

    if uploaded_resume is not None:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                tmp.write(uploaded_resume.getvalue())
                tmp_path = tmp.name
            parsed = parse_resume(tmp_path)
            resume_text = parsed["text"]
            resume_styles = parsed["styles"]
            os.unlink(tmp_path)
            resume_ok = True
            resume_src = uploaded_resume.name
        except Exception as e:
            st.error(f"Error reading uploaded resume: {e}")

    if resume_ok:
        word_count = len(resume_text.split())
        st.success(f"**{resume_src}** — {word_count:,} words extracted")
        if st.checkbox("Show preview", value=False, key="preview_resume"):
            st.text_area(
                "content",
                value=resume_text,
                height=250,
                disabled=True,
                label_visibility="collapsed",
            )

    col_l, col_r = st.columns([3, 1])
    with col_r:
        if st.button("Continue", type="primary", use_container_width=True, disabled=not resume_ok):
            st.session_state.resume_text = resume_text
            st.session_state.resume_styles = resume_styles
            st.session_state.resume_loaded = True
            st.session_state.resume_source = resume_src
            go_to(2)
            st.rerun()

# ═══════════════════════════════════════════════════════════════════════════
# STEP 2 — JOB DESCRIPTION
# ═══════════════════════════════════════════════════════════════════════════
elif current_step == 2:
    intro(
        "Step 02 / 03",
        "Add the job description",
        "Paste or upload a job description to align your resume with the role.",
    )

    jd_source_options = ["Paste text", "Upload file"]
    if "jd_source_choice" not in st.session_state:
        st.session_state.jd_source_choice = jd_source_options[0]

    jd_source = st.radio(
        "Choose source",
        options=jd_source_options,
        horizontal=True,
        key="jd_source_choice",
    )

    job_description = ""
    jd_name = ""

    if jd_source == "Paste text":
        job_description = st.text_area(
            "Job Description",
            height=250,
            placeholder="Paste the full job description here…",
            label_visibility="collapsed",
            key="pasted_jd",
        )
        jd_name = "Pasted JD"
    elif jd_source == "Upload file":
        uploaded_jd = st.file_uploader(
            "Upload job description (.md / .txt)",
            type=["md", "txt"],
            key="jd_upload",
        )
        if uploaded_jd:
            job_description = uploaded_jd.read().decode("utf-8")
            jd_name = uploaded_jd.name

    jd_ok = bool(job_description.strip())

    if jd_ok:
        jd_words = len(job_description.split())
        st.success(f"**{jd_name}** — {jd_words:,} words")
        if st.checkbox("Show preview", value=False, key="preview_jd"):
            st.markdown(job_description[:2000])

    col_l, col_r = st.columns([1, 1])
    with col_l:
        if st.button("Back", use_container_width=True):
            go_to(1)
            st.rerun()
    with col_r:
        if st.button("Continue", type="primary", use_container_width=True, disabled=not jd_ok):
            st.session_state.jd_text = job_description
            st.session_state.jd_loaded = True
            st.session_state.jd_source_name = jd_name
            go_to(3)
            st.rerun()

# ═══════════════════════════════════════════════════════════════════════════
# STEP 3 — REVIEW & GENERATE
# ═══════════════════════════════════════════════════════════════════════════
elif current_step == 3:
    intro(
        "Step 03 / 03",
        "Review &amp; generate",
        "Confirm your inputs and choose an AI model, then generate your tailored resume.",
    )

    r_words = len(st.session_state.resume_text.split())
    j_words = len(st.session_state.jd_text.split())
    st.markdown(
        f"""
    <div class="card-grid">
        <div class="card">
            <span class="card-kicker">Resume</span>
            <span class="card-title">{st.session_state.resume_source}</span>
            <span class="card-meta">{r_words:,} words</span>
        </div>
        <div class="card">
            <span class="card-kicker">Job description</span>
            <span class="card-title">{st.session_state.jd_source_name}</span>
            <span class="card-meta">{j_words:,} words</span>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    api_key_env = os.getenv("OPENROUTER_API_KEY", "")
    if "api_key_input" not in st.session_state:
        st.session_state.api_key_input = api_key_env

    c1, c2 = st.columns(2)
    with c1:
        api_key = st.text_input(
            "API Key",
            type="password",
            help="https://openrouter.ai/keys",
            key="api_key_input",
        )
    with c2:
        # Model IDs verified against openrouter.ai/api/v1/models (2026-10-15).
        # Grouped by vendor, newest first. Every Gemini entry has a
        # "Google AI Studio" endpoint, which tailor_resume() pins for BYOK.
        model_options = {
            "Fusion": "openrouter/fusion",
            # OpenAI
            "OpenAI — GPT-6.1 Sol Pro": "openai/gpt-6.1-sol-pro",
            "OpenAI — GPT-6.1 Sol": "openai/gpt-6.1-sol",
            "OpenAI — GPT-6 Astra Pro": "openai/gpt-6-astra-pro",
            "OpenAI — GPT-6 Astra": "openai/gpt-6-astra",
            "OpenAI — GPT-6 Luna Pro": "openai/gpt-6-luna-pro",
            "OpenAI — GPT-6 Luna": "openai/gpt-6-luna",
            "OpenAI — GPT-5.6 Terra": "openai/gpt-5.6-terra",
            "OpenAI — GPT-5.5": "openai/gpt-5.5",
            # Google
            "Google — Gemini 4 Argon": "google/gemini-4-argon",
            "Google — Gemini 3.8 Flash": "google/gemini-3.8-flash",
            "Google — Gemini 3.7 Flash": "google/gemini-3.7-flash",
            "Google — Gemini 3.5 Flash": "google/gemini-3.5-flash",
            "Google — Gemini 3.5 Flash Lite": "google/gemini-3.5-flash-lite",
            "Google — Gemini 3.1 Pro": "google/gemini-3.1-pro-preview",
            "Google — Gemini 3.1 Flash Lite": "google/gemini-3.1-flash-lite",
            "Google — Gemini 3 Flash": "google/gemini-3-flash-preview",
            "Google — Gemini 3.1 Flash Lite (preview)": "google/gemini-3.1-flash-lite-preview",
            "Google — Gemini 2.5 Pro": "google/gemini-2.5-pro",
            "Google — Gemini 2.5 Flash": "google/gemini-2.5-flash",
            # Anthropic
            "Anthropic — Claude Fable 5.1": "anthropic/claude-fable-5.1",
            "Anthropic — Claude Fable 5": "anthropic/claude-fable-5",
            "Anthropic — Claude Opus 5.5": "anthropic/claude-opus-5.5",
            "Anthropic — Claude Opus 5": "anthropic/claude-opus-5",
            "Anthropic — Claude Opus 4.8": "anthropic/claude-opus-4.8",
            "Anthropic — Claude Opus 4.7": "anthropic/claude-opus-4.7",
            "Anthropic — Claude Sonnet 5.5": "anthropic/claude-sonnet-5.5",
            "Anthropic — Claude Sonnet 5": "anthropic/claude-sonnet-5",
            "Anthropic — Claude Haiku 5.5": "anthropic/claude-haiku-5.5",
            # xAI / Meta / Mistral / Cohere
            "xAI — Grok 4.7": "x-ai/grok-4.7",
            "xAI — Grok 4.6": "x-ai/grok-4.6",
            "Meta — Muse Wonder": "meta/muse-wonder",
            "Meta — Muse Spark 1.3": "meta/muse-spark-1.3",
            "Mistral — Mistral Large 4": "mistralai/mistral-large-4-0",
            "Cohere — Command A+": "cohere/command-a-plus",
            # DeepSeek
            "DeepSeek — V4 Pro 0813": "deepseek/deepseek-v4-pro-0813",
            "DeepSeek — V4.1 Flash": "deepseek/deepseek-v4.1-flash",
            # Qwen
            "Qwen — Qwen3.8 Max Prime": "qwen/qwen3.8-max-prime",
            "Qwen — Qwen3.8 Max (0902)": "qwen/qwen3.8-max-0902",
            "Qwen — Qwen3.8 Flash": "qwen/qwen3.8-flash",
            "Qwen — Qwen3.7 Max": "qwen/qwen3.7-max",
            "Qwen — Qwen3.6 Plus": "qwen/qwen3.6-plus",
            "Qwen — Qwen3.5 397B-A17B": "qwen/qwen3.5-397b-a17b",
            # Z-AI
            "Z-AI — GLM 5.3 Prime": "z-ai/glm-5.3-prime",
            "Z-AI — GLM 5.3": "z-ai/glm-5.3",
            "Z-AI — GLM 5.3 Flash": "z-ai/glm-5.3-flash",
            "Z-AI — GLM-5.2": "z-ai/glm-5.2",
            # Moonshot / MiniMax / Xiaomi / StepFun / NVIDIA
            "Moonshot — Kimi K3": "moonshotai/kimi-k3",
            "Moonshot — Kimi K2.6": "moonshotai/kimi-k2.6",
            "MiniMax — M3": "minimax/minimax-m3",
            "Xiaomi — MiMo V2.6 Pro": "xiaomi/mimo-v2.6-pro",
            "StepFun — Step 5 Preview": "stepfun/step-5-preview",
            "NVIDIA — Nemotron 3 Ultra": "nvidia/nemotron-3-ultra-550b-a55b",
        }
        if "selected_model" not in st.session_state:
            st.session_state.selected_model = "Fusion"

        selected_label = st.selectbox(
            "Model",
            options=list(model_options.keys()),
            key="selected_model",
        )
        model = model_options[selected_label]

    col_l, col_r = st.columns([1, 1])
    with col_l:
        if st.button("Back", use_container_width=True):
            go_to(2)
            st.rerun()
    with col_r:
        can_gen = bool(api_key) and st.session_state.resume_loaded and st.session_state.jd_loaded
        if st.button(
            "Generate tailored CV",
            type="primary",
            use_container_width=True,
            disabled=not can_gen,
        ):
            with st.spinner(""):
                progress = st.progress(0, text="Sending to AI model…")
                try:
                    start = time.time()
                    tailored_cv = tailor_resume(
                        resume_text=st.session_state.resume_text,
                        job_description=st.session_state.jd_text,
                        api_key=api_key,
                        model=model,
                    )
                    elapsed = time.time() - start
                    progress.progress(50, text=f"AI responded in {elapsed:.1f}s — generating documents…")

                    st.session_state.original_text = st.session_state.resume_text

                    save_outputs(tailored_cv)
                    st.session_state.model_id = model
                    st.session_state.used_api_key = api_key
                    st.session_state.gen_elapsed = elapsed
                    progress.progress(100, text="Done")
                    time.sleep(0.5)
                    go_to(4)
                    st.rerun()

                except ValueError as e:
                    st.error(f"Validation Error: {e}")
                except Exception as e:
                    st.error(f"Error: {e}")

    if not can_gen:
        st.caption("Please provide your API key to generate.")

# ═══════════════════════════════════════════════════════════════════════════
# STEP 4 — RESULTS
# ═══════════════════════════════════════════════════════════════════════════
elif current_step == 4 and has_results:
    tailored = st.session_state.tailored_cv

    intro(
        "Results",
        "Your tailored CV is ready",
        f"Generated in {st.session_state.gen_elapsed:.1f}s with {st.session_state.get('model_id', 'the selected model')}.",
    )

    # Downloads
    dl1, dl2 = st.columns(2, gap="small")
    with dl1:
        st.markdown(
            """
        <div class="card">
            <span class="card-kicker">DOCX</span>
            <span class="card-title">Word document</span>
            <p class="card-body">Editable — make further changes in Word.</p>
        </div>
        """,
            unsafe_allow_html=True,
        )
        if st.session_state.output_docx and os.path.exists(st.session_state.output_docx):
            with open(st.session_state.output_docx, "rb") as f:
                st.download_button(
                    "Download DOCX",
                    data=f.read(),
                    file_name=os.path.basename(st.session_state.output_docx),
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )
        else:
            st.caption("DOCX not available")

    with dl2:
        st.markdown(
            """
        <div class="card">
            <span class="card-kicker">PDF</span>
            <span class="card-title">PDF document</span>
            <p class="card-body">Print-ready — requires Word for conversion.</p>
        </div>
        """,
            unsafe_allow_html=True,
        )
        if st.session_state.output_pdf and os.path.exists(st.session_state.output_pdf):
            with open(st.session_state.output_pdf, "rb") as f:
                st.download_button(
                    "Download PDF",
                    data=f.read(),
                    file_name=os.path.basename(st.session_state.output_pdf),
                    mime="application/pdf",
                    use_container_width=True,
                )
        else:
            st.caption("PDF not available (requires Microsoft Word)")

    st.markdown("<div style='height:var(--space-6)'></div>", unsafe_allow_html=True)

    # Tabs
    tab_preview, tab_json = st.tabs(["Preview", "JSON"])

    with tab_preview:
        # Name + Contact
        name = tailored.get("name", "N/A")
        contact = tailored.get("contact", {})
        contact_parts = [contact.get(k, "") for k in ["email", "phone", "location", "linkedin", "other"] if contact.get(k)]
        contact_str = " &nbsp;/&nbsp; ".join(contact_parts)

        st.markdown(
            f"""
        <div class="cv-head">
            <div class="cv-name">{name}</div>
            <div class="cv-contact">{contact_str}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

        sec_no = 0

        # Summary
        summary = tailored.get("professional_summary", "")
        if summary:
            sec_no += 1
            st.markdown(
                f"""<div class="section">{section_head(sec_no, "Professional summary")}
                <p class="section-text">{summary}</p></div>""",
                unsafe_allow_html=True,
            )

        # Skills
        skills = tailored.get("skills", {})
        if skills:
            sec_no += 1
            rows = ""
            for cat, s_list in skills.items():
                tags = "".join(f'<span class="tag">{s}</span>' for s in s_list)
                rows += f'<div class="skill-row"><div class="skill-cat">{cat}</div><div class="tags">{tags}</div></div>'
            st.markdown(
                f'<div class="section">{section_head(sec_no, "Skills")}{rows}</div>',
                unsafe_allow_html=True,
            )

        # Experience
        experience = tailored.get("experience", [])
        if experience:
            sec_no += 1
            rows = ""
            for exp in experience:
                hl = "".join(f"<li>{h}</li>" for h in exp.get("highlights", []))
                rows += f"""<div class="exp">
                    <div>
                        <div class="exp-title">{exp.get('title','')}</div>
                        <div class="exp-company">{exp.get('company','')}</div>
                    </div>
                    <div class="exp-meta">{exp.get('dates','')}<br/>{exp.get('location','')}</div>
                    <ul class="points">{hl}</ul>
                </div>"""
            st.markdown(
                f'<div class="section">{section_head(sec_no, "Professional experience")}{rows}</div>',
                unsafe_allow_html=True,
            )

        # Education
        education = tailored.get("education", [])
        if education:
            sec_no += 1
            rows = "".join(
                f"<tr><td class='strong'>{edu.get('degree','')}</td>"
                f"<td>{edu.get('institution','')}</td><td>{edu.get('dates','')}</td></tr>"
                for edu in education
            )
            st.markdown(
                f"""<div class="section">{section_head(sec_no, "Education")}
                <table class="table"><thead><tr><th>Degree</th><th>Institution</th><th>Dates</th></tr></thead>
                <tbody>{rows}</tbody></table></div>""",
                unsafe_allow_html=True,
            )

        # Certifications
        certs = tailored.get("certifications", [])
        if certs:
            sec_no += 1
            rows = "".join(
                f"<tr><td class='strong'>{c.get('name','')}</td>"
                f"<td>{c.get('issuer','')}</td><td>{c.get('date','')}</td></tr>"
                for c in certs
            )
            st.markdown(
                f"""<div class="section">{section_head(sec_no, "Certifications")}
                <table class="table"><thead><tr><th>Certification</th><th>Issuer</th><th>Date</th></tr></thead>
                <tbody>{rows}</tbody></table></div>""",
                unsafe_allow_html=True,
            )

        # Additional
        additional = tailored.get("additional_sections", {})
        for sec_name, content in additional.items():
            sec_no += 1
            if isinstance(content, list):
                items = "".join(f"<li>{i}</li>" for i in content)
                body = f'<ul class="points" style="margin-top:var(--space-3)">{items}</ul>'
            else:
                body = f'<p class="section-text">{content}</p>'
            st.markdown(
                f'<div class="section">{section_head(sec_no, sec_name)}{body}</div>',
                unsafe_allow_html=True,
            )

    with tab_json:
        st.json(tailored)

    # Feedback / revision
    st.markdown(
        f"""<div class="section">{section_head(None, "Revise")}
        <p class="intro-desc" style="margin:var(--space-3) 0 var(--space-3);">Not quite right? Tell the AI what to change.</p></div>""",
        unsafe_allow_html=True,
    )
    feedback = st.text_area(
        "Feedback",
        key=f"feedback_input_{st.session_state.get('revision_count', 0)}",
        placeholder="e.g. Make the summary shorter, emphasise Python over Java, drop the 2015 internship…",
        label_visibility="collapsed",
    )
    if st.button(
        "Revise CV",
        type="primary",
        use_container_width=True,
        disabled=not feedback.strip(),
    ):
        with st.spinner("Revising your CV…"):
            try:
                start = time.time()
                revised = tailor_resume(
                    resume_text=st.session_state.resume_text,
                    job_description=st.session_state.jd_text,
                    api_key=st.session_state.get("used_api_key") or os.getenv("OPENROUTER_API_KEY", ""),
                    model=st.session_state.get("model_id", "openrouter/fusion"),
                    previous_cv=st.session_state.tailored_cv,
                    feedback=feedback.strip(),
                )
                save_outputs(revised)
                st.session_state.gen_elapsed = time.time() - start
                st.session_state.revision_count = st.session_state.get("revision_count", 0) + 1
                st.rerun()
            except ValueError as e:
                st.error(f"Validation Error: {e}")
            except Exception as e:
                st.error(f"Error: {e}")

    # Start over
    st.markdown("<div style='height:var(--space-4)'></div>", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("Start over", use_container_width=True):
            reset_defaults = {
                "tailored_cv": None,
                "output_docx": None,
                "output_pdf": None,
                "original_text": None,
                "resume_text": "",
                "resume_styles": {},
                "resume_loaded": False,
                "resume_source": "",
                "jd_text": "",
                "jd_loaded": False,
                "jd_source_name": "",
                "gen_elapsed": 0.0,
            }
            for k, v in reset_defaults.items():
                st.session_state[k] = v
            go_to(1)
            st.rerun()

else:
    # Edge case: step 4 but no results
    go_to(1)
    st.rerun()

# ---------------------------------------------------------------------------
# FOOTER
# ---------------------------------------------------------------------------
st.markdown(
    """
<div class="footer"><b>CV Tailor</b> &nbsp;/&nbsp; Built with Streamlit, python-docx &amp; OpenRouter</div>
""",
    unsafe_allow_html=True,
)
