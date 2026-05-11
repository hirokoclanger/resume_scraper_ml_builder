#!/usr/bin/env python3
"""
LinkedIn / Indeed / Glassdoor job scraper using JobSpy.
Open source, free, no actor. Location filters actually work.

Run:  python3 scrape_jobs.py
Or via the dashboard "Run scrape" button.

Install dependency once:
  pip3 install python-jobspy --break-system-packages
"""
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"
RESULTS_DIR = HERE / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def load_config():
    if not CONFIG_PATH.exists():
        sys.exit(f"ERROR: Missing config at {CONFIG_PATH}")
    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
    except json.JSONDecodeError as e:
        sys.exit(f"ERROR: config.json is not valid JSON: {e}")
    return cfg


def import_jobspy():
    try:
        from jobspy import scrape_jobs
        return scrape_jobs
    except ImportError:
        sys.exit(
            "ERROR: python-jobspy is not installed.\n"
            "  Run in Terminal:\n"
            "    pip3 install python-jobspy --break-system-packages\n"
        )


def df_to_dicts(df):
    """Convert pandas DataFrame from JobSpy to plain list of dicts in the
    shape the scorer + dashboard expect."""
    out = []
    for _, row in df.iterrows():
        d = row.to_dict()
        # Normalize NaN to None / empty string
        for k, v in list(d.items()):
            try:
                import math
                if isinstance(v, float) and math.isnan(v):
                    d[k] = None
            except Exception:
                pass
        # Map JobSpy fields to our standard schema
        out.append({
            "id": str(d.get("id") or d.get("job_url") or "")[:200],
            "title": d.get("title") or "",
            "companyName": d.get("company") or "",
            "location": d.get("location") or "",
            "jobUrl": d.get("job_url") or d.get("job_url_direct") or "",
            "applyUrl": d.get("job_url_direct") or d.get("job_url") or "",
            "publishedAt": str(d.get("date_posted") or "")[:10],
            "workType": d.get("job_type") or "",
            "experienceLevel": d.get("job_level") or "",
            "salary": d.get("salary_source") or d.get("min_amount") or "",
            "description": d.get("description") or "",
            "site": d.get("site") or "",
            "isRemote": bool(d.get("is_remote")) if d.get("is_remote") is not None else None,
        })
    return out


def main():
    try:
        scrape_jobs = import_jobspy()
        cfg = load_config()

        search_terms = cfg.get("search_terms") or ["IT governance"]
        locations = cfg.get("locations") or ["Singapore"]
        sites = cfg.get("sites") or ["linkedin", "indeed"]
        results_wanted = int(cfg.get("results_wanted", 30))
        hours_old = int(cfg.get("hours_old", 720))  # last 30 days

        total_combos = len(search_terms) * len(locations)
        print(f"Plan: {len(search_terms)} terms x {len(locations)} locations = {total_combos} searches")
        print(f"Sites: {sites}")
        print(f"Per-search cap: {results_wanted}")
        print(f"Recency cap: last {hours_old} hours\n")

        all_jobs = []
        seen_ids = set()
        started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")

        for term in search_terms:
            for loc in locations:
                # Call each site individually so one failing doesn't kill the others
                for site in sites:
                    print(f"[{term}] @ [{loc}] ({site}) ...", flush=True)
                    try:
                        df = scrape_jobs(
                            site_name=[site],
                            search_term=term,
                            location=loc,
                            results_wanted=results_wanted,
                            hours_old=hours_old,
                            country_indeed=loc if loc in ("Singapore", "Vietnam", "Hong Kong",
                                                           "Australia", "Malaysia", "Thailand",
                                                           "Indonesia", "Philippines", "India",
                                                           "Japan", "Korea", "Taiwan",
                                                           "Germany", "Austria", "Switzerland",
                                                           "Netherlands", "France", "UK",
                                                           "Ireland", "Sweden", "Spain",
                                                           "Italy", "Belgium", "Portugal") else "USA",
                            verbose=0,
                        )
                    except Exception as e:
                        print(f"  ! {site} failed: {type(e).__name__}: {str(e)[:120]}")
                        continue

                    if df is None or len(df) == 0:
                        print(f"  -> 0 jobs from {site}")
                        continue

                    jobs = df_to_dicts(df)
                    new_count = 0
                    for j in jobs:
                        if j["id"] and j["id"] not in seen_ids:
                            seen_ids.add(j["id"])
                            j["search_term"] = term
                            j["search_location"] = loc
                            all_jobs.append(j)
                            new_count += 1
                    print(f"  -> {len(jobs)} from {site} ({new_count} new after dedup)")
                    time.sleep(1)

        out = {
            "scraped_at_utc": started,
            "search_terms": search_terms,
            "locations": locations,
            "sites": sites,
            "count": len(all_jobs),
            "jobs": all_jobs,
        }
        raw_path = RESULTS_DIR / "jobs_raw.json"
        archive_path = RESULTS_DIR / f"jobs_archive_{started}.json"
        for path in (raw_path, archive_path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(out, f, indent=2, ensure_ascii=False)

        print(f"\nDone. {len(all_jobs)} unique jobs collected.")
        print(f"  Raw:     {raw_path}")
        print(f"  Archive: {archive_path}")
        print(f"\nNext: click 'Run scorer' (or run  python3 score_jobs.py).")
        return 0

    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"\nUNEXPECTED ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
