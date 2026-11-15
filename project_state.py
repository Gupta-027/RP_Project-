"""Serializable project state, stable identifiers, and local dependency tracking.

Streamlit holds this object during a session. JSON is the explicit durable save path.
No credentials, embedding models, or caches belong in this object.
"""
import copy
import hashlib
import json
import re
import uuid

from validation import blueprint_fingerprint, validate_project, validate_blueprint

SCHEMA_VERSION = 1
PROJECT_FIELDS = ("schema_version", "id", "course", "syllabus", "modules", "co_drafts",
                  "approved_cos", "programme_outcomes", "matrix", "analysis_questions",
                  "analyses", "blueprint", "paper_questions", "revisions", "retired_sources", "presentation_demo")
SOURCE_COLLECTIONS = ("modules", "approved_cos", "programme_outcomes", "analysis_questions", "sections")
_SENSITIVE = re.compile(r"(^|_)(api_?key|api_?token|secrets?|passwords?|credentials?|(?:access|refresh)_?tokens?|tokens?|authorization|authentication|auth|private_?key|model_object|embedding_cache)($|_)", re.I)


def new_id(prefix="item"):
    return prefix + "_" + uuid.uuid4().hex[:12]


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def new_project():
    return {
        "schema_version": SCHEMA_VERSION, "id": new_id("project"),
        "course": {k: "" for k in ("code", "name", "department", "programme", "semester", "academic_year")},
        "syllabus": "", "modules": [], "co_drafts": [], "approved_cos": [],
        "programme_outcomes": [
            {"id": "PO%d" % i, "kind": "PO", "statement": "", "approved": False} for i in range(1, 12)
        ] + [{"id": "PSO%d" % i, "kind": "PSO", "statement": "", "approved": False} for i in (1, 2)],
        "matrix": [], "analysis_questions": [], "analyses": {},
        "blueprint": {"exam_type": "Mid-semester", "title": "Mid-semester examination",
                      "duration": "90 minutes", "date": "", "target_marks": 30,
                      "module_ids": [], "co_ids": [], "bloom_levels": ["L2", "L3"],
                      "difficulty": "Moderate", "instructions": "Answer all questions.\nUse neat labelled diagrams where necessary.",
                      "sections": [{"id": "SEC1", "title": "Section A", "instructions": "Answer all questions.",
                                    "mode": "compulsory", "count": 6, "attempt": 6,
                                    "marks": 5, "question_marks": [], "subquestions": []}],
                      "acknowledgment": None},
        "paper_questions": [], "revisions": {},
        "retired_sources": {key: [] for key in SOURCE_COLLECTIONS},
    }


def approved_cos(project):
    return [c for c in project.get("approved_cos", [])
            if c.get("status", "approved") == "approved" and c.get("statement", "").strip()]


def derive_modules(syllabus, existing=None):
    """Extract any number of headings; preserve IDs when headings can be matched.

    If there are no recognisable headings the entire source remains one editable
    portion. No topics are invented and no OCR is implied.
    """
    if not isinstance(syllabus, str) or not syllabus.strip():
        return []
    heading = re.compile(r"(?im)^[ \t]*(?:(?:unit|module|chapter|part|section)\s*(?:\d+|[ivxlcdm]+)\b[^\n]*|\d+(?:\.\d+)*[.)]?\s+[^\n]{3,100})$")
    matches = list(heading.finditer(syllabus))
    chunks = []
    if matches:
        if syllabus[:matches[0].start()].strip():
            chunks.append(("Course overview", syllabus[:matches[0].start()].strip()))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(syllabus)
            chunks.append((match.group().strip(), syllabus[match.start():end].strip()))
    else:
        chunks = [("Syllabus portion 1", syllabus.strip())]
    old = list(existing or [])
    used, result = set(), []
    for title, text in chunks:
        match = next((m for m in old if m.get("id") not in used and m.get("title", "").casefold() == title.casefold()), None)
        if match is None:
            match = next((m for m in old if m.get("id") not in used and m.get("text") == text), None)
        ident = match["id"] if match else new_id("MOD")
        used.add(ident)
        result.append({"id": ident, "title": title, "text": text})
    return result


def _co_content(co):
    return {k: co.get(k) for k in ("id", "statement", "module_ids", "bloom_levels")}


def _outcome_content(outcome):
    return {k: outcome.get(k) for k in ("id", "kind", "statement", "approved")}


def outcome_source_fingerprint(project, item=None):
    module_ids = set((item or {}).get("module_ids", []))
    if module_ids:
        modules = [m for m in project.get("modules", []) if m["id"] in module_ids]
        return fingerprint({"module_ids": sorted(module_ids), "modules": modules,
                            "source_present": [m.get("text", "") in project.get("syllabus", "") for m in modules]})
    return fingerprint({"syllabus": project.get("syllabus"), "modules": project.get("modules", [])})


def matrix_source_fingerprint(project, co_id=None, outcome_id=None):
    cos = [_co_content(c) for c in project.get("approved_cos", []) if co_id is None or c["id"] == co_id]
    outcomes = [_outcome_content(o) for o in project.get("programme_outcomes", []) if outcome_id is None or o["id"] == outcome_id]
    module_ids = {m for c in cos for m in c.get("module_ids") or []}
    modules = [m for m in project.get("modules", []) if not module_ids or m["id"] in module_ids]
    return fingerprint({"cos": cos, "outcomes": outcomes, "modules": modules,
                        "source_present": [m.get("text", "") in project.get("syllabus", "") for m in modules]})


def analysis_source_fingerprint(project):
    return fingerprint({"cos": [{**_co_content(c), "status": c.get("status", "approved")} for c in project.get("approved_cos", [])],
                        "syllabus": project.get("syllabus"), "course": project.get("course", {}).get("name")})


def paper_source_fingerprint(project):
    bp = project.get("blueprint", {})
    co_ids, module_ids = set(bp.get("co_ids", [])), set(bp.get("module_ids", []))
    return fingerprint({"blueprint": blueprint_fingerprint(bp),
                        "cos": [{**_co_content(c), "status": c.get("status", "approved")} for c in project.get("approved_cos", []) if c["id"] in co_ids],
                        "modules": [m for m in project.get("modules", []) if m["id"] in module_ids],
                        "source_present": [m.get("text", "") in project.get("syllabus", "")
                                           for m in project.get("modules", []) if m["id"] in module_ids]})


def source_fingerprint(project, kind, item=None):
    if kind in ("outcome", "co"):
        return outcome_source_fingerprint(project, item)
    if kind == "matrix":
        return matrix_source_fingerprint(project, (item or {}).get("co_id"), (item or {}).get("outcome_id"))
    if kind in ("analysis", "analyses"):
        return analysis_source_fingerprint(project)
    if kind in ("paper", "question"):
        return paper_source_fingerprint(project)
    raise ValueError("Unknown dependency kind: " + str(kind))


def _review(item, reason):
    item["status"] = "needs_review"
    item["review_reason"] = reason


def _source_record(record):
    """Snapshot source content, excluding review bookkeeping and runtime objects."""
    return _safe({k: copy.deepcopy(v) for k, v in record.items()
            if k not in ("source_fingerprint", "review_reason", "status", "archive_fingerprint", "archive_reason")}
                )


def _source_collection(project, key):
    return project.get("blueprint", {}).get("sections", []) if key == "sections" else project.get(key, [])


def _archive_source_versions(project, revisions):
    """Keep changed/deleted records so stale references remain auditable and portable."""
    archive = project.setdefault("retired_sources", {key: [] for key in SOURCE_COLLECTIONS})
    previous = revisions.get("source_records", {})
    for key in SOURCE_COLLECTIONS:
        archive.setdefault(key, [])
        current = {r["id"]: _source_record(r) for r in _source_collection(project, key)}
        for old in previous.get(key, []):
            ident = old["id"]
            if key in ("approved_cos", "programme_outcomes") and not old.get("statement", "").strip():
                continue  # Empty PO/PSO templates were never usable reference sources.
            if key == "sections" and validate_blueprint({"target_marks": 1, "sections": [old]}):
                continue  # A temporary invalid widget state never defined valid slots.
            if ident not in current or old != current[ident]:
                digest = fingerprint(old)
                if not any(r.get("archive_fingerprint") == digest for r in archive[key]):
                    archive[key].append({**copy.deepcopy(old), "archive_fingerprint": digest,
                                         "archive_reason": "removed" if ident not in current else "revised"})
    revisions["source_records"] = {key: [_source_record(r) for r in _source_collection(project, key)]
                                   for key in SOURCE_COLLECTIONS}


def refresh_dependencies(project):
    """Flag changed descendants without deleting suggestions or final professor edits.

    Call after editing source data and before rendering dependent actions. Newly
    created material is stamped at its current sources; original fingerprints are
    retained when stale so a second rerun cannot silently clear the warning.
    """
    revisions = project.setdefault("revisions", {})
    _archive_source_versions(project, revisions)
    previous = revisions.get("sources", {})
    current_cos = {c["id"]: fingerprint(_co_content(c)) for c in project.get("approved_cos", [])}
    current_pos = {o["id"]: fingerprint(_outcome_content(o)) for o in project.get("programme_outcomes", [])}
    for co in project.get("approved_cos", []):
        old = previous.get("cos", {}).get(co["id"])
        if old and old != current_cos[co["id"]]:
            _review(co, "Course outcome content changed; approve the revised outcome.")
        source = co.get("source_fingerprint")
        outcome_fp = outcome_source_fingerprint(project, co)
        if source and source != outcome_fp:
            _review(co, "Syllabus or module source changed; review this outcome.")
        if any(mid not in {m["id"] for m in project.get("modules", [])} for mid in co.get("module_ids", [])):
            _review(co, "A related module was removed; choose current modules before approval.")
    for co in project.get("co_drafts", []):
        outcome_fp = outcome_source_fingerprint(project, co)
        if co.get("source_fingerprint") and co["source_fingerprint"] != outcome_fp:
            _review(co, "Syllabus or module source changed since this draft.")
    for outcome in project.get("programme_outcomes", []):
        old = previous.get("pos", {}).get(outcome["id"])
        # Only wording/kind changes revoke approval; approving an unchanged statement is allowed.
        old_content = previous.get("po_statements", {}).get(outcome["id"])
        statement_fp = fingerprint({k: outcome.get(k) for k in ("statement", "kind")})
        if old and old_content and old_content != statement_fp:
            outcome["approved"] = False
    for cell in project.get("matrix", []):
        expected = matrix_source_fingerprint(project, cell.get("co_id"), cell.get("outcome_id"))
        old = cell.get("source_fingerprint")
        if old and old != expected:
            _review(cell, "CO, syllabus, or programme outcome changed since mapping.")
        elif not old:
            cell["source_fingerprint"] = expected
        co = next((c for c in project.get("approved_cos", []) if c["id"] == cell.get("co_id")), None)
        po = next((o for o in project.get("programme_outcomes", []) if o["id"] == cell.get("outcome_id")), None)
        if not co or co.get("status", "approved") != "approved" or not po or not po.get("approved"):
            _review(cell, "A source outcome requires approval or was removed.")
    question_map = {q["id"]: q for q in project.get("analysis_questions", [])}
    valid_co_ids = {c["id"] for c in approved_cos(project)}
    analysis_fp = analysis_source_fingerprint(project)
    for ident, analysis in project.get("analyses", {}).items():
        question = question_map.get(ident)
        qfp = fingerprint(question) if question else None
        if not question or (analysis.get("question_fingerprint") and analysis["question_fingerprint"] != qfp):
            _review(analysis, "Question text, numbering, or marks changed; review previous labels.")
        if analysis.get("source_fingerprint") and analysis["source_fingerprint"] != analysis_fp:
            _review(analysis, "Course outcomes or syllabus changed since analysis.")
        if analysis.get("final_co") and analysis["final_co"] not in valid_co_ids:
            _review(analysis, "The final CO was removed or requires professor approval.")
        analysis.setdefault("question_fingerprint", qfp)
        analysis.setdefault("source_fingerprint", analysis_fp)
    bp = project.get("blueprint", {})
    # Removed sources remain inspectable in history, but cannot remain generation targets.
    active_modules = {m["id"] for m in project.get("modules", [])}
    active_cos = {c["id"] for c in project.get("approved_cos", [])}
    bp["module_ids"] = [mid for mid in bp.get("module_ids", []) if mid in active_modules]
    bp["co_ids"] = [cid for cid in bp.get("co_ids", []) if cid in active_cos]
    if bp.get("acknowledgment") and bp["acknowledgment"] != blueprint_fingerprint(bp):
        bp["acknowledgment"] = None
    paper_fp = paper_source_fingerprint(project)
    for question in project.get("paper_questions", []):
        expected = question.get("source_fingerprint")
        old_qfp = previous.get("paper_questions", {}).get(question["id"])
        content_fp = fingerprint({k: question.get(k) for k in ("text", "marks", "co_id", "bloom_levels", "module_ids", "answer", "marking_guide")})
        if expected and expected != paper_fp:
            _review(question, "Selected syllabus, COs, or blueprint changed; review retained question.")
            question["locked"] = False
        elif not expected:
            question["source_fingerprint"] = paper_fp
        if old_qfp and old_qfp != content_fp:
            _review(question, "Professor edited this question; review the latest content.")
            question["locked"] = False
            if question.get("analysis"):
                question["analysis"]["status"] = "needs_review"
        if question.get("co_id") and question["co_id"] not in valid_co_ids:
            _review(question, "The intended CO was removed or requires professor approval.")
            question["locked"] = False
    revisions["sources"] = {
        "cos": current_cos, "pos": current_pos,
        "po_statements": {o["id"]: fingerprint({k: o.get(k) for k in ("statement", "kind")}) for o in project.get("programme_outcomes", [])},
        "paper_questions": {q["id"]: fingerprint({k: q.get(k) for k in ("text", "marks", "co_id", "bloom_levels", "module_ids", "answer", "marking_guide")}) for q in project.get("paper_questions", [])},
    }
    return project


def _safe(value):
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items() if not _SENSITIVE.search(str(k))
                and type(v) in (str, int, float, bool, list, tuple, dict, type(None))}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value if type(v) in (str, int, float, bool, list, tuple, dict, type(None))]
    return value


def export_project(project):
    """Serialize only project data. Keys containing secrets are dropped recursively."""
    clean = _safe({key: project[key] for key in PROJECT_FIELDS if key in project})
    if isinstance(clean.get("course"), dict):
        clean["course"] = {k: clean["course"].get(k, "") for k in
                           ("code", "name", "department", "programme", "semester", "academic_year")}
    return json.dumps(clean, ensure_ascii=False, indent=2, allow_nan=False)


def import_project(text):
    if not isinstance(text, (str, bytes)) or len(text) > 20_000_000:
        raise ValueError("Project JSON must be text and smaller than 20 MB.")
    try:
        data = json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON number.")))
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid project JSON.") from exc
    if not isinstance(data, dict):
        raise ValueError("Project must be a JSON object.")
    clean = _safe({key: value for key, value in data.items() if key in PROJECT_FIELDS})
    if isinstance(clean.get("course"), dict):
        clean["course"] = {key: clean["course"].get(key, "") for key in
                           ("code", "name", "department", "programme", "semester", "academic_year")}
    try:
        errors = validate_project(clean)
    except (TypeError, KeyError, AttributeError, OverflowError) as exc:
        raise ValueError("Invalid project: malformed data types or references.") from exc
    if errors:
        raise ValueError("Invalid project: " + " ".join(dict.fromkeys(errors)))
    # Optional display metadata comes from validated slots, never invented IDs.
    from validation import build_slots
    clean["blueprint"].setdefault("sections", [])
    slots = {}
    for section in clean.get("retired_sources", {}).get("sections", []):
        slots.update({s["slot_id"]: s for s in build_slots({"target_marks": 1, "sections": [section]})})
    if clean["blueprint"].get("sections"):
        slots.update({s["slot_id"]: s for s in build_slots(clean["blueprint"])})
    for question in clean["paper_questions"]:
        slot = slots[question["slot_id"]]
        for field in ("number", "section_id", "parent_id", "choice_group", "alternative", "parent_marks"):
            question.setdefault(field, copy.deepcopy(slot.get(field)))
        for field, default in (("co_id", ""), ("bloom_levels", []), ("module_ids", []),
                               ("answer", ""), ("notes", ""), ("marking_guide", []), ("status", "draft"), ("locked", False)):
            question.setdefault(field, copy.deepcopy(default))
    for index, question in enumerate(clean["analysis_questions"], 1):
        question.setdefault("number", str(index))
    # These caches are derived, not authoritative source history. Rebuild them
    # instead of trusting arbitrary imported bookkeeping shapes.
    clean["revisions"] = {}
    refresh_dependencies(clean)
    return clean


def export_programme_config(project):
    return json.dumps({"schema_version": 1, "programme_outcomes": _safe(project.get("programme_outcomes", []))}, ensure_ascii=False, indent=2)


def import_programme_config(text):
    try:
        value = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid programme configuration JSON.") from exc
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value.get("schema_version") != 1 or not isinstance(value.get("programme_outcomes"), list):
        raise ValueError("Unsupported programme configuration; expected schema version 1.")
    sample = new_project()
    sample["programme_outcomes"] = value["programme_outcomes"]
    errors = validate_project(sample)
    if errors:
        raise ValueError("Invalid programme configuration: " + " ".join(errors))
    return [{k: copy.deepcopy(o[k]) for k in ("id", "kind", "statement", "approved")}
            for o in value["programme_outcomes"]]
