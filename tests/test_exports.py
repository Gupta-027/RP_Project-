"""Content separation, current edits, choice coverage and paginated export checks."""
import csv
import io
import re
import unittest

import fitz
from docx import Document

from export_utils import (analysis_csv, coverage_summary, final_matrix_csv,
                          matrix_justifications_csv, paper_blocks, paper_docx,
                          paper_pdf)
from validation import build_slots


def export_project_fixture(long=False):
    blueprint = {
        "exam_type": "Custom", "title": "Human-centred Design Assessment",
        "duration": "90 minutes", "date": "2026-11-16", "target_marks": 30,
        "module_ids": ["M1", "M2"], "co_ids": ["CO1", "CO2"],
        "bloom_levels": ["L2", "L4"], "difficulty": "Moderate",
        "instructions": ["Use neat labelled diagrams where necessary."],
        "sections": [
            {"id": "S1", "title": "Section A", "instructions": "Use examples.", "mode": "any", "count": 3, "attempt": 2, "marks": 5, "subquestions": []},
            {"id": "S2", "title": "Section B", "instructions": "", "mode": "either_or", "count": 2, "attempt": 1, "marks": 10, "subquestions": []},
            {"id": "S3", "title": "Section C", "instructions": "", "mode": "compulsory", "count": 2, "attempt": 2, "marks": 5, "subquestions": [{"label": "a", "marks": 2}, {"label": "b", "marks": 3}]},
        ], "acknowledgment": None,
    }
    project = {
        "schema_version": 1, "id": "sample-design-assessment",
        "course": {"code": "DS3101", "name": "Human-centred Design", "department": "Design", "programme": "B.Des", "semester": "5", "academic_year": "2026–27"},
        "syllabus": "Design quality balances aesthetics, function and usability. Design and society include public art and social awareness.",
        "modules": [{"id": "M1", "title": "Design quality", "text": "Design quality balances aesthetics, function and usability."}, {"id": "M2", "title": "Design and society", "text": "Design and society include public art and social awareness."}],
        "co_drafts": [],
        "approved_cos": [{"id": "CO1", "statement": "Explain relationships between aesthetics, function and usability.", "status": "approved", "module_ids": ["M1"], "bloom_levels": ["L2"]}, {"id": "CO2", "statement": "Analyse how design responds to social contexts.", "status": "approved", "module_ids": ["M2"], "bloom_levels": ["L4"]}],
        "programme_outcomes": [{"id": "PO1", "kind": "PO", "statement": "Illustrative sample: apply design knowledge to a concrete problem.", "approved": True}],
        "matrix": [{"co_id": "CO1", "outcome_id": "PO1", "suggested_score": 3, "final_score": 0, "rationale": "Professor found insufficient demonstrated alignment.", "status": "approved", "evidence": []}],
        "analysis_questions": [{"id": "AQ1", "number": "1(a)", "text": "Explain the Design Quality Triangle.", "marks": 3}],
        "analyses": {"AQ1": {"suggestion": {"co": "CO1", "bloom_levels": ["L2"]}, "final_co": "CO2", "final_bloom": ["L4", "L5"], "status": "approved", "notes": "Professor correction"}},
        "blueprint": blueprint, "paper_questions": [],
    }
    for index, slot in enumerate(build_slots(blueprint)):
        co, module, bloom = ("CO1", "M1", "L2") if index % 2 == 0 else ("CO2", "M2", "L4")
        text = f"Using an everyday product of your choice, explain how design decision {index + 1} balances aesthetics, function and usability."
        if long:
            text += " " + ("Discuss an example in its social context, stating your assumptions and explaining the relationship between the design criteria and the user's needs. " * 22)
        project["paper_questions"].append({
            **slot, "text": text, "co_id": co, "bloom_levels": [bloom],
            "module_ids": [module], "difficulty": "Moderate", "rationale": "PRIVATE_RATIONALE",
            "evidence": [{"module_id": module, "quote": project["modules"][0 if module == "M1" else 1]["text"]}],
            "status": "draft", "locked": False, "answer": "PRIVATE_ANSWER",
            "notes": "PRIVATE_REVIEW_NOTE", "requested_co_ids": [co], "requested_bloom_levels": [bloom],
            "marking_guide": [{"criterion": "Relevant explanation with evidence", "marks": slot["marks"]}],
        })
    return project


class ExportTests(unittest.TestCase):
    def test_latest_professor_edits_in_analysis_and_matrix(self):
        project = export_project_fixture()
        row = list(csv.DictReader(io.StringIO(analysis_csv(project).decode("utf-8-sig"))))[0]
        self.assertEqual(row["Final CO"], "CO2")
        self.assertEqual(row["Final Bloom Level"], "L4, L5")
        matrix = list(csv.DictReader(io.StringIO(final_matrix_csv(project).decode("utf-8-sig"))))
        self.assertEqual(matrix[0]["PO1"], "0")
        project["matrix"][0]["status"] = "needs_review"
        matrix = list(csv.DictReader(io.StringIO(final_matrix_csv(project).decode("utf-8-sig"))))
        self.assertEqual(matrix[0]["PO1"], "")
        self.assertIn("3", matrix_justifications_csv(project).decode())

    def test_student_excludes_internal_content_and_uses_actual_marks(self):
        project = export_project_fixture()
        project["blueprint"]["target_marks"] = 100
        for producer in (paper_pdf, paper_docx):
            blob = producer(project, include_answers=True)
            if producer is paper_pdf:
                with fitz.open(stream=blob, filetype="pdf") as pdf:
                    text = "\n".join(page.get_text() for page in pdf)
            else:
                text = "\n".join(p.text for p in Document(io.BytesIO(blob)).paragraphs)
            self.assertIn("Maximum marks: 30", text)
            self.assertNotIn("100", text)
            for private in ("PRIVATE_ANSWER", "PRIVATE_RATIONALE", "PRIVATE_REVIEW_NOTE", "Requested targets", "Final labels"):
                self.assertNotIn(private, text)
            self.assertIn("OR", text)
            self.assertIn("total 5 marks", text)

    def test_faculty_answers_labelled_draft_and_marks_validated(self):
        project = export_project_fixture()
        blocks = paper_blocks(project, faculty=True, include_answers=True)
        text = "\n".join(value for _, value in blocks)
        self.assertIn("PRIVATE_ANSWER", text)
        self.assertIn("DRAFT ANSWER / MARKING GUIDE", text)
        project["paper_questions"][0]["marking_guide"][0]["marks"] = 999
        with self.assertRaisesRegex(ValueError, "marking-guide"):
            paper_docx(project, faculty=True, include_answers=True)

    def test_optional_coverage_is_not_guaranteed(self):
        project = export_project_fixture()
        summary = coverage_summary(project)
        self.assertGreater(summary["COs"]["CO1"]["printed_marks"], summary["COs"]["CO1"]["guaranteed_marks"])
        # Section A has two CO1 questions and one CO2 question: any two guarantee
        # one CO1 question, while either/or B guarantees no particular CO.
        self.assertEqual(summary["COs"]["CO1"]["guaranteed_marks"], 5 + 3 + 3)

    def test_unequal_choices_export_range(self):
        project = export_project_fixture()
        section = project["blueprint"]["sections"][0]
        section["question_marks"] = [3, 5, 7]
        for question, slot in zip(project["paper_questions"], build_slots(project["blueprint"])):
            question["marks"] = slot["marks"]
        self.assertIn("Attemptable marks: 28–32", "\n".join(text for _, text in paper_blocks(project)))

    def test_pagination_and_question_wrapping(self):
        project = export_project_fixture(long=True)
        blob = paper_pdf(project)
        with fitz.open(stream=blob, filetype="pdf") as pdf:
            self.assertGreater(len(pdf), 3)
            text = "\n".join(page.get_text() for page in pdf)
            self.assertIn(project["paper_questions"][-1]["number"] + ".", text)
            self.assertEqual(re.sub(r"\s+", " ", text).count("balances aesthetics, function and usability"), len(project["paper_questions"]))
            for page in pdf:
                for x0, y0, x1, y1, *_ in page.get_text("blocks"):
                    self.assertGreaterEqual(x0, 47)
                    self.assertLessEqual(x1, 548)
                    self.assertGreaterEqual(y0, 40)
                    self.assertLessEqual(y1, 838)
        doc = Document(io.BytesIO(paper_docx(project)))
        self.assertEqual(len(doc.tables), 0)  # Long questions can flow freely.
        self.assertIn(project["paper_questions"][-1]["number"] + ".", "\n".join(p.text for p in doc.paragraphs))
        self.assertEqual(doc.sections[0].page_width.twips, 11909)

    def test_invalid_labels_and_missing_questions_rejected(self):
        project = export_project_fixture()
        project["analyses"]["AQ1"]["final_bloom"] = ["L9"]
        with self.assertRaisesRegex(ValueError, "valid final CO"):
            analysis_csv(project)
        project["paper_questions"].pop()
        with self.assertRaisesRegex(ValueError, "empty"):
            paper_pdf(project)

    def test_subquestion_choice_separator_and_retained_obsolete_items(self):
        project = export_project_fixture()
        section = project["blueprint"]["sections"][1]
        section["subquestions"] = [{"label": "a", "marks": 4}, {"label": "b", "marks": 6}]
        prior = project["paper_questions"][3]
        active_slots = build_slots(project["blueprint"])
        current = {q["slot_id"]: q for q in project["paper_questions"]}
        project["paper_questions"] = [
            {**current.get(slot["slot_id"], prior), **slot} for slot in active_slots
        ]
        project["paper_questions"].append({**prior, "id": "OBSOLETE", "slot_id": "OBSOLETE", "text": "OBSOLETE_TEXT"})
        blocks = paper_blocks(project)
        self.assertEqual(sum(text == "OR" for _, text in blocks), 1)
        text = "\n".join(value for _, value in blocks)
        self.assertIn("Question 4A", text)
        self.assertIn("Question 4B", text)
        self.assertNotIn("OBSOLETE_TEXT", text)

    def test_long_unbroken_url_is_preserved_and_wraps(self):
        project = export_project_fixture()
        url = "https://example.edu/" + "longreference" * 60
        question = "Read this source: " + url + " then evaluate the argument."
        project["paper_questions"][0]["text"] = question
        with fitz.open(stream=paper_pdf(project), filetype="pdf") as pdf:
            text = "".join(page.get_text() for page in pdf)
            self.assertIn(url, re.sub(r"\s+", "", text).replace("\u200b", ""))
            self.assertTrue(all(block[2] <= 548 for page in pdf for block in page.get_text("blocks")))
        doc = Document(io.BytesIO(paper_docx(project)))
        paragraph = next(p for p in doc.paragraphs if url in p.text)
        self.assertIn(question, paragraph.text)
        self.assertIn('w:wordWrap w:val="0"', paragraph._p.xml)

    def test_faculty_guide_label_keeps_first_answer_and_long_answers_flow(self):
        project = export_project_fixture(long=True)
        with fitz.open(stream=paper_pdf(project, faculty=True, include_answers=True), filetype="pdf") as pdf:
            for page in pdf:
                lines = [line for line in page.get_text().splitlines() if not line.startswith("Page ")]
                self.assertFalse(lines[-1].startswith("DRAFT ANSWER"))
        project = export_project_fixture()
        project["paper_questions"][0]["answer"] = "Long answer detail. " * 1500 + "END_OF_LONG_GUIDE"
        with fitz.open(stream=paper_pdf(project, faculty=True, include_answers=True), filetype="pdf") as pdf:
            text = "\n".join(page.get_text() for page in pdf)
            self.assertIn("END_OF_LONG_GUIDE", text)
            self.assertIn(project["paper_questions"][-1]["number"] + ".", text)


if __name__ == "__main__":
    unittest.main()
