"""Course Outcomes & Assessment Studio: Streamlit entry point."""
import os
from copy import deepcopy
import streamlit as st
from dotenv import load_dotenv
import rag_pipeline as rag
from project_state import new_project, refresh_dependencies, export_project, import_project
from ui_workspace import PAGES, render_page, load_demo
from demo_project import build_presentation_demo

load_dotenv()
st.set_page_config(page_title="Course Outcomes & Assessment Studio", page_icon="📘", layout="wide")


def get_setting(name, default=""):
    """Read Cloud secrets first, with environment fallback."""
    try:
        value = st.secrets.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    except FileNotFoundError:
        pass
    return os.getenv(name, "").strip() or default


rag.GEMINI_MODEL = get_setting("GEMINI_MODEL", rag.GEMINI_MODEL)
rag.EMBEDDING_MODEL_NAME = get_setting("EMBEDDING_MODEL", rag.EMBEDDING_MODEL_NAME)
st.session_state.setdefault("project", new_project())
st.session_state.setdefault("ui_epoch", 0)


def replace_project(project):
    st.session_state.project = project
    st.session_state.ui_epoch += 1
    st.session_state.pop("embedding_cache", None)
    st.session_state.pop("export_buffers", None)
    for transient in ("generation_failures", "generation_notice", "extracted_questions"):
        st.session_state.pop(transient, None)


def load_presentation_project():
    previous = st.session_state.project
    if not previous.get("presentation_demo"):
        st.session_state.work_before_demo = deepcopy(previous)
        st.session_state.page_before_demo = st.session_state.get("workspace_page", PAGES[0])
    replace_project(build_presentation_demo())
    st.session_state.workspace_page = PAGES[5]


def restore_work_before_demo():
    previous = st.session_state.pop("work_before_demo", None)
    if previous is not None:
        replace_project(previous)
        previous_page = st.session_state.pop("page_before_demo", PAGES[0])
        st.session_state.workspace_page = previous_page if previous_page in PAGES else PAGES[0]


def show_course_context(placeholder, project):
    with placeholder.container():
        st.write(project["course"].get("name") or project["course"].get("code") or "No subject selected")
        st.caption(project["course"].get("code") or "Enter the subject in Course & Syllabus or at the top of Build Question Paper.")


with st.sidebar:
    st.subheader("Assessment Studio")
    p = st.session_state.project
    course_context = st.empty()
    show_course_context(course_context, p)
    page = st.radio("Workspace", PAGES, key="workspace_page")
    st.divider()
    ready = sum(c.get("status") == "approved" for c in p["approved_cos"])
    pending = sum(q.get("status") != "approved" for q in p["paper_questions"])
    st.caption(f"{len(p['modules'])} modules · {ready} approved COs\n\n{pending} paper items need review")
    st.button("Load presentation demo", type="primary", width="stretch", on_click=load_presentation_project,
        help="Fills all six sections, opens a complete paper preview, and keeps your current project for Restore previous work.")
    st.caption("Complete 30-mark sample paper. No API key needed.")
    if "work_before_demo" in st.session_state:
        st.button("Restore previous work", width="stretch", on_click=restore_work_before_demo)
    if st.button("Load ID2103 sample course", width="stretch", help="Input-only sample. Its CO drafts still need professor approval."):
        replace_project(load_demo())
        st.rerun()
    with st.expander("Restore a saved project"):
        uploaded = st.file_uploader("Project JSON", type=["json"], key="project_upload")
        if st.button("Import project", disabled=uploaded is None):
            try:
                restored = import_project(uploaded.getvalue().decode("utf-8"))
                replace_project(restored)
                st.rerun()
            except (ValueError, TypeError, UnicodeError, KeyError) as error:
                st.error(f"Project was not imported: {error}")
    project_download = st.empty()
    with st.expander("Advanced Settings"):
        api_key = get_setting("GEMINI_API_KEY") or get_setting("GOOGLE_API_KEY")
        if api_key:
            st.success("Gemini API key loaded")
        else:
            st.warning("No Gemini API key found")
            api_key = st.text_input("Gemini API key", type="password", key="runtime_api_key")
        st.caption("Credentials stay outside the project and all downloads.")
        st.write(f"LLM: `{rag.GEMINI_MODEL}`")
        st.write(f"Embeddings: `{rag.EMBEDDING_MODEL_NAME}`")
        st.write(f"Retrieved syllabus chunks: {rag.TOP_K_CHUNKS}")
        st.write(f"Classification: 1 run; up to {rag.MAX_LLM_RUNS} if uncertain")
        st.caption("Configure GEMINI_MODEL and EMBEDDING_MODEL through .env or Streamlit Secrets. Models load only when an explicit action needs them.")
    st.caption("Download project JSON to save across sessions. Session memory is temporary.")

st.caption("COURSE OUTCOMES & ASSESSMENT STUDIO")
p = st.session_state.project
if p.get("presentation_demo"):
    st.info("Presentation demo: prewritten examples with staged approvals and suggestions. The pre-filled data was prepared without live AI calls. PO/PSO wording is illustrative, not official.")
    with st.expander("Suggested presentation tour"):
        st.markdown("1. Show the subject and three syllabus modules in **Course & Syllabus**.\n"
                    "2. In **Course Outcomes**, compare three staged approvals with one draft.\n"
                    "3. Show positive and unmapped relationships, plus a staged professor override, in **CO–PO / PSO Mapping**.\n"
                    "4. In **Analyse Existing Questions**, show the prepared labels and a professor correction. These are examples, not measured predictions.\n"
                    "5. In **Build Question Paper**, review six 5-mark questions, locked items, a disagreement and a draft marking guide. Change the printed count to five to demonstrate the 25-versus-30 marks warning.\n"
                    "6. Return to **Review & Export** to prepare student/faculty PDF and DOCX files.")
refresh_dependencies(p)
render_page(page, p, api_key)
refresh_dependencies(p)
show_course_context(course_context, p)
with project_download:
    st.download_button("Save project JSON", export_project(p), "assessment_project.json", "application/json", width="stretch")
