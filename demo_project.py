"""Complete presentation fixtures. These examples never invoke AI or embeddings.

Approvals and suggestions are staged examples, not research predictions or
institutional decisions. The input-only research sample remains separate.
"""
from copy import deepcopy

from project_state import (new_project, derive_modules, fingerprint,
                           source_fingerprint, refresh_dependencies)
from sample_data import (SAMPLE_COURSE_CODE, SAMPLE_COURSE_NAME, SAMPLE_COS,
                         SAMPLE_SYLLABUS, SAMPLE_QUESTIONS)
from validation import build_slots


PROVENANCE = "prepared_demo"
DEMO_NOTE = "Prepared presentation example; not live AI output or a measured research result."

ILLUSTRATIVE_OUTCOMES = [
    ("PO1", "Apply art and design principles to analyse familiar products."),
    ("PO2", "Analyse design problems in relation to user needs and context."),
    ("PO3", "Develop and justify design concepts for a stated context."),
    ("PO4", "Investigate alternatives using visual analysis and relevant examples."),
    ("PO5", "Select appropriate visual communication tools and methods."),
    ("PO6", "Evaluate design choices in relation to society and cultural context."),
    ("PO7", "Consider environmental responsibility in design decisions."),
    ("PO8", "Justify ethical decisions in art and design practice."),
    ("PO9", "Collaborate effectively when developing and reviewing design work."),
    ("PO10", "Communicate design ideas clearly using appropriate representations."),
    ("PO11", "Reflect on feedback and extend personal learning in design."),
    ("PSO1", "Interpret art and aesthetics to improve human-centred design concepts."),
    ("PSO2", "Propose culturally sensitive and environmentally responsible public design interventions."),
]

CO_QUOTES = [
    "Introduction to art and aesthetics.",
    "Art as a medium of personal expression.",
    "Art as a mirror and as a transformative force in society.",
]

# Only supported example relationships receive a positive score. Other cells
# explicitly demonstrate approved no relationship, rather than an unreviewed blank.
RELATIONSHIPS = {
    "CO1": {
        "PO1": (3, "Explaining design principles directly supports applying foundational design knowledge."),
        "PO2": (2, "The Design Quality Triangle provides a way to analyse product trade-offs."),
        "PO3": (1, "Foundational explanation offers limited support for later concept development."),
        "PO10": (1, "Explaining design quality requires clear communication of the concepts."),
        "PSO1": (3, "Art and aesthetics are explicit content of this course outcome."),
    },
    "CO2": {
        "PO4": (3, "Interpreting artworks involves visual analysis and comparison of interpretations."),
        "PO6": (2, "Identity and lived experience connect interpretation to cultural context."),
        "PO10": (2, "An interpretation must be explained and supported using observed features."),
        "PSO1": (3, "Interpreting aesthetics and artistic expression directly supports this specialisation."),
    },
    "CO3": {
        "PO2": (2, "Analysing society and everyday life gives context to design problems."),
        "PO3": (2, "Public-art examples connect social analysis to justified design proposals."),
        "PO6": (3, "The art-design-society relationship is central to this outcome."),
        "PO7": (2, "The module discusses designers' responsibilities towards the environment."),
        "PO8": (3, "Ethics and social responsibility are explicit syllabus topics."),
        "PO10": (2, "Analysing the social role of art requires a clearly supported argument."),
        "PSO2": (3, "Public art, cultural context and environmental responsibility support this specialisation."),
    },
}

PAPER_ITEMS = [
    {
        "text": "Explain aesthetics, function and usability in the Design Quality Triangle. Use a familiar chair as an example to show how the three components interact.",
        "co_id": "CO1", "bloom_levels": ["L2"], "module_ids": ["M1"],
        "quote": "aesthetics, function and usability.",
        "rationale": "Requires an explanation of three taught concepts and their relationship in an everyday product.",
        "answer": "Aesthetics concerns the chair's visual and sensory character; function concerns support for sitting; usability concerns ease and comfort of use. A suitable example explains how a visual or structural change can affect the other components.",
        "criteria": [("Explain aesthetics, function and usability", 3), ("Explain their interaction using the chair example", 2)],
    },
    {
        "text": "Smartphone A has a visually striking interface with hidden controls. Smartphone B has plain styling and clearly labelled controls. Analyse two trade-offs between aesthetics and usability using the Design Quality Triangle.",
        "co_id": "CO1", "bloom_levels": ["L4"], "module_ids": ["M1"],
        "quote": "aesthetics, function and usability.",
        "rationale": "Requires reasoning about relationships and trade-offs, rather than merely naming the components.",
        "answer": "A justified answer compares the visual character and discoverability of the supplied interfaces, explains two possible trade-offs, and connects the comparison to function and usability. Either interface may be preferred when supported by a clear context.",
        "criteria": [("Analyse two distinct trade-offs", 4), ("Connect the analysis to the Design Quality Triangle", 1)],
    },
    {
        "text": "A photograph shows an empty chair beside a family portrait in a dim room. Analyse how these visual choices could communicate memory and personal identity. Explain why two viewers might interpret the photograph differently.",
        "co_id": "CO2", "bloom_levels": ["L4"], "module_ids": ["M2"],
        "quote": "Art as a medium of personal expression.",
        "rationale": "Provides a complete visual scenario and asks for relationships between features, meaning and subjective interpretation.",
        "answer": "Possible interpretations link the empty chair to absence, the family portrait to shared identity, and the setting to memory or emotion. Alternative interpretations are acceptable when grounded in the described features and differences in viewers' experiences.",
        "criteria": [("Analyse two features in relation to memory or identity", 3), ("Explain differences between viewers' interpretations", 2)],
    },
    {
        "text": "Two viewers disagree about a sculpture: one values technical craftsmanship while the other values originality. Evaluate both positions and give a justified judgment using criteria of artistic merit.",
        "co_id": "CO2", "bloom_levels": ["L5"], "module_ids": ["M2"],
        "quote": "Criteria used to judge artistic merit, originality and craftsmanship.",
        "rationale": "Requires a judgment supported by explicit criteria, while allowing more than one defensible conclusion.",
        "answer": "A strong answer explains what each criterion contributes, recognises limitations of judging by only one criterion, and reaches a reasoned conclusion. No single preference is required.",
        "criteria": [("Evaluate craftsmanship and originality as criteria", 3), ("Give a justified and balanced judgment", 2)],
    },
    {
        "text": "A campus proposes replacing a traditional craft display with a mass-produced installation. Evaluate one cultural and one environmental consequence, then recommend an approach that recognises the designer's responsibilities.",
        "co_id": "CO3", "bloom_levels": ["L5"], "module_ids": ["M3"],
        "quote": "Ethics and responsibility of the designer\ntowards society and the environment.",
        "rationale": "Connects a supplied social-design scenario to cultural context, ethics and environmental responsibility.",
        "answer": "Answers may consider continuity of craft traditions, representation, materials and resource use. Environmental effects should be explained as conditional possibilities because no life-cycle data are supplied. A recommendation must weigh both types of consequence.",
        "criteria": [("Evaluate a cultural consequence", 2), ("Evaluate an environmental consequence", 2), ("Justify a responsible recommendation", 1)],
    },
    {
        "text": "Propose a small public art installation that encourages waste segregation on a college campus. Describe its concept, materials and visitor interaction, and justify how it could create social awareness.",
        "co_id": "CO3", "bloom_levels": ["L6"], "module_ids": ["M3"],
        "quote": "awareness and shaping public opinion.",
        "rationale": "Asks for a new, bounded proposal with an explicit social purpose and a justified relationship between design and awareness.",
        "answer": "One possible concept is an interactive installation using clearly separated reclaimed materials. Visitors place sample objects into labelled parts of the artwork. Any coherent, feasible proposal may be credited when its materials, interaction and awareness goal are justified.",
        "criteria": [("Develop a coherent installation concept", 2), ("Describe appropriate materials and interaction", 2), ("Justify the social-awareness goal", 1)],
    },
]


def example_suggestion(co_id, levels, rationale, evidence):
    """Do not invent retrieval measurements or LLM runs for prepared fixtures."""
    return {"co": co_id, "bloom_levels": levels, "topic": "Art and aesthetics",
        "reason": DEMO_NOTE + " " + rationale, "confidence": "Not measured (demo)",
        "error": "", "co_ranking": [], "syllabus_chunks": [],
        "total_votes": 0, "votes_for_co": 0, "provenance": PROVENANCE,
        "sample_evidence": deepcopy(evidence)}


def build_presentation_demo():
    """Return a complete independent project, ready to preview without setup."""
    p = new_project()
    p["presentation_demo"] = True
    p["course"].update(code=SAMPLE_COURSE_CODE, name=SAMPLE_COURSE_NAME,
        department="Industrial Design (demo)", programme="B.Des. (demo)",
        semester="4", academic_year="2026–27 (sample)")
    p["syllabus"] = SAMPLE_SYLLABUS
    p["modules"] = derive_modules(SAMPLE_SYLLABUS)
    for index, module in enumerate(p["modules"], 1):
        module["id"] = f"M{index}"
    for index, (cid, statement) in enumerate(SAMPLE_COS):
        co = {"id": cid, "statement": statement, "module_ids": [f"M{index + 1}"],
            "bloom_levels": [["L2"], ["L4", "L5"], ["L4", "L5", "L6"]][index],
            "rationale": DEMO_NOTE + " Grounded in the corresponding syllabus unit.",
            "evidence": [{"module_id": f"M{index + 1}", "quote": CO_QUOTES[index]}],
            "status": "approved", "origin": PROVENANCE,
            "notes": "Approval staged for presentation; not an institutional decision."}
        co["source_fingerprint"] = source_fingerprint(p, "co", co)
        p["approved_cos"].append(co)
    p["co_drafts"] = [{"id": "CO4", "statement": "Evaluate ethical and environmental responsibilities in public design interventions.",
        "module_ids": ["M3"], "bloom_levels": ["L5"], "rationale": DEMO_NOTE + " Optional extension to demonstrate individual review.",
        "evidence": [{"module_id": "M3", "quote": CO_QUOTES[2]}], "status": "draft", "origin": PROVENANCE}]
    p["co_drafts"][0]["source_fingerprint"] = source_fingerprint(p, "co", p["co_drafts"][0])
    p["programme_outcomes"] = [{"id": oid, "kind": "PSO" if oid.startswith("PSO") else "PO",
        "statement": "[Illustrative demo] " + statement, "approved": True}
        for oid, statement in ILLUSTRATIVE_OUTCOMES]
    for index, co in enumerate(p["approved_cos"]):
        for outcome in p["programme_outcomes"]:
            score, reason = RELATIONSHIPS[co["id"]].get(outcome["id"],
                (0, "No direct relationship is demonstrated by this CO and its syllabus evidence."))
            evidence = deepcopy(co["evidence"]) if score else []
            override = co["id"] == "CO1" and outcome["id"] == "PO3"
            cell = {"co_id": co["id"], "outcome_id": outcome["id"],
                "suggested_score": 2 if override else score, "final_score": score,
                "rationale": DEMO_NOTE + " " + reason, "evidence": evidence,
                "status": "approved", "provenance": PROVENANCE,
                "notes": "Staged professor override: limited direct support for concept development." if override else "Prepared demonstration relationship; review before real use.",
                "professor_edited": override}
            cell["source_fingerprint"] = source_fingerprint(p, "matrix", cell)
            cell["original_suggestion"] = {k: deepcopy(cell[k]) for k in
                ("suggested_score", "rationale", "evidence", "source_fingerprint")}
            p["matrix"].append(cell)
    prepared_labels = [("CO1", ["L1"]), ("CO1", ["L2"]), ("CO1", ["L4"]),
                       ("CO2", ["L4"]), ("CO2", ["L5"]), ("CO3", ["L4", "L5"]), ("CO3", ["L6"])]
    for index, ((number, text, marks), (cid, final_levels)) in enumerate(zip(SAMPLE_QUESTIONS, prepared_labels), 1):
        question = {"id": f"AQ{index}", "number": number, "text": text, "marks": marks}
        p["analysis_questions"].append(question)
        evidence = p["approved_cos"][int(cid[-1]) - 1]["evidence"]
        suggestion_levels = ["L2"] if index == 3 else final_levels
        p["analyses"][question["id"]] = {"suggestion": example_suggestion(cid, suggestion_levels,
                "Use this prepared example to demonstrate reviewing and correcting final labels.", evidence),
            "final_co": cid, "final_bloom": list(final_levels), "status": "approved",
            "notes": "Prepared correction: L4 reflects analysis of interacting components, beyond explanation." if index == 3 else "Demonstration labels; not a research ground truth.",
            "question_fingerprint": fingerprint(question), "source_fingerprint": source_fingerprint(p, "analysis", question)}
    bp = p["blueprint"]
    bp.update(title="Art & Aesthetics in Design — Demonstration paper", duration="90 minutes", date="2026-11-16",
        target_marks=30, module_ids=["M1", "M2", "M3"], co_ids=["CO1", "CO2", "CO3"],
        bloom_levels=["L2", "L4", "L5", "L6"], difficulty="Mixed",
        instructions="Answer all questions.\nUse neat labelled diagrams where necessary.\nSupport your answers with relevant examples.")
    bp["sections"] = [{"id": "SEC1", "title": "Section A — Art, aesthetics and society",
        "instructions": "Each question carries 5 marks.", "mode": "compulsory", "count": 6,
        "attempt": 6, "marks": 5, "question_marks": [], "subquestions": []}]
    for index, (slot, prepared) in enumerate(zip(build_slots(bp), PAPER_ITEMS)):
        item = {**slot, **{k: deepcopy(prepared[k]) for k in
            ("text", "co_id", "bloom_levels", "module_ids", "answer")},
            "difficulty": "Challenging" if index in (3, 5) else "Moderate",
            "rationale": DEMO_NOTE + " " + prepared["rationale"],
            "evidence": [{"module_id": prepared["module_ids"][0], "quote": prepared["quote"]}],
            "status": "needs_review" if index == 1 else "draft" if index == 5 else "approved",
            "locked": index not in (1, 5), "origin": PROVENANCE,
            "notes": "Prepared review example: inspect the differing Bloom suggestions." if index == 1 else "Presentation sample; review before adapting to a real assessment.",
            "marking_guide": [{"criterion": criterion, "marks": marks} for criterion, marks in prepared["criteria"]],
            "requested_co_ids": list(bp["co_ids"]), "requested_bloom_levels": list(bp["bloom_levels"]),
            "requested_module_ids": list(bp["module_ids"])}
        item["source_fingerprint"] = source_fingerprint(p, "paper", item)
        if index == 1:
            item["analysis"] = {"suggestion": example_suggestion("CO1", ["L2"],
                "A staged disagreement for demonstrating professor control; not an actual model prediction.", item["evidence"]),
                "disagrees": True, "status": "needs_review", "provenance": PROVENANCE,
                "question_fingerprint": fingerprint({"text": item["text"], "marks": item["marks"]}),
                "source_fingerprint": source_fingerprint(p, "analysis")}
        p["paper_questions"].append(item)
    refresh_dependencies(p)
    return p
