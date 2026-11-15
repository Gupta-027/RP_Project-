# Export inspection samples

These are synthetic, manually authored QA fixtures, not Gemini output or an
approved institutional paper. Long repeated scenarios deliberately stress wrapping.
The sample has any-two-of-three, one either/or pair, and compulsory subquestions.
It prints 45 marks and permits 30 marks to be attempted.

- Student: PDF has 7 pages; DOCX has 25 paragraphs. Latest question text, final question, choice separator and actual maximum were extracted successfully.
- Faculty: PDF has 10 pages; DOCX has 115 paragraphs. Latest question text, final question, choice separator and actual maximum were extracted successfully.

Student documents exclude answer keys, evidence, CO/Bloom labels and internal
review notes. Faculty samples intentionally contain obvious PRIVATE_* fixture
markers to verify content separation. Marking guides are labelled reviewable drafts.
First/middle/last and all-page contact sheets were visually inspected for the
student and faculty PDFs. Guide labels stay with the first answer fragment; an
additional automated case verifies that a 30,000-character answer continues
through pages without dropping its final marker. The long-URL stress files verify
that unbroken references wrap rather than being clipped.
Automated geometry checks verify every PDF text block stays inside page bounds;
DOCX uses A4, fixed margins, heading keep-with-next, and free-flowing question
paragraphs instead of tables. DOCX visual pagination was not rendered in this
environment: the installed Word COM server could not open without a desktop logon
session (HRESULT 80070520); no LibreOffice renderer was available. Word/LibreOffice
pagination depends on the installed fonts and renderer; inspect it in the faculty
editor before distribution and after institution-specific formatting changes.

Recreate from the repository root: `python demo/create_export_samples.py`.
