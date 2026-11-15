"""Deterministic exports from the current project, without AI calls or credentials."""
from __future__ import annotations

import csv
import html
import io
import math
import re
from collections import defaultdict

import fitz
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


def _number(value):
    return f"{float(value):g}"


def _csv(headers, rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    # CSV cells beginning with formula characters are text, even in spreadsheet apps.
    for row in rows:
        writer.writerow(["'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value for value in row])
    return output.getvalue().encode("utf-8-sig")


def _evidence_text(evidence):
    return "; ".join(f"{item.get('module_id', '')}: {item.get('quote', '')}" for item in evidence or [])


def final_matrix_csv(project):
    """Only approved final values appear; blank means not approved, 0 means none."""
    cos = [co for co in project.get("approved_cos", []) if co.get("status", "approved") == "approved"]
    outcomes = project.get("programme_outcomes", [])
    lookup = {(cell["co_id"], cell["outcome_id"]): cell for cell in project.get("matrix", [])}
    rows = []
    for co in cos:
        values = []
        for outcome in outcomes:
            cell = lookup.get((co["id"], outcome["id"]), {})
            value = cell.get("final_score") if cell.get("status") == "approved" else ""
            values.append("" if value is None else value)
        rows.append([co["id"], co["statement"], *values])
    return _csv(["CO ID", "CO statement", *[o["id"] for o in outcomes]], rows)


def matrix_justifications_csv(project):
    headers = ["CO ID", "Outcome ID", "AI suggested score", "Final score", "Review status", "Justification", "Syllabus references", "Professor notes", "Original AI score", "Original AI justification", "Original AI references", "Previous suggestion count"]
    rows = [[c.get("co_id", ""), c.get("outcome_id", ""), c.get("suggested_score", ""), c.get("final_score", "") if c.get("status") == "approved" else "", c.get("status", "draft"), c.get("rationale", ""), _evidence_text(c.get("evidence")), c.get("notes", ""), c.get("original_suggestion", c).get("suggested_score", ""), c.get("original_suggestion", c).get("rationale", ""), _evidence_text(c.get("original_suggestion", c).get("evidence")), len(c.get("suggestion_history", []))] for c in project.get("matrix", [])]
    return _csv(headers, rows)


def analysis_csv(project, approved_only=True):
    """Export the authoritative latest professor labels, with explicit validation."""
    rows = []
    valid_cos = {co["id"] for co in project.get("approved_cos", []) if co.get("status", "approved") == "approved"}
    for question in project.get("analysis_questions", []):
        result = project.get("analyses", {}).get(question["id"])
        if not result or (approved_only and result.get("status") != "approved"):
            continue
        co, blooms = result.get("final_co"), result.get("final_bloom", [])
        if co not in valid_cos or not isinstance(blooms, list) or not blooms or any(b not in {"L1", "L2", "L3", "L4", "L5", "L6"} for b in blooms):
            raise ValueError(f"Question {question.get('number', question['id'])}: choose a valid final CO and Bloom level before export.")
        rows.append([question.get("number", ""), question["text"], question.get("marks", 0), co, ", ".join(blooms), result.get("status", "draft"), result.get("notes", "")])
    return _csv(["Question Number", "Question", "Marks", "Final CO", "Final Bloom Level", "Review status", "Professor notes"], rows)


def _paper_questions(project):
    from validation import build_slots, validate_blueprint
    errors = validate_blueprint(project["blueprint"])
    if errors:
        raise ValueError("Invalid blueprint: " + "; ".join(errors))
    slots = build_slots(project["blueprint"])
    raw_questions = project.get("paper_questions", [])
    questions = {q.get("slot_id", q.get("id")): q for q in raw_questions}
    if len(questions) != len(raw_questions):
        raise ValueError("The paper contains duplicate question slots.")
    ordered = []
    for slot in slots:
        question = questions.get(slot.get("slot_id", slot["id"]))
        if not question or not str(question.get("text", "")).strip():
            raise ValueError(f"Question {slot.get('number', slot['id'])} is empty. Complete every blueprint slot before exporting.")
        if question.get("marks") != slot["marks"]:
            raise ValueError(f"Question {slot.get('number', slot['id'])} marks differ from the blueprint.")
        ordered.append({**question, **{key: slot[key] for key in ("number", "section_id", "parent_id", "choice_group", "alternative", "parent_marks") if key in slot}})
    return ordered


def _maximum_text(project):
    from validation import calculate_marks
    marks = calculate_marks(project["blueprint"])
    if marks["minimum"] != marks["maximum"]:
        return f"Attemptable marks: {_number(marks['minimum'])}–{_number(marks['maximum'])} (depends on choices)"
    return f"Maximum marks: {_number(marks['maximum'])}"


def _rule_text(section):
    mode = section.get("mode", "compulsory")
    if mode == "any":
        return f"Answer any {section['attempt']} of {section['count']} questions."
    if mode == "either_or":
        return "Answer one alternative from each either/or pair."
    return "Answer all questions."


def paper_blocks(project, faculty=False, include_answers=False):
    """Shared content for preview, PDF and DOCX; student content is allowlisted."""
    questions = _paper_questions(project)
    course, blueprint = project.get("course", {}), project["blueprint"]
    blocks = [("title", blueprint.get("title") or "Question Paper")]
    if project.get("presentation_demo"):
        blocks.append(("subtitle", "DEMONSTRATION SAMPLE — illustrative presentation data"))
    if faculty:
        blocks.append(("subtitle", "FACULTY REVIEW COPY"))
    blocks.append(("metadata", " · ".join(str(course.get(key, "")) for key in ("code", "name") if course.get(key))))
    details = [f"{key.replace('_', ' ').title()}: {course[key]}" for key in ("department", "programme", "semester", "academic_year") if course.get(key)]
    if details:
        blocks.append(("metadata", " · ".join(details)))
    blocks.append(("metadata", " · ".join(x for x in [f"Date: {blueprint['date']}" if blueprint.get("date") else "", f"Duration: {blueprint['duration']}" if blueprint.get("duration") else "", _maximum_text(project)] if x)))
    instructions = blueprint.get("instructions", [])
    if isinstance(instructions, str):
        instructions = [line.strip() for line in instructions.splitlines() if line.strip()]
    if instructions:
        blocks.append(("heading", "Instructions"))
        blocks.extend(("instruction", str(line)) for line in instructions)
    by_section = defaultdict(list)
    for question in questions:
        by_section[question["section_id"]].append(question)
    for section in blueprint.get("sections", []):
        blocks.append(("heading", section.get("title") or "Section"))
        blocks.append(("instruction", _rule_text(section)))
        if section.get("instructions") and str(section["instructions"]).strip() != _rule_text(section):
            blocks.append(("instruction", str(section["instructions"])))
        previous_group, previous_alternative, previous_parent = None, None, None
        for question in by_section[section["id"]]:
            group = question.get("choice_group")
            alternative = question.get("alternative")
            if group and group == previous_group and alternative != previous_alternative:
                blocks.append(("choice", "OR"))
            previous_group, previous_alternative = group, alternative
            parent = question.get("parent_id")
            if parent and parent != previous_parent:
                parent_number = str(question.get("number", "")).split("(")[0]
                blocks.append(("parent", f"Question {parent_number} — total {_number(question.get('parent_marks', question['marks']))} marks"))
            previous_parent = parent
            number = question.get("number", "")
            blocks.append(("question", f"{number}. {question['text']}  [{_number(question['marks'])} marks]"))
            if faculty:
                blooms = question.get("final_bloom", question.get("bloom_levels", []))
                co = question.get("final_co", question.get("co_id", ""))
                blocks.append(("faculty", f"Final labels: {co or 'Unassigned'} · {', '.join(blooms) or 'Unassigned'} · Status: {question.get('status', 'draft')}"))
                blocks.append(("faculty", "Requested targets: CO " + ", ".join(question.get("requested_co_ids", [])) + "; Bloom " + ", ".join(question.get("requested_bloom_levels", []))))
                if question.get("module_ids"):
                    blocks.append(("faculty", "Syllabus portions: " + ", ".join(question["module_ids"])))
                if question.get("rationale"):
                    blocks.append(("faculty", "Rationale: " + question["rationale"]))
                for evidence in question.get("evidence", []):
                    blocks.append(("faculty", f"Evidence {evidence.get('module_id', '')}: {evidence.get('quote', '')}"))
                if question.get("notes"):
                    blocks.append(("faculty", "Professor review notes: " + question["notes"]))
                analysed = question.get("analysis")
                if analysed:
                    suggestion = analysed.get("suggestion", analysed)
                    blocks.append(("faculty", "Independent analysis suggestion: " + str(suggestion.get("co", "")) + " · " + ", ".join(suggestion.get("bloom_levels", []))))
                if include_answers and (question.get("answer") or question.get("marking_guide")):
                    blocks.append(("answer", "DRAFT ANSWER / MARKING GUIDE — faculty review required"))
                    if question.get("answer"):
                        blocks.append(("faculty", str(question["answer"])))
                    guide = question.get("marking_guide", [])
                    if guide:
                        if any(not isinstance(item, dict) or type(item.get("marks")) not in (int, float) or not math.isfinite(item["marks"]) or item["marks"] <= 0 for item in guide):
                            raise ValueError(f"Question {number}: marking-guide criteria need positive numeric marks.")
                        total = sum(item["marks"] for item in guide)
                        if abs(total - question["marks"]) > 1e-6:
                            raise ValueError(f"Question {number}: marking-guide marks must total {_number(question['marks'])}.")
                        blocks.extend(("faculty", f"{item.get('criterion', '')}: {_number(item['marks'])} marks") for item in guide)
    if faculty:
        blocks.append(("heading", "Coverage and review"))
        blocks.append(("faculty", "Coverage below counts printed questions. Optional alternatives do not guarantee that every student attempts every listed topic or outcome."))
        for dimension, values in coverage_summary(project).items():
            for value, counts in values.items():
                blocks.append(("faculty", f"{dimension}: {value} — printed {_number(counts['printed_marks'])} marks; guaranteed at least {_number(counts['guaranteed_marks'])} marks under attempt rules."))
    return blocks


def paper_docx(project, faculty=False, include_answers=False):
    blocks = paper_blocks(project, faculty, include_answers)
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Inches(8.27), Inches(11.69)
    section.top_margin = section.bottom_margin = Inches(0.65)
    section.left_margin = section.right_margin = Inches(0.7)
    normal = document.styles["Normal"]
    normal.font.name, normal.font.size = "Calibri", Pt(10.5)
    normal.paragraph_format.space_after = Pt(7)
    normal.paragraph_format.line_spacing = 1.12
    for style_name in ("Title", "Subtitle", "Heading 1"):
        document.styles[style_name].font.color.rgb = RGBColor.from_string("183153")
    document.styles["Title"].font.size = Pt(19)
    document.styles["Heading 1"].font.size = Pt(13)
    for kind, text in blocks:
        style = {"title": "Title", "subtitle": "Subtitle", "heading": "Heading 1"}.get(kind)
        paragraph = document.add_paragraph(text, style)
        if re.search(r"\S{60}", text):
            # Preserve the exact source while allowing long URLs/identifiers to
            # wrap. OOXML's wordWrap=off permits character-level breaks:
            # https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.wordwrap
            wrap = OxmlElement("w:wordWrap")
            wrap.set(qn("w:val"), "0")
            paragraph._p.get_or_add_pPr().append(wrap)
        if kind in ("title", "subtitle", "metadata", "choice"):
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if kind == "question":
            paragraph.paragraph_format.space_before = Pt(10)
            paragraph.paragraph_format.widow_control = True
        if kind in ("heading", "answer", "parent"):
            paragraph.paragraph_format.keep_with_next = True
        if kind in ("faculty", "metadata"):
            for run in paragraph.runs:
                run.font.size = Pt(9)
        if kind in ("choice", "answer"):
            for run in paragraph.runs:
                run.bold = True
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer.add_run("Page ")
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def paper_pdf(project, faculty=False, include_answers=False):
    blocks = paper_blocks(project, faculty, include_answers)
    body = []
    for index, (kind, text) in enumerate(blocks):
        tag = "h1" if kind == "title" else "h2" if kind == "heading" else "p"
        # MuPDF Story can clip a token wider than its layout box. Optional
        # zero-width breaks preserve all URL/identifier characters across lines.
        def markup_text(value):
            wrapped = re.sub(r"\S{60,}", lambda match: "\u200b".join(match[0][i:i + 35] for i in range(0, len(match[0]), 35)), value)
            return f'<{tag} class="{kind}">{html.escape(wrapped).replace(chr(10), "<br>")}</{tag}>'
        markup = markup_text(text)
        # A borderless row keeps a short guide label with its first answer or
        # criterion. Story ignores keep-with-next on ordinary paragraphs.
        if kind == "answer" and index + 1 < len(blocks):
            markup = '<table class="guide-start"><tr><td>' + markup
        if index and blocks[index - 1][0] == "answer":
            # Only a short first fragment belongs in the unsplittable table
            # row. Long answers then flow as ordinary paragraphs across pages.
            if len(text) > 240:
                boundary = text.rfind(" ", 0, 180)
                boundary = boundary if boundary > 0 else 180
                markup = markup_text(text[:boundary]) + "</td></tr></table>" + markup_text(text[boundary:])
            else:
                markup += "</td></tr></table>"
        body.append(markup)
    css = """body {font-family: sans-serif; font-size: 10.5pt; line-height: 1.35; color: #172338;} h1 {font-size: 18pt; text-align:center; margin:0 0 8pt;} h2 {font-size:13pt; margin:16pt 0 6pt; page-break-after:avoid;} p {margin:0 0 7pt;} .metadata,.subtitle,.choice {text-align:center;} .metadata,.faculty {font-size:9pt;} .question {margin-top:12pt;} .answer,.choice,.subtitle {font-weight:bold;} .guide-start {width:100%;border-collapse:collapse;} .guide-start td {padding:0;}"""
    story = fitz.Story(html="<html><body>" + "".join(body) + "</body></html>", user_css=css)
    output = io.BytesIO()
    writer = fitz.DocumentWriter(output)
    page_rect = fitz.Rect(0, 0, 595, 842)
    content_rect = fitz.Rect(48, 48, 547, 794)
    story.write(writer, lambda _rect_num, _filled: (page_rect, content_rect, None))
    writer.close()
    with fitz.open(stream=output.getvalue(), filetype="pdf") as pdf:
        for index, page in enumerate(pdf):
            page.insert_text((48, 824), f"Page {index + 1} of {len(pdf)}", fontsize=8, color=(0.3, 0.3, 0.3))
        return pdf.tobytes(garbage=4, deflate=True)


def coverage_summary(project):
    """Conservative marks coverage under each independent section's choice rule.

    Each module/Bloom membership receives the question's marks, so multi-label
    totals overlap. Guarantees are minima over allowable attempts, not attainment.
    """
    from validation import build_slots, validate_blueprint
    if validate_blueprint(project.get("blueprint", {})):
        return {"Modules": {}, "COs": {}, "Bloom levels": {}}
    current_slots = {slot["slot_id"]: slot for slot in build_slots(project["blueprint"])}
    questions = [{**q, **{k: current_slots[q.get("slot_id", q["id"])][k] for k in ("parent_id", "choice_group", "section_id")}}
                 for q in project.get("paper_questions", []) if q.get("slot_id", q["id"]) in current_slots]
    result = {"Modules": {}, "COs": {}, "Bloom levels": {}}
    for dimension, field in (("Modules", "module_ids"), ("COs", "co_id"), ("Bloom levels", "bloom_levels")):
        values = sorted({value for q in questions for value in (q.get(field, []) if field != "co_id" else [q.get(field)]) if value})
        for value in values:
            printed = guaranteed = 0.0
            for section in project.get("blueprint", {}).get("sections", []):
                section_qs = [q for q in questions if q.get("section_id") == section["id"]]
                units = defaultdict(list)
                for question in section_qs:
                    units[question.get("parent_id") or question.get("slot_id") or question["id"]].append(question)
                totals = []
                alternatives = defaultdict(list)
                for unit_id, members in units.items():
                    amount = sum(q.get("marks", 0) for q in members if value in (q.get(field, []) if field != "co_id" else [q.get(field)]))
                    printed += amount
                    totals.append(amount)
                    alternatives[members[0].get("choice_group") or unit_id].append(amount)
                mode = section.get("mode", "compulsory")
                if mode == "any":
                    guaranteed += sum(sorted(totals)[:section.get("attempt", 0)])
                elif mode == "either_or":
                    guaranteed += sum(min(amounts) for amounts in alternatives.values())
                else:
                    guaranteed += sum(totals)
            result[dimension][value] = {"printed_marks": printed, "guaranteed_marks": guaranteed}
    return result
