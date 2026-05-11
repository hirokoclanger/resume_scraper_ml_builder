#!/usr/bin/env python3
"""
Graph-based scorer (v2) — alternative scoring engine.

Treats Philipp's resume as a concept graph with rings of decreasing relevance:
  core   = exact tools/methods (ServiceNow, LeanIX, IT portfolio mgmt, Lean)
  inner  = directly adjacent (governance, transformation, PMO, agile)
  middle = tangential but plausible (cloud, SAP, BI, vendor mgmt)
  outer  = generic IT vocabulary (data, system, platform, integration)

A job's fit_score_v2 is the sum of (ring_weight x match_count), with off-domain
keywords subtracting. Reads jobs_raw.json and merges its v2 fields into
results/jobs_scored.json (preserves the v1 fit_score from score_jobs.py).

Run:  python3 score_jobs_v2.py
"""
import json
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"
RESULTS_DIR.mkdir(exist_ok=True)
CONFIG_PATH = HERE / "config.json"
RAW_PATH = RESULTS_DIR / "jobs_raw.json"
LATEST_PATH = RESULTS_DIR / "jobs_latest.json"
SCORED_PATH = RESULTS_DIR / "jobs_scored.json"
EXCEL_PATH = RESULTS_DIR / "fitting_jobs.xlsx"
DASHBOARD_PATH = HERE / "dashboard.html"

MIN_EXCEL_SCORE_V2 = 40
STRONG_THRESHOLD_V2 = 65
MAYBE_THRESHOLD_V2 = 45
WEAK_THRESHOLD_V2 = 30

# ----------------------------------------------------------------------------
# CONCEPT GRAPH
# Each ring has a weight per match. Distance from "Philipp's center" =
# inverse of relevance.
# ----------------------------------------------------------------------------

CONCEPT_GRAPH = {
    "core": {
        "weight": 6,
        "keywords": [
            # English (exact tools/methods)
            "servicenow", "leanix",
            "it portfolio management", "project portfolio management",
            "process optimization", "operational excellence",
            "process improvement", "process excellence",
            "lean six sigma", "kaizen", "continuous improvement",
            "ai investment", "ai governance", "ai use case evaluation",
            # German (same concepts)
            "it-portfoliomanagement", "projektportfoliomanagement",
            "prozessoptimierung", "prozessverbesserung", "prozessexzellenz",
            "operative exzellenz", "kontinuierliche verbesserung", "kvp",
            "ki-governance", "ki-investition", "ki-strategie",
        ],
    },
    "inner": {
        "weight": 4,
        "keywords": [
            "it governance", "it strategy", "it operating model",
            "pmo", "project portfolio", "portfolio management",
            "program governance", "delivery governance",
            "transformation", "digital transformation",
            "change management", "organizational change", "ocm",
            "stakeholder management", "executive stakeholder",
            "agile", "scrum", "safe", "scaled agile",
            "product owner", "scrum master",
            "lean", "process governance",
            "raid", "dependencies", "decision template",
            "operating cadence", "ways of working",
            # German
            "it-governance", "it-strategie", "it-betriebsmodell",
            "portfoliomanagement", "projektportfolio", "programmleitung",
            "programmmanagement", "projektsteuerung",
            "digitale transformation", "geschäftstransformation",
            "geschaftstransformation", "veränderungsmanagement",
            "veranderungsmanagement", "wandel", "umstrukturierung",
            "stakeholder-management", "stakeholdermanagement",
            "agil", "agilität", "agilitat", "agile methoden",
            "lenkungsausschuss", "lenkungskreis",
            "anforderungsmanagement", "abhängigkeitsmanagement",
            "abhangigkeitsmanagement",
            "prozessmanagement", "geschäftsprozess", "geschaftsprozess",
        ],
    },
    "middle": {
        "weight": 2,
        "keywords": [
            "cloud migration", "cloud transformation", "saas",
            "azure", "aws", "gcp", "google cloud", "hyperscaler",
            "sap", "s/4hana", "salesforce", "workday", "oracle fusion",
            "enterprise architecture", "target operating model", "tom",
            "vendor management", "procurement", "sourcing", "rfp",
            "kpi", "dashboards", "power bi", "tableau",
            "business intelligence", "analytics", "reporting",
            "risk management", "compliance", "audit", "iso 27001",
            "grc", "internal controls",
            "ciso", "cio", "cto", "cfo", "c-level",
            "operating model", "delivery model",
            "intake", "stage gate", "prioritization",
            "budget management", "budget control", "financial controlling",
            "burn rate", "forecasting", "variance",
            # German
            "cloud-migration", "cloud-transformation",
            "unternehmensarchitektur", "unternehmensarchitekt",
            "lieferantenmanagement", "einkauf", "beschaffung",
            "kennzahlen", "auswertungen", "berichtswesen",
            "risikomanagement", "datensicherheit", "informationssicherheit",
            "geschäftsleitung", "geschaftsleitung", "vorstand",
            "budgetverantwortung", "budgetplanung", "budgetkontrolle",
            "finanzcontrolling", "kostenmanagement",
            "datenanalyse", "datenstrategie",
            "priorisierung", "wirtschaftlichkeitsanalyse",
        ],
    },
    "outer": {
        "weight": 1,
        "keywords": [
            "data", "system", "systems", "platform", "platforms",
            "application", "applications", "integration", "integrations",
            "api", "apis", "software", "engineering",
            "automation", "workflow", "workflows",
            "infrastructure", "devops", "sre", "kubernetes",
            "agile delivery", "kanban", "sprint", "backlog",
            "stakeholder", "governance", "improvement", "optimization",
            "ml", "machine learning", "genai", "llm",
            "metric", "metrics", "scorecard",
            # German
            "daten", "systeme", "plattform", "plattformen",
            "anwendung", "anwendungen", "applikation", "applikationen",
            "integration", "schnittstellen", "infrastruktur",
            "automatisierung", "ablauf", "abläufe", "ablaufe",
            "kennzahl", "berichte", "reporting", "kpi",
            "kunstliche intelligenz", "künstliche intelligenz",
            "ki", "maschinelles lernen",
        ],
    },
    # Negative ring: signals the role is not actually IT/transformation work
    "off_domain": {
        "weight": -3,
        "keywords": [
            # English
            "fund finance", "fund accountant", "investment banking",
            "wealth management", "private banking",
            "loan officer", "credit officer", "trading floor",
            "k-12", "k 12", "classroom", "lesson plan", "teacher", "school administrator",
            "patient care", "nursing", "rn license", "physician",
            "litigation", "paralegal", "law clerk",
            "construction site", "civil works",
            "warehouse operations", "forklift", "barista",
            "food service", "restaurant", "kitchen",
            "retail associate", "store associate", "cashier",
            "real estate broker", "property manager",
            "insurance underwriter", "claims adjuster",
            # German
            "rechtsanwalt", "steuerberater", "wirtschaftsprüfer",
            "wirtschaftsprufer", "buchhalter", "buchhaltung",
            "krankenpfleger", "krankenpflegerin", "pflegedienst",
            "lehrer", "lehrerin", "schuleinrichtung",
            "lagerarbeiter", "lkw-fahrer", "spediteur",
            "kassierer", "verkäufer", "verkaufer", "filialleiter",
            "immobilienmakler", "hausmeister",
            "kellner", "barkeeper", "koch", "küche", "kuche",
            "fonds-buchhalter", "kreditsachbearbeiter",
        ],
    },
}


def normalize(s):
    return (s or "").lower()


def score_with_graph(text):
    """Return (score, ring_hits dict, top matches list)."""
    text = normalize(text)
    if not text:
        return 0, {}, []
    ring_hits = {}
    top_matches = []
    score = 0
    for ring_name, ring in CONCEPT_GRAPH.items():
        hits = 0
        ring_matches = []
        for kw in ring["keywords"]:
            # Word-boundary-ish: avoid partial substring like "scrum" matching "scrumptious"
            if " " in kw or "/" in kw or "-" in kw:
                if kw in text:
                    hits += 1
                    ring_matches.append(kw)
            else:
                if re.search(r"\b" + re.escape(kw) + r"\b", text):
                    hits += 1
                    ring_matches.append(kw)
        if hits:
            ring_hits[ring_name] = hits
            score += hits * ring["weight"]
            top_matches.extend(ring_matches[:3])
    return score, ring_hits, top_matches


# Same location scoring as v1 — APAC + remote positive, US-only negative
LOCATION_POSITIVE = {
    "vietnam": 30, "ho chi minh": 30, "hanoi": 30,
    "singapore": 28, "hong kong": 22, "taiwan": 18, "taipei": 18,
    "australia": 18, "sydney": 18, "melbourne": 18,
    "japan": 18, "tokyo": 18, "korea": 16, "seoul": 16,
    "malaysia": 16, "kuala lumpur": 16,
    "thailand": 14, "bangkok": 14,
    "indonesia": 14, "jakarta": 14,
    "philippines": 12, "manila": 12,
    "germany":30,
    "india": 12, "bangalore": 12,
    "apac": 22, "asia pacific": 22, "asia": 12,
    "remote": 18, "anywhere": 18, "worldwide": 18,
}
LOCATION_NEGATIVE_IF_NOT_REMOTE = {
    "united states": -8, "new york": -10, "california": -8,
    "texas": -8, "florida": -8, "illinois": -6, "ohio": -6,
    "colorado": -6, "tennessee": -6, "georgia": -6,
    "north carolina": -6, "oregon": -6, "pennsylvania": -6,
    "boston": -6, "atlanta": -6, "chicago": -6, "san francisco": -6,
    "los angeles": -6, "dallas": -6, "miami": -6,
}


def score_location(location):
    """Location scoring disabled. Location filtering happens at scrape time."""
    return 0, []


def has_it_context(title, description):
    blob = (normalize(title) + " " + normalize(description))
    strong = [
        # English
        "information technology", " it ", " it,", "(it)", "/it ", "it-",
        "software", "infrastructure", "cybersecurity", "saas",
        "servicenow", "leanix", "azure", "aws", "itil", "itsm",
        "cio", "cto", "ciso", "digital transformation", "devops",
        "platform engineering", "enterprise architecture",
        # German
        "informationstechnologie", "informationstechnik",
        "it-leiter", "it-leitung", "it-strategie", "it-governance",
        "it-projekt", "it-architektur", "it-portfolio", "it-prozess",
        "it-management", "softwareentwicklung", "softwarearchitektur",
        "infrastruktur", "cybersicherheit", "datensicherheit",
        "digitale transformation", "digitalisierung",
        "unternehmensarchitektur", "anwendungsentwicklung",
    ]
    if any(kw in blob for kw in strong):
        return True
    medium = [
        "technology", "technical", "digital", "system", "platform",
        "application", "data", "cloud", "automation", "agile",
        "technologie", "technisch", "system", "plattform",
        "anwendung", "applikation", "daten", "automatisierung",
    ]
    return sum(1 for kw in medium if kw in blob) >= 2


def verdict_for(score):
    if score >= STRONG_THRESHOLD_V2:
        return "strong"
    if score >= MAYBE_THRESHOLD_V2:
        return "maybe"
    if score >= WEAK_THRESHOLD_V2:
        return "weak"
    return "skip"


def score_job(job):
    title = job.get("title", "")
    desc = job.get("description", "")

    title_score, title_rings, title_matches = score_with_graph(title)
    desc_score, desc_rings, desc_matches = score_with_graph(desc)

    # When description is missing/thin, boost title weight (LinkedIn DE
    # often returns empty bodies via the public endpoint).
    desc_empty = len((desc or "").strip()) < 50
    title_multiplier = 3.0 if desc_empty else 1.5
    title_cap = 45 if desc_empty else 22

    title_pts = max(min(title_score * title_multiplier, title_cap), -18)
    desc_pts = max(min(desc_score, 50), -25)

    loc_pts, loc_matches = score_location(job.get("location", ""))

    it_ctx = has_it_context(title, desc)
    it_penalty = 0 if it_ctx else -20

    raw = title_pts + desc_pts + loc_pts + it_penalty + 18  # baseline 18
    final = max(0, min(100, int(raw)))

    verdict = verdict_for(final)
    if not it_ctx and verdict == "strong":
        verdict = "maybe"

    # Build reasoning
    bits = []
    combined_rings = {}
    for r, h in title_rings.items():
        combined_rings[r] = combined_rings.get(r, 0) + h
    for r, h in desc_rings.items():
        combined_rings[r] = combined_rings.get(r, 0) + h
    if combined_rings:
        ring_summary = ", ".join(
            f"{r}:{h}" for r, h in
            sorted(combined_rings.items(), key=lambda x: -CONCEPT_GRAPH[x[0]]["weight"])
        )
        bits.append("rings: " + ring_summary)
    if not it_ctx:
        bits.append("no IT context")
    pos_loc = [m for m in loc_matches if not m.startswith("!")]
    neg_loc = [m[1:] for m in loc_matches if m.startswith("!")]
    if pos_loc:
        bits.append("loc: " + ", ".join(pos_loc[:3]))
    if neg_loc:
        bits.append("loc penalty: " + ", ".join(neg_loc[:2]))
    sample = (title_matches + desc_matches)[:6]
    if sample:
        bits.append("hits: " + ", ".join(sample))

    return {
        "fit_score_v2": final,
        "verdict_v2": verdict,
        "fit_reasoning_v2": " | ".join(bits) if bits else "no signals",
        "_signals_v2": {
            "title_pts": int(title_pts),
            "desc_pts": int(desc_pts),
            "loc_pts": int(loc_pts),
            "it_context": it_ctx,
            "rings": combined_rings,
        },
    }


def load_config():
    if not CONFIG_PATH.exists():
        return {"ignore_companies": []}
    with open(CONFIG_PATH) as f:
        return json.load(f)


def is_ignored(job, ignore_list):
    name = normalize(job.get("companyName", ""))
    return any(ig in name for ig in ignore_list)


def main():
    try:
        # Find raw input
        if RAW_PATH.exists():
            source_path = RAW_PATH
        elif LATEST_PATH.exists():
            source_path = LATEST_PATH
        else:
            sys.exit(f"No raw jobs file. Run scrape_jobs.py first.")

        with open(source_path, encoding="utf-8") as f:
            raw = json.load(f)

        cfg = load_config()
        ignore_list = [normalize(c) for c in cfg.get("ignore_companies", [])]

        raw_jobs = raw.get("jobs", [])
        print(f"Loaded {len(raw_jobs)} raw jobs")
        print(f"Ignore list: {ignore_list}")

        # Build a lookup of v1 scores if scored file exists
        v1_lookup = {}
        if SCORED_PATH.exists():
            try:
                v1_data = json.loads(SCORED_PATH.read_text(encoding="utf-8"))
                for j in v1_data.get("jobs", []):
                    if j.get("id"):
                        v1_lookup[j["id"]] = j
            except Exception:
                pass

        kept = []
        dropped = 0
        for job in raw_jobs:
            if is_ignored(job, ignore_list):
                dropped += 1
                continue
            scored = job.copy()
            # Merge in v1 score if it exists for this job
            v1 = v1_lookup.get(job.get("id"))
            if v1:
                for key in ("fit_score", "verdict", "fit_reasoning"):
                    if key in v1:
                        scored[key] = v1[key]
            scored.update(score_job(job))
            kept.append(scored)

        # Sort by v2 score
        kept.sort(key=lambda x: -x["fit_score_v2"])

        out = {
            "candidate": "Philipp Eiselt",
            "scored_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ"),
            "scorer_version": "v2_graph",
            "raw_path": str(source_path),
            "source_count": len(raw_jobs),
            "ignored_count": dropped,
            "scored_count": len(kept),
            "thresholds_v2": {
                "strong": STRONG_THRESHOLD_V2,
                "maybe": MAYBE_THRESHOLD_V2,
                "weak": WEAK_THRESHOLD_V2,
                "min_excel": MIN_EXCEL_SCORE_V2,
            },
            "jobs": kept,
        }
        with open(SCORED_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)

        counts = {"strong": 0, "maybe": 0, "weak": 0, "skip": 0}
        for j in kept:
            counts[j["verdict_v2"]] += 1
        print(f"\nGraph scorer v2 results: {len(kept)} (dropped {dropped} from ignore)")
        print(f"  strong: {counts['strong']}")
        print(f"  maybe : {counts['maybe']}")
        print(f"  weak  : {counts['weak']}")
        print(f"  skip  : {counts['skip']}")
        print(f"  -> {SCORED_PATH}")
        print(f"\nTop 10 by v2:")
        for j in kept[:10]:
            v1 = j.get("fit_score", "-")
            print(f"  v2={j['fit_score_v2']:>3} v1={v1:<3} | {j['verdict_v2']:<6} | {j['title'][:55]:<55} | {j['companyName'][:22]:<22} | {j['location'][:25]}")
        return 0
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
