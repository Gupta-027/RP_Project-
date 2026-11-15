"""AI orchestration is tested with mocked requests; no live Gemini calls."""
import copy
import json
import unittest
from unittest.mock import Mock, patch

import requests

import rag_pipeline as rag
from outcome_service import AIValidationError, draft_course_outcomes, suggest_matrix
from paper_service import (check_generated_questions, duplicate_warnings,
                           generate_paper, validate_question_response, generation_setup_issues)
from project_state import new_project
from validation import acknowledge_blueprint, build_slots


def course_project():
    project = new_project()
    project["course"]["name"] = "Design foundations"
    project["syllabus"] = "Unit 1: Design principles. Explore balance, proportion and contrast in everyday products."
    project["modules"] = [{"id": "M1", "title": "Design principles", "text": project["syllabus"]}]
    project["approved_cos"] = [{"id": "CO1", "statement": "Explain design balance and proportion in everyday products.",
        "module_ids": ["M1"], "bloom_levels": ["L2"], "rationale": "Taught in Unit 1", "evidence": [], "status": "approved"}]
    project["blueprint"].update(module_ids=["M1"], co_ids=["CO1"], bloom_levels=["L2"], target_marks=30)
    return project


def generated(slot):
    return {"slot_id": slot["slot_id"], "text": "Explain how balance shapes the appearance of an everyday product.",
        "marks": slot["marks"], "co_id": "CO1", "bloom_levels": ["L2"], "module_ids": ["M1"],
        "difficulty": "Moderate", "rationale": "Assesses explanation of syllabus design principles.",
        "evidence": [{"module_id": "M1", "quote": "balance, proportion and contrast"}], "answer": "",
        "marking_guide": []}


class GenerationValidationTests(unittest.TestCase):
    def test_missing_subject_is_explained_and_blocks_api_generation(self):
        project = course_project()
        project["course"]["name"] = ""
        with patch("rag_pipeline.call_llm") as call:
            with self.assertRaisesRegex(ValueError, "subject / course name"):
                generate_paper(project, "mock-key")
        call.assert_not_called()

    def test_outcome_setup_distinguishes_missing_approval_from_selection(self):
        project = course_project()
        co = project["approved_cos"].pop()
        co["status"] = "draft"
        project["co_drafts"] = [co]
        issues = generation_setup_issues(project)
        self.assertIn("Approve outcome", issues["outcomes"])
        self.assertNotIn("co_targets", issues)
        with patch("rag_pipeline.call_llm") as call:
            with self.assertRaisesRegex(ValueError, "Approve outcome"):
                generate_paper(project, "mock-key")
        call.assert_not_called()
        co["status"] = "approved"
        project["approved_cos"] = [co]
        project["co_drafts"] = []
        project["blueprint"]["co_ids"] = []
        issues = generation_setup_issues(project)
        self.assertNotIn("outcomes", issues)
        self.assertIn("Course outcomes to assess", issues["co_targets"])
        project["blueprint"]["co_ids"] = ["CO1"]
        self.assertFalse(generation_setup_issues(project))

    def test_stale_module_source_blocks_new_ai_tasks(self):
        project = course_project()
        project["syllabus"] = "A revised syllabus that no longer contains the original module."
        with patch("rag_pipeline.call_llm") as call:
            with self.assertRaises(ValueError):
                generate_paper(project, "mock-key")
            with self.assertRaises(ValueError):
                draft_course_outcomes(project, 1, "mock-key")
            project["programme_outcomes"][0].update(statement="Apply design principles to solve identified problems.", approved=True)
            with self.assertRaises(ValueError):
                suggest_matrix(project, "mock-key")
        call.assert_not_called()

    def test_task_rejects_wrong_counts_marks_ids_and_bloom(self):
        project = course_project()
        slots = build_slots(project["blueprint"])[:1]
        valid = generated(slots[0])
        self.assertFalse(validate_question_response({"questions": [valid]}, slots, project)[1])
        for field, invalid in (("marks", 99), ("marks", True), ("co_id", "CO99"),
                               ("bloom_levels", ["L8"]), ("module_ids", ["M99"]),
                               ("slot_id", "invented"), ("co_id", ["CO1"])):
            with self.subTest(field=field, value=invalid):
                item = copy.deepcopy(valid)
                item[field] = invalid
                self.assertTrue(validate_question_response({"questions": [item]}, slots, project)[1])
        self.assertTrue(validate_question_response({"questions": []}, slots, project)[1])

    def test_marking_guide_must_match_marks(self):
        project = course_project()
        slots = build_slots(project["blueprint"])[:1]
        item = generated(slots[0])
        item["marking_guide"] = [{"criterion": "Explanation", "marks": 2}]
        self.assertTrue(validate_question_response({"questions": [item]}, slots, project)[1])

    def test_partial_failure_preserves_success_and_retry_only_missing(self):
        project = course_project()
        slots = build_slots(project["blueprint"])
        first = json.dumps({"questions": [generated(s) for s in slots[:3]]})
        with patch("rag_pipeline.call_llm", side_effect=[first, rag.LLMUnavailable("Gemini unavailable")]) as call:
            result = generate_paper(project, "mock-key")
        self.assertEqual(call.call_count, 2)
        self.assertEqual(len(result["questions"]), 3)
        self.assertEqual(set(result["failures"]), {s["slot_id"] for s in slots[3:]})
        project["paper_questions"][0]["text"] = "Professor's final edited question."
        retry = json.dumps({"questions": [generated(s) for s in slots[3:]]})
        with patch("rag_pipeline.call_llm", return_value=retry) as call:
            result = generate_paper(project, "mock-key")
        self.assertEqual(call.call_count, 1)
        self.assertFalse(result["failures"])
        self.assertEqual(len(project["paper_questions"]), 6)
        self.assertEqual(project["paper_questions"][0]["text"], "Professor's final edited question.")

    def test_locked_question_is_not_replaced(self):
        project = course_project()
        slot = build_slots(project["blueprint"])[0]
        project["paper_questions"] = [{**generated(slot), **slot, "locked": True, "status": "approved"}]
        before = copy.deepcopy(project["paper_questions"])
        with patch("rag_pipeline.call_llm") as call:
            result = generate_paper(project, "mock-key", slot_ids=[slot["slot_id"]])
        call.assert_not_called()
        self.assertIn(slot["slot_id"], result["failures"])
        self.assertEqual(project["paper_questions"], before)

    def test_invalid_output_retries_once_without_fabrication(self):
        project = course_project()
        with patch("rag_pipeline.call_llm", return_value='{"questions": []}') as call:
            result = generate_paper(project, "mock-key", slot_ids=["SEC1:1"])
        self.assertEqual(call.call_count, 2)
        self.assertEqual(project["paper_questions"], [])
        self.assertIn("SEC1:1", result["failures"])

    def test_duplicate_candidates(self):
        questions = [{"id": "a", "text": "Explain balance in product design."},
                     {"id": "b", "text": "Explain balance in product design!"}]
        self.assertIn("Exact duplicate", duplicate_warnings(questions)[0])

    def test_check_keeps_requested_and_final_labels(self):
        project = course_project()
        slot = build_slots(project["blueprint"])[0]
        item = {**generated(slot), **slot, "locked": True, "status": "approved", "requested_bloom_levels": ["L2"]}
        project["paper_questions"] = [item]
        suggestion = {"co": "CO1", "bloom_levels": ["L4"], "error": "", "confidence": "Low"}
        with patch("rag_pipeline.embed_texts", return_value=[[1.0]]), patch("rag_pipeline.predict_rag_llm", return_value=suggestion):
            result = check_generated_questions(project, "mock-key")
        self.assertEqual(item["bloom_levels"], ["L2"])
        self.assertEqual(item["requested_bloom_levels"], ["L2"])
        self.assertEqual(item["status"], "needs_review")
        self.assertTrue(item["analysis"]["disagrees"])
        self.assertEqual(result["checked"], [item["id"]])

    def test_single_regeneration_keeps_stable_ids_and_other_questions(self):
        project = course_project()
        slots = build_slots(project["blueprint"])
        project["paper_questions"] = [{**generated(s), **s, "locked": False, "status": "draft"} for s in slots]
        project["paper_questions"][1].update(locked=True, status="approved")
        before = copy.deepcopy(project["paper_questions"])
        replacement = generated(slots[0])
        replacement["text"] = "Explain contrast using two everyday consumer products."
        with patch("rag_pipeline.call_llm", return_value=json.dumps({"questions": [replacement]})) as call:
            generate_paper(project, "mock-key", slot_ids=[slots[0]["slot_id"]])
        self.assertEqual(call.call_count, 1)
        self.assertEqual(project["paper_questions"][0]["id"], before[0]["id"])
        self.assertEqual(project["paper_questions"][0]["text"], replacement["text"])
        self.assertEqual(project["paper_questions"][1:], before[1:])

    def test_regenerating_and_checking_manual_question_preserves_question_uuid(self):
        project = course_project()
        slot = build_slots(project["blueprint"])[0]
        project["paper_questions"] = [{**generated(slot), **slot, "id": "manual-question-uuid", "locked": False, "status": "draft"}]
        with patch("rag_pipeline.call_llm", return_value=json.dumps({"questions": [generated(slot)]})):
            generate_paper(project, "mock-key", slot_ids=[slot["slot_id"]])
        self.assertEqual(project["paper_questions"][0]["id"], "manual-question-uuid")
        suggestion = {"co": "CO1", "bloom_levels": ["L2"], "error": ""}
        with patch("rag_pipeline.embed_texts", return_value=[[1.0]]), patch("rag_pipeline.predict_rag_llm", return_value=suggestion):
            result = check_generated_questions(project, "mock-key", ids=["manual-question-uuid"])
        self.assertEqual(result["checked"], ["manual-question-uuid"])

    def test_acknowledgment_cannot_bypass_structure_or_blueprint_changes(self):
        project = course_project()
        project["blueprint"]["target_marks"] = 25
        with patch("rag_pipeline.call_llm") as call:
            with self.assertRaisesRegex(ValueError, "Continue"):
                generate_paper(project, "mock-key")
            acknowledge_blueprint(project["blueprint"])
            project["blueprint"]["sections"][0]["marks"] = 6
            with self.assertRaisesRegex(ValueError, "Continue"):
                generate_paper(project, "mock-key")
            project["blueprint"]["sections"][0]["marks"] = -1
            project["blueprint"]["acknowledgment"] = "anything"
            with self.assertRaisesRegex(ValueError, "positive"):
                generate_paper(project, "mock-key")
        call.assert_not_called()

    def test_check_ignores_retained_obsolete_questions(self):
        project = course_project()
        slot = build_slots(project["blueprint"])[0]
        current = {**generated(slot), **slot, "locked": False, "status": "draft"}
        obsolete = {**current, "id": "OLD:1", "slot_id": "OLD:1"}
        project["paper_questions"] = [current, obsolete]
        suggestion = {"co": "CO1", "bloom_levels": ["L2"], "error": ""}
        with patch("rag_pipeline.embed_texts", return_value=[[1.0]]), patch("rag_pipeline.predict_rag_llm", return_value=suggestion) as call:
            result = check_generated_questions(project, "mock-key")
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result["checked"], [slot["id"]])
        self.assertNotIn("analysis", obsolete)

    def test_failed_recheck_preserves_previous_analysis(self):
        project = course_project()
        slots = build_slots(project["blueprint"])[:2]
        previous = {"suggestion": {"co": "CO1", "bloom_levels": ["L2"], "error": ""}, "disagrees": False}
        project["paper_questions"] = [{**generated(s), **s, "locked": False, "status": "draft", "analysis": copy.deepcopy(previous)} for s in slots]
        with patch("rag_pipeline.embed_texts", return_value=[[1.0]]), patch("rag_pipeline.predict_rag_llm", return_value=rag.failed_result("Gemini unavailable")) as call:
            result = check_generated_questions(project, "mock-key")
        self.assertEqual(call.call_count, 1)
        self.assertEqual(project["paper_questions"][0]["analysis"], previous)
        self.assertEqual(len(result["failures"]), 2)
        self.assertFalse(result["checked"])

    def test_embedding_duplicate_check_is_explicit(self):
        questions = [{"id": "a", "text": "Describe design proportions."},
                     {"id": "b", "text": "Discuss visual sizing ratios."}]
        cache = {}
        with patch("rag_pipeline.embed_texts", return_value=[[1.0, 0.0], [1.0, 0.0]]) as call:
            result = duplicate_warnings(questions, use_embeddings=True, embedding_cache=cache)
        self.assertEqual(call.call_count, 1)
        self.assertIs(call.call_args.kwargs["cache"], cache)
        self.assertIn("embedding similarity", result[0])


class OutcomeTaskTests(unittest.TestCase):
    def test_drafts_do_not_replace_approved_outcomes(self):
        project = course_project()
        before = copy.deepcopy(project["approved_cos"])
        response = {"outcomes": [{"statement": "Explain contrast and proportion in product design.",
            "module_ids": ["M1"], "bloom_levels": ["L2"], "rationale": "Covers stated design principles.",
            "evidence": [{"module_id": "M1", "quote": "balance, proportion and contrast"}]}]}
        with patch("rag_pipeline.call_llm", return_value=json.dumps(response)):
            drafts = draft_course_outcomes(project, 1, "mock-key")
        self.assertEqual(project["approved_cos"], before)
        self.assertEqual(drafts[0]["id"], "CO2")
        self.assertEqual(drafts[0]["status"], "draft")

    def test_invented_evidence_is_rejected(self):
        project = course_project()
        response = {"outcomes": [{"statement": "Explain contrast and proportion in product design.",
            "module_ids": ["M1"], "bloom_levels": ["L2"], "rationale": "Covers stated principles.",
            "evidence": [{"module_id": "M1", "quote": "invented robotics syllabus"}]}]}
        with patch("rag_pipeline.call_llm", return_value=json.dumps(response)) as call:
            with self.assertRaises(AIValidationError):
                draft_course_outcomes(project, 1, "mock-key")
        self.assertEqual(call.call_count, 2)

    def test_drafting_does_not_reuse_retired_outcome_ids(self):
        project = course_project()
        project["retired_sources"]["approved_cos"] = [{"id": "CO2", "statement": "Retired outcome"}]
        response = {"outcomes": [{"statement": "Explain contrast and proportion in product design.",
            "module_ids": ["M1"], "bloom_levels": ["L2"], "rationale": "Covers stated design principles.",
            "evidence": [{"module_id": "M1", "quote": "balance, proportion and contrast"}]}]}
        with patch("rag_pipeline.call_llm", return_value=json.dumps(response)):
            drafts = draft_course_outcomes(project, 1, "mock-key")
        self.assertEqual(drafts[0]["id"], "CO3")

    def test_matrix_requires_meaningful_approved_statements(self):
        project = course_project()
        with patch("rag_pipeline.call_llm") as call:
            with self.assertRaises(ValueError):
                suggest_matrix(project, "mock-key")
        call.assert_not_called()

    def test_matrix_zero_is_explicit_and_invalid_scores_rejected(self):
        project = course_project()
        project["programme_outcomes"] = [{"id": "PO1", "kind": "PO", "statement": "Evaluate design practice in a social context.", "approved": True}]
        response = {"relationships": [{"co_id": "CO1", "outcome_id": "PO1", "score": 0,
            "rationale": "No social context is demonstrated in this CO.", "evidence": []}]}
        with patch("rag_pipeline.call_llm", return_value=json.dumps(response)):
            cells = suggest_matrix(project, "mock-key")
        self.assertEqual(cells[0]["suggested_score"], 0)
        self.assertIsNone(cells[0]["final_score"])
        response["relationships"][0]["score"] = 4
        with patch("rag_pipeline.call_llm", return_value=json.dumps(response)):
            with self.assertRaises(AIValidationError):
                suggest_matrix(project, "mock-key")

    def test_scalar_list_and_nonfinite_json_are_rejected(self):
        project = course_project()
        for raw in ('"text"', '5', 'false', 'null', '[]', '[{"outcomes":[]}]', '{"outcomes": NaN}', 'prefix {"outcomes": []}'):
            with self.subTest(raw=raw), patch("rag_pipeline.call_llm", return_value=raw) as call:
                with self.assertRaises(AIValidationError):
                    draft_course_outcomes(project, 1, "mock-key")
                self.assertEqual(call.call_count, 2)

    def test_insufficient_evidence_explains_missing_input(self):
        project = course_project()
        with patch("rag_pipeline.call_llm", return_value='{"error":"Selected module lacks details of evaluation criteria."}') as call:
            with self.assertRaisesRegex(AIValidationError, "evaluation criteria"):
                draft_course_outcomes(project, 1, "mock-key")
        self.assertEqual(call.call_count, 1)

    def test_matrix_partial_failure_saves_completed_rows(self):
        project = course_project()
        project["approved_cos"].append({**copy.deepcopy(project["approved_cos"][0]), "id": "CO2"})
        project["programme_outcomes"] = [{"id": "PO1", "kind": "PO", "statement": "Evaluate design in a social context.", "approved": True}]
        response = {"relationships": [{"co_id": "CO1", "outcome_id": "PO1", "score": 0,
            "rationale": "No relationship demonstrated.", "evidence": []}]}
        with patch("rag_pipeline.call_llm", side_effect=[json.dumps(response), rag.LLMUnavailable("Gemini unavailable")]):
            with self.assertRaises(rag.LLMUnavailable):
                suggest_matrix(project, "mock-key")
        self.assertEqual(len(project["matrix"]), 1)
        self.assertEqual(project["matrix"][0]["co_id"], "CO1")

    def test_matrix_retains_original_suggestion_and_professor_override(self):
        project = course_project()
        project["programme_outcomes"] = [{"id": "PO1", "kind": "PO", "statement": "Explain design balance in everyday products.", "approved": True}]
        project["matrix"] = [{"co_id": "CO1", "outcome_id": "PO1", "suggested_score": 1, "final_score": 2,
            "rationale": "Original suggestion.", "evidence": [], "status": "draft", "notes": "Professor override.", "professor_edited": True}]
        response = {"relationships": [{"co_id": "CO1", "outcome_id": "PO1", "score": 3,
            "rationale": "New suggestion.", "evidence": [{"module_id": "M1", "quote": "balance, proportion and contrast"}]}]}
        with patch("rag_pipeline.call_llm", return_value=json.dumps(response)):
            cells = suggest_matrix(project, "mock-key")
        self.assertEqual(cells[0]["final_score"], 2)
        self.assertEqual(cells[0]["suggested_score"], 3)
        self.assertEqual(cells[0]["original_suggestion"]["suggested_score"], 1)
        self.assertEqual(cells[0]["notes"], "Professor override.")


class GeminiFailureTests(unittest.TestCase):
    def test_timeout_does_not_expose_request_details(self):
        with patch("rag_pipeline.requests.post", side_effect=requests.Timeout("secret-value")):
            with self.assertRaises(rag.LLMUnavailable) as error:
                rag.call_llm("test", "mock-key")
        self.assertNotIn("secret-value", str(error.exception))

    def test_authentication_does_not_echo_server_body(self):
        response = Mock(status_code=403, text="secret-value")
        with patch("rag_pipeline.requests.post", return_value=response):
            with self.assertRaises(rag.LLMUnavailable) as error:
                rag.call_llm("test", "mock-key")
        self.assertIn("authentication", str(error.exception))
        self.assertNotIn("secret-value", str(error.exception))

    def test_rate_limit_is_bounded(self):
        with patch("rag_pipeline.requests.post", return_value=Mock(status_code=429)) as call, patch("rag_pipeline.time.sleep"):
            with self.assertRaises(rag.LLMUnavailable):
                rag.call_llm("test", "mock-key")
        self.assertEqual(call.call_count, 3)

    def test_malformed_transport_json_is_readable(self):
        response = Mock(status_code=200)
        response.json.side_effect = ValueError("secret-value")
        with patch("rag_pipeline.requests.post", return_value=response):
            with self.assertRaises(rag.LLMUnavailable) as error:
                rag.call_llm("test", "mock-key")
        self.assertIn("no usable text", str(error.exception))
        self.assertNotIn("secret-value", str(error.exception))

    def test_embedding_cache_contains_model_identity(self):
        cache = {}
        model = Mock()
        model.encode.return_value = [[1, 0]]
        with patch("rag_pipeline.load_embedding_model", return_value=model), patch.object(rag, "EMBEDDING_MODEL_NAME", "model-a"):
            rag.embed_texts(["course text"], cache)
            rag.embed_texts(["course text"], cache)
        with patch("rag_pipeline.load_embedding_model", return_value=model), patch.object(rag, "EMBEDDING_MODEL_NAME", "model-b"):
            rag.embed_texts(["course text"], cache)
        self.assertEqual(model.encode.call_count, 2)


if __name__ == "__main__":
    unittest.main()
