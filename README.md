# Course Outcomes & Assessment Studio

A Streamlit faculty workspace for syllabus preparation, Course Outcomes,
CO–PO/PSO mapping, examination-question analysis and question-paper preparation.
This Industrial Design HCI/UX research project makes AI suggestions, evidence,
professor corrections and approval decisions visible. It does not establish
classification accuracy, usability gains, student attainment or accreditation.

## Run locally

Use a supported Python environment with the packages in `requirements.txt`:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Open the local address printed by Streamlit, normally `http://localhost:8501`.
Embeddings load only when required. The first embedding operation may download
the configured sentence-transformer model and requires network access.

## Configuration

For local use, copy `.env.example` to `.env` and set your own key. The app reads
Streamlit Secrets first, then environment variables populated from `.env`:

```dotenv
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.5-flash-lite
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

`GOOGLE_API_KEY` is also accepted. Model IDs remain configurable; availability
and quota depend on your provider account. API credentials, model settings and
retrieval controls are under **Advanced Settings**. Without a saved key, a
password input supports the current session. Retrieval settings are displayed;
model names are configured at deployment rather than changed per session.
Manual preparation, editing,
validation and exports do not require Gemini.

Never commit `.env` or `.streamlit/secrets.toml`. Keep real credentials out of
course text and project files. JSON export excludes credentials, transient
objects and embedding caches. Secrets filename is `secrets.toml` (plural);
`config.yaml` is not a Streamlit secrets source.

## One-click presentation demo

Click **Load presentation demo** in the sidebar to fill all six workspace sections
and open a ready-to-present paper preview. No API key, model download or network
generation is needed. It includes:

- ID2103 Art & Aesthetics in Design, course metadata and three syllabus modules.
- Three staged approved COs and one draft to demonstrate individual review.
- Eleven illustrative POs, two PSOs, and a matrix with positive and unmapped
  relationships plus a staged professor override.
- Seven prepared question-analysis examples, including a final-label correction.
- A 30-mark paper containing six 5-mark questions, locked approved examples,
  two review items, syllabus quotations and draft answer/marking guides.
- Student/faculty PDF and DOCX export, CSV exports and project JSON saving.

All example suggestions and approvals are labelled as prepared demonstration data.
No classification accuracy, cosine similarity, measured confidence, official PO
wording or live AI execution is implied. Demo paper exports carry a demonstration
label. Normal generation/checking actions still require the configured models and
API key when explicitly requested.

**Restore previous work** returns to the project active before loading the demo;
reloading the demo does not overwrite that original in-session snapshot. Download
project JSON to retain work across browser/server sessions. The separate
**Load ID2103 sample course** action retains the original input-only research
sample and its manual outcome-approval workflow.
The ready-filled snapshot is also available at
`demo/ID2103_presentation_demo.json` for reuse through **Restore a saved project**.

## Faculty workflow

1. **Course & Syllabus**: enter the subject / course name and optional code and department/programme details,
   paste text or extract PDF/DOCX/TXT, then review editable module/topic portions.
   Heading detection supports any number of modules. You can correct headings
   and their source text. Empty extraction warns instead of implying OCR support.
2. **Course Outcomes**: enter outcomes manually or explicitly request syllabus-
   grounded drafts (five by default). Review Bloom suggestions, rationale and
   real syllabus references. Edit, add, remove, regenerate and approve individual
   drafts. Drafts stay separate from the approved set. Replacing an existing
   approved outcome requires a deliberate professor action.
3. **CO–PO / PSO Mapping**: configure reusable PO1–PO11 and departmental PSOs
   (initially PSO1/PSO2). Statements start empty because official institution
   wording has not been supplied. Enter meaningful statements and approve them
   before requesting corresponding AI mappings. Import/export configuration for
   reuse. Inspect suggested scores and justifications, edit final scores and
   approve/reject relationships. An unreviewed blank differs from approved 0
   (no demonstrated relationship). The scale is 0/—, 1 low, 2 medium, 3 high.
4. **Analyse Existing Questions**: enter question numbers, text and marks, or use
   uploaded-paper extraction as a copying aid. Run the existing RAG pipeline
   explicitly, inspect CO cosine similarities, retrieved evidence, confidence
   and LLM-run details, then correct final CO/Bloom labels and approve. Multiple
   Bloom levels are supported. Edits live in authoritative project state and
   survive navigation and reruns. Changed questions flag previous labels for
   review; approved CSV export validates final identifiers.
5. **Build Question Paper**: enter or confirm **Subject / course name** at the
   top of the page. The subject is shared with Course & Syllabus; use the direct
   setup buttons to add its syllabus and prepare or approve its outcomes.
   **CO means Course Outcome**, the skill students should demonstrate after
   studying the subject. Under **Course outcomes to assess**, select approved
   outcomes by their IDs and full statements, or explicitly choose all approved
   outcomes. Draft outcomes are never selected or approved automatically.
   The setup checklist explains missing inputs before AI generation is enabled.
   Acknowledging a marks mismatch confirms the structure; it does not complete
   subject setup. Then choose Mid-semester, End-semester or Custom, edit
   metadata, target total, covered portions, approved COs, Bloom targets and
   difficulty. Add/reorder sections and set counts/marks. Advanced section
   controls reveal any-K-of-N, adjacent either/or pairs, unequal marks and
   subquestions. Review marks before explicitly generating. Edit generated items,
   approve/lock them, manually replace failures or regenerate one unlocked item.
   Successful batches remain saved after partial failures. **Check generated
   questions** explicitly runs the original mapping pipeline; its suggestions
   stay separate from requested targets and professor final decisions.
6. **Review & Export**: inspect the paper, choice rules, actual attemptable marks
   and coverage, then download student/faculty PDF or editable DOCX, matrix and
   analysis CSV, or a JSON project snapshot. Student files exclude internal
   evidence, rationale, CO/Bloom labels and answer keys. Faculty files include
   review details; optional answers and marking guides are labelled drafts.

Backwards navigation preserves work. Session state lasts only as long as the
Streamlit session: **download project JSON to save work across sessions**, then
import it to restore. Imports validate the schema version, identifiers, references
and values. Source fingerprints flag affected downstream material for review
without silently discarding it. Review and reapprove stale material before use.
Changed and removed sources remain in the project's source history, so existing
quotations can still be inspected after a syllabus or outcome revision. Archived
sources cannot become new generation targets. Save structured tables and question
forms with their labelled buttons before leaving a section. Final analysis label
corrections save automatically in session memory; approval remains explicit.

## Marks and professor overrides

Marks are calculated in Python. For an equal-mark section:

| Quantity | Calculation |
|---|---|
| Printed marks | Printed question count × marks per question |
| Attemptable marks | Required attempts × marks per question |
| Either/or pair | One alternative contributes to attemptable total |
| Subquestions | Children must add to their parent total |

Any-K choices with unequal marks, or unequal either/or alternatives, retain the
minimum–maximum possible attemptable range. The application explains that the
student's choices affect the total; it does not report one misleading maximum.

The target is a faculty reference. For example, target 30 with five compulsory
5-mark questions prints and permits 25 marks. The workspace warns and offers
**Edit blueprint** or **Continue with this blueprint**. Continuing acknowledges
that exact blueprint, allows generation of five questions and prints actual
maximum 25 on the paper. It never silently adds questions or changes marks.
Six printed 5-mark questions with any five attempted print 30 marks but permit
25 marks. Four compulsory 10-mark questions permit 40 despite a target of 30.

Relevant blueprint changes invalidate the acknowledgment and require review
again. Overrides cannot bypass structural errors such as nonpositive marks,
invalid counts, attempts exceeding printed questions, malformed either/or groups
or subquestions whose marks do not add to the parent.

## AI and research methods

The Gemini REST request layer, configurable models, sentence-transformer
retrieval and confidence rules remain in `rag_pipeline.py`. Existing baselines
keep their separate APIs:

| Function | Role |
|---|---|
| `predict_co_similarity()` | Embedding similarity baseline; CO only |
| `predict_llm_only()` | LLM baseline without retrieved syllabus context |
| `predict_rag_llm()` | CO/Bloom analysis with retrieval and conditional repeated classification |

Classification selects only from the supplied valid CO list. CO drafting is a
separate explicit task. The RAG classifier normally asks once, requests another
opinion when retrieval disagrees or CO similarities are close, and uses at most
three classification runs. Confidence is High/Medium/Low, using retrieval gap
and agreement; agreement does not prove correctness.

CO drafting, matrix suggestions and paper generation use distinct JSON tasks,
bounded malformed-output retries and Python validation. Counts, marks, CO IDs,
Bloom labels and existing module/quotation references are checked. AI calls occur
only through explicit actions. Unavailable credentials, authentication, quota,
network errors and timeouts preserve work and report failures. No fabricated AI
fallback is substituted. Uploaded documents are reference data, not instructions
that may override application rules. Embedding caches are scoped to the session
and keyed by model identity/content; reusable model objects contain no course data.

## Exports and coverage

PDF and DOCX use the same ordered current-paper content and deterministic marks.
Long questions wrap through pages; PDF includes page numbers. DOCX uses A4,
fixed margins, headings that stay with following content and free-flowing question
paragraphs. The current blueprint determines numbering, alternatives and subquestion
marks. Obsolete retained question slots are excluded from the current paper.

Coverage distinguishes printed marks from the minimum marks guaranteed under
attempt rules. Optional questions do not imply that each student attempts every
printed CO/module/Bloom level. Multi-label coverage overlaps and is not student
attainment. Mapping exports preserve original AI suggestions separately from
approved final scores. Blank matrix values mean unapproved; explicit 0 means an
approved absence of demonstrated relationship. CSV spreadsheet-formula prefixes
are escaped as text.

`demo/exports/` contains synthetic long-paper PDF/DOCX QA samples, all-page and
first/middle/last contact sheets, long-URL stress files and an inspection note.
Recreate them with:

```powershell
python demo/create_export_samples.py
```

## Verification

```powershell
python -m compileall -q app.py ui_workspace.py project_state.py validation.py outcome_service.py paper_service.py export_utils.py
python -m unittest discover -s tests -v
```

Tests mock Gemini and cover configuration, structural marks, mismatch overrides,
dependency review, JSON round trips, malformed AI output, partial generation,
authoritative professor edits and PDF/DOCX content separation/wrapping. They do
not establish live model quality or research accuracy. The export geometry checks
inspect PDF text bounds and extract the final questions from multi-page documents.
DOCX structure is inspected with python-docx; visual Word pagination requires a
working desktop renderer and remains an environment-dependent manual check.

Use **Load ID2103 sample course** to exercise ID2103. Existing syllabus and paper
uploads remain in `demo/`; sample input is illustrative and not official PO/PSO
wording. A complete manual workflow is possible without a live Gemini key.

## Files

| File | Responsibility |
|---|---|
| `app.py` | Six-section Streamlit faculty workspace |
| `ui_workspace.py` | Course, outcome, matrix, analysis, blueprint, preview and review controls |
| `project_state.py` | Serializable schema, stable IDs, source dependencies, safe JSON import/export |
| `validation.py` | Marks, choice structures, identifiers and accepted-value validation |
| `outcome_service.py` | Syllabus-grounded CO drafts and matrix suggestions |
| `paper_service.py` | Batched questions, regeneration, duplicate checks, explicit analysis |
| `export_utils.py` | Student/faculty PDF/DOCX, CSV and choice-aware coverage |
| `rag_pipeline.py` | Original embeddings, retrieval, Gemini classification and research baselines |
| `document_utils.py` | PDF/DOCX/TXT extraction |
| `sample_data.py` | ID2103 illustrative inputs |
| `demo_project.py` | Complete, clearly labelled presentation fixtures without AI calls |
| `tests/` | Focused automated checks with mocked APIs |

## Streamlit Community Cloud

Deploy the GitHub repository `Gupta-027/RP_Project-`, branch `main`, with entrypoint
`app.py`. The deployment includes the complete workspace and the **Load presentation
demo** action. Choose Python 3.13 for a new deployment to match the tested local
runtime, or preserve an existing supported runtime when updating an existing app.

For an existing Community Cloud app linked to this branch, pushing the repository
update triggers its redeployment. For a new app, sign in at
<https://share.streamlit.io>, choose **Create app**, select the repository, branch
and entrypoint above, then choose **Deploy**. The public URL is assigned by
Streamlit; localhost preview URLs are not public deployments.

Configure model names and API keys in the app's **Settings → Secrets**, using
`GEMINI_API_KEY` (or `GOOGLE_API_KEY`), optional `GEMINI_MODEL`, and optional
`EMBEDDING_MODEL`. Existing cloud secrets should remain in the hosting account.
The presentation demo and manual preparation/export workflow work without a key;
live AI actions require a valid key and provider access. Local `.env` and secrets
files must never be uploaded to GitHub.

Deploy `app.py` with `requirements.txt`. The verified Streamlit release is pinned
to keep the hosted widget behavior consistent. Keep the CPU-oriented torch installation settings
for lightweight deployment. The smaller default embedding model avoids requiring
GPU infrastructure. No database or additional export service is required.

## Limitations

- AI output requires professor review. It may be incomplete, unsuitable in scope
  or wrong even when retrieved evidence and repeated runs agree.
- PDF extraction handles embedded text. Scanned/image-only files need external
  OCR; this application does not implement OCR. Question splitting remains manual.
- Heading detection is heuristic. Review module boundaries and ensure quoted
  source text actually belongs to the syllabus.
- Duplicate detection flags exact and likely similarities; it cannot prove two
  questions assess the same skill or detect every paraphrase.
- Generated numerical/scenario questions and draft marking guides still require
  faculty verification for solvability, fairness and mark allocation.
- JSON snapshots provide explicit local saving, without accounts, shared editing
  or a durable server database. Keep downloaded research/course data appropriately.
- Provider model availability, quotas and network access can change. Automated
  checks use mocks; a live Gemini end-to-end run is a separate verification step.
- Custom institution layouts may need further formatting. Inspect exported files
  in your actual PDF viewer and DOCX editor before distributing a paper.
