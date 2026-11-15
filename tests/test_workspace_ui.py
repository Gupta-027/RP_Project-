"""Streamlit interaction checks with all AI/network operations disabled."""
import csv
import io
import json
import os
from copy import deepcopy
from contextlib import ExitStack
from pathlib import Path
import unittest
from unittest.mock import patch

import fitz
from docx import Document
from streamlit.testing.v1 import AppTest

from export_utils import analysis_csv
from project_state import (export_project, import_project, new_project,
                           refresh_dependencies)
from ui_workspace import PAGES


APP = Path(__file__).resolve().parents[1] / "app.py"


def control(elements, label):
    return next(element for element in elements if element.label == label)


def new_course_fixture():
    project = new_project()
    project["course"].update(code="UX3201", name="Accessible Interface Design")
    project["syllabus"] = "Module 1: Accessible interfaces\nEvaluate colour contrast, keyboard interaction and readable labels in interface prototypes."
    project["modules"] = [{"id": "M1", "title": "Accessible interfaces", "text": project["syllabus"]}]
    project["approved_cos"] = [
        {"id": "CO1", "statement": "Evaluate interface accessibility using contrast and keyboard criteria.", "module_ids": ["M1"], "bloom_levels": ["L5"], "status": "approved", "evidence": [], "rationale": "Professor entry."},
        {"id": "CO2", "statement": "Analyse interface labels and justify readable alternatives.", "module_ids": ["M1"], "bloom_levels": ["L4", "L5"], "status": "approved", "evidence": [], "rationale": "Professor entry."},
    ]
    bp = project["blueprint"]
    bp.update(exam_type="Custom", title="Accessible interfaces review", module_ids=["M1"], co_ids=["CO1"], bloom_levels=["L4", "L5"], target_marks=30)
    bp["sections"] = [{"id": "S1", "title": "Section A", "instructions": "Answer all questions.", "mode": "compulsory", "count": 1, "attempt": 1, "marks": 5, "question_marks": [], "subquestions": []}]
    refresh_dependencies(project)
    return project


class WorkspaceInteractionTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}))
        self.stack.enter_context(patch("dotenv.load_dotenv"))
        self.stack.enter_context(patch("streamlit.secrets", {}))
        self.ai = self.stack.enter_context(patch("rag_pipeline.call_llm", side_effect=AssertionError("Unexpected live AI action")))
        self.embedding = self.stack.enter_context(patch("rag_pipeline.embed_texts", side_effect=AssertionError("Unexpected model load")))
        self.network = self.stack.enter_context(patch("requests.post", side_effect=AssertionError("Unexpected network request")))

    def tearDown(self):
        self.ai.assert_not_called()
        self.embedding.assert_not_called()
        self.network.assert_not_called()

    def start(self, project=None):
        app = AppTest.from_file(str(APP)).run(timeout=20)
        self.assertEqual(len(app.exception), 0)
        if project:
            app.session_state.project = project
            app.session_state.ui_epoch += 1
            app.run(timeout=20)
        return app

    def navigate(self, app, name):
        control(app.radio, "Workspace").set_value(name).run(timeout=20)
        self.assertEqual(len(app.exception), 0, [str(error.value) for error in app.exception])
        self.assertEqual(app.title[0].value, name)

    def press(self, app, label):
        control(app.button, label).click().run(timeout=20)
        self.assertEqual(len(app.exception), 0, [str(error.value) for error in app.exception])

    def test_id2103_sample_all_workspace_sections_and_manual_approval(self):
        app = self.start()
        self.press(app, "Load ID2103 sample course")
        self.assertEqual(app.session_state.project["course"]["code"], "ID2103")
        self.assertEqual(len(app.session_state.project["modules"]), 3)
        self.assertEqual(len(app.session_state.project["analysis_questions"]), 7)
        for page in PAGES:
            self.navigate(app, page)
        self.navigate(app, "Course Outcomes")
        self.press(app, "Approve outcome")
        self.assertEqual(app.session_state.project["approved_cos"][0]["id"], "CO1")
        self.navigate(app, "Course & Syllabus")
        self.navigate(app, "Course Outcomes")
        self.assertEqual(app.session_state.project["approved_cos"][0]["status"], "approved")

    def test_one_click_presentation_demo_fills_every_page_exports_and_restores_work(self):
        app = self.start(new_course_fixture())
        self.navigate(app, "Build Question Paper")
        previous = deepcopy(app.session_state.project)
        app.session_state["generation_failures"] = {"old-slot": "Old subject failure"}
        app.session_state["extracted_questions"] = "Previous subject's extracted text."
        self.press(app, "Load presentation demo")
        self.assertEqual(app.title[0].value, "Review & Export")
        p = app.session_state.project
        self.assertTrue(p["presentation_demo"])
        self.assertEqual(p["course"]["code"], "ID2103")
        self.assertEqual(len(p["approved_cos"]), 3)
        self.assertEqual(len(p["matrix"]), 39)
        self.assertEqual(len(p["analyses"]), 7)
        self.assertEqual(len(p["paper_questions"]), 6)
        self.assertTrue(any("staged approvals" in item.value for item in app.info))
        self.assertNotIn("generation_failures", app.session_state)
        self.assertNotIn("extracted_questions", app.session_state)
        for page in PAGES:
            self.navigate(app, page)
        self.press(app, "Prepare PDF & DOCX downloads")
        self.assertTrue(app.session_state.export_buffers["student_pdf"].startswith(b"%PDF"))
        # Repeated loading must keep the work from before the first demo load.
        self.press(app, "Load presentation demo")
        self.press(app, "Restore previous work")
        self.assertEqual(app.title[0].value, "Build Question Paper")
        restored = app.session_state.project
        self.assertEqual(restored["id"], previous["id"])
        self.assertEqual(restored["course"], previous["course"])
        self.assertEqual(restored["syllabus"], previous["syllabus"])
        self.assertEqual(restored["blueprint"], previous["blueprint"])
        self.assertFalse(restored.get("presentation_demo"))
        self.assertNotIn("work_before_demo", app.session_state)

    def test_mocked_generation_refreshes_manual_slots_and_preserves_locked_edits(self):
        app = self.start(new_course_fixture())
        control(app.text_input, "Gemini API key").set_value("test-only-key").run(timeout=20)
        self.navigate(app, "Build Question Paper")
        self.press(app, "Continue with this blueprint")
        self.press(app, "Prepare slots for manual questions")
        sid = app.session_state.project["paper_questions"][0]["slot_id"]
        response = {"questions": [{"slot_id": sid,
            "text": "Evaluate keyboard interaction and readable labels in an interface prototype, using explicit criteria.",
            "marks": 5, "co_id": "CO1", "bloom_levels": ["L5"], "module_ids": ["M1"],
            "difficulty": "Moderate", "rationale": "Evaluates the selected accessibility criteria.",
            "evidence": [{"module_id": "M1", "quote": "keyboard interaction and readable labels"}]}]}
        with patch("rag_pipeline.call_llm", return_value=json.dumps(response)) as generated:
            self.press(app, "Generate question drafts")
            self.assertEqual(generated.call_count, 1)
            self.assertEqual(control(app.text_area, "Question text").value, response["questions"][0]["text"])
            edited = "Evaluate a library search interface using keyboard access and readable-label criteria. Justify two improvements."
            control(app.text_area, "Question text").set_value(edited)
            self.press(app, "Approve & lock question")
            self.navigate(app, "Course & Syllabus")
            self.navigate(app, "Build Question Paper")
            self.press(app, "Generate question drafts")
            self.assertEqual(generated.call_count, 1, "Navigation and generation must retain successful locked questions.")
            question = app.session_state.project["paper_questions"][0]
            self.assertTrue(question["locked"])
            self.assertEqual(question["text"], edited)
            self.navigate(app, "Review & Export")
            self.press(app, "Prepare PDF & DOCX downloads")
            with fitz.open(stream=app.session_state.export_buffers["student_pdf"], filetype="pdf") as document:
                content = " ".join(page.get_text() for page in document)
            self.assertIn("library search interface", content)
            self.assertNotIn("faculty", content.lower())

    def test_empty_builder_explains_subject_and_outcome_setup_before_generation(self):
        app = self.start()
        self.navigate(app, "Build Question Paper")
        self.assertEqual(control(app.text_input, "Subject / course name").value, "")
        self.assertTrue(control(app.multiselect, "Course outcomes to assess").disabled)
        self.assertTrue(control(app.button, "Generate question drafts").disabled)
        instructions = " ".join(item.value for item in app.markdown)
        self.assertIn("Enter the subject / course name", instructions)
        self.assertIn("click Approve outcome", instructions)
        self.assertTrue(any("CO = Course Outcome" in item.value for item in app.caption))
        self.assertEqual(app.session_state.project["approved_cos"], [])
        self.assertEqual(app.session_state.project["blueprint"]["co_ids"], [])

    def test_subject_setup_shortcuts_preserve_blueprint_and_manual_questions(self):
        project = new_course_fixture()
        app = self.start(project)
        self.navigate(app, "Build Question Paper")
        self.press(app, "Continue with this blueprint")
        self.press(app, "Prepare slots for manual questions")
        question_id = app.session_state.project["paper_questions"][0]["id"]
        control(app.text_input, "Subject / course name").set_value("Accessible Product Interfaces").run(timeout=20)
        self.assertEqual(app.session_state.project["course"]["name"], "Accessible Product Interfaces")
        self.assertIn("Accessible Product Interfaces", [item.value for item in app.markdown])
        self.press(app, "Set syllabus & modules")
        self.assertEqual(app.title[0].value, "Course & Syllabus")
        self.assertEqual(control(app.text_input, "Subject / course name").value, "Accessible Product Interfaces")
        self.navigate(app, "Build Question Paper")
        self.press(app, "Prepare / approve course outcomes")
        self.assertEqual(app.title[0].value, "Course Outcomes")
        self.press(app, "Return to paper builder")
        self.assertEqual(app.title[0].value, "Build Question Paper")
        self.assertEqual(app.session_state.project["blueprint"]["sections"][0]["count"], 1)
        self.assertEqual(app.session_state.project["blueprint"]["target_marks"], 30)
        self.assertEqual(app.session_state.project["paper_questions"][0]["id"], question_id)

    def test_readable_co_choices_require_explicit_selection_and_keep_drafts_unapproved(self):
        project = new_course_fixture()
        project["blueprint"].update(target_marks=5, co_ids=[], module_ids=[])
        project["co_drafts"] = [{"id": "CO3", "statement": "Create an accessible prototype using appropriate interaction principles.",
                                  "module_ids": ["M1"], "bloom_levels": ["L6"], "status": "draft"}]
        app = self.start(project)
        control(app.text_input, "Gemini API key").set_value("test-only-key").run(timeout=20)
        self.navigate(app, "Build Question Paper")
        choices = control(app.multiselect, "Course outcomes to assess")
        self.assertTrue(any(option.startswith("CO1") and "Evaluate interface accessibility" in option for option in choices.options))
        self.assertFalse(any(option.startswith("CO3") for option in choices.options))
        self.assertTrue(control(app.button, "Generate question drafts").disabled)
        control(app.multiselect, "Covered modules / topics").set_value(["M1"]).run(timeout=20)
        self.press(app, "Use all approved outcomes for this paper")
        self.assertEqual(app.session_state.project["blueprint"]["co_ids"], ["CO1", "CO2"])
        self.assertEqual(app.session_state.project["co_drafts"][0]["status"], "draft")
        self.assertFalse(control(app.button, "Generate question drafts").disabled)
        self.assertFalse(any("default value" in item.value for item in app.warning))

    def test_new_manual_paper_override_edits_approval_preview_and_exports(self):
        app = self.start(new_course_fixture())
        self.navigate(app, "Build Question Paper")
        self.assertTrue(any("Attemptable marks differ" in item.value for item in app.warning))
        self.assertTrue(control(app.button, "Prepare slots for manual questions").disabled)
        self.press(app, "Continue with this blueprint")
        self.assertTrue(app.session_state.project["blueprint"]["acknowledgment"])
        self.assertFalse(control(app.button, "Prepare slots for manual questions").disabled)
        self.press(app, "Prepare slots for manual questions")
        question_text = "Evaluate a login form with low-contrast labels and no keyboard focus indicator. Justify two improvements using accessibility criteria."
        control(app.text_area, "Question text").set_value(question_text)
        control(app.selectbox, "Final intended CO").set_value("CO1")
        control(app.multiselect, "Final intended Bloom levels").set_value(["L5"])
        control(app.multiselect, "Syllabus modules").set_value(["M1"])
        control(app.text_area, "Faculty review notes").set_value("Professor verified the task scope.")
        self.press(app, "Save question edits")
        self.assertEqual(app.session_state.project["paper_questions"][0]["text"], question_text)
        self.press(app, "Approve & lock question")
        self.assertTrue(app.session_state.project["paper_questions"][0]["locked"])
        self.navigate(app, "Course & Syllabus")
        self.navigate(app, "Build Question Paper")
        self.assertEqual(app.session_state.project["paper_questions"][0]["status"], "approved")
        self.assertEqual(app.session_state.project["paper_questions"][0]["text"], question_text)
        self.navigate(app, "Review & Export")
        self.assertTrue(any("Maximum marks: 5" in item.value for item in app.caption))
        self.press(app, "Prepare PDF & DOCX downloads")
        buffers = app.session_state["export_buffers"]
        with fitz.open(stream=buffers["student_pdf"], filetype="pdf") as pdf:
            pdf_text = "\n".join(page.get_text() for page in pdf)
            self.assertIn("Maximum marks: 5", pdf_text)
            self.assertIn("Evaluate a login form", pdf_text)
            self.assertNotIn("Professor verified", pdf_text)
        doc = Document(io.BytesIO(buffers["student_docx"]))
        self.assertIn(question_text, "\n".join(p.text for p in doc.paragraphs))
        restored = import_project(export_project(app.session_state.project))
        self.assertEqual(restored["paper_questions"][0]["text"], question_text)
        self.assertEqual(restored["paper_questions"][0]["status"], "approved")
        # A relevant edit invalidates the acknowledgment and retained approval.
        self.navigate(app, "Build Question Paper")
        control(app.number_input, "Marks per question").set_value(6.0).run(timeout=20)
        self.assertEqual(len(app.exception), 0)
        self.assertIsNone(app.session_state.project["blueprint"]["acknowledgment"])
        self.assertTrue(control(app.button, "Prepare slots for manual questions").disabled)
        self.assertEqual(app.session_state.project["paper_questions"][0]["status"], "needs_review")

    def test_final_analysis_editor_correction_survives_navigation_and_export(self):
        project = new_course_fixture()
        project["analysis_questions"] = [{"id": "AQ1", "number": "1", "text": "Analyse a prototype's labels and propose improvements.", "marks": 5}]
        project["analyses"] = {"AQ1": {"suggestion": {"co": "CO1", "bloom_levels": ["L2"], "confidence": "Low", "co_ranking": [["CO1", .2], ["CO2", .19]], "reason": "Mocked suggestion", "syllabus_chunks": [], "total_votes": 1, "votes_for_co": 1}, "final_co": "CO1", "final_bloom": ["L2"], "status": "draft", "notes": ""}}
        refresh_dependencies(project)
        app = self.start(project)
        self.navigate(app, "Analyse Existing Questions")
        editor_key = f"{app.session_state.ui_epoch}:analysis_finals_editor"
        app.session_state[editor_key] = {"edited_rows": {0: {"Final CO": "CO2", "Final Bloom": "L4, L5", "Review notes": "Professor correction"}}, "added_rows": [], "deleted_rows": []}
        app.run(timeout=20)
        self.assertEqual(app.session_state.project["analyses"]["AQ1"]["final_co"], "CO2")
        self.navigate(app, "Course & Syllabus")
        self.navigate(app, "Analyse Existing Questions")
        self.assertEqual(app.session_state.project["analyses"]["AQ1"]["final_bloom"], ["L4", "L5"])
        self.press(app, "Approve final analysis")
        analysis = app.session_state.project["analyses"]["AQ1"]
        self.assertEqual(analysis["final_co"], "CO2")
        self.assertEqual(analysis["final_bloom"], ["L4", "L5"])
        self.assertEqual(analysis["status"], "approved")
        self.navigate(app, "Course & Syllabus")
        self.navigate(app, "Analyse Existing Questions")
        exported = list(csv.DictReader(io.StringIO(analysis_csv(app.session_state.project).decode("utf-8-sig"))))
        self.assertEqual(exported[0]["Final CO"], "CO2")
        self.assertEqual(exported[0]["Final Bloom Level"], "L4, L5")


if __name__ == "__main__":
    unittest.main()
