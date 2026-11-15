"""Marks, state, imports and identifier validation without network calls."""
import copy
import json
import unittest

from project_state import (new_project, fingerprint, derive_modules, export_project,
                           import_project, refresh_dependencies, matrix_source_fingerprint,
                           paper_source_fingerprint, analysis_source_fingerprint,
                           export_programme_config, import_programme_config,
                           source_fingerprint)
from validation import (calculate_marks, validate_blueprint, acknowledge_blueprint,
                        can_generate, build_slots, validate_generated_items,
                        validate_matrix_cell, validate_final_analysis)


def project_fixture():
    project = new_project()
    project["course"]["name"] = "Design foundations"
    project["syllabus"] = "Unit 1: Form\nStudy balance, proportion and rhythm.\n\nUnit 2: Context\nStudy identity and public art."
    project["modules"] = derive_modules(project["syllabus"])
    mid = project["modules"][0]["id"]
    project["approved_cos"] = [{"id": "CO1", "statement": "Explain balance and proportion.",
                                 "module_ids": [mid], "bloom_levels": ["L2"], "status": "approved"}]
    project["programme_outcomes"][0].update(statement="Apply design knowledge to an identified problem.", approved=True)
    project["blueprint"].update(module_ids=[mid], co_ids=["CO1"])
    return project


class MarksTests(unittest.TestCase):
    def bp(self, count=6, attempt=6, marks=5, mode="compulsory", target=30):
        bp = new_project()["blueprint"]
        bp["target_marks"] = target
        bp["sections"][0].update(count=count, attempt=attempt, marks=marks, mode=mode)
        return bp

    def test_compulsory_exact_total(self):
        result = calculate_marks(self.bp())
        self.assertEqual((result["printed"], result["minimum"], result["maximum"]), (30, 30, 30))
        self.assertFalse(result["mismatch"])

    def test_below_target_and_above_target_are_overridable(self):
        for count, marks, actual in [(5, 5, 25), (4, 10, 40)]:
            with self.subTest(actual=actual):
                bp = self.bp(count, count, marks)
                result = calculate_marks(bp)
                self.assertTrue(result["mismatch"])
                self.assertEqual(result["maximum"], actual)
                self.assertEqual(result["difference"], actual - 30)
                self.assertFalse(can_generate(bp)[0])
                acknowledge_blueprint(bp)
                self.assertTrue(can_generate(bp)[0])
                self.assertEqual(len(build_slots(bp)), count)
                self.assertEqual(bp["target_marks"], 30)

    def test_any_five_of_six(self):
        result = calculate_marks(self.bp(6, 5, 5, "any"))
        self.assertEqual((result["printed"], result["maximum"]), (30, 25))

    def test_either_or_counts_each_pair_once(self):
        bp = self.bp(6, 3, 10, "either_or")
        result = calculate_marks(bp)
        self.assertEqual((result["printed"], result["maximum"]), (60, 30))
        slots = build_slots(bp)
        self.assertEqual([s["number"] for s in slots], ["1A", "1B", "2A", "2B", "3A", "3B"])
        self.assertEqual(slots[0]["choice_group"], slots[1]["choice_group"])
        self.assertNotEqual(slots[1]["choice_group"], slots[2]["choice_group"])

    def test_subquestions_retain_parent_marks(self):
        bp = self.bp(6, 6, 5)
        bp["sections"][0]["subquestions"] = [{"label": "a", "marks": 2}, {"label": "b", "marks": 3}]
        self.assertFalse(validate_blueprint(bp))
        self.assertEqual(calculate_marks(bp)["maximum"], 30)
        slots = build_slots(bp)
        self.assertEqual(len(slots), 12)
        self.assertEqual(slots[0]["number"], "1(a)")
        self.assertEqual(slots[0]["parent_id"], slots[1]["parent_id"])
        self.assertEqual(slots[0]["parent_marks"], 5)

    def test_unequal_optional_marks_preserve_range(self):
        bp = self.bp(3, 2, 5, "any", 10)
        bp["sections"][0]["question_marks"] = [2, 5, 8]
        result = calculate_marks(bp)
        self.assertEqual((result["printed"], result["minimum"], result["maximum"]), (15, 7, 13))
        self.assertTrue(result["ambiguous"])
        self.assertIsNone(result["difference"])
        acknowledge_blueprint(bp)
        self.assertTrue(can_generate(bp)[0])

    def test_unequal_either_or_marks_preserve_range(self):
        bp = self.bp(4, 2, 5, "either_or", 10)
        bp["sections"][0]["question_marks"] = [2, 5, 4, 9]
        result = calculate_marks(bp)
        self.assertEqual((result["minimum"], result["maximum"]), (6, 14))

    def test_independent_sections_add_attemptable_totals(self):
        bp = self.bp(2, 2, 5, target=25)
        bp["sections"].append({"id": "SEC2", "title": "B", "mode": "any", "count": 4, "attempt": 3, "marks": 5})
        result = calculate_marks(bp)
        self.assertEqual((result["printed"], result["maximum"]), (30, 25))

    def test_acknowledgement_invalidates_after_any_blueprint_change(self):
        bp = self.bp(5, 5)
        acknowledge_blueprint(bp)
        for field, value in [("target_marks", 40), ("title", "Revised"), ("module_ids", ["MOD1"])]:
            changed = copy.deepcopy(bp)
            changed[field] = value
            self.assertFalse(can_generate(changed)[0])

    def test_structural_errors_cannot_be_overridden(self):
        changes = [dict(marks=0), dict(marks=-5), dict(count=-1), dict(count=True),
                   dict(attempt=7), dict(mode="invalid"), dict(mode="either_or", count=5, attempt=2),
                   dict(subquestions=[{"label": "a", "marks": 2}]), dict(question_marks=[5, 2])]
        for change in changes:
            with self.subTest(change=change):
                bp = self.bp()
                bp["sections"][0].update(change)
                bp["acknowledgment"] = "forged"
                self.assertTrue(validate_blueprint(bp))
                self.assertFalse(can_generate(bp)[0])
                with self.assertRaises(ValueError):
                    acknowledge_blueprint(bp)

    def test_equivalent_float_widget_numbers_preserve_acknowledgment(self):
        bp = self.bp(5, 5, 5)
        acknowledge_blueprint(bp)
        old_ack = bp["acknowledgment"]
        bp["target_marks"] = 30.0
        bp["sections"][0]["marks"] = 5.0
        self.assertTrue(can_generate(bp)[0])
        self.assertEqual(bp["acknowledgment"], old_ack)


class GenerationValidationTests(unittest.TestCase):
    def setUp(self):
        self.project = project_fixture()
        self.project["blueprint"]["sections"][0].update(count=1, attempt=1, marks=5)
        self.slots = build_slots(self.project["blueprint"])
        mid = self.project["modules"][0]["id"]
        self.item = {**self.slots[0], "text": "Explain balance and proportion using an example.",
                     "co_id": "CO1", "bloom_levels": ["L2"], "module_ids": [mid],
                     "evidence": [{"module_id": mid, "quote": "Study balance, proportion and rhythm."}],
                     "marking_guide": [{"criterion": "Explanation", "marks": 5}]}

    def test_valid_generated_item(self):
        self.assertEqual(validate_generated_items([self.item], self.slots, self.project), [])

    def test_wrong_counts_marks_co_bloom_and_evidence_are_rejected(self):
        self.assertTrue(validate_generated_items([], self.slots, self.project))
        changes = [{"marks": 8}, {"marks": True}, {"co_id": "CO99"}, {"bloom_levels": ["Understand"]},
                   {"slot_id": "unknown"}, {"module_ids": ["invented"]},
                   {"evidence": [{"module_id": self.project["modules"][0]["id"], "quote": "Invented topic"}]},
                   {"marking_guide": [{"criterion": "Work", "marks": 2}]}]
        for change in changes:
            with self.subTest(change=change):
                item = {**self.item, **change}
                self.assertTrue(validate_generated_items([item], self.slots, self.project))

    def test_matrix_scores_and_outcome_statements(self):
        mid = self.project["modules"][0]["id"]
        cell = {"co_id": "CO1", "outcome_id": "PO1", "suggested_score": 0, "final_score": 0, "status": "approved", "evidence": []}
        self.assertEqual(validate_matrix_cell(cell, self.project), [])
        self.assertTrue(validate_matrix_cell({**cell, "suggested_score": 4}, self.project))
        self.assertTrue(validate_matrix_cell({**cell, "final_score": None}, self.project))
        self.project["programme_outcomes"][0]["statement"] = ""
        self.assertTrue(validate_matrix_cell(cell, self.project))


class StateTests(unittest.TestCase):
    def test_modules_use_any_heading_count_and_stable_ids(self):
        text = "\n\n".join("Module %d: Topic\nContent %d." % (i, i) for i in range(1, 8))
        modules = derive_modules(text)
        self.assertEqual(len(modules), 7)
        refreshed = derive_modules(text.replace("Content 2", "Updated content 2"), modules)
        self.assertEqual([m["id"] for m in modules], [m["id"] for m in refreshed])
        self.assertEqual(len(derive_modules("Balance and proportion.")), 1)

    def test_json_roundtrip_excludes_credentials_and_model_objects(self):
        project = project_fixture()
        project["api_key"] = "DO-NOT-SAVE"
        project["analyses"] = {}
        project["course"]["api_key"] = "NESTED-DO-NOT-SAVE"
        project["approved_cos"][0]["credentials"] = {"token": "DO-NOT-SAVE"}
        project["approved_cos"][0]["api_token"] = "DO-NOT-SAVE"
        project["model"] = object()
        serialized = export_project(project)
        self.assertNotIn("DO-NOT-SAVE", serialized)
        restored = import_project(serialized)
        self.assertEqual(restored["id"], project["id"])
        self.assertEqual(restored["blueprint"], project["blueprint"])
        self.assertNotIn("api_key", restored["course"])

    def test_bad_imports_are_rejected(self):
        project = project_fixture()
        bad_values = []
        value = copy.deepcopy(project)
        value["schema_version"] = 99
        bad_values.append(value)
        value = copy.deepcopy(project)
        value["modules"].append(value["modules"][0])
        bad_values.append(value)
        value = copy.deepcopy(project)
        value["approved_cos"][0]["module_ids"] = ["not-found"]
        bad_values.append(value)
        value = copy.deepcopy(project)
        value["blueprint"]["sections"][0]["marks"] = -1
        bad_values.append(value)
        for value in bad_values:
            with self.assertRaises(ValueError):
                import_project(json.dumps(value))

    def test_programme_config_roundtrip(self):
        project = project_fixture()
        self.assertEqual(import_programme_config(export_programme_config(project)), project["programme_outcomes"])

    def test_professor_edits_survive_reruns_and_export(self):
        project = project_fixture()
        question = {"id": "Q1", "number": "1", "text": "Explain proportion.", "marks": 5}
        project["analysis_questions"] = [question]
        project["analyses"]["Q1"] = {"suggestion": {"co": "CO1", "bloom_levels": ["L1"]},
                                        "final_co": "CO1", "final_bloom": ["L2", "L4"], "status": "approved",
                                        "question_fingerprint": fingerprint(question),
                                        "source_fingerprint": analysis_source_fingerprint(project), "notes": "Professor correction"}
        refresh_dependencies(project)
        refresh_dependencies(project)
        restored = import_project(export_project(project))
        self.assertEqual(restored["analyses"]["Q1"]["final_bloom"], ["L2", "L4"])
        self.assertEqual(restored["analyses"]["Q1"]["suggestion"]["bloom_levels"], ["L1"])
        self.assertEqual(validate_final_analysis(restored), [])
        project["analysis_questions"][0]["text"] = "Evaluate proportion."
        refresh_dependencies(project)
        self.assertEqual(project["analyses"]["Q1"]["status"], "needs_review")
        self.assertEqual(project["analyses"]["Q1"]["final_bloom"], ["L2", "L4"])

    def test_changed_outcome_flags_only_its_matrix_cells(self):
        project = project_fixture()
        mid = project["modules"][1]["id"]
        project["approved_cos"].append({"id": "CO2", "statement": "Explain identity in public art.", "module_ids": [mid], "bloom_levels": ["L2"], "status": "approved"})
        for cid in ("CO1", "CO2"):
            project["matrix"].append({"co_id": cid, "outcome_id": "PO1", "suggested_score": 0,
                                      "final_score": 0, "status": "approved", "evidence": [],
                                      "source_fingerprint": matrix_source_fingerprint(project, cid, "PO1")})
        refresh_dependencies(project)
        project["approved_cos"][0]["statement"] = "Evaluate balance and proportion."
        refresh_dependencies(project)
        self.assertEqual(project["matrix"][0]["status"], "needs_review")
        self.assertEqual(project["matrix"][1]["status"], "approved")
        self.assertEqual(project["matrix"][0]["final_score"], 0)

    def test_blueprint_changes_flag_paper_and_clear_acknowledgement(self):
        project = project_fixture()
        bp = project["blueprint"]
        bp["target_marks"] = 40
        acknowledge_blueprint(bp)
        project["paper_questions"] = [{"id": "Q1", "text": "Explain balance.", "marks": 5, "co_id": "CO1",
                                         "bloom_levels": ["L2"], "module_ids": bp["module_ids"], "status": "approved",
                                         "locked": True, "source_fingerprint": paper_source_fingerprint(project)}]
        refresh_dependencies(project)
        bp["sections"][0]["marks"] = 6
        refresh_dependencies(project)
        self.assertIsNone(bp["acknowledgment"])
        self.assertEqual(project["paper_questions"][0]["status"], "needs_review")
        self.assertFalse(project["paper_questions"][0]["locked"])
        self.assertEqual(project["paper_questions"][0]["text"], "Explain balance.")

    def test_unselected_module_changes_do_not_stale_paper(self):
        project = project_fixture()
        before = paper_source_fingerprint(project)
        project["modules"][1]["text"] += " Extra material."
        project["syllabus"] += " Extra material."
        self.assertEqual(paper_source_fingerprint(project), before)

    def test_source_deletions_preserve_historical_references_and_roundtrip(self):
        project = project_fixture()
        mid = project["modules"][0]["id"]
        question = {"id": "AQ1", "number": "1", "text": "Explain balance.", "marks": 5}
        project["analysis_questions"] = [question]
        project["analyses"]["AQ1"] = {"final_co": "CO1", "final_bloom": ["L2"], "status": "approved",
                                         "question_fingerprint": fingerprint(question),
                                         "source_fingerprint": analysis_source_fingerprint(project)}
        project["matrix"] = [{"co_id": "CO1", "outcome_id": "PO1", "suggested_score": 0, "final_score": 0,
                                "evidence": [], "status": "approved", "source_fingerprint": matrix_source_fingerprint(project, "CO1", "PO1")}]
        project["paper_questions"] = [{"id": "SEC1:1", "slot_id": "SEC1:1", "text": "Explain balance.", "marks": 5,
                                        "co_id": "CO1", "bloom_levels": ["L2"], "module_ids": [mid],
                                        "status": "approved", "locked": True,
                                        "source_fingerprint": paper_source_fingerprint(project)}]
        refresh_dependencies(project)
        project["modules"] = project["modules"][1:]
        project["approved_cos"] = []
        project["programme_outcomes"] = project["programme_outcomes"][1:]
        project["analysis_questions"] = []
        refresh_dependencies(project)
        self.assertEqual(project["blueprint"]["module_ids"], [])
        self.assertEqual(project["blueprint"]["co_ids"], [])
        for collection in ("matrix", "paper_questions"):
            self.assertEqual(project[collection][0]["status"], "needs_review")
        self.assertEqual(project["analyses"]["AQ1"]["status"], "needs_review")
        restored = import_project(export_project(project))
        self.assertEqual(restored["matrix"][0]["final_score"], 0)
        self.assertEqual(restored["paper_questions"][0]["text"], "Explain balance.")
        self.assertTrue(all(restored["retired_sources"][key] for key in
                            ("modules", "approved_cos", "programme_outcomes", "analysis_questions")))
        # Removing the historical definition turns this into an unknown reference.
        restored["retired_sources"]["approved_cos"] = []
        with self.assertRaises(ValueError):
            import_project(export_project(restored))

    def test_changed_module_keeps_original_quotations_portable(self):
        project = project_fixture()
        co = project["approved_cos"][0]
        mid = co["module_ids"][0]
        co["evidence"] = [{"module_id": mid, "quote": "Study balance, proportion and rhythm."}]
        co["source_fingerprint"] = source_fingerprint(project, "co", co)
        refresh_dependencies(project)
        project["syllabus"] = project["syllabus"].replace("balance, proportion and rhythm", "colour, texture and contrast")
        project["modules"][0]["text"] = project["modules"][0]["text"].replace("balance, proportion and rhythm", "colour, texture and contrast")
        refresh_dependencies(project)
        self.assertEqual(co["status"], "needs_review")
        restored = import_project(export_project(project))
        self.assertEqual(restored["approved_cos"][0]["evidence"], co["evidence"])
        self.assertEqual(restored["retired_sources"]["modules"][0]["id"], mid)

    def test_unrelated_module_edit_does_not_revoke_individual_co_approval(self):
        project = project_fixture()
        co = project["approved_cos"][0]
        co["source_fingerprint"] = source_fingerprint(project, "co", co)
        refresh_dependencies(project)
        project["syllabus"] += "\nNew identity example."
        project["modules"][1]["text"] += "\nNew identity example."
        refresh_dependencies(project)
        self.assertEqual(co["status"], "approved")

    def test_updated_po_template_can_be_saved_and_reapproved(self):
        project = new_project()
        refresh_dependencies(project)
        project["programme_outcomes"][0].update(statement="Apply design knowledge to an identified problem.", approved=True)
        refresh_dependencies(project)
        project["programme_outcomes"][0]["approved"] = True
        restored = import_project(export_project(project))
        self.assertTrue(restored["programme_outcomes"][0]["approved"])
        self.assertFalse(restored["retired_sources"]["programme_outcomes"])

    def test_professor_reapproval_after_edit_survives_next_refresh(self):
        project = project_fixture()
        co = project["approved_cos"][0]
        co["source_fingerprint"] = source_fingerprint(project, "co", co)
        refresh_dependencies(project)
        co["statement"] = "Evaluate balance and proportion in a design."
        co["source_fingerprint"] = source_fingerprint(project, "co", co)
        refresh_dependencies(project)
        co["status"] = "approved"
        co["source_fingerprint"] = source_fingerprint(project, "co", co)
        refresh_dependencies(project)
        self.assertEqual(co["status"], "approved")

    def test_malformed_identifier_containers_raise_readable_import_error(self):
        project = project_fixture()
        project["matrix"] = [{"co_id": ["CO1"], "outcome_id": {"id": "PO1"}, "suggested_score": 0}]
        with self.assertRaises(ValueError):
            import_project(json.dumps(project))

    def test_retired_analyses_do_not_block_active_approved_mapping_export(self):
        project = project_fixture()
        question = {"id": "AQ1", "number": "1", "text": "Explain balance.", "marks": 5}
        project["analysis_questions"] = [question]
        project["analyses"] = {
            "AQ1": {"status": "approved", "final_co": "CO1", "final_bloom": ["L2"]},
            "retired": {"status": "needs_review", "final_co": "CO99", "final_bloom": []},
        }
        self.assertEqual(validate_final_analysis(project), [])

    def test_changed_section_keeps_old_slots_restorable(self):
        project = project_fixture()
        old_slot = build_slots(project["blueprint"])[-1]
        project["paper_questions"] = [{**old_slot, "id": "preserved-Q", "text": "Explain rhythm.",
                                        "co_id": "CO1", "bloom_levels": ["L2"],
                                        "module_ids": project["blueprint"]["module_ids"],
                                        "status": "approved", "locked": True,
                                        "source_fingerprint": paper_source_fingerprint(project)}]
        refresh_dependencies(project)
        project["blueprint"]["sections"][0].update(count=1, attempt=1)
        refresh_dependencies(project)
        self.assertEqual(project["paper_questions"][0]["status"], "needs_review")
        restored = import_project(export_project(project))
        self.assertEqual(restored["paper_questions"][0]["slot_id"], old_slot["slot_id"])
        self.assertTrue(restored["retired_sources"]["sections"])

    def test_duplicate_and_malformed_question_slot_metadata_are_rejected(self):
        project = project_fixture()
        slot = build_slots(project["blueprint"])[0]
        item = {**slot, "text": "Explain balance.", "co_id": "CO1", "bloom_levels": ["L2"],
                "module_ids": project["blueprint"]["module_ids"], "status": "draft", "locked": False}
        for change in ({"slot_id": ["bad"]}, {"number": 3}, {"parent_id": {}}, {"section_id": "unknown"},
                       {"final_co": "unknown"}, {"final_bloom": ["Understand"]}):
            project["paper_questions"] = [{**item, **change}]
            with self.assertRaises(ValueError):
                import_project(export_project(project))
        project["paper_questions"] = [item, {**item, "id": "different-question-same-slot"}]
        with self.assertRaises(ValueError):
            import_project(export_project(project))

    def test_invalid_intermediate_blueprint_does_not_corrupt_history(self):
        project = project_fixture()
        refresh_dependencies(project)
        project["blueprint"]["sections"][0]["count"] = 0
        refresh_dependencies(project)
        project["blueprint"]["sections"][0]["count"] = 6
        refresh_dependencies(project)
        restored = import_project(export_project(project))
        self.assertEqual(restored["blueprint"]["sections"][0]["count"], 6)

    def test_import_rebuilds_derived_revision_caches(self):
        project = project_fixture()
        project["revisions"] = {"source_records": ["untrusted wrong shape"], "sources": []}
        restored = import_project(export_project(project))
        self.assertIsInstance(restored["revisions"]["source_records"], dict)

    def test_unapproved_co_invalidates_dependent_labels_even_without_prior_fingerprints(self):
        project = project_fixture()
        project["approved_cos"][0]["status"] = "needs_review"
        project["analysis_questions"] = [{"id": "AQ1", "number": "1", "text": "Explain balance.", "marks": 5}]
        project["analyses"]["AQ1"] = {"status": "approved", "final_co": "CO1", "final_bloom": ["L2"]}
        slot = build_slots(project["blueprint"])[0]
        project["paper_questions"] = [{**slot, "text": "Explain balance.", "co_id": "CO1", "bloom_levels": ["L2"],
                                        "module_ids": project["blueprint"]["module_ids"], "status": "approved", "locked": True}]
        refresh_dependencies(project)
        self.assertEqual(project["analyses"]["AQ1"]["status"], "needs_review")
        self.assertEqual(project["paper_questions"][0]["status"], "needs_review")
        self.assertFalse(project["paper_questions"][0]["locked"])

    def test_equivalent_float_blueprint_does_not_stale_approved_paper(self):
        project = project_fixture()
        bp = project["blueprint"]
        bp["target_marks"] = 40
        acknowledge_blueprint(bp)
        slot = build_slots(bp)[0]
        project["paper_questions"] = [{**slot, "text": "Explain balance.", "co_id": "CO1", "bloom_levels": ["L2"],
                                        "module_ids": bp["module_ids"], "status": "approved", "locked": True,
                                        "source_fingerprint": paper_source_fingerprint(project)}]
        refresh_dependencies(project)
        bp["target_marks"] = 40.0
        bp["sections"][0]["marks"] = 5.0
        refresh_dependencies(project)
        self.assertIsNotNone(bp["acknowledgment"])
        self.assertEqual(project["paper_questions"][0]["status"], "approved")
        self.assertTrue(project["paper_questions"][0]["locked"])

    def test_malformed_paper_data_fails_import_with_readable_value_error(self):
        original = project_fixture()
        slot = build_slots(original["blueprint"])[0]
        item = {**slot, "text": "Explain balance.", "co_id": "CO1", "bloom_levels": ["L2"],
                "module_ids": original["blueprint"]["module_ids"], "status": "draft", "locked": False}
        changes = [{"text": []}, {"text": None}, {"co_id": {}}, {"slot_id": None}, {"answer": {}},
                   {"notes": []}, {"rationale": 3}, {"marking_guide": {}},
                   {"marking_guide": [{"criterion": [], "marks": 5}]},
                   {"marking_guide": [{"criterion": "Explanation", "marks": 3}]},
                   {"requested_co_ids": ["CO99"]}, {"requested_module_ids": ["unknown"]},
                   {"requested_bloom_levels": ["Evaluate"]}, {"analysis": []},
                   {"analysis": {"suggestion": []}}, {"analysis": {"status": "official"}}]
        for change in changes:
            with self.subTest(change=change):
                project = copy.deepcopy(original)
                project["paper_questions"] = [{**item, **change}]
                with self.assertRaisesRegex(ValueError, "Invalid project"):
                    import_project(json.dumps(project))
        project = copy.deepcopy(original)
        project["paper_questions"] = [{k: v for k, v in item.items() if k != "slot_id"}]
        with self.assertRaisesRegex(ValueError, "slot ID"):
            import_project(json.dumps(project))

    def test_cross_collection_duplicate_cos_and_malformed_analysis_are_rejected(self):
        project = project_fixture()
        project["co_drafts"] = [copy.deepcopy(project["approved_cos"][0])]
        with self.assertRaisesRegex(ValueError, "unique across"):
            import_project(json.dumps(project))
        project = project_fixture()
        project["analysis_questions"] = [{"id": "AQ1", "number": "1", "text": "Explain balance.", "marks": 5}]
        for analysis in ({"suggestion": []}, {"status": "official"}, {"notes": {}}, {"final_co": []}):
            project["analyses"] = {"AQ1": analysis}
            with self.assertRaisesRegex(ValueError, "Invalid project"):
                import_project(json.dumps(project))

    def test_import_hydrates_optional_course_and_question_display_fields(self):
        project = project_fixture()
        project["course"] = {}
        slot = build_slots(project["blueprint"])[0]
        project["paper_questions"] = [{"id": "manual-question", "slot_id": slot["slot_id"],
                                        "text": "Explain balance.", "marks": 5}]
        restored = import_project(json.dumps(project))
        self.assertEqual(restored["course"]["code"], "")
        self.assertEqual(restored["course"]["name"], "")
        self.assertEqual(restored["paper_questions"][0]["number"], slot["number"])
        self.assertEqual(restored["paper_questions"][0]["section_id"], slot["section_id"])
        self.assertEqual(restored["paper_questions"][0]["co_id"], "")


if __name__ == "__main__":
    unittest.main()
