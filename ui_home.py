"""Institutional project cover and accessible entry points to the faculty workspace."""
import base64
from html import escape
from pathlib import Path

import streamlit as st

HOME_PAGE = "Project overview"
PROJECT_TITLE = "Course Outcomes & Assessment Studio"
AUTHOR_NAME = "Gupta Prasad Adhikari"
ROLL_NUMBER = "123ID0885"
SUPERVISOR = "Prof. B.B.V.L. Deepak"
DEPARTMENT = "Department of Industrial Design"
INSTITUTE = "National Institute of Technology Rourkela"
LOGO_PATH = Path(__file__).resolve().parent / "assets" / "nit_rourkela_logo.png"

MODULE_COPY = [
    ("Course context", "Set the subject, review the syllabus and choose the topics you teach."),
    ("Learning goals", "Draft measurable outcomes, refine their wording and approve the final set."),
    ("Programme alignment", "Review CO–PO and PSO relationships with evidence and final faculty decisions."),
    ("Question analysis", "Inspect existing questions, compare suggestions and correct the final labels."),
    ("Paper preparation", "Choose portions, outcomes and marks, then prepare and review question drafts."),
    ("Final review", "Preview the paper, inspect coverage and download student and faculty versions."),
]


def page_styles():
    """Style only our markup and documented, app-owned container-key classes."""
    cards = ",".join(f".st-key-overview_module_{i}" for i in range(6))
    hover = ",".join(f".st-key-overview_module_{i}:hover" for i in range(6))
    focus = ",".join(f".st-key-overview_module_{i}:focus-within" for i in range(6))
    titles = ",".join(f".st-key-overview_module_{i} h3" for i in range(6))
    return f"""<style>
    .nitr-brand {{ display:flex; align-items:center; gap:20px; margin:0 0 26px; }}
    .nitr-brand img {{ width:84px; height:auto; flex-shrink:0; }}
    .nitr-institute {{ font-size:1.24rem; font-weight:600; color:#14283E; line-height:1.35; margin:0 0 5px; }}
    .nitr-department {{ font-size:1rem; color:#52647A; margin:0; line-height:1.5; }}
    .st-key-project_intro {{ box-sizing:border-box; padding:28px 32px; border:1px solid #E1E7EF; border-top:4px solid #2A6BD4; border-radius:18px; background:#F4F7FC; }}
    .st-key-project_intro h1 {{ color:#14283E; font-size:clamp(2rem,3.4vw,3.15rem); line-height:1.13; font-weight:600; letter-spacing:-0.025em; text-wrap:balance; max-width:850px; padding-top:0; }}
    .nitr-eyebrow {{ font-size:.75rem; letter-spacing:.1em; font-weight:600; color:#335E9C; margin:0 0 8px; }}
    .nitr-project-subtitle {{ color:#334B66; font-size:1.15rem; line-height:1.55; max-width:760px; margin:0 0 6px; }}
    .nitr-project-description {{ color:#52647A; font-size:1rem; line-height:1.6; max-width:780px; margin:0 0 16px; }}
    .st-key-overview_author, .st-key-overview_supervisor {{ box-sizing:border-box; padding:21px 23px; border-radius:12px; background:#FFFFFF; border:1px solid #E1E7EF; }}
    .nitr-detail-label {{ font-size:.72rem; letter-spacing:.09em; font-weight:600; color:#52647A; margin:0 0 9px; }}
    .nitr-person {{ color:#14283E; font-size:1.24rem; font-weight:600; line-height:1.4; margin:0 0 7px; overflow-wrap:break-word; }}
    .nitr-person-detail {{ color:#52647A; font-size:.94rem; line-height:1.5; margin:0; }}
    .nitr-person-detail strong {{ color:#27415F; font-weight:600; letter-spacing:.025em; }}
    {cards} {{ box-sizing:border-box; min-width:0; padding:20px; border-radius:12px; border:1px solid #E1E7EF; background:#FFFFFF; transition:border-color .16s ease, box-shadow .16s ease; }}
    {hover}, {focus} {{ border-color:#2A6BD4; box-shadow:0 5px 18px rgba(30,68,112,.07); }}
    {titles} {{ color:#14283E; font-size:1.15rem; font-weight:600; line-height:1.4; min-height:3.2rem; padding-top:0; padding-bottom:8px; }}
    .nitr-module-meta {{ display:flex; align-items:center; gap:10px; margin-bottom:12px; }}
    .nitr-module-number {{ display:inline-flex; align-items:center; justify-content:center; width:29px; height:29px; background:#EDF3FC; border-radius:7px; color:#245DB2; font-size:.78rem; font-weight:600; font-variant-numeric:tabular-nums; }}
    .nitr-module-category {{ font-size:.75rem; letter-spacing:.025em; color:#52647A; }}
    .nitr-module-description {{ font-size:.95rem; line-height:1.55; color:#52647A; min-height:4.5rem; margin:0 0 13px; }}
    .nitr-overview-footer {{ color:#52647A; font-size:.86rem; line-height:1.6; margin:26px 0 6px; }}
    @media(max-width:640px) {{
      .nitr-brand {{ gap:14px; margin-bottom:20px; align-items:center; }}
      .nitr-brand img {{ width:64px; }}
      .nitr-institute {{ font-size:1.02rem; }}
      .nitr-department {{ font-size:.88rem; }}
      .st-key-project_intro {{ padding:21px 18px; border-radius:14px; }}
      .st-key-project_intro h1 {{ font-size:2rem; line-height:1.16; }}
      .nitr-project-subtitle {{ font-size:1.04rem; }}
      .st-key-overview_author, .st-key-overview_supervisor {{ padding:18px; }}
      .nitr-person {{ font-size:1.15rem; }}
      .nitr-module-description {{ min-height:0; }}
      {titles} {{ min-height:0; }}
    }}
    @media(prefers-reduced-motion:reduce) {{ {cards} {{ transition:none; }} }}
    </style>"""


def render_home(project, pages, navigate, load_demo):
    """Present the author and research context without changing project data."""
    st.markdown(page_styles(), unsafe_allow_html=True)
    encoded_logo = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    st.markdown(f"""<div class="nitr-brand">
        <img src="data:image/png;base64,{encoded_logo}" width="84" height="82"
             alt="National Institute of Technology Rourkela emblem">
        <div><p class="nitr-institute">{escape(INSTITUTE)}</p>
        <p class="nitr-department">{escape(DEPARTMENT)}</p></div>
        </div>""", unsafe_allow_html=True)

    with st.container(key="project_intro"):
        st.markdown('<p class="nitr-eyebrow">RESEARCH PROJECT · INDUSTRIAL DESIGN</p>', unsafe_allow_html=True)
        st.title(PROJECT_TITLE)
        st.markdown('<p class="nitr-project-subtitle">AI-assisted Course Outcome mapping, Bloom’s Taxonomy analysis and question-paper preparation.</p>', unsafe_allow_html=True)
        st.markdown('<p class="nitr-project-description">Prepare outcomes, review AI suggestions and build assessments with the professor in control.</p>', unsafe_allow_html=True)
        a, b = st.columns(2)
        a.button("Enter faculty workspace", type="primary", width="stretch", on_click=navigate, args=(pages[0],), key="overview_enter")
        b.button("Load presentation demo", width="stretch", on_click=load_demo, key="overview_demo",
                 help="Fill all six modules with prepared examples and open the paper preview. No API key is needed.")

    author, guide = st.columns(2, gap="medium")
    with author:
        with st.container(border=False, key="overview_author"):
            st.markdown(f"""<p class="nitr-detail-label">PRESENTED BY</p>
                <p class="nitr-person">{escape(AUTHOR_NAME)}</p>
                <p class="nitr-person-detail">Roll number · <strong>{escape(ROLL_NUMBER)}</strong></p>""", unsafe_allow_html=True)
    with guide:
        with st.container(border=False, key="overview_supervisor"):
            st.markdown(f"""<p class="nitr-detail-label">UNDER THE GUIDANCE OF</p>
                <p class="nitr-person">{escape(SUPERVISOR)}</p>
                <p class="nitr-person-detail">Supervisor · {escape(DEPARTMENT)}</p>""", unsafe_allow_html=True)

    if project.get("presentation_demo"):
        st.info("A presentation demo is loaded. Its approvals and suggestions are prepared examples; programme-outcome wording is illustrative.")
    if project["course"].get("name", "").strip():
        code = project["course"].get("code", "").strip()
        st.caption(f"Active subject: {project['course']['name']}" + (f" · {code}" if code else ""))

    st.header("Explore the workspace")
    st.write("Open any module below. Your saved work stays available as you move between sections.")
    for offset in (0, 3):
        columns = st.columns(3, gap="medium")
        for index, column in enumerate(columns, start=offset):
            category, description = MODULE_COPY[index]
            with column:
                with st.container(border=False, key=f"overview_module_{index}"):
                    st.markdown(f'<div class="nitr-module-meta"><span class="nitr-module-number">{index + 1:02d}</span><span class="nitr-module-category">{escape(category)}</span></div>', unsafe_allow_html=True)
                    st.subheader(pages[index])
                    st.markdown(f'<p class="nitr-module-description">{escape(description)}</p>', unsafe_allow_html=True)
                    st.button(f"Open {pages[index]}", width="stretch", on_click=navigate, args=(pages[index],), key=f"overview_open_{index}")
    st.markdown('<p class="nitr-overview-footer">A research prototype from the Department of Industrial Design, NIT Rourkela. AI suggestions remain subject to professor review and approval.</p>', unsafe_allow_html=True)
