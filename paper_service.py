"""Blueprint-authoritative generation and explicit independent question checks."""
import copy
import difflib
import json
import math
import re

import numpy as np

import rag_pipeline as rag
from outcome_service import (AIValidationError, EVIDENCE_SCHEMA, approved_course_outcomes,
                             evidence_errors, normal_text, response_schema, task_json)
from project_state import fingerprint, source_fingerprint
from validation import build_slots, can_generate, validate_generated_items


QUESTION_SCHEMA = {"type": "object", "required": ["slot_id", "text", "marks", "co_id", "bloom_levels", "module_ids", "difficulty", "rationale", "evidence"],
    "properties": {"slot_id": {"type": "string"}, "text": {"type": "string", "minLength": 5},
        "marks": {"type": "number", "exclusiveMinimum": 0}, "co_id": {"type": "string"},
        "bloom_levels": {"type": "array", "minItems": 1, "items": {"enum": rag.VALID_BLOOM_LEVELS}},
        "module_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "difficulty": {"enum": ["Easy", "Moderate", "Challenging"]}, "rationale": {"type": "string"},
        "evidence": EVIDENCE_SCHEMA, "answer": {"type": "string"},
        "marking_guide": {"type": "array", "items": {"type": "object", "required": ["criterion", "marks"],
            "properties": {"criterion": {"type": "string"}, "marks": {"type": "number", "exclusiveMinimum": 0}},
            "additionalProperties": False}}}, "additionalProperties": False}


def validate_question_response(parsed, slots, project):
    """Strict task schema; metadata is copied from slots only after validation."""
    items = parsed.get("questions")
    if isinstance(items, list):
        preflight = []
        if set(parsed) != {"questions"}:
            preflight.append("Question response must contain only questions.")
        for item in items:
            if not isinstance(item, dict):
                preflight.append("Each question must be an object.")
                continue
            if any(key not in QUESTION_SCHEMA["properties"] for key in item):
                preflight.append("Question fields differ from the task schema.")
            for key in ("slot_id", "co_id", "text", "rationale"):
                if not isinstance(item.get(key), str):
                    preflight.append("Question %s must be text." % key)
            for key in ("bloom_levels", "module_ids"):
                if not isinstance(item.get(key), list) or any(not isinstance(v, str) for v in item.get(key, [])):
                    preflight.append("Question %s must be a list of text identifiers." % key)
            if "id" in item and not isinstance(item["id"], str):
                preflight.append("Question ID must be text.")
        if preflight:
            return None, preflight
    errors = validate_generated_items(items, slots, project)
    if not isinstance(items, list):
        return None, errors
    selected_cos = set(project.get("blueprint", {}).get("co_ids", []))
    selected_blooms = set(project.get("blueprint", {}).get("bloom_levels", []))
    selected_modules = set(project.get("blueprint", {}).get("module_ids", []))
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("co_id") not in selected_cos:
            errors.append("Question CO is outside the requested CO targets.")
        if not isinstance(item.get("bloom_levels"), list) or any(l not in selected_blooms for l in item.get("bloom_levels", [])):
            errors.append("Question Bloom levels are outside the requested targets.")
        if item.get("difficulty") not in ("Easy", "Moderate", "Challenging"):
            errors.append("Difficulty must be Easy, Moderate or Challenging.")
        if not normal_text(item.get("rationale")):
            errors.append("Each question needs a concise rationale.")
        errors.extend(evidence_errors(item.get("evidence"), project.get("modules", []), selected_modules))
        if not isinstance(item.get("answer", ""), str):
            errors.append("An optional answer must be text.")
        guide = item.get("marking_guide", [])
        if isinstance(guide, list) and any(not isinstance(g, dict) or not normal_text(g.get("criterion")) for g in guide):
            errors.append("Each marking-guide criterion must contain text.")
    return items, errors


def generation_setup_issues(project):
    """Actionable subject prerequisites shared by the builder and AI service.

    This only inspects saved course content. Marks acknowledgement is a separate
    decision, and no outcomes are approved or selected implicitly.
    """
    issues = {}
    bp = project.get("blueprint", {})
    if not normal_text(project.get("course", {}).get("name")):
        issues["subject"] = "Enter the subject / course name at the top of this page, or in Course & Syllabus."
    if not normal_text(project.get("syllabus")):
        issues["syllabus"] = "Add this subject's syllabus in Course & Syllabus."
    cos = approved_course_outcomes(project)
    co_map = {c["id"]: c for c in cos}
    mids = {m["id"]: m for m in project.get("modules", [])}
    if not mids:
        issues["modules"] = "In Course & Syllabus, use Find syllabus headings or add and save modules/topics manually."
    if not cos:
        if project.get("co_drafts"):
            issues["outcomes"] = "Open Course Outcomes, review your drafts, and click Approve outcome for each one you want to use."
        elif project.get("approved_cos"):
            issues["outcomes"] = "Open Course Outcomes and review and reapprove the outcomes marked as needing review."
        else:
            issues["outcomes"] = "Open Course Outcomes, enter outcomes manually or use Draft COs from syllabus, then click Approve outcome."
    elif not bp.get("co_ids"):
        issues["co_targets"] = "Under Course outcomes to assess, select at least one approved outcome, such as CO1."
    elif any(c not in co_map for c in bp["co_ids"]):
        issues["co_targets"] = "Some selected outcomes are no longer approved. Review them in Course Outcomes, then select current outcomes under Course outcomes to assess."
    if mids:
        if not bp.get("module_ids"):
            issues["portions"] = "Under Covered modules / topics, select the syllabus portions included in this exam."
        elif any(m not in mids for m in bp["module_ids"]):
            issues["portions"] = "Select current syllabus portions under Covered modules / topics; a previously selected module was removed."
        else:
            selected = [mids[mid] for mid in bp["module_ids"]]
            if any(len(normal_text(m.get("text"))) < 15 for m in selected):
                issues["portions"] = "Selected modules need usable syllabus text, not just headings. Add their text in Course & Syllabus."
            elif any(m["text"] not in project.get("syllabus", "") for m in selected):
                issues["portions"] = "Selected module text is absent from the current syllabus. Review the modules in Course & Syllabus."
    if not bp.get("bloom_levels") or any(l not in rag.VALID_BLOOM_LEVELS for l in bp["bloom_levels"]):
        issues["bloom"] = "Select at least one desired Bloom level, from L1 to L6, for the questions."
    return issues


def _generation_inputs(project):
    allowed, errors = can_generate(project.get("blueprint", {}))
    if not allowed:
        raise ValueError("; ".join(errors))
    issues = generation_setup_issues(project)
    if issues:
        raise ValueError(" ".join(issues.values()))
    bp = project["blueprint"]
    co_map = {c["id"]: c for c in approved_course_outcomes(project)}
    mids = {m["id"]: m for m in project.get("modules", [])}
    return [co_map[c] for c in bp["co_ids"]], [mids[mid] for mid in bp["module_ids"]]


def generate_paper(project, api_key=None, slot_ids=None, batch_size=3):
    """Fill missing slots or explicitly regenerate unlocked slots in bounded batches.

    Successful batches are saved immediately. A later network or schema failure
    leaves those questions and all existing professor edits available for review.
    Calling with no slot IDs retries empty/failed slots, preserving successful ones.
    """
    cos, modules = _generation_inputs(project)
    if type(batch_size) is not int or not 1 <= batch_size <= 5:
        raise ValueError("Batch size must be between one and five.")
    bp = project["blueprint"]
    slots = build_slots(bp)
    slot_map = {s["slot_id"]: s for s in slots}
    current = {q.get("slot_id", q["id"]): q for q in project.get("paper_questions", [])}
    if slot_ids is not None:
        if not isinstance(slot_ids, (list, tuple, set)) or any(not isinstance(s, str) or s not in slot_map for s in slot_ids):
            raise ValueError("Requested regeneration contains an unknown slot ID.")
        requested = set(slot_ids)
    else:
        requested = {s["slot_id"] for s in slots if not normal_text(current.get(s["slot_id"], {}).get("text"))
                     or current.get(s["slot_id"], {}).get("status") == "failed"}
    failures = {}
    pending = []
    for slot in slots:
        sid = slot["slot_id"]
        if sid not in requested:
            continue
        if current.get(sid, {}).get("locked"):
            failures[sid] = "Approved question is locked. Unlock it before regenerating."
        else:
            pending.append(slot)
    for start in range(0, len(pending), batch_size):
        batch = pending[start:start + batch_size]
        prompt = """\nTASK: Write exactly one university examination question for every supplied slot.
The supplied slots are authoritative: preserve exact slot IDs, marks, subquestion
and alternative structure. Do not add, omit or combine slots. Match scope and
cognitive work to marks. Use ONLY selected modules and approved CO targets.
Select Bloom targets based on the complete cognitive task. Numerical/scenario
questions must include all data and assumptions needed for an answer. Do not
repeat the existing questions. Evidence quotes must occur verbatim in modules.
Any answer or marking guide is a faculty-reviewable draft. Optional marking-guide
criteria must allocate exactly the slot marks. No external knowledge is assumed
beyond the supplied syllabus and information provided in the question itself.
SCHEMA: {"questions":[{"slot_id":"S1:1","text":"...","marks":5,
"co_id":"CO1","bloom_levels":["L2"],"module_ids":["M1"],
"difficulty":"Moderate","rationale":"...","evidence":[{"module_id":"M1",
"quote":"exact syllabus quotation"}],"answer":"optional draft answer",
"marking_guide":[{"criterion":"...","marks":5}]}]}
COURSE DATA:\n"""
        prompt += "JSON SCHEMA:\n" + json.dumps(response_schema("questions", QUESTION_SCHEMA, len(batch))) + "\n"
        prompt += json.dumps({"course": project.get("course", {}), "slots": batch,
            "approved_cos": cos, "selected_modules": modules,
            "requested_bloom_levels": bp["bloom_levels"], "difficulty": bp.get("difficulty", "Moderate"),
            "instructions": bp.get("instructions", ""),
            "existing_questions": [q["text"] for q in current.values() if q.get("text")]}, ensure_ascii=False)
        try:
            generated = task_json(prompt, lambda p: validate_question_response(p, batch, project), api_key)
        except (rag.LLMUnavailable, AIValidationError) as error:
            for slot in batch:
                failures[slot["slot_id"]] = str(error)
            # Authentication/quota/network failure should not multiply API requests.
            if isinstance(error, rag.LLMUnavailable):
                for slot in pending[start + batch_size:]:
                    failures[slot["slot_id"]] = "Not attempted after Gemini became unavailable. Retry failed items."
                break
            continue
        for generated_item in generated:
            slot = slot_map[generated_item["slot_id"]]
            # Rejecting wrong counts/marks occurs above; copying metadata is never
            # a silent repair of an invalid generated structure.
            item = {key: copy.deepcopy(generated_item.get(key, default)) for key, default in
                    (("text", ""), ("co_id", ""), ("bloom_levels", []), ("module_ids", []),
                     ("difficulty", "Moderate"), ("rationale", ""), ("evidence", []),
                     ("answer", ""), ("marking_guide", []))}
            item.update(copy.deepcopy(slot))
            if current.get(slot["slot_id"], {}).get("id"):
                item["id"] = current[slot["slot_id"]]["id"]
            item.update(status="draft", locked=False,
                requested_co_ids=list(bp["co_ids"]), requested_bloom_levels=list(bp["bloom_levels"]),
                requested_module_ids=list(bp["module_ids"]))
            item["source_fingerprint"] = source_fingerprint(project, "paper", item)
            current[slot["slot_id"]] = item
        # Keep obsolete material for inspection, while current slots follow print order.
        project["paper_questions"] = [current[s["slot_id"]] for s in slots if s["slot_id"] in current]
        project["paper_questions"] += [q for sid, q in current.items() if sid not in slot_map]
    return {"questions": project.get("paper_questions", []), "failures": failures}


def duplicate_warnings(questions, use_embeddings=False, embedding_cache=None):
    """Exact and likely duplicate candidates; every decision remains with faculty."""
    questions = [q for q in questions if normal_text(q.get("text"))]
    normalized = [re.sub(r"\W+", " ", q["text"].casefold()).strip() for q in questions]
    embeddings = rag.embed_texts([q["text"] for q in questions], cache=embedding_cache) if use_embeddings and questions else None
    warnings = []
    for i in range(len(questions)):
        for j in range(i + 1, len(questions)):
            a = questions[i].get("number", questions[i]["id"])
            b = questions[j].get("number", questions[j]["id"])
            if normalized[i] == normalized[j]:
                warnings.append("Exact duplicate: questions %s and %s." % (a, b))
            elif difflib.SequenceMatcher(None, normalized[i], normalized[j]).ratio() >= .87:
                warnings.append("Likely near-duplicate: questions %s and %s. Review their assessed task." % (a, b))
            elif embeddings is not None and float(np.dot(embeddings[i], embeddings[j])) >= .90:
                warnings.append("Similar question scope: questions %s and %s (embedding similarity). Review their assessed task." % (a, b))
    return warnings


def check_generated_questions(project, api_key=None, ids=None, embedding_cache=None):
    """Explicitly reuse the unchanged RAG classifier; never replace requested labels."""
    cos = approved_course_outcomes(project)
    if not cos:
        raise ValueError("Approve COs before checking generated questions.")
    active_slots = {s["slot_id"] for s in build_slots(project.get("blueprint", {}))}
    active_items = [q for q in project.get("paper_questions", []) if q.get("slot_id", q.get("id")) in active_slots]
    active_ids = active_slots | {q["id"] for q in active_items}
    if ids is not None and (not isinstance(ids, (list, tuple, set)) or any(not isinstance(i, str) or i not in active_ids for i in ids)):
        raise ValueError("Only current blueprint question IDs can be checked.")
    candidates = [q for q in active_items if (ids is None or q["id"] in ids or q.get("slot_id") in ids)
                  and normal_text(q.get("text"))]
    if not candidates:
        return {"checked": [], "failures": {}}
    co_pairs = [(c["id"], c["statement"]) for c in cos]
    co_embeddings = rag.embed_texts(["%s: %s" % pair for pair in co_pairs], cache=embedding_cache)
    # Check against covered portions; retrieval must not introduce uncovered topics.
    selected = set(project.get("blueprint", {}).get("module_ids", []))
    text = "\n\n".join(m["text"] for m in project.get("modules", []) if m["id"] in selected)
    chunks = rag.chunk_syllabus(text)
    chunk_embeddings = rag.embed_texts(chunks, cache=embedding_cache) if chunks else []
    checked, failures = [], {}
    for index, item in enumerate(candidates):
        try:
            result = rag.predict_rag_llm(item["text"], item["marks"],
                project.get("course", {}).get("name", ""), co_pairs, co_embeddings,
                chunks, chunk_embeddings, api_key=api_key)
        except (rag.LLMUnavailable, ValueError) as error:
            failures[item["id"]] = str(error)
            item["last_check_error"] = str(error)
            item["status"] = "needs_review"
            for skipped in candidates[index + 1:]:
                failures[skipped["id"]] = "Not checked after an earlier analysis failure. Retry the remaining items."
            break
        if result.get("error"):
            # A failed re-check must not erase previously successful evidence.
            failures[item["id"]] = result["error"]
            item["last_check_error"] = result["error"]
            item["status"] = "needs_review"
            for skipped in candidates[index + 1:]:
                failures[skipped["id"]] = "Not checked after an earlier analysis failure. Retry the remaining items."
            break
        disagrees = result.get("co") != item.get("co_id") or set(result.get("bloom_levels", [])) != set(item.get("bloom_levels", []))
        if item.get("analysis"):
            item.setdefault("analysis_history", []).append(copy.deepcopy(item["analysis"]))
        item["analysis"] = {"suggestion": result, "disagrees": disagrees,
            "question_fingerprint": fingerprint({"text": item["text"], "marks": item["marks"]}),
            "source_fingerprint": source_fingerprint(project, "analysis")}
        item.pop("last_check_error", None)
        if disagrees:
            item["status"] = "needs_review"
        checked.append(item["id"])
    return {"checked": checked, "failures": failures}
