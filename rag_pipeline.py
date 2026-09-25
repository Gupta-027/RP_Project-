"""
RAG pipeline for automatic CO and Bloom's level detection.

Flow for one examination question:

    question -> embedding -> cosine similarity with COs              (retrieval evidence)
                          -> cosine similarity with syllabus chunks  (course context)
                          -> RAG prompt -> LLM -> JSON -> validation

The application always uses predict_rag_llm(), which is the most accurate of the
three methods. The other two functions are the baselines kept for the comparison
chapter of the report; they are not exposed in the interface.

    predict_co_similarity()  Method 1 - embeddings only, no LLM      (baseline)
    predict_llm_only()       Method 2 - LLM without syllabus context (baseline)
    predict_rag_llm()        Method 3 - retrieval + LLM              (used by the app)

The professor enters each question once. The LLM is normally asked once as well.
It is asked a second and a third time only when the first answer looks uncertain,
and then the majority answer is used. See classify_with_agreement().
"""

import json
import os
import re
import time

import numpy as np
import requests
from dotenv import load_dotenv
from sklearn.metrics.pairwise import cosine_similarity

load_dotenv()

# Which sentence-transformer to use.
#   all-MiniLM-L6-v2   384 dims, about 500 MB of RAM - the default, and the one
#                      that fits inside the Streamlit Community Cloud limit.
#   all-mpnet-base-v2  768 dims, about 800 MB of RAM - better retrieval, use it
#                      locally by setting EMBEDDING_MODEL in .env.
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# The professor enters a question only once. Internally the LLM is normally
# asked only once too. It is asked again, up to this many times, only when the
# evidence is unclear, and then the majority answer is used.
MAX_LLM_RUNS = 3

# The two COs are treated as "almost equally similar" below this gap.
CLOSE_CO_GAP = 0.06

# Number of syllabus chunks retrieved for the RAG prompt.
TOP_K_CHUNKS = 4
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

VALID_BLOOM_LEVELS = ["L1", "L2", "L3", "L4", "L5", "L6"]

BLOOM_DEFINITIONS = """L1 Remember   - recall facts, definitions, terms, lists.
L2 Understand - explain an idea in your own words, describe, summarise, classify.
L3 Apply      - use a concept or procedure in a new or concrete situation.
L4 Analyze    - break something into parts, compare, examine relationships, find causes.
L5 Evaluate   - judge, justify, critique or defend a position using criteria.
L6 Create     - design, propose or combine elements into something new."""


# ----------------------------------------------------------------------
# Embeddings
# ----------------------------------------------------------------------

_model = None


def load_embedding_model():
    """Load the sentence-transformer once and reuse it."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def embed_texts(texts):
    """Return a numpy array of embeddings, one row per text."""
    model = load_embedding_model()
    return model.encode(texts, normalize_embeddings=True)


# ----------------------------------------------------------------------
# Syllabus chunking
# ----------------------------------------------------------------------

def chunk_syllabus(text, min_chars=500, max_chars=800):
    """
    Split the syllabus into paragraph based chunks of roughly 500-800 characters.
    Paragraphs are kept together whenever possible so a chunk stays readable.
    """
    if not text or not text.strip():
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    chunks = []
    current = ""

    for paragraph in paragraphs:
        # A very long paragraph is cut into sentences and regrouped.
        pieces = [paragraph]
        if len(paragraph) > max_chars:
            pieces = re.split(r"(?<=[.!?])\s+", paragraph)

        for piece in pieces:
            if not current:
                current = piece
            elif len(current) + len(piece) + 1 <= max_chars:
                current = current + " " + piece
            else:
                chunks.append(current.strip())
                current = piece

        if len(current) >= min_chars:
            chunks.append(current.strip())
            current = ""

    if current.strip():
        chunks.append(current.strip())

    return [c for c in chunks if c]


# ----------------------------------------------------------------------
# Retrieval
# ----------------------------------------------------------------------

def rank_course_outcomes(question_embedding, co_embeddings, co_ids):
    """
    Cosine similarity between the question and every CO.
    Returns a list of (co_id, score) sorted from the most to the least similar.
    """
    scores = cosine_similarity([question_embedding], co_embeddings)[0]
    ranking = list(zip(co_ids, [float(s) for s in scores]))
    ranking.sort(key=lambda pair: pair[1], reverse=True)
    return ranking


def retrieve_syllabus_chunks(question_embedding, chunk_embeddings, chunks, top_k=3):
    """Return the top-k syllabus chunks most similar to the question."""
    if len(chunks) == 0:
        return []

    scores = cosine_similarity([question_embedding], chunk_embeddings)[0]
    order = np.argsort(scores)[::-1][:top_k]
    return [(chunks[i], float(scores[i])) for i in order]


# ----------------------------------------------------------------------
# Confidence (simple interpretable rule, no fake percentages)
# ----------------------------------------------------------------------

LOWER_ONE_STEP = {"High": "Medium", "Medium": "Low", "Low": "Low"}


def estimate_confidence(co_ranking, predicted_co, votes_for_co=1, total_votes=1):
    """
    Confidence uses two independent pieces of evidence and reports only
    High / Medium / Low. No percentage is invented.

    (a) Retrieval evidence - how clearly the top CO wins the cosine similarity
        comparison:
            gap >= 0.15 -> High, gap >= 0.06 -> Medium, otherwise Low.

    (b) LLM agreement - how many of the repeated LLM runs chose the same CO:
            all runs agree -> High, a majority agrees -> Medium, otherwise Low.

    The weaker of the two is taken, and the result is lowered one more step if
    the LLM chose a CO that retrieval did not rank first, because then the two
    sources of evidence disagree.
    """
    if not co_ranking:
        return "Low"

    gap = 1.0 if len(co_ranking) < 2 else co_ranking[0][1] - co_ranking[1][1]
    if gap >= 0.15:
        retrieval_confidence = "High"
    elif gap >= CLOSE_CO_GAP:
        retrieval_confidence = "Medium"
    else:
        retrieval_confidence = "Low"

    if votes_for_co == total_votes:
        agreement_confidence = "High"
    elif votes_for_co * 2 > total_votes:
        agreement_confidence = "Medium"
    else:
        agreement_confidence = "Low"

    order = ["Low", "Medium", "High"]
    confidence = min(retrieval_confidence, agreement_confidence, key=order.index)

    if predicted_co and predicted_co != co_ranking[0][0]:
        confidence = LOWER_ONE_STEP[confidence]

    return confidence


# ----------------------------------------------------------------------
# LLM call (Gemini REST API)
# ----------------------------------------------------------------------

class LLMUnavailable(RuntimeError):
    """
    The API call itself failed: no key, a network problem, the daily quota is
    used up, or a server error. Sending the same prompt again would not help and
    would only waste more of the quota, so the pipeline stops asking.
    """


def call_llm(prompt, api_key=None, temperature=0.2):
    """
    Send the prompt to Gemini and return the raw text answer.
    Raises LLMUnavailable with a readable message when the call cannot be made.
    """
    api_key = api_key or os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise LLMUnavailable("GEMINI_API_KEY is not set. Add it to the .env file.")

    url = GEMINI_URL.format(model=GEMINI_MODEL)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }

    # The free Gemini endpoint sometimes answers 429 (rate limited) or 503
    # (busy). Those are temporary, so wait a moment and try the same call again
    # instead of failing the whole question.
    response = None
    for attempt in range(3):
        try:
            response = requests.post(
                url,
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=60,
            )
        except requests.RequestException as e:
            raise LLMUnavailable("Could not reach the LLM API: %s" % e)

        if response.status_code not in (429, 503):
            break
        time.sleep(2 * (attempt + 1))

    if response.status_code == 429:
        raise LLMUnavailable(
            "The Gemini free tier daily quota for model '%s' is used up. "
            "Wait until the quota resets, switch GEMINI_MODEL in .env to another "
            "model, or enable billing on the API key." % GEMINI_MODEL)

    if response.status_code != 200:
        raise LLMUnavailable(
            "LLM API error %s: %s" % (response.status_code, response.text[:300]))

    data = response.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(part.get("text", "") for part in parts)
    except (KeyError, IndexError):
        raise LLMUnavailable("Unexpected LLM response: %s" % str(data)[:300])


# ----------------------------------------------------------------------
# Prompt building
# ----------------------------------------------------------------------

def format_course_outcomes(course_outcomes):
    return "\n".join("%s: %s" % (co_id, text) for co_id, text in course_outcomes)


def build_prompt(question, marks, course_name, course_outcomes,
                 co_ranking=None, syllabus_chunks=None):
    """
    Build the classification prompt.

    co_ranking and syllabus_chunks are the retrieved evidence. When they are
    omitted the same prompt becomes the "LLM only" baseline (Method 2), which
    keeps the comparison in the report fair.
    """
    co_ids = [co_id for co_id, _ in course_outcomes]

    sections = [
        "You are helping a university professor map an examination question to one",
        "Course Outcome and to Revised Bloom's Taxonomy levels.",
        "",
        "COURSE: %s" % course_name,
        "",
        "OFFICIAL COURSE OUTCOMES:",
        format_course_outcomes(course_outcomes),
        "",
        "BLOOM'S TAXONOMY (Revised):",
        BLOOM_DEFINITIONS,
        "",
    ]

    if co_ranking:
        sections += [
            "SEMANTIC SIMILARITY (cosine similarity between the question and each CO):",
            "\n".join("%s: %.3f" % (co_id, score) for co_id, score in co_ranking),
            "This is retrieval evidence only. It is a hint, not the answer.",
            "",
        ]

    if syllabus_chunks:
        extracts = "\n\n".join(
            "[%d] %s" % (i + 1, chunk) for i, (chunk, _) in enumerate(syllabus_chunks)
        )
        sections += ["RELEVANT SYLLABUS EXTRACTS:", extracts, ""]

    sections += [
        "QUESTION TO CLASSIFY:",
        question,
        "MARKS: %s" % marks,
        "",
        "RULES:",
        '1. "co" must be exactly one of: %s. Never invent a new CO.' % ", ".join(co_ids),
        '2. "bloom_levels" must be a list containing only L1, L2, L3, L4, L5 or L6.',
        "3. Do not decide the Bloom level from the verb alone. Judge the complete",
        "   cognitive task the student has to perform. For example, Explain why",
        "   method A is better than method B is a judgement (L5), not a plain L2.",
        "4. Use more than one Bloom level only when the question genuinely requires",
        "   two distinct cognitive steps, for example applying a concept and then",
        "   analysing the relationships. Order them from lower to higher.",
        "5. Pick the CO whose subject matter the question actually tests. The",
        "   similarity ranking can be misleading when two COs share vocabulary,",
        "   so prefer the syllabus extracts and the meaning of the CO statement.",
        "6. If the question refers back to a previous question (for example",
        "   'discuss how they interact'), keep it under the same CO as the topic",
        "   it continues.",
        '7. "analysis" is where you think first: name the topic being tested, say',
        "   which CO covers that topic and why, then decide what the student has",
        "   to do cognitively. Write it before choosing the answer fields.",
        '8. "topic" is the short syllabus topic being tested (a few words).',
        '9. "reason" is one short sentence for the professor to read.',
        "",
        "Answer with JSON only, with the keys in exactly this order:",
        '{"analysis": "...", "co": "CO1", "bloom_levels": ["L2"], '
        '"topic": "...", "reason": "..."}',
    ]

    return "\n".join(sections)


# ----------------------------------------------------------------------
# Output parsing and validation
# ----------------------------------------------------------------------

def parse_llm_json(raw_text):
    """Extract the JSON object from the model answer. Returns None on failure."""
    if not raw_text:
        return None

    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None

    try:
        parsed = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, dict) else None


def validate_prediction(parsed, valid_co_ids):
    """
    Check the LLM answer against the COs entered by the professor and against
    the six Bloom levels. Returns (clean_result, error_message).
    """
    if not parsed:
        return None, "The model did not return valid JSON."

    co = str(parsed.get("co", "")).strip().upper().replace(" ", "")
    if co not in valid_co_ids:
        return None, "Predicted CO '%s' is not in the entered CO list." % co

    raw_levels = parsed.get("bloom_levels", [])
    if isinstance(raw_levels, str):
        raw_levels = [part.strip() for part in raw_levels.replace(",", " ").split()]
    if not isinstance(raw_levels, list):
        raw_levels = []

    levels = []
    for level in raw_levels:
        level = str(level).strip().upper().replace(" ", "")
        if level in VALID_BLOOM_LEVELS and level not in levels:
            levels.append(level)

    if not levels:
        return None, "No valid Bloom level (L1-L6) was returned."

    levels.sort()

    return {
        "co": co,
        "bloom_levels": levels,
        "topic": str(parsed.get("topic", "")).strip(),
        "reason": str(parsed.get("reason", "")).strip(),
    }, ""


def classify_with_llm(prompt, valid_co_ids, api_key=None, temperature=0.2):
    """
    Call the LLM, then parse and validate the answer. One retry with a stricter
    instruction if the first answer is unusable.
    Returns (result, error_message).
    """
    retry_prompt = prompt + (
        "\n\nYour previous answer was invalid. Reply with the JSON object only, "
        "nothing else, and use only the Course Outcome ids listed above."
    )

    # LLMUnavailable is deliberately not caught here: if the API itself failed
    # there is nothing to re-parse, so the caller stops instead of asking again.
    last_error = "Could not classify this question."
    for attempt_prompt in [prompt, retry_prompt]:
        raw = call_llm(attempt_prompt, api_key=api_key, temperature=temperature)

        result, error = validate_prediction(parse_llm_json(raw), valid_co_ids)
        if result:
            return result, ""
        last_error = error

    return None, last_error


def needs_second_opinion(result, co_ranking):
    """
    Decide whether one LLM answer is enough for this question.

    A second opinion is asked for only when the evidence is not clean:
      - the LLM chose a CO that semantic retrieval did not rank first, or
      - the best two COs are almost equally similar, so retrieval itself is
        undecided.

    When the LLM and retrieval already point at the same clearly winning CO,
    asking again would almost certainly repeat the same answer, so the extra
    calls are skipped.
    """
    if not co_ranking:
        return False

    if result["co"] != co_ranking[0][0]:
        return True

    gap = 1.0 if len(co_ranking) < 2 else co_ranking[0][1] - co_ranking[1][1]
    return gap < CLOSE_CO_GAP


def count_co_votes(answers):
    votes = {}
    for answer in answers:
        votes[answer["co"]] = votes.get(answer["co"], 0) + 1
    return votes


def classify_with_agreement(prompt, valid_co_ids, co_ranking, api_key=None,
                            max_runs=MAX_LLM_RUNS):
    """
    Ask the LLM once, and ask again only if the answer needs checking.

    The question itself is entered once by the professor. Internally:

      run 1  - near deterministic. If it agrees with semantic retrieval and the
               COs are clearly separated, this answer is accepted and no further
               call is made.
      run 2  - asked only when run 1 looked uncertain. If it chooses the same CO
               as run 1, the two agree and we stop.
      run 3  - asked only when run 1 and run 2 disagree. It breaks the tie.

    The final CO is the one most runs chose, and the Bloom levels are decided by
    majority among only the runs that chose that CO.

    Returns (result, error_message). The result carries "votes_for_co" and
    "total_votes" so the confidence rule can use the level of agreement.
    """
    answers = []
    last_error = "Could not classify this question."

    for i in range(max_runs):
        # the first run is near deterministic, later runs sample alternatives
        temperature = 0.1 if i == 0 else 0.6
        try:
            result, error = classify_with_llm(prompt, valid_co_ids, api_key=api_key,
                                              temperature=temperature)
        except LLMUnavailable as e:
            # the API is down or out of quota - stop, do not burn more calls
            last_error = str(e)
            break

        if not result:
            last_error = error
            continue

        answers.append(result)

        # the first answer is accepted straight away when the evidence is clean
        if len(answers) == 1 and not needs_second_opinion(result, co_ranking):
            break

        # otherwise stop as soon as two runs have chosen the same CO
        if max(count_co_votes(answers).values()) >= 2:
            break

    if not answers:
        return None, last_error

    co_votes = count_co_votes(answers)
    winning_co = max(co_votes, key=lambda co: co_votes[co])

    # majority vote on the Bloom levels, among only the runs that chose that CO
    matching = [a for a in answers if a["co"] == winning_co]
    bloom_votes = {}
    for answer in matching:
        key = tuple(answer["bloom_levels"])
        bloom_votes[key] = bloom_votes.get(key, 0) + 1
    winning_bloom = max(bloom_votes, key=lambda levels: bloom_votes[levels])

    # the explanation is taken from a run that matches the final answer
    best = next(a for a in matching if tuple(a["bloom_levels"]) == winning_bloom)

    return {
        "co": winning_co,
        "bloom_levels": list(winning_bloom),
        "topic": best["topic"],
        "reason": best["reason"],
        "votes_for_co": co_votes[winning_co],
        "total_votes": len(answers),
    }, ""


# ----------------------------------------------------------------------
# The three prediction methods
# ----------------------------------------------------------------------

def predict_co_similarity(question, course_outcomes, co_embeddings):
    """
    Method 1 - baseline. Cosine similarity only, no LLM.
    It can predict the CO but it cannot predict a Bloom level.
    """
    co_ids = [co_id for co_id, _ in course_outcomes]
    question_embedding = embed_texts([question])[0]
    ranking = rank_course_outcomes(question_embedding, co_embeddings, co_ids)

    return {
        "co": ranking[0][0],
        "bloom_levels": [],
        "topic": "",
        "reason": "Highest cosine similarity with the CO statement.",
        "co_ranking": ranking,
        "syllabus_chunks": [],
        "confidence": estimate_confidence(ranking, ranking[0][0]),
        "votes_for_co": 1,
        "total_votes": 1,
        "error": "",
    }


def predict_llm_only(question, marks, course_name, course_outcomes, api_key=None):
    """
    Method 2 - baseline. The LLM sees the question and the COs but gets no
    retrieved syllabus context and no similarity ranking.
    """
    co_ids = [co_id for co_id, _ in course_outcomes]
    prompt = build_prompt(question, marks, course_name, course_outcomes)
    try:
        result, error = classify_with_llm(prompt, co_ids, api_key=api_key)
    except LLMUnavailable as e:
        return failed_result(str(e))

    if not result:
        return failed_result(error)

    result.update({"co_ranking": [], "syllabus_chunks": [], "confidence": "Medium",
                   "votes_for_co": 1, "total_votes": 1, "error": ""})
    return result


def predict_rag_llm(question, marks, course_name, course_outcomes, co_embeddings,
                    syllabus_chunks, chunk_embeddings, api_key=None,
                    top_k=TOP_K_CHUNKS, max_runs=MAX_LLM_RUNS):
    """
    Method 3 - the method used by the application.

    The retrieved CO ranking and the retrieved syllabus chunks are added to the
    LLM prompt, so the model reasons with course specific context. The LLM is
    asked once, and asked again only when that first answer looks uncertain.
    """
    co_ids = [co_id for co_id, _ in course_outcomes]

    question_embedding = embed_texts([question])[0]
    co_ranking = rank_course_outcomes(question_embedding, co_embeddings, co_ids)

    retrieved = []
    if syllabus_chunks:
        retrieved = retrieve_syllabus_chunks(
            question_embedding, chunk_embeddings, syllabus_chunks, top_k=top_k
        )

    prompt = build_prompt(question, marks, course_name, course_outcomes,
                          co_ranking=co_ranking, syllabus_chunks=retrieved)
    result, error = classify_with_agreement(prompt, co_ids, co_ranking,
                                            api_key=api_key, max_runs=max_runs)

    if not result:
        failed = failed_result(error)
        failed["co_ranking"] = co_ranking
        failed["syllabus_chunks"] = retrieved
        return failed

    result.update({
        "co_ranking": co_ranking,
        "syllabus_chunks": retrieved,
        "confidence": estimate_confidence(
            co_ranking, result["co"], result["votes_for_co"], result["total_votes"]
        ),
        "error": "",
    })
    return result


def failed_result(error):
    """Used when the LLM answer could not be validated even after the retry."""
    return {
        "co": "",
        "bloom_levels": [],
        "topic": "",
        "reason": "Could not classify this question.",
        "co_ranking": [],
        "syllabus_chunks": [],
        "confidence": "Low",
        "votes_for_co": 0,
        "total_votes": 0,
        "error": error,
    }
