"""Native Streamlit views; the versioned project holds authoritative edits."""
from copy import deepcopy
import json
import math
import re
import pandas as pd
import streamlit as st
import rag_pipeline as rag
import outcome_service as outcomes
import paper_service as papers
import export_utils as exports
from document_utils import clean_text, extract_text
from project_state import (new_project, new_id, derive_modules, approved_cos, fingerprint,
    refresh_dependencies, source_fingerprint, import_programme_config, export_programme_config)
from validation import (validate_blueprint, calculate_marks, acknowledge_blueprint,
    can_generate, build_slots, validate_final_analysis, validate_matrix_cell)
from sample_data import (SAMPLE_COURSE_CODE, SAMPLE_COURSE_NAME, SAMPLE_COS,
                         SAMPLE_SYLLABUS, SAMPLE_QUESTIONS)

PAGES = ["Course & Syllabus", "Course Outcomes", "CO–PO / PSO Mapping",
         "Analyse Existing Questions", "Build Question Paper", "Review & Export"]
BLOOMS = ["L1", "L2", "L3", "L4", "L5", "L6"]


def key(name):
    return f"{st.session_state.get('ui_epoch', 0)}:{name}"


def reset_widgets():
    st.session_state.ui_epoch = st.session_state.get("ui_epoch", 0) + 1
    st.rerun()


def navigate_to(page):
    """Button callback runs before sidebar navigation is rendered again."""
    st.session_state.workspace_page = page


def text_field(obj, field, label, prefix="", area=False, **kwargs):
    method = st.text_area if area else st.text_input
    obj[field] = method(label, value=obj.get(field, ""), key=key(prefix + field), **kwargs)


def split_ids(value):
    return list(dict.fromkeys(v.strip() for v in re.split(r"[,;\n]", str(value or "")) if v.strip()))


def joined(value):
    return ", ".join(str(v) for v in value) if isinstance(value, list) else str(value or "")


def rows(frame):
    return frame.astype(object).where(pd.notna(frame), None).to_dict("records")


def task(callback):
    try:
        with st.spinner("Preparing suggestions. Saved work is retained…"):
            return callback()
    except (ValueError, RuntimeError, TypeError, KeyError) as error:
        st.error(str(error))
        return None
    except (ImportError, OSError):
        st.error("The local embedding model is unavailable. Check the installation and model download access, then retry. Saved work is retained.")
        return None


def load_demo():
    p = new_project()
    p["course"].update(code=SAMPLE_COURSE_CODE, name=SAMPLE_COURSE_NAME)
    p["syllabus"] = SAMPLE_SYLLABUS
    p["modules"] = derive_modules(SAMPLE_SYLLABUS)
    p["co_drafts"] = [{"id": cid, "statement": statement, "module_ids": [p["modules"][i]["id"]],
        "bloom_levels": [], "rationale": "Illustrative sample; professor review required.",
        "evidence": [], "status": "draft", "origin": "sample"}
        for i, (cid, statement) in enumerate(SAMPLE_COS)]
    p["analysis_questions"] = [{"id": new_id("AQ"), "number": n, "text": t, "marks": m}
                               for n, t, m in SAMPLE_QUESTIONS]
    refresh_dependencies(p)
    return p


def evidence_view(evidence, p):
    modules = {m["id"]: m for m in p["modules"]}
    if not evidence:
        st.caption("No supporting quotation recorded. Review the source before approval.")
    for item in evidence:
        if isinstance(item, dict):
            mid = item.get("module_id", "")
            source = modules.get(mid, {})
            quote = item.get("quote", "")
            historical = bool(quote and quote not in source.get("text", ""))
            if historical:
                source = next((m for m in p.get("retired_sources", {}).get("modules", [])
                               if m["id"] == mid and quote in m.get("text", "")), source)
            st.caption(f"{mid} · {source.get('title', 'Source no longer available')}{' · historical source' if historical else ''}")
            st.text(item.get("quote", ""))


def render_page(page, p, api_key):
    st.title(page)
    dict(zip(PAGES, [course_page, outcomes_page, matrix_page, analysis_page, paper_page, review_page]))[page](p, api_key)


def course_page(p, api_key):
    st.write("Enter the subject for your question paper, check its syllabus, and organise the portions you teach.")
    a, b = st.columns([1, 2])
    with a:
        text_field(p["course"], "code", "Subject / course code (optional)", placeholder="ID2103")
    with b:
        text_field(p["course"], "name", "Subject / course name", placeholder="Art & Aesthetics in Design")
    with st.expander("Department and academic details"):
        cols = st.columns(2)
        for i, (field, label) in enumerate([("department", "Department"), ("programme", "Programme"),
                                           ("semester", "Semester"), ("academic_year", "Academic year")]):
            with cols[i % 2]:
                text_field(p["course"], field, label)
    st.subheader("Syllabus")
    uploaded = st.file_uploader("Upload PDF, DOCX or TXT", type=["pdf", "docx", "txt"], key=key("syllabus_upload"))
    if st.button("Extract syllabus text", disabled=uploaded is None):
        text, error = extract_text(uploaded)
        if error:
            st.error(error)
        elif len(clean_text(text)) < 30:
            st.warning("No usable text found. Paste the syllabus; scanned PDFs need external OCR.")
        else:
            p["syllabus"] = clean_text(text)
            reset_widgets()
    text_field(p, "syllabus", "Syllabus text", area=True, height=260,
               help="Check extracted text before use. This app does not perform OCR.")
    if p["syllabus"].strip() and len(p["syllabus"].strip()) < 30:
        st.warning("Add more teaching content to support grounded suggestions.")
    st.subheader("Modules & topics")
    st.caption("Use any number of modules. Keep IDs stable and copy supporting text from the syllabus.")
    if st.button("Find syllabus headings", disabled=not p["syllabus"].strip()):
        p["modules"] = derive_modules(p["syllabus"], p["modules"])
        reset_widgets()
    with st.form(key("modules_form")):
        frame = st.data_editor(pd.DataFrame(p["modules"], columns=["id", "title", "text"]), num_rows="dynamic", hide_index=True,
            width="stretch", key=key("modules_table"), column_config={"id": "Module ID", "title": "Title / topic",
            "text": st.column_config.TextColumn("Syllabus source text", width="large")})
        if st.form_submit_button("Save modules"):
            saved, errors, seen = [], [], set()
            for row in rows(frame):
                if not row.get("title") and not row.get("text"):
                    continue
                row = {"id": str(row.get("id") or new_id("MOD")), "title": str(row.get("title") or "Untitled topic"), "text": str(row.get("text") or "")}
                if row["id"] in seen:
                    errors.append("Module IDs must be unique.")
                if row["text"] and row["text"] not in p["syllabus"]:
                    errors.append(f"{row['id']}: source text must occur in the syllabus.")
                seen.add(row["id"])
                saved.append(row)
            if errors:
                st.error(" ".join(errors))
            else:
                p["modules"] = saved
                reset_widgets()
    if not p["modules"]:
        st.info("Find headings or add topics above. Exam portions are selected from this list.")
    else:
        st.success(f"{len(p['modules'])} modules available for outcome and paper preparation.")


def outcome_errors(co, p):
    errors = []
    if len(co.get("statement", "").strip()) < 12:
        errors.append("Enter a meaningful measurable outcome.")
    if any(m not in {m["id"] for m in p["modules"]} for m in co.get("module_ids", [])):
        errors.append("Select existing modules.")
    if any(b not in BLOOMS for b in co.get("bloom_levels", [])):
        errors.append("Use Bloom levels L1 through L6.")
    return errors


def outcomes_page(p, api_key):
    st.write("Prepare measurable outcomes. Draft suggestions and the approved set remain separate.")
    st.caption("CO means Course Outcome: what students should be able to do after studying this subject. Review each outcome and click Approve outcome to make it available in Build Question Paper.")
    if p["course"].get("name", "").strip():
        st.write("Subject:", p["course"]["name"])
    else:
        st.info("No subject has been entered yet. Set its name and syllabus in Course & Syllabus or enter the name at the top of Build Question Paper.")
    st.button("Return to paper builder", on_click=navigate_to, args=(PAGES[4],), key=key("outcomes_to_paper"))
    a, b, c = st.columns(3)
    a.metric("Approved outcomes", len(approved_cos(p)))
    b.metric("Drafts to review", len(p["co_drafts"]))
    c.metric("Syllabus modules", len(p["modules"]))
    count = st.number_input("Requested CO count", 1, 30, 5, key=key("co_count"))
    if st.button("Draft COs from syllabus", type="primary"):
        result = task(lambda: outcomes.draft_course_outcomes(p, int(count), api_key))
        if result is not None:
            p["co_drafts"].extend(result)
            reset_widgets()
    with st.expander("Add a manual course outcome", expanded=not p["co_drafts"] and not p["approved_cos"]):
        with st.form(key("manual_co")):
            statement = st.text_area("Measurable outcome", placeholder="Analyse… using… to…")
            mids = st.multiselect("Related modules", [m["id"] for m in p["modules"]])
            levels = st.multiselect("Suggested Bloom levels", BLOOMS)
            if st.form_submit_button("Add outcome draft"):
                used = {c["id"] for c in p["co_drafts"] + p["approved_cos"] + p.get("retired_sources", {}).get("approved_cos", [])}
                index = 1
                while f"CO{index}" in used:
                    index += 1
                co = {"id": f"CO{index}", "statement": statement.strip(), "module_ids": mids, "bloom_levels": levels,
                      "rationale": "Professor-entered outcome.", "evidence": [], "origin": "manual", "status": "draft"}
                errors = outcome_errors(co, p)
                if errors:
                    st.error(" ".join(errors))
                else:
                    p["co_drafts"].append(co)
                    reset_widgets()
    for collection, title in [("co_drafts", "Draft outcomes"), ("approved_cos", "Approved set & revisions")]:
        st.subheader(title)
        if not p[collection]:
            st.caption("No outcomes here yet.")
        for co in list(p[collection]):
            with st.expander(f"{co['id']} · {co.get('status', 'draft').replace('_', ' ')} · {co['statement'][:85]}"):
                with st.form(key(f"co:{collection}:{co['id']}")):
                    statement = st.text_area("Outcome statement", co["statement"])
                    mods = [m["id"] for m in p["modules"]]
                    mids = st.multiselect("Modules", mods, [m for m in co.get("module_ids", []) if m in mods])
                    levels = st.multiselect("Bloom levels", BLOOMS, co.get("bloom_levels", []))
                    save = st.form_submit_button("Save professor edits")
                    approve = st.form_submit_button("Approve outcome", type="primary")
                    if save or approve:
                        candidate = {**co, "statement": statement.strip(), "module_ids": mids, "bloom_levels": levels}
                        errors = outcome_errors(candidate, p)
                        if approve and collection == "co_drafts" and any(c["id"] == co["id"] for c in p["approved_cos"]):
                            errors.append("This ID already exists in the approved set; it cannot be replaced silently.")
                        if errors:
                            st.error(" ".join(errors))
                        else:
                            co.setdefault("original_statement", co["statement"])
                            co.update(candidate, status="approved" if approve else "draft", professor_edited=True)
                            co["source_fingerprint"] = source_fingerprint(p, "co", co)
                            if approve and collection == "co_drafts":
                                p["approved_cos"].append(deepcopy(co))
                                p["co_drafts"].remove(co)
                            # Record the edit before reapproval so dependency tracking does not undo approval.
                            refresh_dependencies(p)
                            if approve:
                                target = next(c for c in p["approved_cos"] if c["id"] == co["id"])
                                target.update(status="approved", source_fingerprint=source_fingerprint(p, "co", target))
                            reset_widgets()
                st.write(co.get("rationale", ""))
                if co.get("review_reason"):
                    st.warning(co["review_reason"])
                evidence_view(co.get("evidence", []), p)
                if collection == "co_drafts" and st.button("Regenerate this draft", key=key(f"regen_co:{co['id']}")):
                    result = task(lambda: outcomes.draft_course_outcomes(p, 1, api_key, replace_id=co["id"]))
                    if result:
                        p[collection][p[collection].index(co)] = result[0]
                        reset_widgets()
                if st.button("Remove outcome", key=key(f"remove_co:{collection}:{co['id']}")):
                    p[collection].remove(co)
                    reset_widgets()
    st.caption("Classification selects from approved COs only. Creating outcomes is a separate deliberate action.")


def programme_configuration(p):
    with st.expander("Programme outcomes & department PSOs", expanded=not any(o.get("approved") for o in p["programme_outcomes"])):
        st.info("Enter your institution's wording. PO1–PO11 and PSO1–PSO2 are empty templates, not official statements.")
        with st.form(key("po_form")):
            frame = st.data_editor(pd.DataFrame(p["programme_outcomes"], columns=["id", "kind", "statement", "approved"]),
                num_rows="dynamic", hide_index=True, width="stretch", key=key("po_editor"),
                column_config={"id": "Outcome ID", "kind": st.column_config.SelectboxColumn("Type", options=["PO", "PSO"]),
                "statement": st.column_config.TextColumn("Institution / department statement", width="large"),
                "approved": st.column_config.CheckboxColumn("Professor approved")})
            if st.form_submit_button("Save programme configuration"):
                try:
                    values = rows(frame)
                    for value in values:
                        value["id"] = str(value.get("id") or "").strip()
                        value["statement"] = str(value.get("statement") or "").strip()
                        value["approved"] = bool(value.get("approved"))
                    config = {"schema_version": 1, "programme_outcomes": values}
                    p["programme_outcomes"] = import_programme_config(json.dumps(config))
                    wanted_approvals = {o["id"]: o["approved"] for o in p["programme_outcomes"]}
                    refresh_dependencies(p)
                    # Saving the labelled approval checkbox explicitly approves revised wording.
                    for outcome in p["programme_outcomes"]:
                        outcome["approved"] = wanted_approvals[outcome["id"]]
                    reset_widgets()
                except (ValueError, TypeError, KeyError) as error:
                    st.error(str(error))
        st.download_button("Export programme configuration", export_programme_config(p), "programme_outcomes.json", "application/json")
        uploaded = st.file_uploader("Reuse a programme configuration", type=["json"], key=key("po_upload"))
        if st.button("Import programme configuration", disabled=uploaded is None):
            try:
                p["programme_outcomes"] = import_programme_config(uploaded.getvalue().decode("utf-8"))
                reset_widgets()
            except (ValueError, TypeError, KeyError, UnicodeError) as error:
                st.error(f"Configuration was not imported: {error}")


def matrix_page(p, api_key):
    st.write("Review curricular relationships and set the final mapping strength for each cell.")
    programme_configuration(p)
    cos = approved_cos(p)
    if not cos:
        st.info("Approve a course outcome to prepare a matrix.")
        return
    st.caption("Scale: — = no demonstrated relationship · 1 = low · 2 = medium · 3 = high. Blank = not reviewed.")
    st.caption("Relationships are not measured student attainment or accreditation validation.")
    if st.button("Suggest CO–PO / PSO relationships", type="primary"):
        result = task(lambda: outcomes.suggest_matrix(p, api_key))
        if result is not None:
            p["matrix"] = result
            reset_widgets()
    pos = p["programme_outcomes"]
    pairs = {(c["co_id"], c["outcome_id"]): c for c in p["matrix"]}
    records = []
    for co in cos:
        row = {"CO": co["id"]}
        for o in pos:
            score = pairs.get((co["id"], o["id"]), {}).get("final_score")
            row[o["id"]] = None if score is None else "—" if score == 0 else str(score)
        records.append(row)
    with st.form(key("matrix_form")):
        frame = st.data_editor(pd.DataFrame(records), hide_index=True, disabled=["CO"], width="stretch", key=key("matrix_editor"),
            column_config={o["id"]: st.column_config.SelectboxColumn(o["id"], options=["—", "1", "2", "3"]) for o in pos})
        if st.form_submit_button("Save final matrix edits"):
            for row in rows(frame):
                for o in pos:
                    value = row.get(o["id"])
                    score = None if value is None else 0 if value == "—" else int(value)
                    cell = pairs.get((row["CO"], o["id"]))
                    if cell is None:
                        if score is None:
                            continue
                        cell = {"co_id": row["CO"], "outcome_id": o["id"], "suggested_score": None, "final_score": None,
                                "rationale": "", "evidence": [], "status": "draft"}
                        p["matrix"].append(cell)
                    if score != cell.get("final_score"):
                        cell.update(final_score=score, status="draft", professor_edited=True)
                    cell.setdefault("source_fingerprint", source_fingerprint(p, "matrix", cell))
            reset_widgets()
    if not p["matrix"]:
        st.info("Enter final values or request AI suggestions. Empty cells remain unreviewed.")
        return
    co_id = st.selectbox("Review CO relationships", [c["id"] for c in cos], key=key("matrix_co"))
    for cell in [c for c in p["matrix"] if c["co_id"] == co_id]:
        with st.expander(f"{co_id} → {cell['outcome_id']} · {cell.get('status', 'draft').replace('_', ' ')}"):
            suggested = cell.get("suggested_score")
            final = cell.get("final_score")
            prepared = cell.get("provenance") == "prepared_demo"
            suggestion_label = "Prepared example suggestion" if prepared else "AI suggestion"
            st.write(f"{suggestion_label}: {suggested if suggested is not None else 'none'} · Final: {final if final is not None else 'not reviewed'}")
            st.write(cell.get("rationale", ""))
            if cell.get("review_reason"):
                st.warning(cell["review_reason"])
            evidence_view(cell.get("evidence", []), p)
            with st.form(key(f"relationship:{co_id}:{cell['outcome_id']}")):
                note = st.text_area("Professor justification / review note", cell.get("notes", ""))
                module_ids = [m["id"] for m in p["modules"]]
                previous_ref = next(iter(cell.get("evidence", [])), {})
                module_id = st.selectbox("Supporting syllabus module", [""] + module_ids,
                    index=module_ids.index(previous_ref["module_id"]) + 1 if previous_ref.get("module_id") in module_ids else 0)
                quote = st.text_area("Supporting syllabus quotation", previous_ref.get("quote", ""),
                    help="Copy an exact passage from the selected module. Positive relationships require evidence.")
                approve = st.form_submit_button("Approve relationship")
                accept = st.form_submit_button("Accept example score & approve" if prepared else "Accept AI score & approve", disabled=cell.get("suggested_score") is None)
                reject = st.form_submit_button("Reject suggestion / approve no relationship")
                if approve or accept or reject:
                    candidate = {**cell, "notes": note, "status": "approved"}
                    if quote.strip():
                        candidate["evidence"] = [{"module_id": module_id, "quote": quote.strip()}]
                    if accept:
                        candidate["final_score"] = cell["suggested_score"]
                    if reject:
                        candidate.setdefault("original_suggestion", {k: deepcopy(cell.get(k)) for k in ("suggested_score", "rationale", "evidence", "source_fingerprint")})
                        candidate.update(final_score=0, evidence=[], rejected_suggestion=True)
                    errors = validate_matrix_cell(candidate, p)
                    if candidate.get("final_score") is None:
                        errors.append("Set a final score in the matrix first.")
                    if errors:
                        st.error(" ".join(errors))
                    else:
                        cell.update(candidate, source_fingerprint=source_fingerprint(p, "matrix", candidate))
                        reset_widgets()
    st.download_button("Final matrix CSV", exports.final_matrix_csv(p), "co_programme_matrix.csv", "text/csv")
    st.download_button("Relationships & justifications CSV", exports.matrix_justifications_csv(p), "matrix_justifications.csv", "text/csv")


def analyse_questions(p, api_key, question_ids=None):
    cos = approved_cos(p)
    if not cos:
        raise ValueError("Approve course outcomes before analysing questions.")
    if not api_key:
        raise ValueError("Add a Gemini API key in Advanced Settings.")
    cache = st.session_state.setdefault("embedding_cache", {})
    tuples = [(c["id"], c["statement"]) for c in cos]
    co_vectors = rag.embed_texts([f"{cid}: {statement}" for cid, statement in tuples], cache=cache)
    chunks = rag.chunk_syllabus(p["syllabus"])
    chunk_vectors = rag.embed_texts(chunks, cache=cache) if chunks else []
    questions = [q for q in p["analysis_questions"] if q["text"].strip() and (question_ids is None or q["id"] in question_ids)]
    progress = st.progress(0.0)
    for i, q in enumerate(questions):
        result = rag.predict_rag_llm(q["text"], q["marks"], p["course"]["name"], tuples, co_vectors, chunks, chunk_vectors, api_key=api_key)
        previous = p["analyses"].get(q["id"], {})
        p["analyses"][q["id"]] = {"suggestion": result,
            "final_co": previous.get("final_co") or result.get("co", ""),
            "final_bloom": previous.get("final_bloom") or result.get("bloom_levels", []),
            "status": "needs_review" if previous else "draft", "notes": previous.get("notes", ""),
            "question_fingerprint": fingerprint(q), "source_fingerprint": source_fingerprint(p, "analysis", q)}
        progress.progress((i + 1) / max(len(questions), 1))
    progress.empty()
    return True


def analysis_page(p, api_key):
    st.write("Analyse existing questions, inspect the retrieval evidence, and approve or correct final labels.")
    with st.expander("Extract text from a question paper"):
        uploaded = st.file_uploader("Existing PDF, DOCX or TXT", type=["pdf", "docx", "txt"], key=key("analysis_upload"))
        if st.button("Extract question-paper text", disabled=uploaded is None):
            text, error = extract_text(uploaded)
            if error:
                st.error(error)
            elif not text.strip():
                st.warning("No text found. Scanned PDFs require external OCR.")
            else:
                st.session_state["extracted_questions"] = clean_text(text)
        if st.session_state.get("extracted_questions"):
            st.text_area("Extracted text: copy each question to the table", st.session_state["extracted_questions"], height=220)
    with st.form(key("analysis_questions_form")):
        frame = st.data_editor(pd.DataFrame(p["analysis_questions"], columns=["id", "number", "text", "marks"]),
            hide_index=True, num_rows="dynamic", disabled=["id"], width="stretch", key=key("analysis_questions_editor"),
            column_config={"id": st.column_config.TextColumn("Stable ID", width="small"), "number": "Number",
                "text": st.column_config.TextColumn("Question", width="large"), "marks": st.column_config.NumberColumn("Marks", min_value=0, step=1)})
        if st.form_submit_button("Save questions"):
            saved = []
            for index, row in enumerate(rows(frame)):
                if str(row.get("text") or "").strip():
                    saved.append({"id": row.get("id") or new_id("AQ"), "number": str(row.get("number") or index + 1),
                                  "text": str(row["text"]).strip(), "marks": float(row.get("marks") or 0)})
            p["analysis_questions"] = saved
            refresh_dependencies(p)
            reset_widgets()
    if st.button("Analyse questions", type="primary", disabled=not p["analysis_questions"]):
        refresh_dependencies(p)
        if task(lambda: analyse_questions(p, api_key)):
            reset_widgets()
    if not p["analyses"]:
        st.info("Save questions and run an analysis to see suggestions. AI runs only when requested.")
        return
    final_rows = []
    for q in p["analysis_questions"]:
        a = p["analyses"].get(q["id"])
        if a:
            r = a.get("suggestion", {})
            final_rows.append({"id": q["id"], "Number": q["number"], "Question": q["text"], "Marks": q["marks"],
                "Suggested CO": r.get("co", ""), "Suggested Bloom": joined(r.get("bloom_levels", [])),
                "Confidence": r.get("confidence", "Low"), "Final CO": a.get("final_co", ""),
                "Final Bloom": joined(a.get("final_bloom", [])), "Review notes": a.get("notes", ""), "Status": a.get("status", "draft")})
    if not final_rows:
        st.info("Previous analyses are preserved in the project. Add the corresponding questions to review them.")
        return
    st.caption("Final-label edits save automatically in this session. Approve them explicitly before approved export.")
    with st.container():
        frame = st.data_editor(pd.DataFrame(final_rows), hide_index=True, width="stretch", key=key("analysis_finals_editor"),
            disabled=["id", "Number", "Question", "Marks", "Suggested CO", "Suggested Bloom", "Confidence", "Status"],
            column_config={"Final CO": st.column_config.SelectboxColumn("Final CO", options=[c["id"] for c in approved_cos(p)]),
                           "Final Bloom": st.column_config.TextColumn("Final Bloom", help="Multiple levels allowed, e.g. L3, L4")})
        for row in rows(frame):
            analysis = p["analyses"][row["id"]]
            co, bloom, notes = row["Final CO"], split_ids(row["Final Bloom"]), row["Review notes"] or ""
            if (co, bloom, notes) != (analysis.get("final_co"), analysis.get("final_bloom", []), analysis.get("notes", "")):
                analysis.update(final_co=co, final_bloom=bloom, notes=notes, status="draft")
        save = st.button("Save final labels")
        approve = st.button("Approve final analysis", type="primary")
        if save or approve:
            candidate = deepcopy(p)
            if approve:
                active_ids = {q["id"] for q in p["analysis_questions"]}
                for qid, analysis in candidate["analyses"].items():
                    if qid in active_ids:
                        analysis["status"] = "approved"
            errors = validate_final_analysis(candidate)
            if not approve:
                # Drafts can be saved before approval; labels are still validated.
                errors = [error for error in errors if "needs professor approval" not in error]
            if errors:
                st.error(" ".join(errors))
            else:
                if approve:
                    for q in p["analysis_questions"]:
                        if q["id"] in p["analyses"]:
                            p["analyses"][q["id"]].update(status="approved", question_fingerprint=fingerprint(q), source_fingerprint=source_fingerprint(p, "analysis", q))
                reset_widgets()
    for q in p["analysis_questions"]:
        a = p["analyses"].get(q["id"])
        if not a:
            continue
        r = a.get("suggestion", {})
        with st.expander(f"{q['number']} · {a.get('status', 'draft').replace('_', ' ')} · evidence and LLM details"):
            if a.get("review_reason"):
                st.warning(a["review_reason"])
            st.write(r.get("reason", ""))
            st.write("Topic:", r.get("topic", ""))
            if r.get("provenance") == "prepared_demo":
                st.caption("Prepared example labels. Similarity and confidence were not measured; no LLM runs were made for this example.")
                evidence_view(r.get("sample_evidence", []), p)
            else:
                st.write("CO cosine similarity:", r.get("co_ranking", []))
                for chunk, score in r.get("syllabus_chunks", []):
                    st.caption(f"Retrieved syllabus · similarity {score:.3f}")
                    st.text(chunk)
                st.write(f"LLM runs: {r.get('total_votes', 0)} · votes for selected CO: {r.get('votes_for_co', 0)}")
            if r.get("error"):
                st.error(r["error"])
    try:
        st.download_button("Approved analysis CSV", exports.analysis_csv(p), "question_analysis.csv", "text/csv")
    except ValueError as error:
        st.caption(f"Approved export: {error}")


def paper_subject_setup(p):
    """Keep the subject visible at the point where professors prepare a paper."""
    with st.container(border=True):
        st.subheader("Subject for this question paper")
        st.caption("Enter your subject below. Its syllabus and approved course outcomes are shared with Course & Syllabus. To reuse another saved subject, import its project JSON from the sidebar.")
        name, code = st.columns([2, 1])
        with name:
            text_field(p["course"], "name", "Subject / course name", prefix="paper_course:",
                       placeholder="e.g. Art & Aesthetics in Design")
        with code:
            text_field(p["course"], "code", "Subject / course code (optional)", prefix="paper_course:", placeholder="e.g. ID2103")
        a, b = st.columns(2)
        a.button("Set syllabus & modules", on_click=navigate_to, args=(PAGES[0],), key=key("paper_to_syllabus"))
        b.button("Prepare / approve course outcomes", on_click=navigate_to, args=(PAGES[1],), key=key("paper_to_outcomes"))
        st.caption("CO = Course Outcome: a statement of what students should be able to do. For example, ‘Analyse how art and design influence society.’ You choose which approved outcomes this paper assesses below.")


def select_paper_outcomes(p, co_ids):
    """An explicit selection never approves a draft or replaces outcome content."""
    p["blueprint"]["co_ids"] = list(co_ids)
    st.session_state.ui_epoch = st.session_state.get("ui_epoch", 0) + 1


def blueprint_editor(p):
    bp = p["blueprint"]
    types = ["Mid-semester", "End-semester", "Custom"]
    current = bp.get("exam_type", "Mid-semester")
    bp["exam_type"] = st.selectbox("Exam type", types, index=types.index(current) if current in types else 0, key=key("exam_type"))
    a, b = st.columns(2)
    with a:
        text_field(bp, "title", "Exam title")
        text_field(bp, "duration", "Duration", placeholder="2 hours")
    with b:
        text_field(bp, "date", "Exam date", placeholder="YYYY-MM-DD (optional)")
        bp["target_marks"] = st.number_input("Target total marks", min_value=0.0, value=float(bp.get("target_marks", 30)), step=1.0, key=key("target_marks"))
    if st.button("Use exam-type marks default", disabled=bp["exam_type"] == "Custom"):
        bp["target_marks"] = 50 if bp["exam_type"] == "End-semester" else 30
        reset_widgets()
    mods = [m["id"] for m in p["modules"]]
    bp["module_ids"] = st.multiselect("Covered modules / topics", mods, [m for m in bp.get("module_ids", []) if m in mods],
        format_func=lambda mid: next(f"{mid} · {m['title']}" for m in p["modules"] if m["id"] == mid), key=key("covered_modules"))
    co_lookup = {c["id"]: c for c in approved_cos(p)}
    cos = list(co_lookup)
    bp["co_ids"] = st.multiselect("Course outcomes to assess", cos, [c for c in bp.get("co_ids", []) if c in cos],
        format_func=lambda cid: f"{cid} — {co_lookup[cid]['statement']}", key=key("paper_cos"),
        disabled=not cos, placeholder="Select approved outcomes for this paper" if cos else "Approve course outcomes first",
        help="CO means Course Outcome. Only outcomes explicitly approved in Course Outcomes appear here. Selecting CO1 means this paper should assess the skill described in CO1.")
    if cos:
        st.button("Use all approved outcomes for this paper", on_click=select_paper_outcomes, args=(p, cos), key=key("paper_all_cos"))
        if bp["co_ids"]:
            for cid in bp["co_ids"]:
                st.caption(f"{cid}: {co_lookup[cid]['statement']}")
    else:
        st.info("There are no approved course outcomes yet. Open Course Outcomes, add or draft outcomes, then click Approve outcome. They will appear here for selection.")
    bp["bloom_levels"] = st.multiselect("Desired Bloom levels", BLOOMS, bp.get("bloom_levels", ["L2", "L3"]), key=key("paper_bloom"))
    levels = ["Mixed", "Easy", "Moderate", "Challenging"]
    current = bp.get("difficulty", "Mixed")
    bp["difficulty"] = st.selectbox("Difficulty preference", levels, index=levels.index(current) if current in levels else 0, key=key("difficulty"))
    if isinstance(bp.get("instructions"), list):
        bp["instructions"] = "\n".join(bp["instructions"])
    text_field(bp, "instructions", "Paper instructions", area=True, height=100)
    st.subheader("Sections")
    st.caption("Counts are printed parent questions. Each either/or alternative counts as one printed question.")
    for index, section in enumerate(list(bp["sections"])):
        sid = section["id"]
        with st.container(border=True):
            st.markdown(f"**Section {index + 1}**")
            text_field(section, "title", "Section title", prefix=sid)
            cols = st.columns(3)
            with cols[0]:
                section["count"] = st.number_input("Questions to print", min_value=0, max_value=100, value=int(section.get("count", 6)), key=key(sid + "count"))
            with cols[1]:
                section["marks"] = st.number_input("Marks per question", min_value=0.0, value=float(section.get("marks", 5)), step=1.0, key=key(sid + "marks"))
            with cols[2]:
                if section.get("mode", "compulsory") == "compulsory":
                    section["attempt"] = section["count"]
                    st.metric("Students attempt", section["count"])
                else:
                    section["attempt"] = st.number_input("Students must attempt", min_value=0, max_value=100, value=int(section.get("attempt", 1)), key=key(sid + "attempt"))
            text_field(section, "instructions", "Section instructions", prefix=sid)
            with st.expander("Choice rules & subquestions"):
                modes = ["compulsory", "any", "either_or"]
                section["mode"] = st.selectbox("Attempt rule", modes, index=modes.index(section.get("mode", "compulsory")),
                    format_func=lambda v: {"compulsory": "All questions compulsory", "any": "Answer any K of N", "either_or": "Either/or pairs (adjacent alternatives)"}[v], key=key(sid + "mode"))
                st.caption("Either/or requires an even printed count and attempt count equal to half that count.")
                raw = st.text_input("Unequal marks (optional, one value per printed question)", joined(section.get("question_marks", [])), key=key(sid + "unequal"))
                try:
                    # Repeated marks matter: never deduplicate this sequence.
                    section["question_marks"] = [float(v.strip()) for v in raw.split(",")] if raw.strip() else []
                    if any(not math.isfinite(value) for value in section["question_marks"]):
                        raise ValueError("Marks must be finite.")
                except ValueError:
                    st.error("Enter comma-separated numeric marks.")
                    section["question_marks"] = [0]
                with st.form(key(sid + "subquestions_form")):
                    frame = st.data_editor(pd.DataFrame(section.get("subquestions", []), columns=["label", "marks"]), num_rows="dynamic", hide_index=True,
                        width="stretch", key=key(sid + "subquestions"), column_config={"label": "Subquestion label (a, b…)", "marks": st.column_config.NumberColumn("Marks", min_value=0.0)})
                    if st.form_submit_button("Save subquestion structure"):
                        section["subquestions"] = [{"label": str(r.get("label") or "").strip(), "marks": float(r.get("marks") or 0)}
                            for r in rows(frame) if r.get("label") or r.get("marks")]
                        reset_widgets()
            controls = st.columns(3)
            if controls[0].button("Move up", key=key(sid + "up"), disabled=index == 0):
                bp["sections"][index - 1], bp["sections"][index] = section, bp["sections"][index - 1]
                reset_widgets()
            if controls[1].button("Move down", key=key(sid + "down"), disabled=index == len(bp["sections"]) - 1):
                bp["sections"][index + 1], bp["sections"][index] = section, bp["sections"][index + 1]
                reset_widgets()
            if controls[2].button("Remove section", key=key(sid + "remove")):
                bp["sections"].remove(section)
                reset_widgets()
    if st.button("Add section"):
        bp["sections"].append({"id": new_id("SEC"), "title": f"Section {len(bp['sections']) + 1}", "instructions": "Answer all questions.",
            "mode": "compulsory", "count": 1, "attempt": 1, "marks": 5, "question_marks": [], "subquestions": []})
        reset_widgets()
    return bp


def marks_panel(bp):
    errors = validate_blueprint(bp)
    if errors:
        for error in errors:
            st.error(error)
        st.caption("Structural errors must be corrected; the override cannot bypass them.")
        return False
    totals = calculate_marks(bp)
    a, b, c = st.columns(3)
    a.metric("Entered target", f"{totals['target']:g}")
    b.metric("Printed question marks", f"{totals['printed']:g}")
    actual = f"{totals['minimum']:g}–{totals['maximum']:g}" if totals["ambiguous"] else f"{totals['maximum']:g}"
    c.metric("Attemptable marks range" if totals["ambiguous"] else "Actual attemptable maximum", actual)
    if totals.get("difference") is not None:
        st.caption(f"Actual minus target: {totals['difference']:+g} marks.")
    if totals["mismatch"] or totals["ambiguous"]:
        st.warning("Attemptable marks differ from the target or depend on the options chosen. The student paper will show the actual total or range. Edit the blueprint or explicitly retain this structure.")
        if totals["ambiguous"]:
            st.caption("Use equal marks for optional questions or alternatives to remove ambiguity. Continuing preserves this range.")
        cols = st.columns(2)
        if cols[0].button("Edit blueprint"):
            bp["acknowledgment"] = None
            st.info("Edit the section controls above, then review the recalculated marks.")
        if cols[1].button("Continue with this blueprint", type="primary"):
            acknowledge_blueprint(bp)
            reset_widgets()
        if can_generate(bp)[0]:
            st.success("Professor acknowledged the current structure. The original target remains available.")
    else:
        st.success("Attemptable marks match the target.")
    return can_generate(bp)[0]


def manual_slots(p):
    existing = {q["slot_id"] for q in p["paper_questions"]}
    for slot in build_slots(p["blueprint"]):
        if slot["slot_id"] in existing:
            continue
        q = {**slot, "text": "", "co_id": "", "bloom_levels": [], "module_ids": [],
            "difficulty": "Moderate", "rationale": "Professor-entered question.", "evidence": [], "status": "draft", "locked": False,
            "answer": "", "marking_guide": [], "requested_co_ids": list(p["blueprint"]["co_ids"]),
            "requested_bloom_levels": list(p["blueprint"]["bloom_levels"])}
        q["source_fingerprint"] = source_fingerprint(p, "paper", q)
        p["paper_questions"].append(q)


def show_generation_result(result):
    failures = result.get("failures", {})
    st.session_state["generation_failures"] = failures
    st.session_state["generation_notice"] = True
    reset_widgets()


def paper_question_editor(p, api_key):
    slots = {s["slot_id"]: s for s in build_slots(p["blueprint"])}
    active = [q for q in p["paper_questions"] if q.get("slot_id") in slots]
    if not active:
        return
    st.subheader("Question drafts & professor edits")
    st.caption("Blueprint marks and counts are authoritative. Save edits before navigating. Unlock approved questions before editing or regenerating them.")
    for warning in papers.duplicate_warnings(active):
        st.warning(str(warning))
    a, b = st.columns(2)
    if a.button("Check generated questions"):
        if task(lambda: papers.check_generated_questions(p, api_key, embedding_cache=st.session_state.setdefault("embedding_cache", {}))) is not None:
            reset_widgets()
    if b.button("Check semantic duplicates"):
        warnings = task(lambda: papers.duplicate_warnings(active, use_embeddings=True, embedding_cache=st.session_state.setdefault("embedding_cache", {})))
        if warnings:
            for warning in warnings:
                st.warning(warning)
        elif warnings is not None:
            st.success("No duplicate candidates found at the configured threshold. Review remains necessary.")
    for q in active:
        slot = slots[q["slot_id"]]
        with st.expander(f"Q{slot['number']} · {q['marks']:g} marks · {q.get('status', 'draft').replace('_', ' ')}{' · locked' if q.get('locked') else ''}"):
            if q.get("marks") != slot["marks"] or q.get("parent_id") != slot.get("parent_id") or q.get("choice_group") != slot.get("choice_group"):
                st.warning(f"The current blueprint requires {slot['marks']:g} marks for this slot. The retained question has its previous structure.")
                if st.button("Apply current slot marks & structure", key=key(q["id"] + "apply_slot"), disabled=bool(q.get("locked"))):
                    q.setdefault("revision_history", []).append({k: deepcopy(v) for k, v in q.items() if k != "revision_history"})
                    q.update({k: deepcopy(v) for k, v in slot.items() if k != "id"})
                    q.update(status="draft", locked=False, source_fingerprint=source_fingerprint(p, "paper", q))
                    refresh_dependencies(p)
                    reset_widgets()
            if q.get("review_reason"):
                st.warning(q["review_reason"])
            if q.get("analysis", {}).get("disagrees"):
                if q["analysis"].get("provenance") == "prepared_demo":
                    st.warning("Prepared demo disagreement: the example suggestion differs from the intended labels. Review the evidence and choose your final labels.")
                else:
                    st.warning("Independent analysis disagrees with the intended labels. Review the evidence; your labels are retained.")
            if q.get("last_check_error"):
                st.error(q["last_check_error"])
            st.caption(f"Requested COs: {joined(q.get('requested_co_ids', []))} · Requested Bloom: {joined(q.get('requested_bloom_levels', []))}")
            if q.get("locked"):
                st.write(q["text"])
                if st.button("Unlock for editing", key=key(q["id"] + "unlock")):
                    q.update(locked=False, status="draft")
                    reset_widgets()
            else:
                with st.form(key(q["id"] + "edit")):
                    text = st.text_area("Question text", q["text"], height=150)
                    options = [""] + [c["id"] for c in approved_cos(p)]
                    co_id = st.selectbox("Final intended CO", options, index=options.index(q.get("co_id", "")) if q.get("co_id") in options else 0)
                    blooms = st.multiselect("Final intended Bloom levels", BLOOMS, [b for b in q.get("bloom_levels", []) if b in BLOOMS])
                    mids = p["blueprint"]["module_ids"]
                    modules = st.multiselect("Syllabus modules", mids, [m for m in q.get("module_ids", []) if m in mids])
                    answer = st.text_area("Optional answer / marking-guide draft (faculty only)", q.get("answer", ""))
                    guide = st.data_editor(pd.DataFrame(q.get("marking_guide", []), columns=["criterion", "marks"]), num_rows="dynamic", hide_index=True,
                        column_config={"marks": st.column_config.NumberColumn("Marks", min_value=0.0)})
                    notes = st.text_area("Faculty review notes", q.get("notes", ""))
                    save = st.form_submit_button("Save question edits")
                    approve = st.form_submit_button("Approve & lock question", type="primary")
                    if save or approve:
                        criteria = [{"criterion": str(r.get("criterion") or ""), "marks": float(r.get("marks") or 0)}
                            for r in rows(guide) if r.get("criterion") or r.get("marks")]
                        errors = []
                        if criteria and abs(sum(c["marks"] for c in criteria) - float(slot["marks"])) > 1e-8:
                            errors.append("Marking criteria must total the question marks.")
                        if any(c["marks"] <= 0 or not c["criterion"].strip() for c in criteria):
                            errors.append("Each criterion needs text and positive marks.")
                        if approve and (not text.strip() or co_id not in options[1:] or not blooms or not modules):
                            errors.append("Approval needs question text, an approved CO, Bloom labels and selected modules.")
                        if errors:
                            st.error(" ".join(errors))
                        else:
                            changed = text.strip() != q["text"] or co_id != q.get("co_id") or blooms != q.get("bloom_levels")
                            q.setdefault("original_question", {k: deepcopy(v) for k, v in q.items() if k not in ("original_question", "revision_history")})
                            q.update(text=text.strip(), co_id=co_id, bloom_levels=blooms, module_ids=modules, answer=answer,
                                marking_guide=criteria, notes=notes, status="approved" if approve else "draft", locked=bool(approve), professor_edited=True)
                            if changed and q.get("analysis"):
                                q["analysis"]["status"] = "needs_review"
                            refresh_dependencies(p)
                            q.update(status="approved" if approve else "draft", locked=bool(approve), source_fingerprint=source_fingerprint(p, "paper", q))
                            reset_widgets()
                if st.button("Regenerate only this question", key=key(q["id"] + "regenerate")):
                    result = task(lambda: papers.generate_paper(p, api_key, slot_ids=[q["slot_id"]]))
                    if result is not None:
                        show_generation_result(result)
            with st.expander("Rationale, source evidence & subsequent analysis"):
                st.write(q.get("rationale", ""))
                evidence_view(q.get("evidence", []), p)
                if q.get("analysis"):
                    st.json(q["analysis"])
    retired = [q for q in p["paper_questions"] if q.get("slot_id") not in slots]
    if retired:
        with st.expander("Preserved questions outside the current blueprint"):
            for q in retired:
                st.write(q.get("number"), q.get("text"), q.get("status"))


def paper_page(p, api_key):
    st.write("Choose the subject, syllabus portions and approved outcomes, then set the exam structure. Drafts follow your exact counts, alternatives and marks.")
    if st.session_state.pop("generation_notice", False):
        failures = st.session_state.get("generation_failures", {})
        if failures:
            st.warning("Some items failed. Successful drafts were preserved. Retry failed slots or write their questions manually.")
            for sid, error in failures.items():
                st.caption(f"{sid}: {error}")
        else:
            st.success("Drafts prepared. Review and approve each question. Existing successful items are retained; regenerate individual unlocked questions to replace them.")
    paper_subject_setup(p)
    setup_status = st.container()
    bp = blueprint_editor(p)
    refresh_dependencies(p)
    setup_issues = papers.generation_setup_issues(p)
    with setup_status:
        if setup_issues:
            st.info("Before generating questions, complete the subject setup:")
            st.markdown("\n".join(f"- {message}" for message in setup_issues.values()))
        else:
            st.success(f"Subject setup ready: {p['course']['name']} · {len(bp['module_ids'])} selected modules/topics · {len(bp['co_ids'])} selected course outcomes.")
    allowed = marks_panel(bp)
    if setup_issues:
        st.caption("Accepting the marks warning confirms the exam structure only. Complete the subject setup above to enable AI generation; you can still edit the blueprint and prepare manual slots.")
    if not api_key:
        st.info("AI generation also needs a Gemini API key in Advanced Settings. Manual paper preparation is available without a key.")
    generation_ready = allowed and not setup_issues and bool(api_key)
    a, b = st.columns(2)
    if a.button("Generate question drafts", type="primary", disabled=not generation_ready) and generation_ready:
        result = task(lambda: papers.generate_paper(p, api_key))
        if result is not None:
            show_generation_result(result)
    if b.button("Prepare slots for manual questions", disabled=not allowed):
        manual_slots(p)
        reset_widgets()
    failures = st.session_state.get("generation_failures", {})
    if failures and st.button("Retry failed items only", disabled=not generation_ready) and generation_ready:
        result = task(lambda: papers.generate_paper(p, api_key, slot_ids=list(failures)))
        if result is not None:
            show_generation_result(result)
    if not validate_blueprint(bp):
        paper_question_editor(p, api_key)


def review_page(p, api_key):
    st.write("Review the latest paper and coverage, then prepare student and faculty files. Save project JSON for future editing.")
    bp = p["blueprint"]
    if validate_blueprint(bp):
        st.info("Complete a valid blueprint in Build Question Paper to preview a paper.")
        return
    slots = build_slots(bp)
    questions = {q["slot_id"]: q for q in p["paper_questions"]}
    active = [questions[s["slot_id"]] for s in slots if s["slot_id"] in questions]
    if not active:
        st.info("Generate drafts or prepare manual slots to build the paper.")
        return
    review_count = sum(q.get("status") != "approved" for q in active)
    if review_count:
        st.warning(f"Draft paper: {review_count} items need professor review. Files reflect the current drafts.")
    with st.container(border=True):
        try:
            for kind, text in exports.paper_blocks(p):
                if kind == "title":
                    st.subheader(text)
                elif kind == "heading":
                    st.markdown(f"### {text}")
                elif kind == "choice":
                    st.markdown("**OR**")
                elif kind == "metadata":
                    st.caption(text)
                else:
                    st.text(text)
        except ValueError as error:
            st.warning(str(error))
            totals = calculate_marks(bp)
            actual = f"{totals['minimum']:g}–{totals['maximum']:g}" if totals["ambiguous"] else f"{totals['maximum']:g}"
            st.subheader(bp.get("title") or "Question paper")
            st.write(f"{p['course'].get('code', '')} · {p['course'].get('name', '')}")
            st.caption(f"Duration: {bp.get('duration', '')} · Date: {bp.get('date', '')} · Attemptable marks: {actual}")
            st.text(bp.get("instructions", ""))
            for section in bp["sections"]:
                st.markdown(f"### {section['title']}")
                st.write(section.get("instructions", ""))
                if section["mode"] == "any":
                    st.caption(f"Answer any {section['attempt']} of {section['count']} questions.")
                elif section["mode"] == "either_or":
                    st.caption("Answer one alternative from each either/or pair.")
                for slot in [s for s in slots if s["section_id"] == section["id"]]:
                    q = questions.get(slot["slot_id"], {})
                    st.text(f"{slot['number']}. {q.get('text') or '[Question not prepared]'} [{slot['marks']:g} marks]")
    st.subheader("Coverage")
    st.caption("Printed coverage includes alternatives. Guaranteed coverage accounts for choices; students need not attempt every printed question.")
    summary = exports.coverage_summary(p)
    if isinstance(summary, dict):
        for title, value in summary.items():
            st.markdown(f"**{title.replace('_', ' ').title()}**")
            if isinstance(value, list):
                st.dataframe(pd.DataFrame(value), hide_index=True, width="stretch")
            elif isinstance(value, dict):
                st.dataframe(pd.DataFrame.from_dict(value, orient="index"), width="stretch")
            else:
                st.write(value)
    else:
        st.dataframe(summary, width="stretch")
    st.subheader("Export paper")
    st.caption("Student files contain the paper only. Faculty files include labels, sources and notes. Answers and marking guides are faculty-reviewable drafts.")
    include_answers = st.checkbox("Include answer / marking-guide drafts in faculty files", key=key("include_answers"))
    if st.button("Prepare PDF & DOCX downloads", type="primary"):
        def prepare():
            return {"fingerprint": fingerprint([p, include_answers]),
                "student_pdf": exports.paper_pdf(p), "student_docx": exports.paper_docx(p),
                "faculty_pdf": exports.paper_pdf(p, faculty=True, include_answers=include_answers),
                "faculty_docx": exports.paper_docx(p, faculty=True, include_answers=include_answers)}
        result = task(prepare)
        if result:
            st.session_state["export_buffers"] = result
    buffers = st.session_state.get("export_buffers", {})
    if buffers.get("fingerprint") == fingerprint([p, include_answers]):
        cols = st.columns(2)
        for i, role in enumerate(["student", "faculty"]):
            with cols[i]:
                for ext, mime in [("pdf", "application/pdf"), ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")]:
                    st.download_button(f"{role.title()} paper {ext.upper()}", buffers[f"{role}_{ext}"], f"{role}_paper.{ext}", mime)
    st.download_button("Final matrix CSV", exports.final_matrix_csv(p), "co_programme_matrix.csv", "text/csv")
    st.download_button("Matrix justifications CSV", exports.matrix_justifications_csv(p), "matrix_justifications.csv", "text/csv")
    try:
        st.download_button("Approved question mappings CSV", exports.analysis_csv(p), "question_mappings.csv", "text/csv")
    except ValueError as error:
        st.caption(f"Question mappings export: {error}")
