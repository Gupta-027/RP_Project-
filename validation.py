"""Pure domain rules. Marks and accepted identifiers never come from an LLM."""
import hashlib
import json
import math
import re

BLOOM_LEVELS = ("L1", "L2", "L3", "L4", "L5", "L6")
STATUSES = ("draft", "approved", "needs_review", "rejected", "failed")


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _integer(value):
    return type(value) is int


def _string_ids(value):
    return isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value)


def _optional_text_errors(record, fields, prefix):
    return [prefix + " " + field + " must be text." for field in fields
            if field in record and not isinstance(record[field], str)]


def _analysis_shape_errors(record, prefix):
    if not isinstance(record, dict):
        return [prefix + " must be an object."]
    errors = _optional_text_errors(record, ("notes", "review_reason", "question_fingerprint", "source_fingerprint"), prefix)
    if "status" in record and record["status"] not in STATUSES:
        errors.append(prefix + " has an invalid review status.")
    if "suggestion" in record and not isinstance(record["suggestion"], dict):
        errors.append(prefix + " suggestion must be an object.")
    if "disagrees" in record and type(record["disagrees"]) is not bool:
        errors.append(prefix + " disagreement flag must be boolean.")
    return errors


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def blueprint_fingerprint(bp):
    """An acknowledgement covers every blueprint field except the acknowledgement."""
    def canonical(value):
        # Streamlit number inputs can change 5 to 5.0 without changing a plan.
        # Structural validation still checks integer-only counts separately.
        if type(value) is float and math.isfinite(value) and value.is_integer():
            return int(value)
        if isinstance(value, dict):
            return {k: canonical(v) for k, v in value.items()}
        if isinstance(value, list):
            return [canonical(v) for v in value]
        return value
    return _hash(canonical({k: v for k, v in bp.items() if k != "acknowledgment"}))


def acknowledge_blueprint(bp):
    if validate_blueprint(bp):
        raise ValueError("Fix structural errors before acknowledging the blueprint.")
    bp["acknowledgment"] = blueprint_fingerprint(bp)
    return bp["acknowledgment"]


def _section_marks(section):
    return section.get("question_marks") or [section.get("marks", 0)] * section.get("count", 0)


def validate_blueprint(bp):
    errors = []
    if not isinstance(bp, dict):
        return ["Blueprint must be an object."]
    target = bp.get("target_marks")
    if not _number(target) or target <= 0:
        errors.append("Target marks must be a positive number.")
    sections = bp.get("sections", [])
    if not isinstance(sections, list) or not sections:
        return errors + ["Add at least one section."]
    seen = set()
    for i, section in enumerate(sections):
        prefix = "Section %s" % (i + 1)
        if not isinstance(section, dict):
            errors.append(prefix + " must be an object.")
            continue
        ident = section.get("id")
        errors.extend(_optional_text_errors(section, ("title", "instructions"), prefix))
        if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", ident) or ident in seen:
            errors.append(prefix + " needs a unique stable ID.")
        else:
            seen.add(ident)
        count, attempt, marks = section.get("count"), section.get("attempt"), section.get("marks")
        valid_count = _integer(count) and 1 <= count <= 200
        if not valid_count:
            errors.append(prefix + " generated count must be an integer between 1 and 200.")
        if not _integer(attempt) or attempt < 1 or (valid_count and attempt > count):
            errors.append(prefix + " attempt count must be between one and generated count.")
        if not _number(marks) or marks <= 0:
            errors.append(prefix + " marks per question must be positive.")
        mode = section.get("mode", "compulsory")
        if mode not in ("compulsory", "any", "either_or"):
            errors.append(prefix + " has an invalid choice rule.")
        if mode == "compulsory" and attempt != count:
            errors.append(prefix + " compulsory sections must require all questions.")
        if mode == "either_or" and valid_count and (count % 2 or attempt != count // 2):
            errors.append(prefix + " either/or requires an even printed count and one attempt per adjacent pair.")
        qmarks = section.get("question_marks", [])
        if not isinstance(qmarks, list) or (qmarks and (not valid_count or len(qmarks) != count)):
            errors.append(prefix + " question marks must list one value per printed question.")
            qmarks = []
        if qmarks and any(not _number(m) or m <= 0 for m in qmarks):
            errors.append(prefix + " individual marks must be positive numbers.")
        subs = section.get("subquestions", [])
        if not isinstance(subs, list):
            errors.append(prefix + " subquestions must be a list.")
            continue
        labels, sub_total = set(), 0
        for sub in subs:
            if not isinstance(sub, dict):
                errors.append(prefix + " subquestion must be an object.")
                continue
            label, submarks = sub.get("label"), sub.get("marks")
            if not isinstance(label, str) or not re.fullmatch(r"[A-Za-z0-9]+", label) or label in labels:
                errors.append(prefix + " subquestion labels must be nonempty and unique.")
            labels.add(str(label))
            if not _number(submarks) or submarks <= 0:
                errors.append(prefix + " subquestion marks must be positive.")
            else:
                sub_total += submarks
        parent_marks = qmarks or [marks]
        if subs and any(not _number(m) or not math.isclose(sub_total, m) for m in parent_marks):
            errors.append(prefix + " subquestion marks must add to every parent question total.")
    return errors


def calculate_marks(bp):
    errors = validate_blueprint(bp)
    result = {"printed": 0, "minimum": 0, "maximum": 0,
              "target": bp.get("target_marks"), "mismatch": False,
              "ambiguous": False, "difference": None, "errors": errors}
    if errors:
        return result
    for section in bp["sections"]:
        marks = _section_marks(section)
        result["printed"] += sum(marks)
        mode, attempt = section.get("mode", "compulsory"), section["attempt"]
        if mode == "any":
            ordered = sorted(marks)
            low, high = sum(ordered[:attempt]), sum(ordered[-attempt:])
        elif mode == "either_or":
            pairs = [marks[i:i + 2] for i in range(0, len(marks), 2)]
            low, high = sum(min(p) for p in pairs), sum(max(p) for p in pairs)
        else:
            low = high = sum(marks)
        result["minimum"] += low
        result["maximum"] += high
    result["ambiguous"] = not math.isclose(result["minimum"], result["maximum"])
    result["mismatch"] = result["ambiguous"] or not math.isclose(result["maximum"], bp["target_marks"])
    if not result["ambiguous"]:
        result["difference"] = result["maximum"] - bp["target_marks"]
    return result


def can_generate(bp):
    errors = validate_blueprint(bp)
    if errors:
        return False, errors
    marks = calculate_marks(bp)
    if marks["mismatch"] and bp.get("acknowledgment") != blueprint_fingerprint(bp):
        return False, ["Review the marks warning and choose Continue with this blueprint."]
    return True, []


def build_slots(bp):
    """Return immutable assessable leaf slots; subquestions retain parent/choice links."""
    errors = validate_blueprint(bp)
    if errors:
        raise ValueError("; ".join(errors))
    slots, display = [], 1
    for section in bp["sections"]:
        for index, marks in enumerate(_section_marks(section)):
            base = "%s:%d" % (section["id"], index + 1)
            is_choice = section.get("mode") == "either_or"
            group = "%s:pair:%d" % (section["id"], index // 2 + 1) if is_choice else None
            number = str(display)
            if is_choice:
                number += "A" if index % 2 == 0 else "B"
            common = {"section_id": section["id"], "choice_group": group,
                      "parent_marks": marks, "question_index": index,
                      "alternative": ("A" if index % 2 == 0 else "B") if is_choice else None}
            subs = section.get("subquestions", [])
            if subs:
                for sub in subs:
                    ident = base + ":" + sub["label"]
                    slots.append({**common, "id": ident, "slot_id": ident,
                                  "number": number + "(" + sub["label"] + ")",
                                  "parent_id": base, "marks": sub["marks"]})
            else:
                slots.append({**common, "id": base, "slot_id": base,
                              "number": number, "parent_id": None, "marks": marks})
            if not is_choice or index % 2 == 1:
                display += 1
    return slots


def _valid_evidence(evidence, project, required=False, include_archived=False):
    errors = []
    modules = {m["id"]: m for m in project.get("modules", [])}
    historical = project.get("retired_sources", {}).get("modules", []) if include_archived else []
    if not isinstance(evidence, list) or (required and not evidence):
        return ["Evidence must contain existing module references and exact syllabus quotations."]
    for ref in evidence:
        if not isinstance(ref, dict) or not isinstance(ref.get("module_id"), str):
            errors.append("Evidence references an unknown module.")
            continue
        candidates = ([modules[ref["module_id"]]] if ref["module_id"] in modules else [])
        candidates += [m for m in historical if m["id"] == ref["module_id"]]
        if not candidates:
            errors.append("Evidence references an unknown module.")
            continue
        quote = ref.get("quote")
        if not isinstance(quote, str) or not quote.strip() or not any(quote in m.get("text", "") for m in candidates):
            errors.append("Evidence quote does not occur in the referenced module.")
    return errors


def validate_matrix_cell(cell, project):
    errors = []
    cos = {c["id"]: c for c in project.get("approved_cos", []) if c.get("status", "approved") == "approved"}
    outcomes = {o["id"]: o for o in project.get("programme_outcomes", [])}
    if cell.get("co_id") not in cos:
        errors.append("Matrix CO is not in the approved CO set.")
    outcome = outcomes.get(cell.get("outcome_id"))
    if not outcome or not outcome.get("approved") or len(outcome.get("statement", "").strip()) < 12:
        errors.append("Matrix outcome needs a meaningful approved statement.")
    for key in ("suggested_score", "final_score"):
        score = cell.get(key)
        if score is not None and (not _integer(score) or score not in range(4)):
            errors.append("Matrix scores must be 0, 1, 2, 3, or unreviewed (null).")
    if cell.get("status") == "approved" and cell.get("final_score") is None:
        errors.append("An approved relationship needs a final score, including explicit zero for no relationship.")
    positive = cell.get("final_score") if cell.get("status") == "approved" else cell.get("suggested_score") or cell.get("final_score")
    errors.extend(_valid_evidence(cell.get("evidence", []), project, required=bool(positive)))
    return errors


def validate_generated_items(items, slots, project):
    errors = []
    if not isinstance(items, list):
        return ["Generated questions must be a list."]
    if len(items) != len(slots):
        errors.append("Generated question count does not match the requested slots.")
    expected = {s["slot_id"]: s for s in slots}
    co_ids = {c["id"] for c in project.get("approved_cos", []) if c.get("status", "approved") == "approved"}
    requested_cos = set(project.get("blueprint", {}).get("co_ids", []))
    if requested_cos:
        co_ids &= requested_cos
    module_ids = set(project.get("blueprint", {}).get("module_ids", []))
    seen, ids = set(), set()
    for item in items:
        if not isinstance(item, dict):
            errors.append("Each generated item must be an object.")
            continue
        slot_id = item.get("slot_id", item.get("id"))
        if not isinstance(slot_id, str):
            errors.append("Generated slot IDs must be text.")
            continue
        slot = expected.get(slot_id)
        if slot is None or slot_id in seen:
            errors.append("Generated slot IDs are unknown or duplicated.")
            continue
        seen.add(slot_id)
        ident = item.get("id", slot_id)
        existing_ids = {q.get("id") for q in project.get("paper_questions", [])
                        if q.get("slot_id", q.get("id")) == slot_id and isinstance(q.get("id"), str)}
        allowed_ids = existing_ids | {slot.get("id", slot_id)}
        if not isinstance(ident, str) or not ident.strip() or ident not in allowed_ids:
            errors.append("Generated question ID differs from its stable slot ID.")
        elif ident in ids:
            errors.append("Generated question IDs must be unique.")
        else:
            ids.add(ident)
        if not _number(item.get("marks")) or item["marks"] != slot["marks"]:
            errors.append("Generated marks differ from the authoritative blueprint.")
        for key in ("section_id", "parent_id", "choice_group", "number"):
            if key in item and item[key] != slot.get(key):
                errors.append("Generated %s differs from the authoritative slot." % key)
        if not isinstance(item.get("text"), str) or len(item["text"].strip()) < 5:
            errors.append("Generated question text is empty or unusable.")
        if not isinstance(item.get("co_id"), str) or item.get("co_id") not in co_ids:
            errors.append("Generated question references an unknown or unapproved CO.")
        blooms = item.get("bloom_levels")
        if not isinstance(blooms, list) or not blooms or any(b not in BLOOM_LEVELS for b in blooms):
            errors.append("Generated Bloom levels must use L1 through L6.")
        refs = item.get("module_ids")
        if not _string_ids(refs) or not refs or any(r not in module_ids for r in refs):
            errors.append("Generated question must reference selected modules only.")
        errors.extend(_valid_evidence(item.get("evidence", []), project, required=True))
        for ref in item.get("evidence", []) if isinstance(item.get("evidence"), list) else []:
            if isinstance(ref, dict) and ref.get("module_id") not in module_ids:
                errors.append("Evidence is outside selected syllabus portions.")
        guide = item.get("marking_guide", [])
        if not isinstance(guide, list):
            errors.append("Marking guide must be a list.")
        elif guide:
            if any(not isinstance(g, dict) or not _number(g.get("marks")) or g["marks"] <= 0 for g in guide):
                errors.append("Marking guide criteria need positive marks.")
            elif not math.isclose(sum(g["marks"] for g in guide), slot["marks"]):
                errors.append("Marking guide total must equal question marks.")
    return errors


def validate_final_analysis(project):
    errors = []
    co_ids = {c["id"] for c in project.get("approved_cos", []) if c.get("status", "approved") == "approved"}
    questions = {q["id"] for q in project.get("analysis_questions", [])}
    active_analyses = {ident: value for ident, value in project.get("analyses", {}).items() if ident in questions}
    for ident, analysis in active_analyses.items():
        if analysis.get("status") != "approved":
            errors.append("Question %s needs professor approval." % ident)
        if analysis.get("final_co") not in co_ids:
            errors.append("Question %s has an invalid final CO." % ident)
        levels = analysis.get("final_bloom", [])
        if not isinstance(levels, list) or not levels or any(b not in BLOOM_LEVELS for b in levels):
            errors.append("Question %s has invalid final Bloom labels." % ident)
    if not active_analyses:
        errors.append("There are no analysed questions to export.")
    return errors


def validate_project(project):
    """Validate persisted projects, including retained material requiring review."""
    errors = []
    if not isinstance(project, dict):
        return ["Project must be a JSON object."]
    if type(project.get("schema_version")) is not int or project["schema_version"] != 1:
        errors.append("Unsupported project schema version; expected 1.")
    if "presentation_demo" in project and type(project["presentation_demo"]) is not bool:
        errors.append("Presentation demo flag must be boolean.")
    if not isinstance(project.get("id"), str) or not project["id"]:
        errors.append("Project needs a stable ID.")
    if not isinstance(project.get("course"), dict) or any(not isinstance(v, str) for v in project.get("course", {}).values()):
        errors.append("Course metadata must contain text values.")
    if not isinstance(project.get("syllabus"), str):
        errors.append("Syllabus must be text.")
    lists = ("modules", "co_drafts", "approved_cos", "programme_outcomes", "matrix", "analysis_questions", "paper_questions")
    for key in lists:
        values = project.get(key)
        if not isinstance(values, list) or any(not isinstance(v, dict) for v in values):
            errors.append(key + " must be a list of objects.")
            continue
        seen = set()
        for value in values:
            ident = (value.get("co_id"), value.get("outcome_id")) if key == "matrix" else value.get("id")
            valid_id = (all(isinstance(v, str) and v.strip() for v in ident)
                        if isinstance(ident, tuple) else isinstance(ident, str) and bool(ident.strip()))
            if not valid_id:
                errors.append(key + " has missing or duplicate IDs.")
            elif ident in seen:
                errors.append(key + " has missing or duplicate IDs.")
            else:
                seen.add(ident)
            if "status" in value and value["status"] not in STATUSES:
                errors.append(key + " has an invalid review status.")
            errors.extend(_optional_text_errors(value, ("notes", "review_reason", "rationale", "professor_notes", "source_fingerprint"), key))
    if errors:
        return errors
    if {co["id"] for co in project["co_drafts"]} & {co["id"] for co in project["approved_cos"]}:
        errors.append("CO IDs must be unique across draft and approved sets.")
    archive = project.get("retired_sources", {})
    if not isinstance(archive, dict):
        return errors + ["Retired sources must be an object."]
    for key in ("modules", "approved_cos", "programme_outcomes", "analysis_questions", "sections"):
        records = archive.get(key, [])
        if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
            errors.append("Retired " + key + " must be a list of source records.")
            continue
        seen_versions = set()
        for record in records:
            ident, digest = record.get("id"), record.get("archive_fingerprint")
            content = {k: v for k, v in record.items() if k not in ("archive_fingerprint", "archive_reason")}
            if not isinstance(ident, str) or not ident.strip() or not isinstance(digest, str) or digest != _hash(content):
                errors.append("Retired source record has an invalid ID or content fingerprint.")
                continue
            if (ident, digest) in seen_versions:
                errors.append("Duplicate retired source version.")
            seen_versions.add((ident, digest))
            if key == "modules" and (not isinstance(record.get("title"), str) or not isinstance(record.get("text"), str)):
                errors.append("Retired module source needs title and text.")
            if key in ("approved_cos", "programme_outcomes") and (not isinstance(record.get("statement"), str) or not record["statement"].strip()):
                errors.append("Retired outcome source needs a statement.")
            if key == "analysis_questions" and (not isinstance(record.get("text"), str) or not _number(record.get("marks")) or record["marks"] < 0):
                errors.append("Retired question source needs text and nonnegative marks.")
            if key == "sections":
                errors.extend(validate_blueprint({"target_marks": 1, "sections": [record]}))
    if errors:
        return errors
    active_mids = {m["id"] for m in project["modules"]}
    active_coids = {c["id"] for c in project["approved_cos"]}
    active_poids = {o["id"] for o in project["programme_outcomes"]}
    mids = active_mids | {m["id"] for m in archive.get("modules", [])}
    coids = active_coids | {c["id"] for c in archive.get("approved_cos", [])}
    poids = active_poids | {o["id"] for o in archive.get("programme_outcomes", [])}
    for historical_co in archive.get("approved_cos", []):
        if not _string_ids(historical_co.get("module_ids", [])) or any(m not in mids for m in historical_co.get("module_ids", [])):
            errors.append("Retired CO references an unknown module.")
        errors.extend(_valid_evidence(historical_co.get("evidence", []), project, include_archived=True))
    for module in project["modules"]:
        if not isinstance(module.get("title"), str) or not isinstance(module.get("text"), str):
            errors.append("Modules need a title and source text.")
    for outcome in project["co_drafts"] + project["approved_cos"]:
        if not isinstance(outcome.get("statement"), str) or not outcome["statement"].strip():
            errors.append("Every CO needs a statement.")
        if not _string_ids(outcome.get("module_ids", [])) or any(m not in mids for m in outcome.get("module_ids", [])):
            errors.append("CO references an unknown module.")
        blooms = outcome.get("bloom_levels", [])
        if not isinstance(blooms, list) or any(b not in BLOOM_LEVELS for b in blooms):
            errors.append("CO has an unsupported Bloom level.")
        errors.extend(_valid_evidence(outcome.get("evidence", []), project, include_archived=True))
        if outcome.get("status") == "approved" and any(m not in active_mids for m in outcome.get("module_ids", [])):
            errors.append("Approved CO refers to retired modules and needs review.")
    for outcome in project["programme_outcomes"]:
        if outcome.get("kind") not in ("PO", "PSO") or not isinstance(outcome.get("statement"), str) or type(outcome.get("approved")) is not bool:
            errors.append("Programme outcomes need kind PO/PSO, a statement, and boolean approval.")
        elif outcome["approved"] and len(outcome["statement"].strip()) < 12:
            errors.append("Approved programme outcomes require meaningful statements.")
    for cell in project["matrix"]:
        if cell.get("co_id") not in coids or cell.get("outcome_id") not in poids:
            errors.append("Matrix references a missing CO or programme outcome.")
        if cell.get("status") == "approved" and (cell.get("co_id") not in active_coids or cell.get("outcome_id") not in active_poids):
            errors.append("Approved matrix relationship refers to retired sources and needs review.")
        for field in ("final_score", "suggested_score"):
            score = cell.get(field)
            if score is not None and (not _integer(score) or score not in range(4)):
                errors.append("Matrix contains an invalid score.")
        errors.extend(_valid_evidence(cell.get("evidence", []), project, include_archived=True))
        if "original_suggestion" in cell and not isinstance(cell["original_suggestion"], dict):
            errors.append("Original matrix suggestion must be an object.")
        if "suggestion_history" in cell and (not isinstance(cell["suggestion_history"], list) or any(not isinstance(v, dict) for v in cell["suggestion_history"])):
            errors.append("Matrix suggestion history must be a list of objects.")
        previous = []
        if isinstance(cell.get("original_suggestion"), dict):
            previous.append(cell["original_suggestion"])
        if isinstance(cell.get("suggestion_history"), list):
            previous.extend(v for v in cell["suggestion_history"] if isinstance(v, dict))
        for suggestion in previous:
            errors.extend(_optional_text_errors(suggestion, ("rationale", "source_fingerprint"), "Historical matrix suggestion"))
            score = suggestion.get("suggested_score")
            if score is not None and (not _integer(score) or score not in range(4)):
                errors.append("Historical matrix suggestion has an invalid score.")
            if "evidence" in suggestion:
                errors.extend(_valid_evidence(suggestion["evidence"], project, include_archived=True))
    for question in project["analysis_questions"]:
        if not isinstance(question.get("text"), str) or not _number(question.get("marks")) or question["marks"] < 0:
            errors.append("Analysis question text or marks are invalid.")
        if "number" in question and not isinstance(question["number"], str):
            errors.append("Analysis question number must be text.")
    analyses = project.get("analyses")
    if not isinstance(analyses, dict):
        errors.append("Analyses must be keyed by question ID.")
    else:
        active_qids = {q["id"] for q in project["analysis_questions"]}
        qids = active_qids | {q["id"] for q in archive.get("analysis_questions", [])}
        for ident, analysis in analyses.items():
            if ident not in qids or not isinstance(analysis, dict):
                errors.append("Analysis references an unknown question.")
                continue
            errors.extend(_analysis_shape_errors(analysis, "Question analysis"))
            if "final_co" in analysis and not isinstance(analysis["final_co"], str):
                errors.append("Analysis final CO must be text or empty.")
            elif analysis.get("final_co") and analysis["final_co"] not in coids:
                errors.append("Analysis references an unknown CO.")
            if analysis.get("status") == "approved" and (ident not in active_qids or analysis.get("final_co") not in active_coids):
                errors.append("Approved analysis refers to retired sources and needs review.")
            levels = analysis.get("final_bloom", [])
            if not isinstance(levels, list) or any(b not in BLOOM_LEVELS for b in levels):
                errors.append("Analysis has unsupported Bloom labels.")
    bp = project.get("blueprint")
    if not isinstance(bp, dict):
        return errors + ["Blueprint must be an object."]
    errors.extend(_optional_text_errors(bp, ("exam_type", "title", "duration", "date", "difficulty"), "Blueprint"))
    instructions = bp.get("instructions", "")
    if not isinstance(instructions, str) and (not isinstance(instructions, list) or any(not isinstance(v, str) for v in instructions)):
        errors.append("Blueprint instructions must be text or a list of text instructions.")
    if "acknowledgment" in bp and bp["acknowledgment"] is not None and not isinstance(bp["acknowledgment"], str):
        errors.append("Blueprint acknowledgment must be a fingerprint string or null.")
    if not isinstance(bp.get("sections", []), list):
        return errors + ["Blueprint sections must be a list."]
    if not _number(bp.get("target_marks")) or bp["target_marks"] <= 0:
        errors.append("Blueprint target marks must be positive.")
    # An unfinished blueprint is a valid saved draft; impossible values are not.
    if bp.get("sections"):
        errors.extend(validate_blueprint(bp))
    if not _string_ids(bp.get("module_ids", [])) or not _string_ids(bp.get("co_ids", [])):
        errors.append("Blueprint module and CO references must be ID lists.")
    elif any(m not in active_mids for m in bp.get("module_ids", [])) or any(c not in active_coids for c in bp.get("co_ids", [])):
        errors.append("Blueprint references missing modules or COs.")
    if not _string_ids(bp.get("bloom_levels", [])) or any(b not in BLOOM_LEVELS for b in bp.get("bloom_levels", [])):
        errors.append("Blueprint has unsupported Bloom levels.")
    section_ids = {s["id"] for s in bp.get("sections", [])} | {s["id"] for s in archive.get("sections", [])}
    slot_ids, known_slots = set(), set()
    if bp.get("sections") and not validate_blueprint(bp):
        known_slots.update(s["slot_id"] for s in build_slots(bp))
    for section in archive.get("sections", []):
        known_slots.update(s["slot_id"] for s in build_slots({"target_marks": 1, "sections": [section]}))
    for item in project["paper_questions"]:
        if not isinstance(item.get("text"), str):
            errors.append("Paper question text must be a string, including an empty manual draft.")
        errors.extend(_optional_text_errors(item, ("answer", "difficulty", "last_check_error"), "Paper question"))
        if not _number(item.get("marks")) or item["marks"] <= 0:
            errors.append("Paper question marks must be positive.")
        if not isinstance(item.get("co_id", ""), str):
            errors.append("Paper question CO must be text or empty.")
        elif item.get("co_id") and item["co_id"] not in coids:
            errors.append("Paper question references a missing CO.")
        if item.get("final_co") and (not isinstance(item["final_co"], str) or item["final_co"] not in coids):
            errors.append("Paper final CO references a missing outcome.")
        if item.get("status") == "approved" and (item.get("co_id") not in active_coids or any(m not in active_mids for m in item.get("module_ids", []))):
            errors.append("Approved paper question refers to retired sources and needs review.")
        if not _string_ids(item.get("module_ids", [])) or any(m not in mids for m in item.get("module_ids", [])):
            errors.append("Paper question references a missing module.")
        if not _string_ids(item.get("bloom_levels", [])) or any(b not in BLOOM_LEVELS for b in item.get("bloom_levels", [])):
            errors.append("Paper question has unsupported Bloom labels.")
        if "final_bloom" in item and (not _string_ids(item["final_bloom"]) or any(b not in BLOOM_LEVELS for b in item["final_bloom"])):
            errors.append("Paper question has unsupported final Bloom labels.")
        if type(item.get("locked", False)) is not bool:
            errors.append("Paper question lock must be boolean.")
        slot_id = item.get("slot_id")
        if not isinstance(slot_id, str) or not slot_id.strip():
            errors.append("Paper question slot ID must be nonempty text.")
        elif slot_id in slot_ids:
            errors.append("Paper contains duplicate slot IDs.")
        elif slot_id not in known_slots:
            errors.append("Paper question references an unknown current or historical slot.")
        else:
            slot_ids.add(slot_id)
        if "number" in item and (not isinstance(item["number"], str) or not item["number"].strip()):
            errors.append("Paper display number must be nonempty text.")
        if "section_id" in item and (not isinstance(item["section_id"], str) or item["section_id"] not in section_ids):
            errors.append("Paper question references an unknown current or historical section.")
        for field in ("parent_id", "choice_group"):
            if item.get(field) is not None and not isinstance(item[field], str):
                errors.append("Paper %s metadata must be text or null." % field)
        errors.extend(_valid_evidence(item.get("evidence", []), project, include_archived=True))
        for field, references in (("requested_co_ids", coids), ("requested_module_ids", mids), ("requested_bloom_levels", BLOOM_LEVELS)):
            values = item.get(field, [])
            if not _string_ids(values) or any(v not in references for v in values):
                errors.append("Paper " + field + " contains invalid or unknown references.")
        guide = item.get("marking_guide", [])
        if not isinstance(guide, list):
            errors.append("Paper marking guide must be a list.")
        elif guide:
            if any(not isinstance(g, dict) or not isinstance(g.get("criterion"), str) or not g["criterion"].strip()
                   or not _number(g.get("marks")) or g["marks"] <= 0 for g in guide):
                errors.append("Paper marking criteria need text and positive finite marks.")
            elif _number(item.get("marks")) and not math.isclose(sum(g["marks"] for g in guide), item["marks"]):
                errors.append("Paper marking guide total must equal question marks.")
        if "analysis" in item:
            errors.extend(_analysis_shape_errors(item["analysis"], "Paper question analysis"))
        if "analysis_history" in item:
            if not isinstance(item["analysis_history"], list):
                errors.append("Paper analysis history must be a list of analysis objects.")
            else:
                for historical in item["analysis_history"]:
                    errors.extend(_analysis_shape_errors(historical, "Historical paper analysis"))
    return errors
