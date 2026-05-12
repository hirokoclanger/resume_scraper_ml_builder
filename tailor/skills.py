#!/usr/bin/env python3
"""Skill registry + JD/CV skill extraction for the v2 tailored page.

Powers /api/jd_analyze: identify the high-value skills the JD demands, then
check which of those already appear in the candidate's CV bullets so the
React page can render a coverage gauge and a missing-skills list per the
2026 research recommendation that 76 % of recruiters filter by skills
first.

Editorial-team-maintained: when Philipp encounters a JD requirement the
engine doesn't recognise, add the skill below. No code changes needed
elsewhere — the registry is the single source of truth.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Skill:
    canonical: str           # display label
    aliases: tuple[str, ...] # case-insensitive substrings that map to this skill
    category: str            # for grouping in the UI


# Curated registry. Order is roughly importance / specificity — first match
# wins when aliases overlap (e.g. "agile coaching" should match the
# specific phrase before the generic "agile" token).
SKILL_REGISTRY: tuple[Skill, ...] = (
    # --- Platforms / tools (the highest-signal skills for IT roles) ---
    Skill("ServiceNow ITSM", ("servicenow itsm", "service now itsm"), "platforms"),
    Skill("ServiceNow", ("servicenow", "service now", "now platform"), "platforms"),
    Skill("LeanIX", ("leanix", "lean ix"), "platforms"),
    Skill("Jira", ("jira",), "platforms"),
    Skill("Confluence", ("confluence",), "platforms"),
    Skill("SAP S/4HANA", ("s/4hana", "s4hana", "s/4 hana"), "platforms"),
    Skill("SAP", ("sap ", "sap.", "sap,"), "platforms"),
    Skill("Microsoft Azure", ("azure",), "platforms"),
    Skill("Amazon AWS", ("aws", "amazon web services"), "platforms"),
    Skill("Google Cloud", ("gcp", "google cloud"), "platforms"),
    Skill("Power BI", ("power bi", "powerbi"), "platforms"),
    Skill("Tableau", ("tableau",), "platforms"),
    Skill("Snowflake", ("snowflake",), "platforms"),
    Skill("Kubernetes", ("kubernetes", "k8s"), "platforms"),

    # --- Methods & frameworks ---
    Skill("Agile", ("agile",), "methods"),
    Skill("Scrum", ("scrum",), "methods"),
    Skill("SAFe", ("safe ", "scaled agile"), "methods"),
    Skill("Kanban", ("kanban",), "methods"),
    Skill("Lean", ("lean ", "lean methodology"), "methods"),
    Skill("Six Sigma", ("six sigma", "6 sigma"), "methods"),
    Skill("BPM", ("bpm", "business process management"), "methods"),
    Skill("RPA", ("rpa", "robotic process automation"), "methods"),
    Skill("Waterfall", ("waterfall",), "methods"),
    Skill("DevOps", ("devops",), "methods"),
    Skill("Hybrid delivery", ("hybrid delivery", "hybrid agile"), "methods"),

    # --- Governance / portfolio practices ---
    Skill("IT Portfolio Management", ("portfolio management", "it portfolio", "project portfolio"), "governance"),
    Skill("Steering committee", ("steering committee", "steering cadence", "steering forum"), "governance"),
    Skill("RAID management", ("raid management", "raid log", "raid"), "governance"),
    Skill("Change control", ("change control", "change management"), "governance"),
    Skill("Risk management", ("risk management", "risk framework"), "governance"),
    Skill("Audit", ("audit",), "governance"),
    Skill("Compliance", ("compliance", "regulatory"), "governance"),
    Skill("Policy framework", ("policy framework", "control framework"), "governance"),
    Skill("Capacity planning", ("capacity planning",), "governance"),
    Skill("Demand management", ("demand management",), "governance"),
    Skill("PMO", ("pmo",), "governance"),
    Skill("Enterprise Architecture", ("enterprise architecture", "ea ", "eam"), "governance"),

    # --- Product / delivery ---
    Skill("Product Owner", ("product owner", "po"), "product"),
    Skill("Product Manager", ("product manager", "product management"), "product"),
    Skill("Backlog management", ("backlog",), "product"),
    Skill("User stories", ("user stories", "user story"), "product"),
    Skill("Roadmap", ("roadmap",), "product"),
    Skill("Discovery", ("product discovery", "discovery work", "customer interview"), "product"),
    Skill("OKRs", ("okr", "objectives and key results"), "product"),

    # --- AI / ML ---
    Skill("AI Governance", ("ai governance", "ai policy", "responsible ai"), "ai"),
    Skill("AI Evaluation", ("ai evaluation", "ai investment evaluation", "ai roi", "model evaluation"), "ai"),
    Skill("AI Strategy", ("ai strategy", "ai roadmap", "ai vision"), "ai"),
    Skill("Machine Learning", ("machine learning", "ml ops", "mlops"), "ai"),
    Skill("LLM", ("llm ", "large language model"), "ai"),
    Skill("EU AI Act", ("eu ai act", "ai act"), "ai"),

    # --- Leadership / stakeholder ---
    Skill("CIO reporting", ("cio reporting", "report to cio", "cio level"), "leadership"),
    Skill("Board reporting", ("board reporting", "board level", "executive board"), "leadership"),
    Skill("Cross-functional leadership", ("cross-functional", "cross functional"), "leadership"),
    Skill("Vendor management", ("vendor management", "vendor coordination"), "leadership"),
    Skill("Stakeholder management", ("stakeholder management", "stakeholder engagement"), "leadership"),
    Skill("Mentoring", ("mentor", "coaching"), "leadership"),

    # --- Certifications ---
    Skill("PMP", ("pmp",), "certifications"),
    Skill("PRINCE2", ("prince2", "prince 2"), "certifications"),
    Skill("PSM I", ("psm i", "professional scrum master"), "certifications"),
    Skill("CSM", ("csm ", "certified scrum master"), "certifications"),
    Skill("ITIL", ("itil",), "certifications"),
    Skill("SAFe Scrum", ("safe scrum",), "certifications"),

    # --- Industry / domain ---
    Skill("Automotive", ("automotive", "commercial vehicle"), "industry"),
    Skill("Industrial / Manufacturing", ("industrial", "manufacturing", "shop floor", "production"), "industry"),
    Skill("Banking", ("banking", "financial services", "fintech"), "industry"),
    Skill("Consulting", ("consulting", "advisory"), "industry"),
)


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    return re.sub(r"\s+", " ", text)


def extract_skills(text: str) -> list[str]:
    """Return canonical skill labels present in `text`. Order matches the
    registry (highest-signal first)."""
    norm = _normalise(text)
    found: list[str] = []
    seen: set[str] = set()
    for skill in SKILL_REGISTRY:
        if skill.canonical in seen:
            continue
        for alias in skill.aliases:
            if alias.lower() in norm:
                found.append(skill.canonical)
                seen.add(skill.canonical)
                break
    return found


def coverage(jd_text: str, cv_texts: Iterable[str]) -> dict:
    """Compare the skills demanded by `jd_text` against the union of
    `cv_texts` (typically summary + skills + every picked bullet).

    Returns:
      {
        "jd_skills":      [...],            # canonical labels present in JD
        "present":        [...],            # subset in CV too
        "missing":        [...],            # JD skills NOT in CV
        "coverage_pct":   float,            # len(present)/len(jd_skills)
        "by_category":    {cat: {"present":[], "missing":[]}, ...},
      }
    """
    jd_skills = extract_skills(jd_text)
    joined_cv = "\n".join(t or "" for t in cv_texts)
    cv_skills = set(extract_skills(joined_cv))
    present = [s for s in jd_skills if s in cv_skills]
    missing = [s for s in jd_skills if s not in cv_skills]
    pct = (len(present) / len(jd_skills) * 100.0) if jd_skills else 0.0
    by_cat: dict[str, dict] = {}
    skill_to_cat = {sk.canonical: sk.category for sk in SKILL_REGISTRY}
    for s in present:
        by_cat.setdefault(skill_to_cat.get(s, "other"), {"present": [], "missing": []})["present"].append(s)
    for s in missing:
        by_cat.setdefault(skill_to_cat.get(s, "other"), {"present": [], "missing": []})["missing"].append(s)
    return {
        "jd_skills": jd_skills,
        "present": present,
        "missing": missing,
        "coverage_pct": round(pct, 1),
        "by_category": by_cat,
    }
