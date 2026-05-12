#!/usr/bin/env python3
"""Render the same tailored composition as PDF, but as a .docx that ATS
systems parse most reliably (research_2026.md §"Format Rules").

Pandoc isn't installed on this machine, so we write the .docx directly
with python-docx. This is *deliberately* plain — no tables, no columns,
no text boxes, no header/footer with key info, no embedded images other
than the optional headshot, no fancy styling. Order and content match
the PDF; only the visual polish differs.

Public API mirrors `render_pdf`:
    render_docx(tailored, output_dir, filename_stem, *, include_photo=True) -> Path
"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

# Same helpers as the PDF renderer.
from tailor.render_pdf import (  # noqa: E402  — same package
    find_photo,
    slugify,                       # re-exported for callers
    _split_phones,
)


_PURPLE = RGBColor(0x4A, 0x2D, 0x96)


def _set_style(run, *, bold=False, italic=False, size_pt=None, color=None, font="Calibri"):
    run.bold = bold
    run.italic = italic
    if size_pt is not None:
        run.font.size = Pt(size_pt)
    if color is not None:
        run.font.color.rgb = color
    run.font.name = font


def _h2(doc: Document, text: str):
    """Section title bar — bold purple capitalised text with a thin underline."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(3)
    r = p.add_run(text.upper())
    _set_style(r, bold=True, size_pt=11, color=_PURPLE)
    # Add the underline via the paragraph's bottom border. python-docx
    # doesn't expose this directly so we drop into the XML.
    from docx.oxml.ns import nsdecls, qn
    from docx.oxml import OxmlElement
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "8071BD")
    pBdr.append(bottom)
    pPr.append(pBdr)


def _bullet(doc: Document, text: str):
    p = doc.add_paragraph(style="List Bullet")
    r = p.add_run(text)
    _set_style(r, size_pt=10)
    p.paragraph_format.space_after = Pt(2)


def _para(doc: Document, text: str, *, bold=False, size_pt=10, align=None, space_after=None):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    r = p.add_run(text)
    _set_style(r, bold=bold, size_pt=size_pt)
    if space_after is not None:
        p.paragraph_format.space_after = Pt(space_after)


def _header_block(doc: Document, header: dict, photo_path: Path | None):
    """Top of document: name + headline + contact lines. python-docx doesn't
    do floating images well so the headshot, if present, sits inline at the
    right edge of the name paragraph."""
    # Name line
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r = p.add_run(header.get("name", "Philipp Eiselt"))
    _set_style(r, bold=True, size_pt=22)
    if photo_path and photo_path.exists():
        # Inline image after a tab — ATS parsers ignore images, so this is
        # cosmetic only.
        p.add_run().add_break()
    if photo_path and photo_path.exists():
        # Floating-like effect: separate paragraph for the photo at the top
        # right. ATS won't read it; humans will see it.
        photo_p = doc.add_paragraph()
        photo_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        photo_run = photo_p.add_run()
        try:
            photo_run.add_picture(str(photo_path), width=Inches(1.1))
        except Exception:
            pass

    if header.get("headline"):
        _para(doc, header["headline"], size_pt=12, space_after=4)

    # Address (line 1) + availability (line 2) on separate paragraphs.
    location = (header.get("location") or "").strip()
    parts = [p_.strip() for p_ in re.split(r"\s+·\s+|\s+\|\s+", location) if p_.strip()]
    if parts:
        _para(doc, parts[0].rstrip(",") + ",", size_pt=10, space_after=2)
    if len(parts) > 1:
        avail = ", ".join(re.sub(r"\s+-\s+", ", ", x) for x in parts[1:])
        _para(doc, avail, size_pt=10, space_after=4)

    # Contact line — email | phone | website | linkedin, comma-joined for ATS.
    primary_phone, extra_phones = _split_phones(header.get("phone", ""))
    contacts = []
    if header.get("email"):    contacts.append(header["email"])
    if primary_phone:          contacts.append(primary_phone)
    for ep in extra_phones:    contacts.append(ep)
    if header.get("website"):  contacts.append(header["website"])
    if header.get("linkedin"): contacts.append(header["linkedin"])
    if contacts:
        _para(doc, ", ".join(contacts), size_pt=10, space_after=6)


def render_docx(tailored: dict, output_dir: Path, filename_stem: str,
                *, include_photo: bool = True) -> Path:
    """Render tailored composition as a .docx. Returns the produced path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    doc = Document()
    # Tighter margins, A4 ATS-safe.
    for section in doc.sections:
        section.top_margin = Inches(0.6)
        section.bottom_margin = Inches(0.6)
        section.left_margin = Inches(0.7)
        section.right_margin = Inches(0.7)

    photo = find_photo() if include_photo else None
    _header_block(doc, tailored["header"], photo)

    # Section order matches the PDF.
    if tailored.get("summary"):
        _h2(doc, "Summary")
        _para(doc, tailored["summary"], size_pt=10, space_after=6)

    if tailored.get("roles"):
        _h2(doc, "Experience")
        for r in tailored["roles"]:
            if not r["highlights"]:
                continue
            # Role title + company + dates in one bold line, location on the next.
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(0)
            rb = p.add_run(f"{r['position']}, {r['company']}")
            _set_style(rb, bold=True, size_pt=10)
            rb2 = p.add_run(f"   {r['start_date']} – {r['end_date']}")
            _set_style(rb2, italic=True, size_pt=10)
            if r.get("location"):
                _para(doc, r["location"], size_pt=10, space_after=2)
            for h in r["highlights"]:
                _bullet(doc, h)

    if tailored.get("education"):
        _h2(doc, "Education")
        for line in tailored["education"]:
            _para(doc, line, size_pt=10, space_after=2)

    if tailored.get("projects"):
        _h2(doc, "Personal Software Projects")
        for proj in tailored["projects"]:
            name = proj.get("name", "")
            summary = proj.get("summary", "")
            if name and summary:
                p = doc.add_paragraph()
                p.paragraph_format.space_after = Pt(2)
                rn = p.add_run(name + ". ")
                _set_style(rn, bold=True, size_pt=10)
                rs = p.add_run(summary)
                _set_style(rs, size_pt=10)
            elif name:
                _para(doc, name, bold=True, size_pt=10, space_after=2)
            elif summary:
                _para(doc, summary, size_pt=10, space_after=2)

    if tailored.get("languages"):
        _h2(doc, "Languages")
        for line in tailored["languages"]:
            _para(doc, line, size_pt=10, space_after=2)

    if tailored.get("skills"):
        _h2(doc, "Core Competencies")
        for s in tailored["skills"]:
            _bullet(doc, s)

    if tailored.get("certifications"):
        _h2(doc, "Certifications")
        for line in tailored["certifications"]:
            _bullet(doc, line)

    target = output_dir / f"{filename_stem}.docx"
    if target.exists():
        target.unlink()
    doc.save(target)
    return target
