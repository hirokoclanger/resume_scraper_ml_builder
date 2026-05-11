#!/usr/bin/env python3
"""
Extract a structured bullet corpus from Philipp's resume source files.

Sources (in priority order):
  1. The 'master sentences' markdown file in CV/Resume/Claudes/ — authoritative
     structure for roles, dates, headers, summary, certifications.
  2. All .docx files under CV/Resume/Claudes/ (recursive) — phrasing variants
     merged into the master role buckets via company match.
  3. PDFs are skipped — every .docx covers the same content with cleaner
     extraction, and PDF text extraction introduces noise.

Output: corpus/corpus.json — single structured document with:
  - header: name, headline, location, contacts (from master)
  - summary_pool: candidate summary sentences with tags
  - skills_pool: candidate skill bullet lines
  - roles: ordered list of experience roles, each with a pool of candidate
    highlight bullets
  - projects, education, certifications, languages: small fixed lists

Each bullet is a dict: {id, text, source, tags[]}.

Run: python tailor/extract_corpus.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Optional

import docx  # python-docx

HERE = Path(__file__).resolve().parent.parent
CLAUDES = Path(
    "/Users/ttt/Library/Mobile Documents/com~apple~CloudDocs/CV/Resume/Claudes"
)
CORPUS_DIR = HERE / "corpus"
OUT_PATH = CORPUS_DIR / "corpus.json"
MASTER_NAME = "Philipp Eiselt Resume - master sentences.md"

# Section labels we recognise as headings inside docx files (case-insensitive,
# stripped of trailing punctuation). Anything else marked bold is treated as
# a role title.
SECTION_NAMES = {
    "summary", "profile", "core focus", "core competencies", "skills",
    "experience", "professional experience", "work experience",
    "education", "languages", "certifications", "certificates",
    "personal software projects", "projects", "personal projects",
    "founder ventures (concurrent, 2024 - present)",
}

# Roles in canonical order (most recent first). A heading line is matched to a
# role when ANY of its `match_keywords` substrings appear in the line
# (case-insensitive). Keywords are tuned to be unique enough that no false
# matches occur across the 5 roles.
CANONICAL_ROLES = [
    {
        "key": "aixxen_solo_2026",
        "position": "Solo Founder — AIXXEN (AI portfolio cockpit)",
        "company": "AIXXEN",
        "start_date": "2026-02",
        "end_date": "present",
        "location": "Solo, remote",
        "match_keywords": ["aixxen", "solo founder"],
        "master_only": True,
    },
    {
        "key": "icelt_2026",
        "position": "Independent IT Project, Governance & Transformation Consultant",
        "company": "ICELT",
        "start_date": "2026-01",
        "end_date": "present",
        "location": "Ho Chi Minh City, Vietnam",
        "match_keywords": ["consultant", "icelt", "independent it"],
        # Reject docx variants — the old freelance bullets are inaccurate now.
        "master_only": True,
    },
    {
        "key": "career_break_2026",
        "position": "Career break — Southeast Asia travel",
        "company": "Self-funded",
        "start_date": "2026-01",
        "end_date": "2026-03",
        "location": "Vietnam, Cambodia, Thailand",
        "match_keywords": ["career break", "southeast asia travel"],
        "master_only": True,
    },
    {
        "key": "man_portfolio_2022",
        "position": "IT Portfolio Manager and Product Owner",
        "company": "MAN Truck & Bus SE (Volkswagen Group / TRATON)",
        "start_date": "2022-09",
        "end_date": "2025-12",
        "location": "Munich, Germany",
        "match_keywords": ["portfolio manager", "portfolio and product", "product owner"],
    },
    {
        "key": "man_techpm_2018",
        "position": "Technical Project Manager (concurrent role)",
        "company": "MAN Truck & Bus SE",
        "start_date": "2018-01",
        "end_date": "2022-08",
        "location": "Munich, Germany",
        "match_keywords": ["technical project manager"],
    },
    {
        "key": "man_supervisor_2012",
        "position": "Supervisor, Production",
        "company": "MAN Truck & Bus SE",
        "start_date": "2012-12",
        "end_date": "2022-08",
        "location": "Munich, Germany",
        "match_keywords": ["supervisor"],
    },
    {
        "key": "man_operator_2004",
        "position": "Machine Operator and Group Coordinator",
        "company": "MAN Truck & Bus SE",
        "start_date": "2004-09",
        "end_date": "2012-11",
        "location": "Munich, Germany",
        "match_keywords": ["machine operator", "group coordinator"],
    },
]


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def dedup_key(text: str) -> str:
    t = re.sub(r"[^a-z0-9]+", "", text.lower())
    return t[:120]


KEYWORD_TAGS = {
    "governance": ["governance", "compliance", "audit", "policy", "raid"],
    "portfolio": ["portfolio", "intake", "book of work", "demand management"],
    "steering": ["steering", "committee", "forum", "executive", "cio", "board"],
    "servicenow": ["servicenow", "itsm"],
    "leanix": ["leanix", "enterprise architecture", "ea ", "eam "],
    "product_owner": ["product owner", "backlog", "sprint", "scrum", "safe", "agile"],
    "saas_cloud": ["azure", "aws", "saas", "cloud", "s/4hana", "sap"],
    "transformation": [
        "transformation", "rollout", "migration", "five-year", "5-year", "roadmap",
        "operating model", "change",
    ],
    "metric": [
        "%", "€", "eur", "m€", "$", "k$", "reduced", "increased", "cut by",
        "dropped", "lifted", "from ", " to ", "ROI", "uptime", "downtime",
    ],
    "leadership": [
        "led", "chaired", "owned", "ran ", "managed", "mentored", "supervised",
        "responsible for", "single point of contact",
    ],
    "tooling": [
        "servicenow", "leanix", "jira", "confluence", "power bi", "sap", "sap hr",
        "azure", "aws", "kubernetes", "power bi", "azure devops",
    ],
    "stakeholder_global": [
        "germany", "sweden", "portugal", "india", "brazil", "us ", "austria",
        "vietnam", "global", "cross-site", "cross-functional",
    ],
    "delivery": [
        "delivery", "rollout", "implementation", "commissioning", "handover",
        "go-live",
    ],
    "budget": ["budget", "forecast", "contingency", "variance", "cost", "€", "eur"],
}


def autotag(text: str) -> list[str]:
    low = text.lower()
    tags = []
    for tag, keywords in KEYWORD_TAGS.items():
        for kw in keywords:
            if kw in low:
                tags.append(tag)
                break
    return tags


def parse_master_md(path: Path) -> dict:
    """Parse the master sentences markdown. Returns the seed corpus structure."""
    if not path.exists():
        raise FileNotFoundError(f"Master sentences file missing: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()

    corpus = {
        "header": {
            "name": "Philipp Eiselt",
            "headline": "",
            "location": "",
            "email": "",
            "phone": "",
            "website": "",
            "linkedin": "",
        },
        "header_variants": {},   # key -> header dict; filled by parse step below
        "default_header_key": "germany",
        "summary_pool": [],
        "skills_pool": [],
        "roles": [
            {
                "key": r["key"],
                "position": r["position"],
                "company": r["company"],
                "start_date": r["start_date"],
                "end_date": r["end_date"],
                "location": r["location"],
                "highlights_pool": [],
                "summary_line": "",
            }
            for r in CANONICAL_ROLES
        ],
        "projects": [],
        "education": [],
        "certifications": [],
        "languages": [],
    }

    # Walk lines, tracking section + role context.
    section: Optional[str] = None       # "core_competencies" | "experience" | ...
    current_role_key: Optional[str] = None
    bullet_counter = {"sum": 0, "skl": 0, "exp": 0, "prj": 0, "cer": 0, "edu": 0, "lan": 0}

    def next_id(prefix: str) -> str:
        bullet_counter[prefix] += 1
        return f"{prefix}-{bullet_counter[prefix]:03d}"

    # The first few lines hold the header.
    if lines and lines[0].startswith("# "):
        # Title line — skip; name is hardcoded.
        pass
    # Find headline + contacts from the first few non-blank lines after the title.
    head_block = []
    for raw in lines[:8]:
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        head_block.append(s)
    if head_block:
        corpus["header"]["headline"] = head_block[0]
    for s in head_block[1:]:
        # Address line
        if any(tok in s.lower() for tok in ["str.", "strasse", "germany", "open to"]):
            corpus["header"]["location"] = s
        # Contact line
        elif "@" in s or "+" in s or "linkedin" in s.lower() or "icelt.net" in s.lower():
            parts = [p.strip() for p in re.split(r"\s+·\s+|\s+\|\s+", s)]
            for part in parts:
                if "@" in part and not corpus["header"]["email"]:
                    corpus["header"]["email"] = part
                elif part.startswith("+") and not corpus["header"]["phone"]:
                    corpus["header"]["phone"] = part
                elif "linkedin" in part.lower() and not corpus["header"]["linkedin"]:
                    corpus["header"]["linkedin"] = part
                elif "icelt.net" in part.lower() and not corpus["header"]["website"]:
                    corpus["header"]["website"] = part

    # Helper: find role index by canonical match_keywords.
    def role_idx_for_header(line: str) -> Optional[int]:
        low = line.lower()
        for i, r in enumerate(CANONICAL_ROLES):
            if any(kw in low for kw in r["match_keywords"]):
                return i
        return None

    # Body walk.
    current_header_key: Optional[str] = None
    header_buf: list[str] = []

    def flush_header_buf():
        """Commit the accumulated 3-line header variant into corpus."""
        nonlocal header_buf, current_header_key
        if not current_header_key or not header_buf:
            header_buf = []
            return
        # Lines: 0=headline, 1=location/rights, 2=contacts (· separated)
        headline = header_buf[0] if len(header_buf) > 0 else ""
        location = header_buf[1] if len(header_buf) > 1 else ""
        contacts_raw = header_buf[2] if len(header_buf) > 2 else ""
        h = {
            "name": "Philipp Eiselt",
            "headline": headline,
            "location": location,
            "email": "",
            "phone": "",
            "website": "",
            "linkedin": "",
        }
        parts = [p.strip() for p in re.split(r"\s+·\s+|\s+\|\s+", contacts_raw)]
        phones: list[str] = []
        for part in parts:
            low = part.lower()
            if "@" in part and not h["email"]:
                h["email"] = part
            elif part.startswith("+") or (re.match(r"^\d", part) and any(ch.isdigit() for ch in part)):
                # Multiple phones get joined with ' · ' so all show on the CV.
                phones.append(part if part.startswith("+") else f"+{part}")
            elif "linkedin" in low and not h["linkedin"]:
                h["linkedin"] = part
            elif (".net" in low or ".com" in low or ".app" in low or ".io" in low) and not h["website"]:
                h["website"] = part
        if phones:
            h["phone"] = " · ".join(phones)
        corpus["header_variants"][current_header_key] = h
        header_buf = []

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue
        # Headings
        m = re.match(r"^(#{2,3})\s+(.*)$", line)
        if m:
            # Closing any open header variant before changing sections.
            if section == "header_variants":
                flush_header_buf()
            level = len(m.group(1))
            txt = m.group(2).strip()
            low = re.sub(r"\s+", " ", txt.lower())
            if level == 2:
                if "core competenc" in low or low == "skills":
                    section = "skills"
                    current_role_key = None
                elif "header variants" in low or low == "header":
                    section = "header_variants"
                    current_header_key = None
                elif "summary" in low or "profile" in low:
                    section = "summary"
                    current_role_key = None
                elif "experience" in low:
                    section = "experience"
                    current_role_key = None
                elif "project" in low:
                    section = "projects"
                    current_role_key = None
                elif "education" in low:
                    section = "education"
                    current_role_key = None
                elif "language" in low:
                    section = "languages"
                    current_role_key = None
                elif "certif" in low:
                    section = "certifications"
                    current_role_key = None
                else:
                    section = None
                    current_role_key = None
            elif level == 3 and section == "experience":
                idx = role_idx_for_header(txt)
                current_role_key = CANONICAL_ROLES[idx]["key"] if idx is not None else None
            elif level == 3 and section == "header_variants":
                flush_header_buf()  # commit previous variant if any
                current_header_key = re.sub(r"[^a-z0-9_]+", "", txt.lower()) or None
                header_buf = []
            continue

        # Bullets ("- ..." or "* ...")
        m = re.match(r"^[-*]\s+(.*)$", line.strip())
        if m:
            text = normalise(m.group(1))
            if not text:
                continue
            if section == "skills":
                corpus["skills_pool"].append({
                    "id": next_id("skl"),
                    "text": text,
                    "source": MASTER_NAME,
                    "tags": autotag(text),
                })
            elif section == "experience" and current_role_key:
                for r in corpus["roles"]:
                    if r["key"] == current_role_key:
                        r["highlights_pool"].append({
                            "id": next_id("exp"),
                            "text": text,
                            "source": MASTER_NAME,
                            "tags": autotag(text),
                        })
                        break
            elif section == "projects":
                corpus["projects"].append({
                    "id": next_id("prj"),
                    "text": text,
                    "source": MASTER_NAME,
                    "tags": autotag(text),
                })
            elif section == "certifications":
                corpus["certifications"].append({
                    "id": next_id("cer"),
                    "text": text,
                    "source": MASTER_NAME,
                    "tags": autotag(text),
                })
            continue

        # Non-bullet body text — summary, role-summary (sub-headers under role), or
        # education/languages paragraphs.
        text = normalise(line.strip())
        if not text:
            continue
        if section == "header_variants" and current_header_key:
            # Skip the explanatory paragraph that appears before the first variant.
            if not header_buf and (text.startswith("Each variant") or text.lower().startswith("format")):
                continue
            header_buf.append(text)
            continue
        if section == "summary":
            corpus["summary_pool"].append({
                "id": next_id("sum"),
                "text": text,
                "source": MASTER_NAME,
                "tags": autotag(text),
            })
        elif section == "experience" and current_role_key:
            # Could be a role-summary sentence (intro paragraph under the role).
            for r in corpus["roles"]:
                if r["key"] == current_role_key:
                    if not r["summary_line"]:
                        # First non-bullet line under a role becomes the summary.
                        r["summary_line"] = text
                    else:
                        # Subsequent paragraphs join the highlights pool.
                        r["highlights_pool"].append({
                            "id": next_id("exp"),
                            "text": text,
                            "source": MASTER_NAME,
                            "tags": autotag(text),
                        })
                    break
        elif section == "education":
            corpus["education"].append({
                "id": next_id("edu"),
                "text": text,
                "source": MASTER_NAME,
                "tags": autotag(text),
            })
        elif section == "languages":
            corpus["languages"].append({
                "id": next_id("lan"),
                "text": text,
                "source": MASTER_NAME,
                "tags": autotag(text),
            })
        elif section == "projects":
            # Project intro paragraph (e.g. "Three solo full-stack builds…")
            corpus["projects"].append({
                "id": next_id("prj"),
                "text": text,
                "source": MASTER_NAME,
                "tags": autotag(text),
            })
        elif section == "skills":
            # The original "Core focus" line phrased as a paragraph; treat as a
            # single skills candidate.
            corpus["skills_pool"].append({
                "id": next_id("skl"),
                "text": text,
                "source": MASTER_NAME,
                "tags": autotag(text),
            })

    # Flush any trailing header variant that was left open at EOF / before a
    # section we already detected.
    if section == "header_variants":
        flush_header_buf()

    # Promote the chosen default header_variant to the top-level `header` for
    # back-compat with existing rendering paths.
    if corpus["header_variants"]:
        default_key = corpus["default_header_key"]
        if default_key not in corpus["header_variants"]:
            default_key = next(iter(corpus["header_variants"]))
            corpus["default_header_key"] = default_key
        corpus["header"] = dict(corpus["header_variants"][default_key])

    return corpus


def parse_docx(path: Path) -> list[tuple[str, str]]:
    """Return list of (section_hint, paragraph_text) from a docx file.

    section_hint is one of: "summary" | "skills" | "experience:<role_key>" |
    "projects" | "education" | "certifications" | "languages" | "" (unknown).
    Role detection is by substring match on the canonical role match_keywords.
    """
    try:
        d = docx.Document(str(path))
    except Exception as e:
        print(f"  ! cannot open {path.name}: {e}", file=sys.stderr)
        return []
    section: str = ""
    current_role_key: Optional[str] = None
    out: list[tuple[str, str]] = []
    for par in d.paragraphs:
        text = normalise(par.text)
        if not text:
            continue
        is_bold = bool(par.runs and par.runs[0].bold)
        low = text.lower()
        # Section header?
        if is_bold:
            stripped = re.sub(r"[:.\s]+$", "", low)
            if stripped in SECTION_NAMES or any(
                s in stripped for s in (
                    "summary", "core focus", "core competenc", "experience",
                    "education", "language", "certif", "project",
                )
            ):
                if "summary" in stripped or "profile" in stripped:
                    section = "summary"
                elif "core" in stripped or "skill" in stripped:
                    section = "skills"
                elif "experience" in stripped:
                    section = "experience"
                elif "project" in stripped or "venture" in stripped:
                    section = "projects"
                elif "education" in stripped:
                    section = "education"
                elif "language" in stripped:
                    section = "languages"
                elif "certif" in stripped:
                    section = "certifications"
                else:
                    section = ""
                current_role_key = None
                continue
            # A bold line inside experience can be a role header, a project
            # entry header (founder ventures / product names), or just a bolded
            # sentence. We only treat it as a role header when it matches
            # canonical keywords. If it looks like a projects pivot (founder /
            # venture / personal software), switch section to projects so any
            # following bullets land there. Otherwise we *clear* the current
            # role so subsequent non-bold paragraphs are dropped (safer than
            # spilling into the wrong role).
            if section == "experience":
                matched = False
                for r in CANONICAL_ROLES:
                    if any(kw in low for kw in r["match_keywords"]):
                        current_role_key = r["key"]
                        matched = True
                        break
                if not matched:
                    if any(t in low for t in ("founder venture", "personal software", "personal project", "side project")):
                        section = "projects"
                        current_role_key = None
                    else:
                        current_role_key = None
                continue
        # Body paragraph.
        if section == "experience" and current_role_key:
            out.append((f"experience:{current_role_key}", text))
        elif section in ("summary", "skills", "projects", "education", "languages", "certifications"):
            out.append((section, text))
    return out


def merge_into_corpus(corpus: dict, docx_extracts: list[tuple[Path, list[tuple[str, str]]]]) -> dict:
    """Merge extracted docx paragraphs into the seed corpus, deduping by
    normalised text. Each bullet keeps its first-seen source. New bullets get
    incrementing ids per section."""
    # Build lookup of existing dedup keys to suppress duplicates.
    seen: set[str] = set()
    for b in corpus["summary_pool"]:
        seen.add(dedup_key(b["text"]))
    for b in corpus["skills_pool"]:
        seen.add(dedup_key(b["text"]))
    for r in corpus["roles"]:
        for b in r["highlights_pool"]:
            seen.add(dedup_key(b["text"]))
        if r["summary_line"]:
            seen.add(dedup_key(r["summary_line"]))
    for b in corpus["projects"]:
        seen.add(dedup_key(b["text"]))
    for b in corpus["education"]:
        seen.add(dedup_key(b["text"]))
    for b in corpus["languages"]:
        seen.add(dedup_key(b["text"]))
    for b in corpus["certifications"]:
        seen.add(dedup_key(b["text"]))

    # Continue numbering from current max id per prefix.
    def next_id_factory(prefix: str, start: int):
        n = [start]
        def f():
            n[0] += 1
            return f"{prefix}-{n[0]:03d}"
        return f

    def max_id(pool: list[dict], prefix: str) -> int:
        mx = 0
        for b in pool:
            m = re.match(rf"^{prefix}-(\d+)$", b["id"])
            if m:
                mx = max(mx, int(m.group(1)))
        return mx

    role_pool_ids: dict[str, callable] = {}
    for r in corpus["roles"]:
        role_pool_ids[r["key"]] = next_id_factory("exp", max_id(r["highlights_pool"], "exp"))

    next_sum = next_id_factory("sum", max_id(corpus["summary_pool"], "sum"))
    next_skl = next_id_factory("skl", max_id(corpus["skills_pool"], "skl"))
    next_prj = next_id_factory("prj", max_id(corpus["projects"], "prj"))
    next_cer = next_id_factory("cer", max_id(corpus["certifications"], "cer"))
    next_edu = next_id_factory("edu", max_id(corpus["education"], "edu"))
    next_lan = next_id_factory("lan", max_id(corpus["languages"], "lan"))

    master_only_role_keys = {r["key"] for r in CANONICAL_ROLES if r.get("master_only")}
    for src_path, paragraphs in docx_extracts:
        for section_hint, text in paragraphs:
            key = dedup_key(text)
            if not key or key in seen:
                continue
            seen.add(key)
            tags = autotag(text)
            rec = {"text": text, "source": src_path.name, "tags": tags}
            if section_hint == "summary":
                rec["id"] = next_sum()
                corpus["summary_pool"].append(rec)
            elif section_hint == "skills":
                rec["id"] = next_skl()
                corpus["skills_pool"].append(rec)
            elif section_hint.startswith("experience:"):
                role_key = section_hint.split(":", 1)[1]
                if role_key in master_only_role_keys:
                    continue  # honour master_only — reject docx variants
                for r in corpus["roles"]:
                    if r["key"] == role_key:
                        rec["id"] = role_pool_ids[role_key]()
                        r["highlights_pool"].append(rec)
                        break
            elif section_hint == "projects":
                rec["id"] = next_prj()
                corpus["projects"].append(rec)
            elif section_hint == "certifications":
                rec["id"] = next_cer()
                corpus["certifications"].append(rec)
            elif section_hint == "education":
                rec["id"] = next_edu()
                corpus["education"].append(rec)
            elif section_hint == "languages":
                rec["id"] = next_lan()
                corpus["languages"].append(rec)
            # Unknown sections silently dropped.
    return corpus


def main() -> int:
    print(f"Reading master file: {MASTER_NAME}")
    master_path = CLAUDES / MASTER_NAME
    corpus = parse_master_md(master_path)
    print(f"  summary={len(corpus['summary_pool'])} skills={len(corpus['skills_pool'])}")
    for r in corpus["roles"]:
        print(f"  role {r['key']}: {len(r['highlights_pool'])} bullets")

    print(f"\nScanning {CLAUDES} for .docx files...")
    docx_files = sorted(p for p in CLAUDES.rglob("*.docx") if not p.name.startswith("~"))
    print(f"  found {len(docx_files)} docx files")
    extracts = []
    for p in docx_files:
        pars = parse_docx(p)
        extracts.append((p, pars))
        print(f"  {p.name}: {len(pars)} paragraphs")

    corpus = merge_into_corpus(corpus, extracts)

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(corpus, ensure_ascii=False, indent=2))
    print(f"\nWrote {OUT_PATH}")
    print(f"  summary={len(corpus['summary_pool'])} skills={len(corpus['skills_pool'])}")
    print(f"  projects={len(corpus['projects'])} certs={len(corpus['certifications'])}")
    print(f"  education={len(corpus['education'])} languages={len(corpus['languages'])}")
    for r in corpus["roles"]:
        print(f"  role {r['key']:<24} -> {len(r['highlights_pool'])} highlight candidates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
