#!/usr/bin/env python3
"""Aggregate JD-derived skills/keywords per draft role and embed them
into the drafts/*.md files.

For each scored job, classify into the closest of the seven role drafts
using a keyword-overlap scorer (title + description), then run the
canonical SKILL_REGISTRY over the JD text. Skill frequencies are summed
per role, then each drafts/<role>.md is updated in place with a
"## Keywords from recent listings" block delimited by HTML comment
markers so re-runs replace the block instead of duplicating.

Reads:  results/jobs_scored.json
Writes: drafts/Eiselt_*.md  (in-place, between the marker block)

Usage:
    .venv/bin/python tailor/analyze_listings.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SCORED = HERE / "results" / "jobs_scored.json"
DRAFTS_DIR = HERE / "drafts"

sys.path.insert(0, str(HERE))
from tailor.skills import extract_skills  # noqa: E402

# Each draft role is identified by a strong-signal keyword set.
# The classifier scores a JD against each set (substring matches on the
# normalised title + first 2000 chars of description). Highest score
# wins; ties broken by the role declared first.
DRAFT_ROLES = [
    {
        "key": "ITGovernance",
        "label": "IT Governance",
        "must_include_any": ["governance"],
        "boost_keywords": [
            "raid", "audit", "policy", "control framework", "compliance",
            "steering committee", "risk management", "policy framework",
            "data governance", "ai governance",
        ],
    },
    {
        "key": "PortfolioManager",
        "label": "Project Portfolio Manager",
        "must_include_any": ["portfolio"],
        "boost_keywords": [
            "intake", "prioritisation", "prioritization", "capacity planning",
            "demand management", "book of work", "budget",
            "portfolio management", "ppm",
        ],
    },
    {
        "key": "PMO",
        "label": "PMO",
        "must_include_any": ["pmo", "programme office", "program office", "project management office"],
        "boost_keywords": [
            "methodology", "standards", "delivery framework", "mentor",
            "coaching", "project managers", "governance cadence",
            "reporting", "stage gate",
        ],
    },
    {
        "key": "StrategicIT",
        "label": "Strategic IT",
        "must_include_any": ["strategy", "strategic", "transformation"],
        "boost_keywords": [
            "roadmap", "five-year", "5-year", "business case", "cio",
            "executive", "operating model", "multi-year", "vision",
            "modernisation", "modernization",
        ],
    },
    {
        "key": "ManagementConsultant",
        "label": "Management Consultant",
        "must_include_any": ["consultant", "consulting", "advisor", "advisory"],
        "boost_keywords": [
            "engagement", "client", "principal", "partner", "practice",
            "billable", "delivery lead", "managing consultant",
        ],
    },
    {
        "key": "ITProjectManager",
        "label": "IT Project Manager",
        "must_include_any": ["project manager", "project lead", "programme manager", "program manager"],
        "boost_keywords": [
            "it project", "agile", "scrum", "safe", "jira", "scope", "schedule",
            "raid", "go-live", "sprint", "stakeholder",
        ],
        "exclude_if_any": [],
    },
    {
        "key": "ProjectManager",
        "label": "Project Manager (general)",
        "must_include_any": ["project manager", "project lead"],
        "boost_keywords": [
            "engineering", "plant", "construction", "manufacturing",
            "production", "cross-functional", "vendor", "contractor",
        ],
        # General PM only wins when the JD does NOT specifically say "IT".
        "exclude_if_any": ["it project manager", "senior it pm", "it programme manager", "software"],
    },
]


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def classify(title: str, description: str) -> str | None:
    """Return the role key with the highest match score, or None if no role
    meets its `must_include_any` threshold."""
    blob = normalise(title) + " || " + normalise(description)[:2000]
    scores: list[tuple[int, str]] = []
    for role in DRAFT_ROLES:
        if not any(kw in blob for kw in role["must_include_any"]):
            continue
        if any(neg in blob for neg in role.get("exclude_if_any", [])):
            continue
        score = sum(2 for kw in role["must_include_any"] if kw in blob)
        score += sum(1 for kw in role.get("boost_keywords", []) if kw in blob)
        scores.append((score, role["key"]))
    if not scores:
        return None
    scores.sort(key=lambda x: -x[0])
    return scores[0][1]


def aggregate(jobs: list[dict]) -> dict[str, dict]:
    """Return {role_key: {"n": int, "skill_counts": Counter,
    "companies": [...]}} from the scored jobs."""
    out: dict[str, dict] = defaultdict(lambda: {
        "n": 0, "skill_counts": Counter(), "companies": [], "titles": [],
    })
    for j in jobs:
        title = j.get("title", "") or ""
        desc = j.get("description", "") or ""
        role_key = classify(title, desc)
        if not role_key:
            continue
        bucket = out[role_key]
        bucket["n"] += 1
        bucket["companies"].append(j.get("companyName", "") or "")
        bucket["titles"].append(title)
        for skill in extract_skills(title + " " + desc):
            bucket["skill_counts"][skill] += 1
    return out


MARKER_START = "<!-- KEYWORDS_FROM_LISTINGS:START -->"
MARKER_END = "<!-- KEYWORDS_FROM_LISTINGS:END -->"


def render_block(role_key: str, agg: dict, scrape_ts: str) -> str:
    """Render the markdown block to inject. Idempotent — re-runs overwrite."""
    n = agg["n"]
    if n == 0:
        return (
            f"{MARKER_START}\n"
            f"## Keywords from recent listings\n\n"
            f"> No listings classified as **{role_key}** in the latest scrape\n"
            f"> ({scrape_ts}). Adjust the classifier keywords in\n"
            f"> `tailor/analyze_listings.py` or run a wider scrape.\n"
            f"{MARKER_END}\n"
        )
    skill_counts: Counter = agg["skill_counts"]
    high, mid, low = [], [], []
    for skill, count in sorted(skill_counts.items(), key=lambda x: -x[1]):
        pct = (count / n) * 100
        line = f"**{skill}** _{count}/{n} · {pct:.0f}%_"
        if pct >= 50:
            high.append(line)
        elif pct >= 20:
            mid.append(line)
        else:
            low.append(line)

    # Company sample (up to 8 unique)
    seen, samples = set(), []
    for c in agg["companies"]:
        if c and c not in seen:
            seen.add(c)
            samples.append(c)
        if len(samples) >= 8:
            break

    parts = [
        MARKER_START,
        "## Keywords from recent listings",
        "",
        f"> Aggregated from **{n} listings** classified as *{role_key}* in the scrape of {scrape_ts}.",
        "> Frequencies are computed against the canonical skill registry.",
        "> Use this to validate which competencies to surface first.",
        "",
    ]
    if high:
        parts.append("**High frequency (≥ 50 % of listings)** — must surface in your top half of page 1.")
        parts.append("")
        for line in high:
            parts.append(f"- {line}")
        parts.append("")
    if mid:
        parts.append("**Medium frequency (20 – 50 %)** — surface if you have legitimate experience.")
        parts.append("")
        for line in mid:
            parts.append(f"- {line}")
        parts.append("")
    if low:
        parts.append("**Low frequency (< 20 %)** — niche; ignore unless the specific listing names it.")
        parts.append("")
        for line in low[:15]:
            parts.append(f"- {line}")
        if len(low) > 15:
            parts.append(f"- _… {len(low)-15} more low-frequency skills omitted_")
        parts.append("")
    if samples:
        parts.append(f"**Sample companies** (up to 8 of {len(set(agg['companies']))}): {', '.join(samples)}")
        parts.append("")
    parts.append(MARKER_END)
    return "\n".join(parts) + "\n"


def upsert_block(md_path: Path, block: str) -> bool:
    """Inject `block` into `md_path`, replacing any existing block between
    the markers. Returns True if the file was modified."""
    if not md_path.exists():
        return False
    original = md_path.read_text(encoding="utf-8")
    pattern = re.compile(
        re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END) + r"\n?",
        re.DOTALL,
    )
    if pattern.search(original):
        new = pattern.sub(block, original)
    else:
        # Insert before the trailing boilerplate sections (Education / Certs / Languages)
        # — pick whichever section heading appears first.
        anchor_idx = None
        for anchor in ("## Education", "## Certifications", "## Languages"):
            i = original.find(anchor)
            if i >= 0 and (anchor_idx is None or i < anchor_idx):
                anchor_idx = i
        if anchor_idx is None:
            new = original.rstrip() + "\n\n" + block
        else:
            new = original[:anchor_idx] + block + "\n" + original[anchor_idx:]
    if new == original:
        return False
    md_path.write_text(new, encoding="utf-8")
    return True


def main() -> int:
    if not SCORED.exists():
        print(f"ERROR: {SCORED} missing — run scrape_jobs.py + score_jobs.py first")
        return 2
    data = json.loads(SCORED.read_text())
    jobs = data.get("jobs", [])
    scrape_ts = data.get("scraped_at_utc") or data.get("scored_at_utc") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if isinstance(scrape_ts, str):
        scrape_ts = scrape_ts[:10]

    print(f"Classifying {len(jobs)} jobs into 7 role buckets …")
    agg = aggregate(jobs)
    total_classified = sum(b["n"] for b in agg.values())
    print(f"  classified: {total_classified} / {len(jobs)} (rest: off-topic / unclassifiable)")
    print()

    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    for role in DRAFT_ROLES:
        key = role["key"]
        md = DRAFTS_DIR / f"Eiselt_{key}.md"
        bucket = agg.get(key, {"n": 0, "skill_counts": Counter(), "companies": [], "titles": []})
        block = render_block(key, bucket, scrape_ts)
        changed = upsert_block(md, block)
        marker = "✓ updated" if changed else "= unchanged"
        if not md.exists():
            marker = "✗ no draft file"
        print(f"  {marker}  {md.name:<40} n={bucket['n']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
