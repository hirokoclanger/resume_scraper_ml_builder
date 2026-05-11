#!/usr/bin/env python3
"""
Score the raw jobs from results/jobs_raw.json against Philipp's profile.
Pure Python, rule-based, no LLM, no API key. Tweak the keyword lists below
to change the ranking.

Outputs:
  results/jobs_scored.json   — all jobs with fit_score + verdict + reasoning
  results/fitting_jobs.xlsx  — Excel of jobs scoring >= MIN_EXCEL_SCORE
  dashboard.html             — live HTML dashboard with new data baked in
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"
CONFIG_PATH = HERE / "config.json"
RAW_PATH = RESULTS_DIR / "jobs_raw.json"
LATEST_PATH = RESULTS_DIR / "jobs_latest.json"  # legacy fallback
SCORED_PATH = RESULTS_DIR / "jobs_scored.json"
EXCEL_PATH = RESULTS_DIR / "fitting_jobs.xlsx"
DASHBOARD_PATH = HERE / "dashboard.html"

MIN_EXCEL_SCORE = 40   # any job at or above goes into the Excel
STRONG_THRESHOLD = 65
MAYBE_THRESHOLD = 45
WEAK_THRESHOLD = 30

# ----------------------------------------------------------------------------
# SCORING RULES — Description-weighted. Titles can mislead; descriptions are
# what actually describes the work. Theme buckets group related keywords so
# a job hitting many themes scores higher.
# ----------------------------------------------------------------------------

# Title keywords (modest weight, max ±25). Title alone never makes/breaks a job.
# German equivalents are included with the same weights.
TITLE_POSITIVE = {
    # English roles
    "portfolio": 12, "pmo": 10, "governance": 10, "transformation": 9,
    "operational excellence": 12, "process improvement": 10,
    "process expert": 10, "process engineer": 8, "process": 5,
    "change management": 9, "change manager": 9,
    "servicenow": 10, "leanix": 10, "itil": 8, "itsm": 8,
    "enterprise architect": 8, "enterprise architecture": 8,
    "it strategy": 10, "it director": 10, "it manager": 7,
    "program manager": 7, "program director": 9, "head of program": 9,
    "project portfolio": 12, "project manager": 5,
    "product owner": 7, "scrum master": 5,
    "ai governance": 10, "ai strategy": 8,
    "delivery manager": 6, "delivery lead": 6,
    "consulting": 4, "consultant": 4,
    # German role variants
    "it-portfolio": 12, "it-portfoliomanagement": 12,
    "it-governance": 10, "it-strategie": 10, "it-leiter": 10, "it-leitung": 10,
    "it-direktor": 10, "it-projektportfolio": 12,
    "it-projektleiter": 7, "it-projektleitung": 7, "it-projektmanager": 5,
    "it-prozess": 7, "it-prozessmanager": 8, "prozessmanager": 7,
    "prozessoptimierung": 12, "prozessverbesserung": 10,
    "prozessexzellenz": 12, "prozesse": 4,
    "transformation": 9, "transformationsmanager": 9,
    "veränderungsmanagement": 9, "veranderungsmanagement": 9,
    "prozessmanagement": 9,
    "geschäftsprozess": 6, "geschaftsprozess": 6,
    "digitale transformation": 10, "digitalisierung": 8,
    "leiter": 7, "leitung": 7, "geschäftsführer": 8, "geschaftsfuhrer": 8,
    "berater": 4, "beratung": 4, "it-berater": 6,
    "lieferantenmanagement": 6, "anforderungsmanagement": 6,
    "risikomanagement": 6,
    "unternehmensarchitekt": 8, "enterprise-architekt": 8,
    "agil": 4, "agilität": 4, "agilitat": 4,
    "ki-strategie": 10, "ki-governance": 10, "ki-investition": 10,
    "strategischer projektleiter": 8, "strategisches projektmanagement": 10,
    # Seniority signals (English + German)
    "director": 6, "head of": 7, "lead": 4, "senior": 3, "vp": 6, "chief": 8,
    "manager": 3, "principal": 5,
    "direktor": 6, "leitender": 5, "leitende": 5,
}

# Title kill-words (light penalties — don't kill on a single keyword,
# the description still gets to redeem). Removed engineer/developer
# because Philipp builds full-stack too. Removed certs as kill-words.
TITLE_NEGATIVE = {
    "junior": -25, "entry": -25, "entry-level": -25, "intern": -30,
    "assistant": -20, "administrative assistant": -35, "executive assistant": -30,
    "recruiter": -40, "recruiting": -40, "talent acquisition": -40,
    "vp of sales": -35, "account executive": -35, "sales rep": -35,
    "graphic": -40, "graphic designer": -45,
    "nurse": -50, "clinical": -35, "physician": -50,
    "k-12": -50, "k 12": -50, "teacher": -45, "elementary": -45, "campus director": -30,
    "paralegal": -45, "law clerk": -45, "attorney": -40,
    "painter": -50, "barista": -50, "waiter": -50,
    "real estate": -40, "broker": -35,
    "social media manager": -30, "creator relations": -30,
}

# DESCRIPTION SCORING — heavily weighted, themed.
# Each theme fires once if any of its keywords match, awarding the bucket score.
# Then individual keyword hits add small points on top.
DESCRIPTION_THEMES = {
    "process_governance": {
        "score": 10,
        "keywords": [
            # English
            "process improvement", "process optimization", "process excellence",
            "operational excellence", "continuous improvement", "lean", "six sigma",
            "kaizen", "bpm", "business process", "process governance",
            "operating model", "operating cadence", "ways of working",
            "workflow optimization", "process redesign", "process automation",
            # German
            "prozessoptimierung", "prozessverbesserung", "prozessexzellenz",
            "kontinuierliche verbesserung", "kvp", "geschäftsprozess",
            "geschaftsprozess", "prozessmanagement", "prozessgestaltung",
            "prozessautomatisierung", "ablauforganisation", "prozessdesign",
            "operative exzellenz", "prozesslandschaft", "wertstromanalyse",
        ],
    },
    "portfolio_pmo": {
        "score": 12,
        "keywords": [
            "portfolio management", "project portfolio", "it portfolio",
            "ppm", "pmo", "program management", "program governance",
            "stage gate", "intake", "prioritization", "demand management",
            "delivery governance", "project governance", "raid",
            "dependencies", "dependency management",
            # German
            "portfoliomanagement", "projektportfolio", "it-portfolio",
            "programmleitung", "programmmanagement", "projektmanagement",
            "projektportfoliomanagement", "stage-gate", "priorisierung",
            "anforderungsmanagement", "abhängigkeitsmanagement",
            "abhangigkeitsmanagement", "projektsteuerung",
            "lenkungsausschuss", "projektleitung",
        ],
    },
    "transformation_change": {
        "score": 10,
        "keywords": [
            "transformation", "digital transformation", "business transformation",
            "change management", "organizational change", "ocm", "adkar",
            "modernization", "reorganization", "restructuring",
            "target operating model", "tom",
            # German
            "digitale transformation", "geschäftstransformation",
            "geschaftstransformation", "veränderungsmanagement",
            "veranderungsmanagement", "wandel", "umstrukturierung",
            "reorganisation", "modernisierung", "digitalisierung",
            "zielbetriebsmodell", "transformationsprogramm",
        ],
    },
    "saas_platform": {
        "score": 8,
        "keywords": [
            "servicenow", "leanix", "saas", "platform implementation",
            "platform rollout", "system implementation", "erp", "s/4hana", "sap",
            "salesforce", "workday", "oracle fusion", "azure", "aws", "gcp",
            "cloud migration", "cloud transformation", "hyperscaler",
            "ITIL", "itsm", "itam", "service management",
            "integration", "api", "data migration",
            # German
            "plattformeinführung", "plattformeinfuhrung", "systemeinführung",
            "systemeinfuhrung", "cloud-migration", "cloud-transformation",
            "datenmigration", "service-management", "servicemanagement",
            "anwendungseinführung", "anwendungseinfuhrung",
            "softwareeinführung", "softwareeinfuhrung",
        ],
    },
    "governance_compliance": {
        "score": 8,
        "keywords": [
            "it governance", "governance", "grc", "compliance",
            "audit", "risk management", "internal controls", "soc",
            "policy", "framework", "standards", "controls", "iso 27001",
            "data governance", "information security",
            # German
            "it-governance", "risikomanagement", "compliance",
            "datenschutz", "datensicherheit", "informationssicherheit",
            "interne kontrolle", "richtlinien", "regelwerk",
            "datenstrategie", "data governance",
        ],
    },
    "leadership_stakeholder": {
        "score": 7,
        "keywords": [
            "stakeholder management", "executive stakeholder", "c-level",
            "cio", "cfo", "ceo", "board", "steering committee", "steering",
            "cross-functional", "matrix", "global team", "international",
            "mentor", "coaching", "people management", "team leadership",
            # German
            "stakeholder-management", "stakeholdermanagement",
            "geschäftsleitung", "geschaftsleitung", "vorstand",
            "lenkungsausschuss", "lenkungskreis", "führung", "fuhrung",
            "führungserfahrung", "fuhrungserfahrung", "teamleitung",
            "mitarbeiterführung", "mitarbeiterfuhrung",
            "internationale teams", "globale teams",
        ],
    },
    "agile_delivery": {
        "score": 5,
        "keywords": [
            "agile", "scrum", "safe", "scaled agile", "kanban",
            "sprint", "backlog", "product owner", "scrum master",
            "iterative", "delivery cadence",
            # German
            "agile methoden", "agil", "agilität", "agilitat",
            "agile arbeitsweise", "agile transformation",
        ],
    },
    "ai_data": {
        "score": 6,
        "keywords": [
            "ai governance", "ai investment", "ai strategy", "ai use case",
            "ai adoption", "artificial intelligence", "machine learning",
            "ml", "genai", "generative ai", "llm",
            "data analytics", "bi", "business intelligence",
            "power bi", "tableau", "kpi", "dashboard", "reporting",
            # German
            "künstliche intelligenz", "kunstliche intelligenz", "ki", "ki-strategie",
            "ki-governance", "ki-investition", "ki-anwendung",
            "maschinelles lernen", "datenanalyse", "datenanalysen",
            "geschäftsanalyse", "geschaftsanalyse", "berichtswesen",
            "kennzahlen", "auswertungen", "analytik",
        ],
    },
    "industry_fit": {
        "score": 5,
        "keywords": [
            "manufacturing", "automotive", "industrial", "logistics",
            "supply chain", "operations", "production", "engineering",
            "consulting", "advisory", "transformation services",
            # German
            "automobilindustrie", "fertigung", "produktion", "industrie",
            "lieferkette", "logistik", "automatisierung",
            "beratung", "strategieberatung", "managementberatung",
            "unternehmensberatung",
        ],
    },
    "budget_finance": {
        "score": 6,
        "keywords": [
            "budget management", "budget control", "financial controlling",
            "p&l", "burn rate", "forecasting", "variance", "capex", "opex",
            "cost optimization", "vendor management", "procurement", "sourcing",
            # German
            "budgetverantwortung", "budgetplanung", "budgetkontrolle",
            "finanzcontrolling", "kostenmanagement", "kostenoptimierung",
            "lieferantenmanagement", "einkauf", "beschaffung",
            "wirtschaftlichkeit", "wirtschaftlichkeitsanalyse",
        ],
    },
}

# Individual description keyword bonuses (on top of theme matches)
DESCRIPTION_KEYWORD_BONUS = {
    "servicenow": 3, "leanix": 3, "itil": 2, "itsm": 2,
    "lean six sigma": 2, "black belt": 1, "green belt": 1,
    "stakeholder": 1, "governance": 1, "transformation": 1,
    "portfolio": 1, "pmo": 1, "agile": 1, "saas": 1,
    "saas migration": 2, "saas implementation": 2,
    "process optimization": 2, "process improvement": 2,
    "operational excellence": 2,
    "change management": 1,
    "lean": 1, "six sigma": 1, "kaizen": 1,
    "cio": 1, "cfo": 1, "c-level": 1, "executive": 1,
    "cross-functional": 1, "global": 1, "international": 1,
}

# IT / tech context — split into STRONG (any one is enough) and MEDIUM
# (need at least two). This prevents false positives where a logistics or
# finance role briefly mentions "data" or "system".
IT_STRONG_KEYWORDS = [
    # English
    "information technology", " it ", " it,", "/it ", "(it)", "it/",
    "it-", "software", "software engineering", "software development",
    "infrastructure", "cybersecurity", "cyber security",
    "saas", "servicenow", "leanix", "sap s/4", "s/4hana",
    "azure", "aws", "gcp", "google cloud",
    "itil", "itsm", "itam", "service management", "servicemanagement",
    "cio", "cto", "ciso",
    "digital transformation", "digital strategy", "digital platform",
    "devops", "devsecops", "sre", "site reliability",
    "platform engineering", "application architecture",
    "enterprise architecture", "cloud architecture",
    "cybersec", "infosec",
    # German
    "informationstechnologie", "informationstechnik",
    "softwareentwicklung", "softwarearchitektur",
    "it-architektur", "it-leitung", "it-leiter",
    "it-strategie", "it-governance", "it-projekt",
    "it-projektleiter", "it-portfolio", "it-prozess",
    "it-berater", "it-consulting", "it-management",
    "infrastruktur", "cybersicherheit", "datensicherheit",
    "anwendungsentwicklung", "softwarearchitekt", "anwendungsarchitekt",
    "digitale transformation", "digitalisierung",
    "unternehmensarchitektur", "unternehmensarchitekt",
]
IT_MEDIUM_KEYWORDS = [
    # English
    "technology", "technical", "digital", "digitalization", "digitisation",
    "system", "systems", "platform", "application", "applications",
    "data", "cloud", "automation", "integration", "api",
    "engineering", "tech ", "tech,", "tech-",
    "agile", "scrum", "devops",
    "salesforce", "workday", "oracle fusion",
    # German
    "technologie", "technologien", "technisch",
    "digital", "digitale", "system", "systeme",
    "plattform", "plattformen", "anwendung", "anwendungen",
    "applikation", "daten", "automatisierung", "schnittstellen",
    "agile methoden", "agil", "agilität", "agilitat",
]

# Finance / sales / commercial-only domain kill words (in title).
# These dominate a role; even if the description has portfolio/governance
# language, the actual work is finance or sales not IT.
TITLE_DOMAIN_NEGATIVE = {
    "fund finance": -35, "fund accountant": -40, "fund manager": -25,
    "trade revenue": -40, "revenue management": -25, "trade finance": -30,
    "treasury": -20, "tax manager": -35, "audit manager": -25,
    "sales manager": -30, "sales operations": -30, "sales director": -30,
    "commercial strategy": -25, "commercial operations": -20,
    "commercial capabilities": -20, "commercial lead": -20,
    "investment manager": -25, "investment director": -25,
    "wealth": -30, "credit officer": -30, "loan officer": -30,
    "marketing manager": -30, "brand manager": -30, "category manager": -25,
    "supply chain manager": -10,  # mild — might intersect IT
    "facilities": -25, "fm director": -25, "facility manager": -25,
    "property manager": -35, "real estate manager": -35,
    "hr manager": -30, "people manager": -25, "compensation": -30,
    "store manager": -45, "branch manager": -35,
    "accountant": -45, "accounting": -35,
}

# Description kill-words (only really obvious mismatches; descriptions
# rarely deserve hard kills — verdict will downrank naturally if no
# theme matches). NOTE: certs like PMP, CSM, Black Belt are NOT here
# because those are nice-to-have, not requirements.
DESCRIPTION_NEGATIVE = {
    "must have a nursing": -30, "rn license": -30, "patient care": -25,
    "k-12 administration": -30, "lesson plan": -30, "classroom": -25,
    "must be an attorney": -30, "bar exam": -30, "bar admission": -30,
    "must be licensed cpa": -25,
    "construction site": -20, "civil engineer": -15,
    "fluent in mandarin": -8, "native chinese": -8,
    "fluent in french required": -8,
    "must reside in": -10,  # often US-only
    "must be a us citizen": -25, "us citizenship required": -25,
    "security clearance": -20, "top secret": -20,
}

# Location keywords: positive scoring for APAC + remote
LOCATION_POSITIVE = {
    # Vietnam = highest (already based there)
    "vietnam": 40, "ho chi minh": 40, "hanoi": 40, "saigon": 40,
    # APAC primary
    "singapore": 35, "hong kong": 30, "taiwan": 28, "taipei": 28,
    "australia": 25, "sydney": 25, "melbourne": 25,
    "japan": 25, "tokyo": 25, "korea": 22, "seoul": 22,
    "malaysia": 22, "kuala lumpur": 22,
    "thailand": 20, "bangkok": 20,
    "indonesia": 20, "jakarta": 20,
    "germany":40,
    "philippines": 18, "manila": 18,
    "india": 18, "bangalore": 18, "mumbai": 18,
    "apac": 30, "asia pacific": 30, "asia": 18,
    # Remote
    "remote": 25, "anywhere": 25, "worldwide": 25, "global": 12,
}

# Location kill-words: explicit US/EU only locations get negative if not also remote
LOCATION_NEGATIVE_IF_NOT_REMOTE = {
    # US states/cities — common ones from past scrape
    "united states": -8, "ny": -10, "new york": -10, "california": -8, "ca": -5,
    "texas": -8, "tx": -5, "florida": -8, "fl": -5, "illinois": -8,
    "ohio": -8, "colorado": -8, "tennessee": -8, "georgia": -8,
    "north carolina": -8, "oregon": -8, "pennsylvania": -8, "washington": -5,
    "boston": -8, "atlanta": -8, "chicago": -8, "san francisco": -8,
    "los angeles": -8, "dallas": -8, "miami": -8,
}


def normalize(s):
    return (s or "").lower()


def score_title(title):
    """Title weight is light (cap +25 / -45). Titles can mislead, so we
    don't let a single kill-word tank a job by itself, but domain-specific
    kill words (finance, sales, etc.) get applied here."""
    t = normalize(title)
    pts = 0
    matches = []
    for kw, val in TITLE_POSITIVE.items():
        if kw in t:
            pts += val
            matches.append(kw)
    for kw, val in TITLE_NEGATIVE.items():
        if kw in t:
            pts += val
            matches.append(f"!{kw}")
    for kw, val in TITLE_DOMAIN_NEGATIVE.items():
        if kw in t:
            pts += val
            matches.append(f"!{kw}")
    return max(min(pts, 25), -50), matches


def has_it_context(title, description):
    """Return True if the role has real IT/tech context. Requires either
    one STRONG keyword (e.g., software, ServiceNow, ITIL) OR two MEDIUM
    keywords (data + system + platform etc.). Prevents finance/logistics
    roles from being mistaken for IT just because they mention 'data' once."""
    blob = (normalize(title) + " " + normalize(description))
    if any(kw in blob for kw in IT_STRONG_KEYWORDS):
        return True
    medium_hits = sum(1 for kw in IT_MEDIUM_KEYWORDS if kw in blob)
    return medium_hits >= 2


def score_description(desc):
    """Description weight is heavy (cap +60). Theme-based: each theme bucket
    fires once if any of its keywords match, then individual keyword bonuses
    add small points."""
    d = normalize(desc)
    if not d:
        return 0, []
    pts = 0
    matches = []
    themes_hit = []
    for theme_name, theme in DESCRIPTION_THEMES.items():
        for kw in theme["keywords"]:
            if kw in d:
                pts += theme["score"]
                themes_hit.append(theme_name)
                matches.append(theme_name)
                break  # one hit per theme
    for kw, val in DESCRIPTION_KEYWORD_BONUS.items():
        if kw in d:
            pts += val
    for kw, val in DESCRIPTION_NEGATIVE.items():
        if kw in d:
            pts += val
            matches.append(f"!{kw}")
    return max(min(pts, 45), -30), matches


def score_location(location):
    """Location scoring disabled per user request. Location is filtered at
    the scrape level via config.json's locations list, so post-scrape we
    don't re-penalize geography here."""
    return 0, []


def verdict_for(score):
    if score >= STRONG_THRESHOLD:
        return "strong"
    if score >= MAYBE_THRESHOLD:
        return "maybe"
    if score >= WEAK_THRESHOLD:
        return "weak"
    return "skip"


def reasoning(title_matches, desc_matches, loc_matches):
    bits = []
    pos = [m for m in title_matches if not m.startswith("!")]
    neg = [m[1:] for m in title_matches if m.startswith("!")]
    if pos:
        bits.append("title: " + ", ".join(pos[:4]))
    if neg:
        bits.append("title penalty: " + ", ".join(neg[:3]))
    desc_themes = [m for m in desc_matches if not m.startswith("!")]
    desc_neg = [m[1:] for m in desc_matches if m.startswith("!")]
    if desc_themes:
        # Pretty-print theme names
        pretty = [t.replace("_", " ") for t in desc_themes]
        bits.append("description themes: " + ", ".join(pretty))
    if desc_neg:
        bits.append("description block: " + ", ".join(desc_neg[:2]))
    pos_loc = [m for m in loc_matches if not m.startswith("!")]
    neg_loc = [m[1:] for m in loc_matches if m.startswith("!")]
    if pos_loc:
        bits.append("location: " + ", ".join(pos_loc[:3]))
    if neg_loc:
        bits.append("location penalty: " + ", ".join(neg_loc[:3]))
    return " | ".join(bits) if bits else "no signals from title or description"


def score_job(job):
    title = job.get("title", "")
    desc = job.get("description", "")
    title_pts, title_m = score_title(title)
    desc_pts, desc_m = score_description(desc)
    loc_pts, loc_m = score_location(job.get("location", ""))

    # When description is missing or very thin (LinkedIn DE often strips
    # descriptions), boost title weight so a strong title can still rank.
    desc_empty = len((desc or "").strip()) < 50
    if desc_empty:
        title_pts = max(min(int(title_pts * 1.8), 45), -50)
        title_m.append("desc_empty:title_boost")

    # Hard requirement: must have IT / tech context. Without it, the role
    # is most likely finance / sales / commercial / HR even if the
    # description happens to mention "transformation" or "stakeholder".
    it_ctx = has_it_context(title, desc)
    it_penalty = 0
    if not it_ctx:
        it_penalty = -20
        title_m.append("!no_IT_context")

    raw = title_pts + desc_pts + loc_pts + it_penalty
    final = max(0, min(100, raw + 18))

    # Don't allow strong verdict without IT context, regardless of score
    verdict = verdict_for(final)
    if not it_ctx and verdict == "strong":
        verdict = "maybe"

    return {
        "fit_score": int(final),
        "verdict": verdict,
        "fit_reasoning": reasoning(title_m, desc_m, loc_m),
        "_signals": {
            "title_pts": title_pts,
            "desc_pts": desc_pts,
            "location_pts": loc_pts,
            "it_context": it_ctx,
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


def write_excel(scored, path):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        print("openpyxl not installed. Run:  pip3 install openpyxl --break-system-packages")
        return False

    wb = Workbook()
    ws = wb.active
    ws.title = "Fitting jobs"
    headers = ["Fit", "Verdict", "Title", "Company", "Location", "Posted", "Type", "Why fit", "LinkedIn link"]
    ws.append(headers)

    header_fill = PatternFill(start_color="2A3F5F", end_color="2A3F5F", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    thin = Side(border_style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    verdict_fill = {
        "strong": PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid"),
        "maybe": PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid"),
        "weak": PatternFill(start_color="FFD7D7", end_color="FFD7D7", fill_type="solid"),
        "skip": PatternFill(start_color="EEEEEE", end_color="EEEEEE", fill_type="solid"),
    }
    for col_idx, _ in enumerate(headers, 1):
        c = ws.cell(row=1, column=col_idx)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        c.border = border

    fitting = [j for j in scored if j["fit_score"] >= MIN_EXCEL_SCORE]
    fitting.sort(key=lambda x: -x["fit_score"])

    for j in fitting:
        ws.append([
            j["fit_score"], j["verdict"], j["title"], j["companyName"],
            j["location"], j.get("publishedAt", ""),
            j.get("workType", "") or j.get("contractType", "") or "",
            j["fit_reasoning"], j["jobUrl"],
        ])
        r = ws.max_row
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=r, column=col_idx)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = border
            if col_idx == 2 and j["verdict"] in verdict_fill:
                cell.fill = verdict_fill[j["verdict"]]
        link_cell = ws.cell(row=r, column=9)
        link_cell.hyperlink = j["jobUrl"]
        link_cell.value = "Open in LinkedIn"
        link_cell.font = Font(color="0563C1", underline="single")

    for i, w in enumerate([7, 10, 42, 26, 26, 14, 14, 60, 22], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[1].height = 22
    ws.freeze_panes = "A2"
    if ws.max_row > 1:
        ws.auto_filter.ref = ws.dimensions

    # Summary tab
    ws2 = wb.create_sheet("Summary")
    ws2.append(["Field", "Value"])
    ws2.append(["Total scored", len(scored)])
    ws2.append(["In this Excel (>= " + str(MIN_EXCEL_SCORE) + ")", len(fitting)])
    ws2.append(["Strong", sum(1 for j in scored if j["verdict"] == "strong")])
    ws2.append(["Maybe", sum(1 for j in scored if j["verdict"] == "maybe")])
    ws2.append(["Weak", sum(1 for j in scored if j["verdict"] == "weak")])
    ws2.append(["Generated", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")])
    for c in ws2["A"]:
        c.font = Font(bold=True)
    ws2.column_dimensions["A"].width = 36
    ws2.column_dimensions["B"].width = 32

    wb.save(path)
    return True


def update_dashboard(scored, raw_meta):
    """No-op. The server-mode dashboard fetches fresh data from /api/scored
    on every page load, so we no longer bake data into the HTML.
    Keeping this function for backwards compatibility with the call site."""
    return False
    # The original embed-into-HTML code is preserved below but unreachable.
    if not DASHBOARD_PATH.exists():
        print(f"Dashboard not found at {DASHBOARD_PATH}, skipping HTML update.")
        return False
    payload = {
        "candidate": "Philipp Eiselt",
        "scraped_at_utc": raw_meta.get("scraped_at_utc", ""),
        "scored_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ"),
        "source_count": raw_meta.get("count", len(scored)),
        "scored_count": len(scored),
        "jobs": [
            {
                "id": j.get("id"),
                "title": j.get("title"),
                "companyName": j.get("companyName"),
                "location": j.get("location"),
                "publishedAt": j.get("publishedAt"),
                "workType": j.get("workType"),
                "experienceLevel": j.get("experienceLevel"),
                "jobUrl": j.get("jobUrl"),
                "applyUrl": j.get("applyUrl"),
                "fit_score": j["fit_score"],
                "verdict": j["verdict"],
                "fit_reasoning": j["fit_reasoning"],
            }
            for j in sorted(scored, key=lambda x: -x["fit_score"])
        ],
    }
    payload_js = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    html = DASHBOARD_PATH.read_text(encoding="utf-8")
    # Match either `const DATA = ...;` or `let DATA = ...;` (single line)
    pattern = re.compile(r"(const|let)\s+DATA\s*=\s*[^;]+;", re.DOTALL)
    new_html, n = pattern.subn(f"let DATA = {payload_js};", html, count=1)
    if n == 0:
        # New server-mode dashboard fetches via /api/scored — no embedded data needed
        return False
    DASHBOARD_PATH.write_text(new_html, encoding="utf-8")
    return True


def main():
    # Prefer jobs_raw.json, fall back to jobs_latest.json (legacy filename)
    source_path = None
    if RAW_PATH.exists():
        source_path = RAW_PATH
    elif LATEST_PATH.exists():
        source_path = LATEST_PATH
        print(f"Note: using legacy {LATEST_PATH.name}. Re-run scrape_jobs.py to switch to jobs_raw.json.")
    else:
        sys.exit(f"No raw jobs file found. Run scrape_jobs.py first (looked for {RAW_PATH.name} and {LATEST_PATH.name}).")

    with open(source_path, encoding="utf-8") as f:
        raw = json.load(f)

    cfg = load_config()
    ignore_list = [normalize(c) for c in cfg.get("ignore_companies", [])]

    raw_jobs = raw.get("jobs", [])
    print(f"Loaded {len(raw_jobs)} raw jobs from {source_path.name}")
    print(f"Ignore list: {ignore_list}")

    # Capture v2 fields if jobs_scored.json already exists, so we don't
    # wipe the v2 graph scores when re-running v1
    v2_lookup = {}
    if SCORED_PATH.exists():
        try:
            prev = json.loads(SCORED_PATH.read_text(encoding="utf-8"))
            for j in prev.get("jobs", []):
                if j.get("id"):
                    v2_lookup[j["id"]] = {
                        k: j[k] for k in ("fit_score_v2", "verdict_v2", "fit_reasoning_v2", "_signals_v2")
                        if k in j
                    }
        except Exception:
            pass

    kept = []
    dropped = 0
    for job in raw_jobs:
        if is_ignored(job, ignore_list):
            dropped += 1
            continue
        scored = job.copy()
        scored.update(score_job(job))
        # Restore v2 fields if previously scored
        if job.get("id") in v2_lookup:
            scored.update(v2_lookup[job["id"]])
        kept.append(scored)

    kept.sort(key=lambda x: -x["fit_score"])

    # Write scored JSON
    out = {
        "candidate": "Philipp Eiselt",
        "scored_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ"),
        "raw_path": str(RAW_PATH),
        "source_count": len(raw_jobs),
        "ignored_count": dropped,
        "scored_count": len(kept),
        "thresholds": {
            "strong": STRONG_THRESHOLD, "maybe": MAYBE_THRESHOLD,
            "weak": WEAK_THRESHOLD, "min_excel": MIN_EXCEL_SCORE,
        },
        "jobs": kept,
    }
    with open(SCORED_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    # Verdict counts
    counts = {"strong": 0, "maybe": 0, "weak": 0, "skip": 0}
    for j in kept:
        counts[j["verdict"]] += 1

    print(f"\nScored: {len(kept)}  (dropped {dropped} from ignore list)")
    print(f"  strong : {counts['strong']}")
    print(f"  maybe  : {counts['maybe']}")
    print(f"  weak   : {counts['weak']}")
    print(f"  skip   : {counts['skip']}")
    print(f"  -> {SCORED_PATH}")

    # Excel
    if write_excel(kept, EXCEL_PATH):
        print(f"  -> {EXCEL_PATH}")

    # Dashboard
    if update_dashboard(kept, raw):
        print(f"  -> {DASHBOARD_PATH}  (reload in browser)")

    # Top 10 preview
    print(f"\nTop 10:")
    for j in kept[:10]:
        print(f"  [{j['fit_score']:>3}] {j['verdict']:<6} {j['title'][:55]:<55} | {j['companyName'][:22]:<22} | {j['location'][:25]}")


if __name__ == "__main__":
    import traceback
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(f"\nUNEXPECTED ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
