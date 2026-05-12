#!/usr/bin/env python3
"""Load a hand-curated drafts/Eiselt_*.md into a `tailored` dict ready for
render_pdf.render_pdf().

The drafts are the editorially-clean source of truth — written by the
recruiter agent, reviewed by Philipp, optionally further tweaked. They
short-circuit the BM25 retrieval engine: the bullets are already chosen
and ordered for a specific target role, so the library renders them
verbatim against any of the four header geographies.

Public API:
    list_drafts() -> list[dict]                   # one entry per drafts/Eiselt_*.md
    load_draft(name) -> dict (without header)     # text-level parse
    build_tailored(draft, header) -> dict         # render-ready
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

HERE = Path(__file__).resolve().parent.parent
DRAFTS_DIR = HERE / "drafts"
CORPUS_PATH = HERE / "corpus" / "corpus.json"

# Canonical role metadata shared with extract_corpus.py — duplicated here
# (instead of imported) to keep this module standalone. Updates rare.
# Keys / dates / locations stay in lockstep with CANONICAL_ROLES.
_CANONICAL = [
    ("aixxen_solo_2026", "AIXXEN", "2026-02", "present", "Solo, remote",
        ["aixxen", "solo founder"]),
    ("icelt_2026", "ICELT", "2026-01", "present", "Ho Chi Minh City, Vietnam",
        ["icelt", "independent it"]),
    ("career_break_2026", "Self-funded", "2026-01", "2026-03", "Vietnam, Cambodia, Thailand",
        ["career break", "southeast asia"]),
    ("man_portfolio_2022", "MAN Truck & Bus SE", "2022-09", "2025-12", "Munich, Germany",
        ["portfolio manager", "portfolio and product"]),
    ("man_techpm_2018", "MAN Truck & Bus SE", "2018-01", "2022-08", "Munich, Germany",
        ["technical project manager"]),
    ("man_supervisor_2012", "MAN Truck & Bus SE", "2012-12", "2022-08", "Munich, Germany",
        ["supervisor"]),
    ("man_operator_2004", "MAN Truck & Bus SE", "2004-09", "2012-11", "Munich, Germany",
        ["machine operator", "group coordinator"]),
]


_KW_BLOCK = re.compile(
    r"<!-- KEYWORDS_FROM_LISTINGS:START -->.*?<!-- KEYWORDS_FROM_LISTINGS:END -->\n?",
    re.DOTALL,
)


def list_drafts() -> list[dict]:
    """Return a sorted list of {key, name, label, path} for each draft on disk."""
    if not DRAFTS_DIR.exists():
        return []
    items: list[dict] = []
    for p in sorted(DRAFTS_DIR.glob("Eiselt_*.md")):
        # filename stem → display label. Two split points:
        #   1. lowercase → uppercase   ("ProductOwner" → "Product Owner")
        #   2. uppercase → uppercase-then-lowercase  ("ITProjectManager"
        #      → "IT Project Manager"; "PMO" stays "PMO").
        stem = p.stem.replace("Eiselt_", "")
        label = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])|(?<=[a-z])(?=[A-Z])", " ", stem)
        items.append({"key": stem, "label": label, "filename": p.name, "path": str(p)})
    return items


def _strip_keyword_block(text: str) -> str:
    return _KW_BLOCK.sub("", text)


def _section_split(text: str) -> dict[str, str]:
    """Split a draft into {section_heading_lower: body_text} pairs.
    Section headings are `## ...` lines. Body is the markdown between
    that heading and the next `## ` heading (or EOF)."""
    out: dict[str, str] = {}
    blocks = re.split(r"\n## ", "\n" + text)
    for block in blocks[1:]:  # blocks[0] is everything before the first `## `
        head, _, body = block.partition("\n")
        key = head.strip().lower()
        out[key] = body.strip()
    return out


def _parse_bullets(body: str) -> list[str]:
    """Return the `- ...` items in `body`, in order. Non-bullet prose is
    ignored. Surrounding whitespace stripped."""
    out: list[str] = []
    for line in body.splitlines():
        m = re.match(r"^\s*-\s+(.*)$", line)
        if m:
            out.append(m.group(1).strip())
    return out


def _match_canonical_role(heading: str) -> tuple[str, str, str, str, str] | None:
    """heading is the `### ...` line content (without the leading hashes).
    Returns (key, company, start_date, end_date, location) for the matching
    canonical role, or None."""
    low = heading.lower()
    for key, company, start, end, loc, kws in _CANONICAL:
        if any(kw in low for kw in kws):
            return key, company, start, end, loc
    return None


def _parse_experience(body: str) -> list[dict]:
    """Each `### ...` inside the Experience section is a role. Lines that
    follow up to the next `### ` are: optional (Company / Location) line
    (skipped), optional intro line, then bullets."""
    roles: list[dict] = []
    current_heading: str | None = None
    current_bullets: list[str] = []

    def flush():
        if current_heading is None:
            return
        canon = _match_canonical_role(current_heading)
        if not canon:
            return
        key, company, start, end, location = canon
        # The draft heading is `Position, Company, Date - Date`. Use the
        # first comma-separated part as the displayed position.
        position = current_heading.split(",")[0].strip()
        roles.append({
            "key": key,
            "position": position,
            "company": company,
            "start_date": start,
            "end_date": end,
            "location": location,
            "summary_line": "",
            "highlights": list(current_bullets),
        })

    for line in body.splitlines():
        m = re.match(r"^###\s+(.*)$", line)
        if m:
            flush()
            current_heading = m.group(1).strip()
            current_bullets = []
            continue
        bm = re.match(r"^\s*-\s+(.*)$", line)
        if bm:
            current_bullets.append(bm.group(1).strip())
    flush()
    return roles


def _parse_summary(body: str) -> str:
    """The Summary section is a single paragraph. Return it as plain text
    with internal newlines collapsed to spaces."""
    text = body.strip()
    return re.sub(r"\s+", " ", text)


def _parse_lines(body: str) -> list[str]:
    """Return non-bullet non-blank lines verbatim. Used for Education /
    Languages where the draft may have prose paragraphs."""
    return [ln.strip() for ln in body.splitlines() if ln.strip() and not ln.startswith("-")]


def _parse_headline(header_body: str) -> str | None:
    """The draft's ## Header section first content line is `**Bold Title**`.
    That title is the headline this draft wants under the candidate's name —
    it differs per role (e.g. "Senior IT Governance Manager" for the
    governance draft, "Senior Product Owner — ServiceNow ITSM / LeanIX" for
    the PO draft) and overrides the geography header's default headline."""
    for ln in header_body.splitlines():
        s = ln.strip()
        m = re.match(r"^\*\*(.+?)\*\*$", s)
        if m:
            return m.group(1).strip()
    return None


def load_draft(filename: str) -> dict:
    """Read one drafts/Eiselt_*.md and return a partial composition (no
    header — the caller supplies one)."""
    path = DRAFTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"draft not found: {path}")
    text = _strip_keyword_block(path.read_text(encoding="utf-8"))
    sections = _section_split(text)

    headline = _parse_headline(sections.get("header", ""))
    summary = _parse_summary(sections.get("summary", ""))
    skills = _parse_bullets(sections.get("core competencies", ""))
    roles = _parse_experience(sections.get("experience", ""))
    education = _parse_lines(sections.get("education", ""))
    certifications = _parse_bullets(sections.get("certifications", ""))
    languages = _parse_lines(sections.get("languages", ""))

    # Projects: drafts don't include the section by default. Pull from the
    # master corpus so PDFs include them consistently.
    projects = _master_projects()

    return {
        "headline": headline,
        "summary": summary,
        "skills": skills,
        "roles": roles,
        "projects": projects,
        "education": education,
        "certifications": certifications,
        "languages": languages,
    }


def _master_projects() -> list[dict]:
    """Three solo product entries from the corpus, formatted for RenderCV.

    Parse note: each project line looks like
        `AIXXEN ([www.aixxen.com](https://www.aixxen.com)). description...`
    The naive `\\(([^)]*)\\)` pattern fails because the markdown link
    contains nested parens. Splitting on the first `"). "` delimiter is
    reliable — that's the end of the name+link block in every entry.
    """
    if not CORPUS_PATH.exists():
        return []
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    out: list[dict] = []
    seen: set[str] = set()
    for b in corpus.get("projects", []):
        if not b.get("source", "").endswith(".md"):
            continue
        text = b["text"]
        # First word is the project name. RenderCV will display it bold.
        name_m = re.match(r"^([A-Za-z][A-Za-z0-9_]*)\b", text)
        if not name_m:
            continue
        name = name_m.group(1)
        if name in seen:
            continue
        seen.add(name)
        # Description starts after the first "). " (close-paren period
        # space) if present; otherwise from the first ". " after the
        # name; otherwise just trail the whole text after the name.
        idx = text.find("). ")
        if idx > 0:
            rest = text[idx + 3:].strip()
        else:
            rest = text[len(name):].lstrip(". ").strip()
        out.append({"name": name, "summary": rest})
    return out


def build_tailored(draft_filename: str, header: dict, *, draft_label: str | None = None) -> dict:
    """Assemble the full render-ready dict from a draft + a chosen header
    variant. The draft's headline override (parsed from its ## Header
    section) replaces the geography header's default headline so each
    cell's top line matches the draft's target role title."""
    body = load_draft(draft_filename)
    merged_header = dict(header)
    if body.get("headline"):
        merged_header["headline"] = body["headline"]
    return {
        "profile": "draft",
        "profile_label": draft_label or draft_filename.replace("Eiselt_", "").replace(".md", ""),
        "variant": "draft",
        "variant_label": "Draft",
        "header": merged_header,
        "summary": body["summary"],
        "skills": body["skills"],
        "roles": body["roles"],
        "projects": body["projects"],
        "education": body["education"],
        "certifications": body["certifications"],
        "languages": body["languages"],
        "trace": {"source": "draft", "draft": draft_filename},
    }
