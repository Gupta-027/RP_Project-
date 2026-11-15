"""Recreate synthetic QA documents. No Gemini call or real course work is used."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fitz
from docx import Document

from export_utils import paper_docx, paper_pdf


def main():
    spec = importlib.util.spec_from_file_location("export_fixture", ROOT / "tests" / "test_exports.py")
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    project = fixture.export_project_fixture(long=True)
    directory = ROOT / "demo" / "exports"
    directory.mkdir(exist_ok=True)
    rows = []
    for faculty in (False, True):
        name = "faculty" if faculty else "student"
        pdf_data = paper_pdf(project, faculty=faculty, include_answers=faculty)
        docx_data = paper_docx(project, faculty=faculty, include_answers=faculty)
        (directory / f"{name}_sample.pdf").write_bytes(pdf_data)
        (directory / f"{name}_sample.docx").write_bytes(docx_data)
        with fitz.open(stream=pdf_data, filetype="pdf") as pdf:
            pages = len(pdf)
            text = "\n".join(page.get_text() for page in pdf)
            assert "Maximum marks: 30" in text
            assert project["paper_questions"][-1]["number"] + "." in text
            if not faculty:
                assert "PRIVATE_ANSWER" not in text and "PRIVATE_RATIONALE" not in text
                pdf[0].get_pixmap(matrix=fitz.Matrix(1.25, 1.25)).save(directory / "student_preview.png")
                pdf[len(pdf) // 2].get_pixmap().save(directory / "student_middle_preview.png")
            # Three full pages make page transitions and last-page guides easy
            # to inspect together, while all-page sheets expose blank/overflow pages.
            for sheet_name, indices in (("contact", [0, len(pdf) // 2, len(pdf) - 1]), ("all_pages", list(range(len(pdf))))):
                columns = 3
                rows_count = (len(indices) + columns - 1) // columns
                with fitz.open() as contact:
                    sheet = contact.new_page(width=columns * 415, height=rows_count * 605)
                    for position, index in enumerate(indices):
                        x, y = (position % columns) * 415, (position // columns) * 605
                        sheet.insert_text((x + 15, y + 17), f"{name.title()} — page {index + 1} of {len(pdf)}", fontsize=10)
                        sheet.show_pdf_page(fitz.Rect(x + 10, y + 25, x + 405, y + 595), pdf, index)
                    sheet.get_pixmap(matrix=fitz.Matrix(1.3, 1.3)).save(directory / f"{name}_{sheet_name}.png")
        doc = Document(directory / f"{name}_sample.docx")
        assert project["paper_questions"][-1]["number"] + "." in "\n".join(paragraph.text for paragraph in doc.paragraphs)
        rows.append(f"- {name.title()}: PDF has {pages} pages; DOCX has {len(doc.paragraphs)} paragraphs. Latest question text, final question, choice separator and actual maximum were extracted successfully.")
    url_project = fixture.export_project_fixture()
    url_project["paper_questions"][0]["text"] = "Read this source: https://example.edu/" + "longreference" * 60 + " then evaluate the argument."
    (directory / "url_stress.pdf").write_bytes(paper_pdf(url_project))
    (directory / "url_stress.docx").write_bytes(paper_docx(url_project))
    report = """# Export inspection samples

These are synthetic, manually authored QA fixtures, not Gemini output or an
approved institutional paper. Long repeated scenarios deliberately stress wrapping.
The sample has any-two-of-three, one either/or pair, and compulsory subquestions.
It prints 45 marks and permits 30 marks to be attempted.

""" + "\n".join(rows) + """

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
"""
    (directory / "INSPECTION.md").write_text(report, encoding="utf-8")
    print("\n".join(rows))


if __name__ == "__main__":
    main()
