"""
Single page Streamlit application for the research project:
Automatic Course Outcome and Bloom's Taxonomy Level Detection from
Examination Questions using RAG and LLM.

The professor enters the course, the Course Outcomes, the syllabus and the
questions. The app suggests a CO and Bloom level for every question, and the
professor makes the final decision.
"""

import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

import rag_pipeline as rag
from document_utils import clean_text, extract_text

load_dotenv()

st.set_page_config(page_title="CO and Bloom Level Detection", layout="wide")


def get_setting(name, default=""):
    """
    Read a setting from Streamlit Secrets when the app runs on Streamlit Cloud,
    and from the .env file when it runs on a laptop.
    """
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass  # no secrets file at all, which is normal when running locally
    return os.getenv(name, default)


# Let the deployed app override the two model names without editing the code.
rag.GEMINI_MODEL = get_setting("GEMINI_MODEL", rag.GEMINI_MODEL)
rag.EMBEDDING_MODEL_NAME = get_setting("EMBEDDING_MODEL", rag.EMBEDDING_MODEL_NAME)

# Keep the whole interface white. The theme is set in .streamlit/config.toml,
# and this small style block covers the few areas Streamlit shades by default.
st.markdown(
    """
    <style>
      .stApp, section[data-testid="stSidebar"], header[data-testid="stHeader"],
      div[data-testid="stBottomBlockContainer"] { background-color: #FFFFFF; }
      section[data-testid="stSidebar"] { border-right: 1px solid #E4E4E4; }
      div[data-testid="stExpander"], div[data-testid="stAlert"],
      div[data-testid="stFileUploaderDropzone"] { background-color: #FFFFFF; }
      div[data-testid="stFileUploaderDropzone"] { border: 1px dashed #CCCCCC; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Automatic CO and Bloom's Taxonomy Level Detection")
st.caption(
    "Research prototype - the system suggests a Course Outcome and Bloom level "
    "for each examination question. The professor is the final authority."
)


# ----------------------------------------------------------------------
# Sample data used for testing (input data only, no expected answers)
# ----------------------------------------------------------------------

SAMPLE_COURSE_CODE = "ID2103"
SAMPLE_COURSE_NAME = "Art & Aesthetics in Design"

SAMPLE_COS = [
    ["CO1", "Explain fundamental concepts and principles related to art, aesthetics and design quality."],
    ["CO2", "Interpret and evaluate art in relation to identity, emotion and individual human experience."],
    ["CO3", "Analyze the relationship between art, design, society and everyday life."],
]

SAMPLE_SYLLABUS = """Unit 1: Foundations of Art, Aesthetics and Design Quality
Introduction to art and aesthetics. Definition of beauty, form and proportion.
Elements and principles of design: line, shape, colour, texture, balance, rhythm,
contrast and unity. The Design Quality Triangle and its three primary components,
namely aesthetics, function and usability. How the three components are balanced
against each other in a product, and how a change in one component affects the
others. Examples from everyday consumer products such as furniture, mobile phones
and televisions.

Unit 2: Art, Identity and Human Experience
Art as a medium of personal expression. How personal identity, memory, emotion and
lived experience are communicated through painting, sculpture, photography, music
and performance. Interpretation of an artwork by the viewer. Subjectivity of taste.
Why certain artworks remain valued across generations while artistic trends change.
Criteria used to judge artistic merit, originality and craftsmanship.

Unit 3: Art, Design and Society
Art as a mirror and as a transformative force in society. Art movements and social
change. Design and culture, tradition and modernity. Public art, craft traditions
and everyday objects. The role of art in questioning social norms, creating social
awareness and shaping public opinion. Ethics and responsibility of the designer
towards society and the environment.
"""

SAMPLE_QUESTIONS = [
    ["1(a)", "Explain the three primary components of the Design Quality Triangle.", 3],
    ["1(b)", "Discuss how they interact with each other in the context of product design with reference to a smart television.", 5],
    ["2(a)", "Explore how personal identity, emotions, and individual experiences are communicated through different forms of art.", 4],
    ["2(b)", "Why are some artworks revered across generations regardless of changing artistic trends?", 4],
    ["3(a)", "Critically analyze how art acts as a transformative force in society by challenging norms and promoting social awareness.", 4],
]


# ----------------------------------------------------------------------
# Session state
# ----------------------------------------------------------------------

def init_state():
    defaults = {
        "course_code": "",
        "course_name": "",
        "co_table": pd.DataFrame(
            [["CO1", ""], ["CO2", ""], ["CO3", ""]],
            columns=["CO ID", "CO Statement"],
        ),
        "syllabus_text": "",
        "question_table": pd.DataFrame(
            [["", "", 0]], columns=["Question Number", "Question", "Marks"]
        ),
        "results": None,
        "details": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def load_sample_data():
    st.session_state.course_code = SAMPLE_COURSE_CODE
    st.session_state.course_name = SAMPLE_COURSE_NAME
    st.session_state.co_table = pd.DataFrame(SAMPLE_COS, columns=["CO ID", "CO Statement"])
    st.session_state.syllabus_text = SAMPLE_SYLLABUS
    st.session_state.question_table = pd.DataFrame(
        SAMPLE_QUESTIONS, columns=["Question Number", "Question", "Marks"]
    )
    st.session_state.results = None
    st.session_state.details = []


init_state()


# Loading the sentence-transformer takes a few seconds, so cache it.
@st.cache_resource(show_spinner="Loading the sentence-transformer model...")
def get_embedding_model():
    return rag.load_embedding_model()


# ----------------------------------------------------------------------
# Sidebar - settings
# ----------------------------------------------------------------------

with st.sidebar:
    st.header("Settings")

    api_key = get_setting("GEMINI_API_KEY")
    if api_key:
        st.success("Gemini API key loaded")
    else:
        st.warning("No Gemini API key found")
        api_key = st.text_input("Gemini API key", type="password")

    st.write("Embedding model: `%s`" % rag.EMBEDDING_MODEL_NAME)
    st.write("LLM: `%s`" % rag.GEMINI_MODEL)
    st.write("Syllabus chunks retrieved: %d" % rag.TOP_K_CHUNKS)
    st.write("LLM runs per question: 1, up to %d if unsure" % rag.MAX_LLM_RUNS)
    st.caption(
        "You enter each question once. The system asks the LLM once, and asks "
        "again (at most %d times in total) only when that answer disagrees with "
        "the semantic retrieval or the COs are too close to separate."
        % rag.MAX_LLM_RUNS
    )

    st.divider()
    if st.button("Load sample course data"):
        load_sample_data()
        st.rerun()


# ----------------------------------------------------------------------
# 1. Course details
# ----------------------------------------------------------------------

st.header("1. Course details")

col1, col2 = st.columns(2)
with col1:
    st.session_state.course_code = st.text_input(
        "Course Code", value=st.session_state.course_code, placeholder="ID2103"
    )
with col2:
    st.session_state.course_name = st.text_input(
        "Course Name", value=st.session_state.course_name,
        placeholder="Art & Aesthetics in Design",
    )


# ----------------------------------------------------------------------
# 2. Course outcomes
# ----------------------------------------------------------------------

st.header("2. Course Outcomes")
st.caption("The AI can only choose from these COs. It is never allowed to invent a new one.")

co_table = st.data_editor(
    st.session_state.co_table,
    num_rows="dynamic",
    width="stretch",
    key="co_editor",
    column_config={
        "CO ID": st.column_config.TextColumn("CO ID", width="small", required=True),
        "CO Statement": st.column_config.TextColumn("CO Statement", width="large"),
    },
)
st.session_state.co_table = co_table


def get_course_outcomes():
    """Read the CO table as a list of (co_id, statement), skipping empty rows."""
    outcomes = []
    for _, row in st.session_state.co_table.iterrows():
        co_id = str(row["CO ID"]).strip().upper().replace(" ", "")
        statement = str(row["CO Statement"]).strip()
        if co_id and co_id.lower() != "nan" and statement and statement.lower() != "nan":
            outcomes.append((co_id, statement))
    return outcomes


# ----------------------------------------------------------------------
# 3. Syllabus
# ----------------------------------------------------------------------

st.header("3. Syllabus")

syllabus_file = st.file_uploader(
    "Upload the syllabus (PDF / DOCX / TXT), or paste it below",
    type=["pdf", "docx", "txt"],
    key="syllabus_upload",
)

if syllabus_file is not None:
    if st.button("Extract text from the uploaded syllabus"):
        text, error = extract_text(syllabus_file)
        if error:
            st.error(error)
        else:
            st.session_state.syllabus_text = clean_text(text)
            st.success("Extracted %d characters." % len(st.session_state.syllabus_text))

st.session_state.syllabus_text = st.text_area(
    "Syllabus text (check it before analysing)",
    value=st.session_state.syllabus_text,
    height=220,
)

if st.session_state.syllabus_text.strip():
    preview_chunks = rag.chunk_syllabus(st.session_state.syllabus_text)
    st.caption("The syllabus will be split into %d chunk(s) for retrieval." % len(preview_chunks))


# ----------------------------------------------------------------------
# 4. Questions
# ----------------------------------------------------------------------

st.header("4. Examination questions")
st.caption(
    "The questions are written by the professor. The system does not generate questions."
)

with st.expander("Optional: upload a question paper and copy the text"):
    paper_file = st.file_uploader(
        "Question paper (PDF / DOCX / TXT)", type=["pdf", "docx", "txt"], key="paper_upload"
    )
    if paper_file is not None and st.button("Extract question paper text"):
        text, error = extract_text(paper_file)
        if error:
            st.error(error)
        else:
            st.text_area("Extracted text", value=clean_text(text), height=250)
            st.info(
                "Automatic question splitting is not reliable enough for a research "
                "prototype, so please copy the questions into the table below."
            )

question_table = st.data_editor(
    st.session_state.question_table,
    num_rows="dynamic",
    width="stretch",
    key="question_editor",
    column_config={
        "Question Number": st.column_config.TextColumn("Question Number", width="small"),
        "Question": st.column_config.TextColumn("Question", width="large"),
        "Marks": st.column_config.NumberColumn("Marks", min_value=0, step=1, width="small"),
    },
)
st.session_state.question_table = question_table


def get_questions():
    """Read the question table, skipping rows with no question text."""
    questions = []
    for i, row in st.session_state.question_table.iterrows():
        text = str(row["Question"]).strip()
        if not text or text.lower() == "nan":
            continue
        number = str(row["Question Number"]).strip()
        if not number or number.lower() == "nan":
            number = str(i + 1)
        marks = row["Marks"]
        marks = 0 if pd.isna(marks) else int(marks)
        questions.append({"number": number, "text": text, "marks": marks})
    return questions


# ----------------------------------------------------------------------
# 5. Analysis
# ----------------------------------------------------------------------

st.header("5. Analyse the questions")


def run_analysis(course_outcomes, questions, syllabus_text, api_key):
    """Run the RAG + LLM pipeline on every question and return the result rows."""
    get_embedding_model()  # make sure the model is loaded before the loop

    co_texts = ["%s: %s" % (co_id, text) for co_id, text in course_outcomes]
    co_embeddings = rag.embed_texts(co_texts)

    chunks = rag.chunk_syllabus(syllabus_text)
    chunk_embeddings = rag.embed_texts(chunks) if chunks else []

    rows = []
    details = []
    progress = st.progress(0.0, text="Analysing questions...")

    for i, question in enumerate(questions):
        result = rag.predict_rag_llm(
            question["text"], question["marks"], st.session_state.course_name,
            course_outcomes, co_embeddings, chunks, chunk_embeddings,
            api_key=api_key,
        )

        bloom = ", ".join(result["bloom_levels"])
        rows.append({
            "Question Number": question["number"],
            "Question": question["text"],
            "Marks": question["marks"],
            "Suggested CO": result["co"],
            "Suggested BL": bloom,
            "Topic": result["topic"],
            "Confidence": result["confidence"],
            "Reason": result["reason"] if not result["error"] else result["error"],
            "Final CO": result["co"],
            "Final BL": bloom,
        })
        details.append({"question": question, "result": result})

        progress.progress((i + 1) / len(questions), text="Analysing question %d of %d" % (i + 1, len(questions)))

    progress.empty()
    return pd.DataFrame(rows), details


if st.button("Analyze Questions", type="primary"):
    course_outcomes = get_course_outcomes()
    questions = get_questions()

    if not course_outcomes:
        st.error("Please enter at least one Course Outcome.")
    elif not questions:
        st.error("Please enter at least one question.")
    elif not api_key:
        st.error("A Gemini API key is required. Add it to .env or in the sidebar.")
    else:
        if not st.session_state.syllabus_text.strip():
            st.warning("No syllabus entered, so retrieval will run without syllabus context.")
        with st.spinner("Running the pipeline. Uncertain questions are checked "
                        "again, so this can take a while..."):
            results, details = run_analysis(
                course_outcomes, questions, st.session_state.syllabus_text, api_key,
            )
        st.session_state.results = results
        st.session_state.details = details


# ----------------------------------------------------------------------
# 6. Results and professor correction
# ----------------------------------------------------------------------

if st.session_state.results is not None:
    st.header("6. Results")
    st.caption("Edit the Final CO and Final BL columns if you disagree with the suggestion.")

    co_ids = [co_id for co_id, _ in get_course_outcomes()]

    edited = st.data_editor(
        st.session_state.results,
        width="stretch",
        key="results_editor",
        disabled=["Question Number", "Question", "Marks", "Suggested CO",
                  "Suggested BL", "Topic", "Confidence", "Reason"],
        column_config={
            "Question": st.column_config.TextColumn("Question", width="large"),
            "Reason": st.column_config.TextColumn("Reason", width="medium"),
            "Final CO": st.column_config.SelectboxColumn(
                "Final CO", options=co_ids, required=False, width="small"
            ),
            "Final BL": st.column_config.TextColumn(
                "Final BL", help="One or more levels, for example: L3, L4", width="small"
            ),
        },
    )

    # Show the retrieval evidence so the pipeline is transparent during the viva.
    with st.expander("Show retrieval evidence (CO similarity and syllabus chunks)"):
        for item in st.session_state.details:
            st.markdown("**%s** - %s" % (item["question"]["number"], item["question"]["text"]))
            ranking = item["result"]["co_ranking"]
            if ranking:
                st.write("CO cosine similarity: " + "  |  ".join(
                    "%s = %.3f" % (co_id, score) for co_id, score in ranking
                ))
            chunks = item["result"]["syllabus_chunks"]
            for j, (chunk, score) in enumerate(chunks):
                st.caption("Chunk %d (similarity %.3f): %s" % (j + 1, score, chunk[:300]))
            total = item["result"]["total_votes"]
            if total:
                if total == 1:
                    st.write("LLM runs: 1 (the first answer agreed with retrieval, "
                             "so no re-check was needed)")
                else:
                    st.write("LLM runs: %d (re-checked because the first answer was "
                             "uncertain) - %d of %d chose %s" % (
                                 total, item["result"]["votes_for_co"], total,
                                 item["result"]["co"]))
            if item["result"]["error"]:
                st.error(item["result"]["error"])
            st.divider()

    # CSV export of the final, professor approved mapping.
    export = edited[["Question Number", "Question", "Marks", "Final CO", "Final BL"]].copy()
    export = export.rename(columns={"Final CO": "Final CO", "Final BL": "Final Bloom Level"})

    st.download_button(
        "Download Final Results as CSV",
        data=export.to_csv(index=False).encode("utf-8"),
        file_name="co_bloom_mapping_%s.csv" % (st.session_state.course_code or "course"),
        mime="text/csv",
    )
