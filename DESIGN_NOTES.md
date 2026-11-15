# Faculty workspace design lock

The existing Streamlit light theme and the supplied brief are the build target.
Refero live research was attempted but returned `NO_SUBSCRIPTION`; no live
reference screens were available. Research uses the installed Refero typography,
craft-details, and visual-workflow guides instead.

| Decision | Source | Role and reason |
| --- | --- | --- |
| White canvas, blue primary actions, dark text | User brief and existing config | Preserve the academic workspace; blue identifies actions rather than decoration. |
| Six sidebar sections with course and review counts | User brief; craft navigation/state guide | Keep course context visible and allow returning without losing edits. |
| Native labelled controls and editable tables | User brief; craft forms/accessibility guide | Retain keyboard focus, readable tables, and explicit save/approval actions. |
| Three heading levels, system sans, generous spacing | Refero typography guide | Keep hierarchy consistent without external fonts or frontend dependencies. |
| Separate draft suggestions, professor final values, evidence expanders | Research brief | Make provenance and control visible; never erase suggestions on override. |
| Marks summary beside an explicit continuation warning | Marks requirements | Keep the actual attemptable marks visible; attach acknowledgement to the exact blueprint. |
| Choice and subquestion controls in expanders | User brief; craft forms guide | Progressive disclosure keeps the default blueprint straightforward. |
| Subject name at the top of the paper builder, shared with course setup | User's missing-subject screenshot; existing Streamlit form design | Make the subject visible beside the work it controls; retain one course per project. |
| Full Course Outcome statements in selection, plain-language CO definition, direct setup navigation | User's unexplained CO error; Refero craft form guidance | Explain the required choice before generation, preserve deliberate approval and existing blueprint edits. |
| Setup checklist and disabled AI action when course content is missing | User's empty-course screenshot; existing validation rules | Keep marks acknowledgement independent of subject readiness and provide the next step inline. |

Reject decorative imagery, gradients, unreadable muted text, CSS overrides of
Streamlit internals, and colour-only status. No custom frontend assets are needed.
Visual QA must be reported separately from Streamlit AppTest interaction checks.

## Institutional opening-page reference lock

The requested project cover and the existing white/blue Streamlit theme are the
direct-build target. Live Refero research remains unavailable (`NO_SUBSCRIPTION`);
the installed typography and craft/accessibility references guide this extension.
The authentic emblem comes from the NIT Rourkela website, unchanged. The student,
roll number and supervisor information is supplied explicitly by the user.

| Decision | Reference / role | Reason |
| --- | --- | --- |
| Official emblem with institute and department lockup | NIT Rourkela official site and supplied affiliation | Make the institutional context visible before the project introduction. |
| Dark navy project title on a pale blue academic cover | Existing white/blue theme; Refero typography guide | Establish a readable heading and clear visual hierarchy without a decorative font. |
| Presented-by and supervisor details in equal information panels | User's requested project-cover content | Show Gupta Prasad Adhikari, 123ID0885 and Prof. B.B.V.L. Deepak on first arrival. |
| Project overview as the initial route, followed by the existing six sections | User's requested opening experience | Keep the introduction visible to new visitors and preserve free workspace navigation. |
| Hover/focus treatment with native buttons on six module cards | Refero focus/forms guide; existing workspace navigation | Provide pointer feedback while retaining keyboard access and saved project state. |

Tokens: white canvas; #F4F7FC cover/field surface; #14283E text; #52647A secondary
text; existing #2A6BD4 action accent; #E1E7EF borders; restrained 12–18px radii.
Only owned HTML classes and Streamlit's documented container-key classes are
styled. Keep emblem colours, native focus rings, and reduced-motion preferences.
Reject gradients, fabricated research metrics, automatic hover navigation and
changes to student/faculty paper export content for this introduction-only work.

Verification: all 99 tests pass, including first-visit content, all six module
launchers, preservation of saved course data, and restoring the overview after
loading the presentation demo. Chrome checks at 1440 × 1000 and 390 × 844 confirmed
the bundled emblem loads, the module border changes on hover, every module opens,
and there are no application/runtime exceptions or mobile horizontal overflow.
Desktop and mobile cover/module screenshots were inspected against this lock;
evidence is stored in `.tmp/qa/21–24` and `overview-report.json`.

## Real-browser verification

On 16 November 2026, the app was inspected in local headless Chrome through the
Chrome DevTools Protocol using an isolated task profile. Desktop screenshots used
1440 × 1000 pixels; mobile screenshots used 390 × 844 pixels.

The browser loaded the ID2103 sample and navigated all six workspace pages. The
course fields, syllabus controls, outcome drafts, programme configuration, question
table, blueprint and review empty state rendered without Streamlit or browser
runtime exceptions. Mobile controls stacked without horizontal page overflow.

A separate temporary harness supplied a clearly labelled, manually authored paper
fixture. Five compulsory questions worth five marks each, with target 30, showed
an actual maximum of 25 in the student preview. The browser changed the target,
verified that the acknowledgement was invalidated, and continued explicitly with
the revised blueprint. A question was edited through real input events and saved;
its latest text appeared after navigating to Review & Export. The question editor,
marks warning, coverage tables and desktop/mobile preview were visually inspected.

Fourteen local screenshots and detailed reports are under `.tmp/qa/`, which is
ignored by Git. The key evidence files are `10-fixture-marks-override.png`,
`11-fixture-ack-invalidated.png`, `12-fixture-edited-preview.png`,
`13-fixture-preview-mobile.png`, `14-fixture-question-editor.png` and
`qa-summary.json`. A concise check manifest is retained in
`demo/ui_qa_report.json`; local screenshot paths need a fresh QA run in another
checkout.

Both local Streamlit health checks returned HTTP 200. The QA servers and isolated
browser instance were stopped afterwards. This browser run made no live Gemini
requests and downloaded no embedding model. PDF pagination and PDF/DOCX content
were covered by separate export checks. Visual DOCX pagination remains unverified
because desktop Word rendering was unavailable.

## Subject and outcome setup follow-up

The user's empty-course screenshot exposed a missing explanation at the point of
generation. The paper builder now starts with a shared subject-name field and
direct syllabus/outcome setup buttons. Approved outcome options show their full
statements, and choosing all approved outcomes remains an explicit action.
The subject checklist and marks acknowledgement report separate prerequisites.

The follow-up passed 91 automated tests. Real Chrome checks confirmed subject
entry is shared with Course & Syllabus, setup navigation works, an individually
approved sample CO appears by ID and statement, generation stays disabled before
setup, and mobile width has no page overflow. No browser or Streamlit exception
occurred in the successful run, and no live AI generation was requested.
Screenshots 15–17 and `subject-setup-report.json` are stored under `.tmp/qa/`.

## One-click presentation data

The requested presentation action uses the existing native primary button and
status banner patterns. It loads a separate, complete project, opens the paper
preview, and keeps one in-session snapshot for Restore previous work. Prepared
suggestions, staged approvals and illustrative programme outcomes remain labelled;
no live prediction, cosine measurement or accuracy claim is fabricated. The demo
flag survives JSON export/import and adds a sample label to paper exports.

All 96 automated checks passed. An isolated Chrome session loaded the demo in one
click, visited all six populated sections, prepared the four PDF/DOCX downloads,
restored the previous project and reloaded the demo. Desktop and mobile screenshots
were inspected with no page overflow or application/runtime exceptions. No AI
generation/check action was invoked. Screenshots 18–19 and
`presentation-demo-report.json` are in `.tmp/qa/`.
