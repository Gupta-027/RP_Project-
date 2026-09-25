# Automatic Course Outcome and Bloom's Taxonomy Level Detection from Examination Questions using RAG and LLM

A small research prototype built as a college Research Project (RP).

---

## Problem statement

In our university, professors write examination questions manually and then map
each question to:

1. a **Course Outcome (CO)** defined for that course, and
2. one or more **Bloom's Taxonomy levels (BL)**.

This mapping is done by hand for every question of every paper. It is repetitive,
it takes time, and different faculty members sometimes map the same question
differently. The mapping is also needed for Outcome Based Education (OBE)
documentation, so it cannot be skipped.

## Objective

To investigate whether an AI system that combines **sentence embeddings**,
**retrieval**, **RAG** and an **LLM** can automatically *suggest* the correct CO
and Bloom level for a professor-written examination question.

Scope notes:

* The system **does not generate examination questions**. The professor writes them.
* The system **only suggests**. The professor reviews and can change every suggestion.
* The AI may only pick a CO from the list the professor entered. It can never
  invent a new CO.

## Methodology

For each question the pipeline runs these steps.

| Step | What happens |
|------|--------------|
| 1 | Every Course Outcome statement is converted into an embedding using `all-mpnet-base-v2`. |
| 2 | The syllabus is split into paragraph-based chunks of roughly 500-800 characters, and each chunk is embedded. |
| 3 | The examination question is embedded with the same model. |
| 4 | Cosine similarity is computed between the question and every CO. This gives a ranking such as `CO1 = 0.46, CO3 = 0.42, CO2 = 0.22`. This ranking is **retrieval evidence, not the final answer**. |
| 5 | Cosine similarity is computed between the question and every syllabus chunk, and the top 4 chunks are retrieved. |
| 6 | A prompt is built containing the course name, the question, the marks, all official COs, the CO similarity ranking, the retrieved syllabus chunks and the Revised Bloom's Taxonomy definitions. This is the **RAG** step. |
| 7 | The LLM (Gemini) is asked to answer with a small JSON object. The first field is `analysis`, so the model states the topic and the reasoning before it commits to a CO and a level. |
| 8 | The answer is **checked only if it needs checking**. If the LLM chose the same CO that retrieval ranked first and the COs are clearly separated, that single answer is accepted. Otherwise the same prompt is sent again (up to 3 times in total) and the majority answer wins. |
| 9 | The JSON is parsed and validated. The CO must exist in the entered CO list and the Bloom levels must be within L1-L6. If an answer is unusable the call is retried once; if every run fails the app shows *"Could not classify this question."* and continues with the next question. |
| 10 | The result is shown in a table where the professor can override the Final CO and Final BL, and export a CSV. |

### Step 8 in detail - asking again only when needed

The professor types each question **once**. The repeated LLM calls are internal,
and they do not happen on every question:

| Situation | What the system does |
|-----------|----------------------|
| The LLM picked the CO that retrieval also ranked first, and that CO wins by a clear margin | accept the answer, **1 LLM call** |
| The LLM picked a different CO from retrieval, **or** the top two COs are almost equally similar (gap < 0.06) | ask a second time; if the two runs choose the same CO, accept it, **2 LLM calls** |
| The first two runs disagree | ask a third time and take the majority, **3 LLM calls** |

The first run uses a near-deterministic temperature; the later runs sample, so a
re-check is a genuine second opinion rather than the same answer repeated.

On the five sample questions this used **7 LLM calls instead of 15**: the three
clear questions were decided in one call, and only the two where the CO
similarities were nearly tied (gaps of 0.038 and 0.004) needed a re-check. The
project still trades speed for accuracy where it matters - a larger embedding
model, and a second opinion on the uncertain questions - but it does not pay
that cost on questions that were never in doubt.

### Why retrieval is used instead of similarity alone

Cosine similarity alone can tell which CO statement is *worded* most like the
question, but it cannot judge the **cognitive level** the question demands. For
example `"Explain why method A is better than method B"` contains the verb
*Explain*, yet the actual task is a judgement (L5), not a plain L2 recall of an
explanation. The prompt explicitly instructs the model not to classify from the
verb alone.

Retrieval also helps the CO decision. Questions such as *"Discuss how they
interact with each other in the context of product design with reference to a
smart television"* do not repeat the wording of any CO, and the CO scores end up
close together (`CO1 = 0.377, CO3 = 0.312, CO2 = 0.145` in our test run). The
retrieved syllabus chunk for that question is the Unit 1 text about the Design
Quality Triangle, which is the context the LLM needs in order to place it
confidently under CO1. This is the gap the project is investigating.

### Revised Bloom's Taxonomy used

```
L1 Remember    L2 Understand    L3 Apply
L4 Analyze     L5 Evaluate      L6 Create
```

A question may legitimately carry more than one level (for example `L3, L4`),
because our university papers do use multiple BL values for a single question.

### Confidence

Confidence is reported only as **High / Medium / Low**. No fake percentage is
produced. It combines two independent pieces of evidence:

*Retrieval evidence* - the gap between the best and second-best CO cosine
similarity: `>= 0.15` -> High, `>= 0.06` -> Medium, smaller -> Low.

*LLM agreement* - how many of the runs that were actually made chose the same
CO: all of them -> High, a majority -> Medium, otherwise Low. A question decided
in a single call counts as full agreement, because it was only allowed to stop
early when retrieval already agreed with it.

The weaker of the two is taken, and it is lowered one further step if the LLM
chose a CO that retrieval did not rank first, because then the two sources of
evidence disagree. A Low row is a signal to the professor to look at that
question first.

## Architecture

```
Course details + Course Outcomes + Syllabus + Questions   (entered by the professor)
                              |
                              v
                   sentence-transformers
                   (all-mpnet-base-v2)
                              |
             +----------------+----------------+
             |                                 |
   cosine similarity vs COs        cosine similarity vs syllabus chunks
      (CO ranking)                       (top-4 chunks)
             |                                 |
             +----------------+----------------+
                              v
                        RAG prompt
                              |
                              v
                        LLM (Gemini)
                              |
                              v
          JSON  {analysis, co, bloom_levels, topic, reason}
                              |
                              v
         validation (CO must exist, BL must be L1-L6, retry once)
                              |
                              v
                   answer clear and agrees
                     with retrieval?  ---- no ---> ask again (max 3)
                              |                        |
                             yes                 majority vote
                              |                        |
                              +-----------+------------+
                                          v
              result table -> professor edits -> CSV export
```

### Research methods kept separate

The application always runs Method 3, because it is the most accurate of the
three. The other two are kept only as **baseline functions** in
[rag_pipeline.py](rag_pipeline.py) for the comparison chapter of the report;
they are not offered in the interface, so the professor is never asked to pick
an algorithm:

| Function | Method |
|----------|--------|
| `predict_co_similarity()` | Method 1 - cosine similarity only, no LLM. Predicts CO only, cannot predict a Bloom level. |
| `predict_llm_only()` | Method 2 - LLM with the COs but **without** the retrieved syllabus context and without the similarity ranking. |
| `predict_rag_llm()` | Method 3 - retrieval + LLM, with a second opinion only on uncertain questions. **This is what the application uses.** |

To evaluate the baselines later, call the functions directly from a small
script; no change to `app.py` is needed.

## Technology used

| Component | Choice |
|-----------|--------|
| UI | Streamlit (one page) |
| Embeddings | `sentence-transformers`, model `all-mpnet-base-v2` (768 dimensions) |
| Similarity | `scikit-learn` cosine similarity |
| LLM | Gemini (`gemini-3.5-flash-lite`) through its REST API using `requests` |
| PDF text | PyMuPDF |
| DOCX text | python-docx |
| Tables / CSV | pandas |

No vector database is used. The project handles a few COs and a few syllabus
chunks per course, so a plain NumPy matrix with cosine similarity is both
sufficient and easier to explain. A vector database would add infrastructure
without adding accuracy at this scale.

## Files

```
CO_mapping__RP/
├── app.py                    Streamlit single page application
├── rag_pipeline.py           embeddings, retrieval, RAG prompt, LLM call, validation
├── document_utils.py         PDF / DOCX / TXT text extraction
├── .streamlit/config.toml    forces the plain white theme
├── requirements.txt
├── .env.example
└── README.md
```

## Installation

```bash
pip install -r requirements.txt
```

The first run downloads the `all-mpnet-base-v2` model (about 420 MB)
automatically and caches it, so the first start is slow and needs an internet
connection. Later runs load it from the cache.

## API key configuration

1. Get a free Gemini API key from <https://aistudio.google.com/apikey>.
2. Copy `.env.example` to `.env`:

```bash
copy .env.example .env
```

3. Open `.env` and put your key in:

```
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-3.5-flash-lite
```

**Free tier quota matters.** The Gemini free tier limits requests *per model,
per day* - on the full `flash` models this can be as low as **20 requests per
day**, which is only about three demo runs. The `-lite` models have a much
larger allowance, which is why `gemini-3.5-flash-lite` is the default. If you
see the message *"the free tier daily quota is used up"*, either wait for the
reset or change `GEMINI_MODEL` in `.env` to another model id, since each model
has its own separate daily allowance.

If no `.env` file is present, the app shows a password box in the sidebar where
the key can be pasted for that session instead.

## Run command

```bash
streamlit run app.py
```

The app opens at <http://localhost:8501>.

## Example input

Press **"Load sample course data"** in the sidebar to fill in the test course.

Course: `ID2103 - Art & Aesthetics in Design`

```
CO1: Explain fundamental concepts and principles related to art, aesthetics and design quality.
CO2: Interpret and evaluate art in relation to identity, emotion and individual human experience.
CO3: Analyze the relationship between art, design, society and everyday life.
```

Question `1(a)`, 3 marks:

```
Explain the three primary components of the Design Quality Triangle.
```

## Expected type of output

The LLM returns a small JSON object:

```json
{
  "analysis": "The question asks for the three components of the Design Quality Triangle, which Unit 1 covers. That is a fundamental design concept, so it belongs to CO1. The student has to describe the components in their own words.",
  "co": "CO1",
  "bloom_levels": ["L2"],
  "topic": "Design Quality Triangle",
  "reason": "The question tests understanding of a fundamental design concept."
}
```

The `analysis` field is the model's reasoning step. It is not shown in the
result table; only `co`, `bloom_levels`, `topic` and `reason` are displayed.

and for a question that needs two cognitive steps:

```json
{
  "analysis": "...",
  "co": "CO1",
  "bloom_levels": ["L3", "L4"],
  "topic": "Design Quality Triangle",
  "reason": "The student must apply the concept to a product and analyse how its components relate."
}
```

This is displayed as a table with the columns *Question, Marks, Suggested CO,
Suggested BL, Topic, Confidence, Reason, Final CO, Final BL*. The last two
columns are editable by the professor, and the CSV export contains:

```
Question Number, Question, Marks, Final CO, Final Bloom Level
```

Note: these are the *type* of output expected. The actual values always come
from the pipeline at run time. No expected answer is hardcoded anywhere in the
code.

## Results actually observed

A live run on the ID2103 sample course (5 questions, `gemini-3.5-flash-lite`,
`all-mpnet-base-v2`) gave:

| | Result |
|---|---|
| Course Outcome agreement with the reference labels | **5 of 5** |
| Bloom level agreement | partial - see below |
| LLM calls used | 7 (not 15: three questions were decided in a single call) |
| Wall clock | about 17 seconds |

The Bloom levels were close but not exact. The system tended to add an extra
`L2` alongside the correct higher level, for example predicting `L2, L5` where
the reference label was `L5`, and predicting `L2` where the reference was
`L3, L4`. The higher level was usually present; the extra `L2` came from the
surface verb ("Explain", "Discuss") that the question happens to open with.

For comparison, the larger `gemini-3.5-flash` performed **worse** on the same
five questions (4 of 5 COs, one question failing to classify at all) and took
76 seconds, which is why the lite model is the default. This is a single
five-question run and should be read as an illustration, not as a measured
accuracy figure.

## Limitations

1. CO statements are written differently in every course, so the quality of the
   suggestion depends heavily on how precisely the COs are worded.
2. CO and Bloom classification is partly subjective. Two faculty members can
   reasonably assign different levels to the same question.
3. A single question can validly belong to more than one Bloom level, so a single
   "correct answer" does not always exist, and accuracy is harder to define.
4. The LLM output is a suggestion only. Faculty validation is required, and the
   application is designed around that assumption.
5. Results depend on the quality and completeness of the syllabus text. A short
   or badly extracted syllabus weakens the retrieval step.
6. The evaluation set in this project is very small (one course, five questions),
   so no statistical conclusion can be drawn from it. It only demonstrates that
   the pipeline works.
7. Automatic extraction of individual questions from a question paper PDF is not
   reliable, so manual entry is the primary input method. Upload is provided only
   as a text-extraction aid.
8. Cosine similarity with `all-mpnet-base-v2` is computed on general-purpose
   embeddings that were not trained on education or OBE text.
9. Asking the LLM again reduces random variation but does not remove it. Two or
   three runs can still agree on the same wrong answer, so agreement is not
   proof of correctness.
10. The rule that decides when to ask again uses a fixed similarity gap of 0.06,
    chosen by inspection of the sample course rather than by tuning on a
    labelled dataset. A question the system judged "clear" can still be wrong.
11. Course Outcome prediction was noticeably more reliable than Bloom level
    prediction in our runs. The Bloom level is the harder half of the problem,
    and the system still leans on the opening verb more than it should despite
    the prompt instructing otherwise.
12. The project depends on a third party API with a free tier daily quota. If
    the quota is exhausted the app reports it clearly and stops rather than
    retrying, but no classification is possible until the quota resets.

## Future scope

* Collect a larger labelled dataset of questions with faculty-approved CO and BL
  values, and report accuracy for Method 1, Method 2 and Method 3 on it.
* Measure agreement between two faculty members on the same set of questions, to
  establish a human baseline the system can be compared against.
* Try a domain-adapted or fine-tuned embedding model instead of a
  general-purpose one.
* Improve automatic question extraction from question-paper files.
* Let the professor's corrections be stored and used as few-shot examples in the
  prompt, so the system adapts to how a particular department maps questions.
