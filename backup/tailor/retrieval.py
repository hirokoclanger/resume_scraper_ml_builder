#!/usr/bin/env python3
"""
Retrieval engine for tailoring Philipp's resume to a JD.

Pure local — no LLM calls. Pipeline:

  1. Load corpus.json (produced by extract_corpus.py).
  2. Tokenize the JD and each candidate bullet.
  3. Score every bullet pool (summary, skills, per-role highlights) with BM25
     against JD tokens.
  4. Detect the JD's closest role profile (governance / portfolio / product
     owner / servicenow / strategic / transformation) and apply a profile
     boost to bullets whose tags match the profile's preferred_tags.
  5. For each requested variant (metrics / leadership / tooling), apply a
     second tag boost and re-rank.
  6. Select top-N per role using role_budgets from profiles.json, with a
     soft duplicate-content guard (avoid picking two bullets that share
     too many content words).

Public API:
    rank_for_jd(jd_text, corpus, config) -> dict (debug structure)
    build_variant(jd_text, corpus, config, variant_key) -> dict
        { "profile": str, "summary": str, "skills": [str],
          "roles": [ {role_key, position, company, start_date, end_date,
                      location, summary_line, highlights: [str]} ],
          "projects": [{"name","summary","highlights"}],
          "education": [str], "certifications": [str], "languages": [str],
          "trace": {...}  # which bullet ids were chosen and why
        }
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from rank_bm25 import BM25Okapi

HERE = Path(__file__).resolve().parent.parent
CORPUS_PATH = HERE / "corpus" / "corpus.json"
PROFILES_PATH = Path(__file__).resolve().parent / "profiles.json"

# Very small stopword list — enough to drop the most common JD noise without
# losing domain terms. Deliberately keeps verbs like "lead", "manage".
STOPWORDS = set("""
a an the and or but if while of for in on at to from by with as is are was were
be been being have has had do does did will would could should may might must
this that these those it its their our your his her my we you they them us
who whom which what when where why how
also more most less few many much such only just any all some no not nor
about against above below into onto over under between among through during
including based upon per via etc eg e.g ie i.e
job role position candidate experience required preferred responsibilities
ability skills work team
""".split())

WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+\-/.]*", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Lowercase, alphanumeric+symbols words, drop stopwords + very short tokens."""
    text = text.lower()
    # Normalize a few currency / metric markers so they survive tokenisation.
    text = text.replace("€", " eur ").replace("$", " usd ").replace("%", " pct ")
    tokens = WORD_RE.findall(text)
    out = []
    for t in tokens:
        if len(t) < 2:
            continue
        if t in STOPWORDS:
            continue
        # Trim trailing dots/dashes
        t = t.strip(".-+/")
        if t:
            out.append(t)
    return out


def load_corpus(path: Path = CORPUS_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_profiles(path: Path = PROFILES_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def detect_profile(jd_text: str, profiles_cfg: dict) -> dict:
    """Score each profile by detector_keyword hit count; return the best one
    plus the runner-up for diagnostic purposes."""
    low = jd_text.lower()
    scored = []
    for p in profiles_cfg["profiles"]:
        score = 0
        hits = []
        for kw in p["detector_keywords"]:
            if kw in low:
                score += 1
                hits.append(kw)
        scored.append((score, p, hits))
    scored.sort(key=lambda x: -x[0])
    primary = scored[0] if scored else (0, profiles_cfg["profiles"][0], [])
    runner = scored[1] if len(scored) > 1 else (0, None, [])
    return {
        "profile": primary[1],
        "score": primary[0],
        "hits": primary[2],
        "runner_up": runner[1]["key"] if runner[1] else None,
        "runner_up_score": runner[0],
    }


def _bm25_scores(jd_tokens: list[str], pool: list[dict]) -> list[float]:
    """BM25 score for each bullet in `pool` against the JD tokens. Returns a
    list parallel to `pool`."""
    if not pool:
        return []
    corpus_tokens = [tokenize(b["text"]) or ["__empty__"] for b in pool]
    bm = BM25Okapi(corpus_tokens)
    scores = bm.get_scores(jd_tokens) if jd_tokens else [0.0] * len(pool)
    return list(scores)


def _profile_boost(bullet: dict, profile: dict) -> float:
    """Additive boost based on tag overlap with profile preferred_tags and
    text occurrence of boost_phrases."""
    boost = 0.0
    bullet_tags = set(bullet.get("tags", []))
    for tag in profile.get("preferred_tags", []):
        if tag in bullet_tags:
            boost += 1.5
    low = bullet["text"].lower()
    for phrase in profile.get("boost_phrases", []):
        if phrase in low:
            boost += 1.0
    return boost


def _variant_boost(bullet: dict, variant: dict) -> float:
    """Multiplicative boost for variant tag presence."""
    boost = 1.0
    tags = set(bullet.get("tags", []))
    for tag in variant.get("boost_tags", []):
        if tag in tags:
            boost *= variant.get("boost_factor", 1.0)
    return boost


def _dedup_words(text: str) -> set[str]:
    return set(tokenize(text))


def _too_similar(text_a: str, text_b: str, threshold: float = 0.55) -> bool:
    """Soft duplicate check: Jaccard over content tokens."""
    a, b = _dedup_words(text_a), _dedup_words(text_b)
    if not a or not b:
        return False
    inter = len(a & b)
    union = len(a | b)
    return (inter / union) >= threshold if union else False


def select_top_n(
    pool: list[dict],
    scores: list[float],
    n: int,
    similarity_threshold: float = 0.55,
) -> list[dict]:
    """Pick top-n bullets by descending score, skipping any that are too
    similar to a previously picked bullet."""
    ranked = sorted(zip(pool, scores), key=lambda x: -x[1])
    picked: list[dict] = []
    for bullet, score in ranked:
        if len(picked) >= n:
            break
        if any(_too_similar(bullet["text"], p["text"], similarity_threshold) for p in picked):
            continue
        picked.append(bullet)
    return picked


def score_bullets(
    pool: list[dict],
    jd_tokens: list[str],
    profile: dict,
    variant: dict,
) -> list[tuple[dict, float]]:
    """Return [(bullet, final_score)] in pool order (caller sorts)."""
    base = _bm25_scores(jd_tokens, pool)
    out: list[tuple[dict, float]] = []
    for bullet, b in zip(pool, base):
        profile_b = _profile_boost(bullet, profile)
        variant_m = _variant_boost(bullet, variant)
        final = (b + profile_b) * variant_m
        out.append((bullet, final))
    return out


def build_variant(
    jd_text: str,
    corpus: dict,
    profiles_cfg: dict,
    variant_key: str,
) -> dict:
    """Produce a complete tailored CV structure for a single variant."""
    jd_tokens = tokenize(jd_text)
    detect = detect_profile(jd_text, profiles_cfg)
    profile = detect["profile"]
    variant = next(v for v in profiles_cfg["variants"] if v["key"] == variant_key)
    role_budgets: dict = profiles_cfg["role_budgets"]
    skills_n = profiles_cfg.get("skills_target_count", 8)

    trace: dict = {
        "profile": profile["key"],
        "profile_label": profile["label"],
        "profile_hits": detect["hits"],
        "profile_score": detect["score"],
        "runner_up": detect["runner_up"],
        "variant": variant["key"],
        "selections": {},
    }

    # Summary: pick the single highest-scoring candidate.
    sum_scored = sorted(
        score_bullets(corpus["summary_pool"], jd_tokens, profile, variant),
        key=lambda x: -x[1],
    )
    summary_text = sum_scored[0][0]["text"] if sum_scored else ""
    if sum_scored:
        trace["selections"]["summary"] = [sum_scored[0][0]["id"]]

    # Skills: top-N by score (no similarity check — skills are short lines).
    skl_scored = sorted(
        score_bullets(corpus["skills_pool"], jd_tokens, profile, variant),
        key=lambda x: -x[1],
    )
    skills_picked = [b for b, _ in skl_scored[:skills_n]]
    skills_text = [b["text"] for b in skills_picked]
    trace["selections"]["skills"] = [b["id"] for b in skills_picked]

    # Per-role highlights.
    roles_out = []
    for r in corpus["roles"]:
        budget = role_budgets.get(r["key"], 3)
        if budget <= 0 or not r["highlights_pool"]:
            roles_out.append({
                **{k: r[k] for k in ("key", "position", "company", "start_date", "end_date", "location")},
                "summary_line": r.get("summary_line", ""),
                "highlights": [],
            })
            continue
        scored = score_bullets(r["highlights_pool"], jd_tokens, profile, variant)
        pool = [b for b, _ in scored]
        scores = [s for _, s in scored]
        picked = select_top_n(pool, scores, budget)
        trace["selections"][r["key"]] = [b["id"] for b in picked]
        roles_out.append({
            **{k: r[k] for k in ("key", "position", "company", "start_date", "end_date", "location")},
            "summary_line": r.get("summary_line", ""),
            "highlights": [b["text"] for b in picked],
        })

    # Projects, education, certs, languages: use the master file's first
    # entries (they are deterministic, no ranking needed).
    projects = _select_master_projects(corpus)
    education = [b["text"] for b in corpus["education"] if b["source"].endswith(".md")]
    certs = [b["text"] for b in corpus["certifications"] if b["source"].endswith(".md")]
    langs = [b["text"] for b in corpus["languages"] if b["source"].endswith(".md")]

    return {
        "profile": profile["key"],
        "profile_label": profile["label"],
        "variant": variant["key"],
        "variant_label": variant["label"],
        "header": corpus["header"],
        "summary": summary_text,
        "skills": skills_text,
        "roles": roles_out,
        "projects": projects,
        "education": education,
        "certifications": certs,
        "languages": langs,
        "trace": trace,
    }


def _select_master_projects(corpus: dict) -> list[dict]:
    """Project entries in the master file. Each is one paragraph that starts
    with the project name. Returns a list of {name, summary} for RenderCV."""
    out = []
    seen_names: set[str] = set()
    for b in corpus["projects"]:
        if not b["source"].endswith(".md"):
            continue
        text = b["text"]
        # Match "NAME (url). REST" or "NAME. REST"
        m = re.match(r"^([A-Za-z0-9_]+)\s*\(([^)]*)\)\.\s*(.*)$", text)
        if m:
            name, link, rest = m.group(1), m.group(2), m.group(3)
            if name in seen_names:
                continue
            seen_names.add(name)
            out.append({"name": f"[{name}]({link.strip()})" if link.strip() else name, "summary": rest.strip()})
        else:
            # Intro paragraph (no project name) — keep as opening summary line.
            if not seen_names:  # only the first one
                out.append({"name": "Personal software projects", "summary": text})
    return out


def build_all_variants(
    jd_text: str,
    corpus: dict | None = None,
    profiles_cfg: dict | None = None,
) -> list[dict]:
    """Produce the three variants (metrics / leadership / tooling)."""
    corpus = corpus or load_corpus()
    profiles_cfg = profiles_cfg or load_profiles()
    out = []
    for v in profiles_cfg["variants"]:
        out.append(build_variant(jd_text, corpus, profiles_cfg, v["key"]))
    return out


def build_editable_view(
    jd_text: str,
    corpus: dict | None = None,
    profiles_cfg: dict | None = None,
    variant_key: str = "metrics",
) -> dict:
    """Produce a structured view for the editable modal: the picked
    composition plus every UNPICKED candidate in each pool so the UI can
    offer "+ add" choices. All bullet objects carry their id so the client
    can send them back unchanged for rendering."""
    corpus = corpus or load_corpus()
    profiles_cfg = profiles_cfg or load_profiles()
    variant = build_variant(jd_text, corpus, profiles_cfg, variant_key)

    # The picked structure has bullet TEXTS only; we want IDs too for
    # round-tripping. Rebuild with ids by matching against the pool.
    picked_ids: dict = variant["trace"]["selections"]

    def with_id(pool: list[dict], picked_id_list: list[str]) -> list[dict]:
        by_id = {b["id"]: b for b in pool}
        return [{"id": i, "text": by_id[i]["text"], "tags": by_id[i].get("tags", [])}
                for i in picked_id_list if i in by_id]

    def unpicked(pool: list[dict], picked_id_list: list[str]) -> list[dict]:
        picked_set = set(picked_id_list)
        return [{"id": b["id"], "text": b["text"], "tags": b.get("tags", [])}
                for b in pool if b["id"] not in picked_set]

    summary_picked = with_id(corpus["summary_pool"], picked_ids.get("summary", []))
    summary_unpicked = unpicked(corpus["summary_pool"], picked_ids.get("summary", []))

    skills_picked = with_id(corpus["skills_pool"], picked_ids.get("skills", []))
    skills_unpicked = unpicked(corpus["skills_pool"], picked_ids.get("skills", []))

    roles_out = []
    for r in corpus["roles"]:
        ids = picked_ids.get(r["key"], [])
        roles_out.append({
            "key": r["key"],
            "position": r["position"],
            "company": r["company"],
            "start_date": r["start_date"],
            "end_date": r["end_date"],
            "location": r["location"],
            "highlights_picked": with_id(r["highlights_pool"], ids),
            "highlights_unpicked": unpicked(r["highlights_pool"], ids),
        })

    return {
        "profile": variant["profile"],
        "profile_label": variant["profile_label"],
        "variant": variant["variant"],
        "variant_label": variant["variant_label"],
        "runner_up_profile": variant["trace"].get("runner_up"),
        "header": corpus["header"],
        "header_variants": corpus.get("header_variants", {}),
        "default_header_key": corpus.get("default_header_key", "germany"),
        "summary": {
            "picked": summary_picked,
            "unpicked": summary_unpicked,
        },
        "skills": {
            "picked": skills_picked,
            "unpicked": skills_unpicked,
        },
        "roles": roles_out,
        "projects": variant["projects"],
        "education": variant["education"],
        "certifications": variant["certifications"],
        "languages": variant["languages"],
        "available_variants": [
            {"key": v["key"], "label": v["label"]}
            for v in profiles_cfg["variants"]
        ],
    }


def composition_from_edits(edits: dict) -> dict:
    """Translate the client-side edited composition (only bullet ids per
    section plus optional overrides) back into the shape build_variant()
    returns, so render_pdf.build_rendercv_yaml() can consume it.

    `edits` shape:
      {
        company, title, variant, profile, profile_label,
        header: {...},               # optional, falls back to corpus header
        summary_id: "sum-001" | None,
        skill_ids: ["skl-001", ...],
        roles: [ {key, highlight_ids: ["exp-001", ...]} ],
        # projects/education/certifications/languages are not editable in v1
      }
    """
    corpus = load_corpus()

    by_id_summary = {b["id"]: b for b in corpus["summary_pool"]}
    by_id_skills = {b["id"]: b for b in corpus["skills_pool"]}
    by_id_role: dict[str, dict] = {}
    by_id_highlight: dict[str, dict] = {}
    role_meta_by_key: dict[str, dict] = {}
    for r in corpus["roles"]:
        role_meta_by_key[r["key"]] = r
        for b in r["highlights_pool"]:
            by_id_highlight[b["id"]] = b
            by_id_role[b["id"]] = r["key"]

    summary_text = ""
    if edits.get("summary_id") and edits["summary_id"] in by_id_summary:
        summary_text = by_id_summary[edits["summary_id"]]["text"]

    skills_text = [by_id_skills[i]["text"] for i in edits.get("skill_ids", []) if i in by_id_skills]

    roles_out = []
    for re in edits.get("roles", []):
        meta = role_meta_by_key.get(re.get("key"))
        if not meta:
            continue
        hl_ids = re.get("highlight_ids", [])
        hl_text = [by_id_highlight[i]["text"] for i in hl_ids if i in by_id_highlight]
        roles_out.append({
            "key": meta["key"],
            "position": meta["position"],
            "company": meta["company"],
            "start_date": meta["start_date"],
            "end_date": meta["end_date"],
            "location": meta["location"],
            "summary_line": meta.get("summary_line", ""),
            "highlights": hl_text,
        })

    # Bind projects/education/etc to the master-file content (deterministic).
    projects = _select_master_projects(corpus)
    education = [b["text"] for b in corpus["education"] if b["source"].endswith(".md")]
    certs = [b["text"] for b in corpus["certifications"] if b["source"].endswith(".md")]
    langs = [b["text"] for b in corpus["languages"] if b["source"].endswith(".md")]

    # Header: client may send either a header_key referencing the corpus
    # variants, or a full header dict, or nothing (falls back to the corpus
    # default).
    header = None
    if edits.get("header_key"):
        header = corpus.get("header_variants", {}).get(edits["header_key"])
    if header is None:
        header = edits.get("header") or corpus["header"]
    return {
        "profile": edits.get("profile", "custom"),
        "profile_label": edits.get("profile_label", "Custom edit"),
        "variant": edits.get("variant", "custom"),
        "variant_label": edits.get("variant_label", "Custom"),
        "header": header,
        "summary": summary_text,
        "skills": skills_text,
        "roles": roles_out,
        "projects": projects,
        "education": education,
        "certifications": certs,
        "languages": langs,
        "trace": {"source": "edits"},
    }


def build_brief(variant: dict) -> str:
    """Render a markdown brief showing what was selected for a single variant.
    Used in the dashboard modal so the user can scan the choices before
    generating the PDF."""
    lines: list[str] = []
    lines.append(f"**Detected profile:** {variant['profile_label']}  ")
    lines.append(f"**Variant:** {variant['variant_label']}")
    lines.append("")
    if variant.get("summary"):
        lines.append("## Summary")
        lines.append(variant["summary"])
        lines.append("")
    if variant.get("skills"):
        lines.append("## Core Competencies")
        for s in variant["skills"]:
            lines.append(f"- {s}")
        lines.append("")
    lines.append("## Experience highlights")
    for r in variant["roles"]:
        if not r["highlights"]:
            continue
        lines.append(f"### {r['position']} — {r['company']}  ({r['start_date']} – {r['end_date']})")
        for h in r["highlights"]:
            lines.append(f"- {h}")
        lines.append("")
    return "\n".join(lines).strip()


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--jd", default="", help="JD text or path to a text file")
    p.add_argument("--variant", default="metrics")
    args = p.parse_args()
    jd = args.jd
    if jd and Path(jd).exists():
        jd = Path(jd).read_text(encoding="utf-8")
    if not jd:
        jd = (
            "Senior Project Portfolio Manager with strong ServiceNow background. "
            "Owns intake, RAID and steering for an IT portfolio. Reports to the CIO. "
            "Experience with Jira, LeanIX and Azure preferred."
        )
    corpus = load_corpus()
    cfg = load_profiles()
    result = build_variant(jd, corpus, cfg, args.variant)
    print(json.dumps(result, ensure_ascii=False, indent=2))
