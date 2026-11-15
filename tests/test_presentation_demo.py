"""Prepared presentation fixtures are valid, labelled and usable without AI."""
import io
import unittest
from unittest.mock import patch

import fitz
from docx import Document

from demo_project import build_presentation_demo
from export_utils import paper_pdf, paper_docx, final_matrix_csv, analysis_csv
from paper_service import generation_setup_issues
from project_state import export_project, import_project, refresh_dependencies
from validation import (validate_project, validate_generated_items, validate_matrix_cell,
                        build_slots, calculate_marks, can_generate)


class PresentationDemoTests(unittest.TestCase):
    def test_complete_project_has_traceable_valid_data_and_exact_marks(self):
        p = build_presentation_demo()
        self.assertFalse(validate_project(p))
        self.assertFalse(generation_setup_issues(p))
        self.assertEqual(len(p["approved_cos"]), 3)
        self.assertEqual(len(p["co_drafts"]), 1)
        self.assertNotIn("CO4", p["blueprint"]["co_ids"])
        self.assertTrue(all(o["statement"].startswith("[Illustrative demo]") for o in p["programme_outcomes"]))
        self.assertEqual(len(p["programme_outcomes"]), 13)
        self.assertEqual(len(p["matrix"]), 39)
        self.assertTrue(any(c["final_score"] == 0 for c in p["matrix"]))
        for cell in p["matrix"]:
            self.assertFalse(validate_matrix_cell(cell, p))
        self.assertFalse(validate_generated_items(p["paper_questions"], build_slots(p["blueprint"]), p))
        marks = calculate_marks(p["blueprint"])
        self.assertEqual((marks["printed"], marks["maximum"], marks["target"]), (30, 30, 30))
        self.assertTrue(can_generate(p["blueprint"])[0])
        self.assertEqual(sum(q["locked"] for q in p["paper_questions"]), 4)
        self.assertEqual(p["paper_questions"][1]["status"], "needs_review")
        self.assertEqual(p["paper_questions"][5]["status"], "draft")

    def test_example_suggestions_do_not_invent_model_measurements(self):
        p = build_presentation_demo()
        for analysis in p["analyses"].values():
            result = analysis["suggestion"]
            self.assertEqual(result["provenance"], "prepared_demo")
            self.assertEqual(result["confidence"], "Not measured (demo)")
            self.assertEqual(result["total_votes"], 0)
            self.assertFalse(result["co_ranking"])
            self.assertFalse(result["syllabus_chunks"])
        corrected = p["analyses"]["AQ3"]
        self.assertNotEqual(corrected["suggestion"]["bloom_levels"], corrected["final_bloom"])
        overridden = next(c for c in p["matrix"] if (c["co_id"], c["outcome_id"]) == ("CO1", "PO3"))
        self.assertEqual(overridden["suggested_score"], 2)
        self.assertEqual(overridden["final_score"], 1)
        self.assertEqual(overridden["original_suggestion"]["suggested_score"], 2)

    def test_demo_exports_without_ai_and_keeps_provenance_after_roundtrip(self):
        with patch("rag_pipeline.call_llm", side_effect=AssertionError("No AI in demo")) as ai, \
             patch("rag_pipeline.embed_texts", side_effect=AssertionError("No embeddings in demo")) as embedding, \
             patch("requests.post", side_effect=AssertionError("No network in demo")) as network:
            p = build_presentation_demo()
            p["paper_questions"][5]["text"] = "Propose a public art concept encouraging reuse on a college campus, and justify the design."
            refresh_dependencies(p)
            restored = import_project(export_project(p))
            self.assertTrue(restored["presentation_demo"])
            self.assertEqual(restored["paper_questions"][5]["text"], p["paper_questions"][5]["text"])
            student_pdf = paper_pdf(restored)
            student_docx = paper_docx(restored)
            faculty_docx = paper_docx(restored, faculty=True, include_answers=True)
            with fitz.open(stream=student_pdf, filetype="pdf") as pdf:
                text = "\n".join(page.get_text() for page in pdf)
            self.assertIn("DEMONSTRATION SAMPLE", text)
            self.assertIn("Maximum marks: 30", text)
            self.assertIn("encouraging reuse", text)
            self.assertNotIn("marking guide", text.lower())
            student_text = "\n".join(p.text for p in Document(io.BytesIO(student_docx)).paragraphs)
            faculty_text = "\n".join(p.text for p in Document(io.BytesIO(faculty_docx)).paragraphs)
            self.assertIn("DEMONSTRATION SAMPLE", student_text)
            self.assertNotIn("DRAFT ANSWER", student_text)
            self.assertIn("DRAFT ANSWER / MARKING GUIDE", faculty_text)
            self.assertIn("CO1", final_matrix_csv(restored).decode("utf-8-sig"))
            self.assertIn("Prepared correction", analysis_csv(restored).decode("utf-8-sig"))
            ai.assert_not_called()
            embedding.assert_not_called()
            network.assert_not_called()

    def test_invalid_demo_flag_is_rejected_on_import(self):
        p = build_presentation_demo()
        p["presentation_demo"] = "true"
        with self.assertRaisesRegex(ValueError, "demo flag must be boolean"):
            import_project(export_project(p))


if __name__ == "__main__":
    unittest.main()
