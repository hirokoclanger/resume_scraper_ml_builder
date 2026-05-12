#!/usr/bin/env python3
"""
Local HTTP server for the job finder dashboard.
Run from this folder:
    python3 server.py
Then open http://localhost:8765 in your browser.

The server runs background scrape and score subprocesses on demand and
streams logs back to the dashboard. All endpoints are local-only — bound
to 127.0.0.1.
"""
# --- venv bootstrap ---------------------------------------------------------
# The tailor engine needs python-docx, rank_bm25, ruamel.yaml, and rendercv,
# all installed into ./.venv. If the user runs `python3 server.py` with the
# system Python (which is what most terminals default to), the imports below
# would fail. Re-exec through the venv interpreter automatically.
#
# Detection: `.venv/bin/python` is a symlink to the system python, so
# `Path.resolve()` collapses them. The reliable signal is `sys.prefix`,
# which points to the venv root only when the venv's python was invoked.
import os as _os
import sys as _sys
from pathlib import Path as _Path
_HERE = _Path(__file__).resolve().parent
_VENV_DIR = _HERE / ".venv"
_VENV_PY = _VENV_DIR / "bin" / "python"
if (
    _VENV_PY.exists()
    and not _os.environ.get("JOB_FINDER_SKIP_VENV_BOOTSTRAP")
    and _Path(_sys.prefix).resolve() != _VENV_DIR.resolve()
):
    _os.environ["JOB_FINDER_SKIP_VENV_BOOTSTRAP"] = "1"  # prevent re-exec loops
    _os.execv(str(_VENV_PY), [str(_VENV_PY), str(_Path(__file__).resolve()), *_sys.argv[1:]])
# ---------------------------------------------------------------------------
import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import uuid
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
PORT = int(os.environ.get("JOB_FINDER_PORT", 8765))

CONFIG_PATH = HERE / "config.json"
SCORED_PATH = HERE / "results" / "jobs_scored.json"
RAW_PATH = HERE / "results" / "jobs_raw.json"
DASHBOARD_PATH = HERE / "dashboard.html"
PASTE_PATH = HERE / "paste.html"
LIBRARY_PATH = HERE / "library.html"
CATALOG_PATH = HERE / "source_catalog.txt"
ENV_PATH = HERE / ".env"
CORPUS_PATH = HERE / "corpus" / "corpus.json"
TAILORED_DIR = HERE / "results" / "tailored"
MASTER_PATH = Path(
    "/Users/ttt/Library/Mobile Documents/com~apple~CloudDocs/CV/Resume/Claudes/Philipp Eiselt Resume - master sentences.md"
)

# Local tailoring engine (pure retrieval — no Claude API).
sys.path.insert(0, str(HERE))
from tailor.retrieval import (  # noqa: E402
    build_all_variants,
    build_brief,
    build_editable_view,
    build_variant,
    composition_from_edits,
    load_corpus,
    load_profiles,
)
from tailor.render_pdf import render_pdf, slugify  # noqa: E402
from tailor.render_docx import render_docx  # noqa: E402
from tailor.skills import coverage as skill_coverage, extract_skills  # noqa: E402
from tailor.draft_loader import list_drafts, build_tailored as draft_build_tailored  # noqa: E402

# Will be set after server constructed so /api/shutdown can stop it
_server_ref = None


def load_env_file():
    """Tiny .env loader. No external dependency. Lines like KEY=value, ignores
    comments and blanks. Existing os.environ values win (so shell exports
    override the file)."""
    if not ENV_PATH.exists():
        return
    try:
        for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            # Strip optional matching quotes
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception as e:
        print(f"Warning: failed to read .env: {e}", file=sys.stderr)


load_env_file()

TASKS = {}  # task_id -> { "status", "log", "exit_code", "kind" }
TASKS_LOCK = threading.Lock()


def run_subprocess_task(task_id, kind, cmd):
    """Run cmd in subprocess, capturing log line by line."""
    with TASKS_LOCK:
        TASKS[task_id] = {"status": "running", "log": "", "exit_code": None, "kind": kind}
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=HERE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in proc.stdout:
            with TASKS_LOCK:
                TASKS[task_id]["log"] += line
        proc.wait(timeout=900)
        with TASKS_LOCK:
            TASKS[task_id]["status"] = "done" if proc.returncode == 0 else "error"
            TASKS[task_id]["exit_code"] = proc.returncode
    except Exception as e:
        with TASKS_LOCK:
            TASKS[task_id]["status"] = "error"
            TASKS[task_id]["log"] += f"\n[server error] {e}\n"
            TASKS[task_id]["exit_code"] = -1


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Quieter logging
        sys.stderr.write(f"[{self.log_date_time_string()}] {fmt % args}\n")

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, mime: str):
        if not path.exists():
            self.send_error(404, f"Not found: {path.name}")
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _resolve_scored_job(self, job_id):
        """Return the job dict for `job_id` from the scored results, or None."""
        if not SCORED_PATH.exists():
            return None
        scored = json.loads(SCORED_PATH.read_text())
        return next((j for j in scored.get("jobs", []) if str(j.get("id")) == str(job_id)), None)

    def _ensure_corpus(self):
        """Return (corpus, profiles_cfg) or raise a user-facing error."""
        if not CORPUS_PATH.exists():
            raise RuntimeError(
                "Corpus not built yet. Run: "
                ".venv/bin/python tailor/extract_corpus.py"
            )
        return load_corpus(CORPUS_PATH), load_profiles()

    def _handle_tailor(self, body):
        """Local-only structured tailoring view for a scored job. Returns the
        full editable composition (picked + unpicked bullets per pool) so the
        dashboard can render an editable modal. No external API.
        """
        job_id = body.get("job_id", "")
        if not job_id:
            self._send_json({"error": "job_id required"}, status=400)
            return
        job = self._resolve_scored_job(job_id)
        if not job:
            self._send_json({"error": f"Job {job_id} not found in scored results"}, status=404)
            return
        try:
            corpus, cfg = self._ensure_corpus()
        except RuntimeError as e:
            self._send_json({"error": str(e)}, status=500)
            return

        jd_text = (job.get("description") or "")
        title = job.get("title", "")
        company = job.get("companyName", "")
        location = job.get("location", "")
        variant_key = body.get("variant") or "metrics"

        view = build_editable_view(jd_text, corpus, cfg, variant_key)
        self._send_json({
            "status": "ok",
            "source": "local_retrieval",
            "job": {"title": title, "company": company, "location": location},
            "view": view,
        })

    def _produce_pdfs(self, jd_text, company, title, header_key=None, include_photo=True):
        """Render every variant and return a list of {variant, profile, name, url}."""
        if not jd_text or len(jd_text.strip()) < 20:
            raise ValueError("JD text too short — need at least a paragraph of role description.")
        corpus, cfg = self._ensure_corpus()
        header_variants = corpus.get("header_variants", {})
        if header_key and header_key not in header_variants:
            raise ValueError(f"unknown header variant '{header_key}'")
        chosen_header = header_variants.get(header_key) if header_key else None
        company_slug = slugify(company or "Unknown")
        title_slug = slugify(title or "Role")
        results = []
        for v in cfg["variants"]:
            variant = build_variant(jd_text, corpus, cfg, v["key"])
            if chosen_header:
                variant["header"] = chosen_header
            stem = f"Eiselt__{company_slug}__{title_slug}__{v['key']}"
            if header_key:
                stem = f"Eiselt__{company_slug}__{title_slug}__{header_key}__{v['key']}"
            pdf = render_pdf(variant, TAILORED_DIR, stem, include_photo=include_photo)
            results.append({
                "variant": v["key"],
                "variant_label": v["label"],
                "profile": variant["profile"],
                "profile_label": variant["profile_label"],
                "filename": pdf.name,
                "url": f"/api/tailored/{pdf.name}",
                "size_bytes": pdf.stat().st_size,
            })
        return results

    def _handle_tailor_pdf(self, body):
        """Produce PDFs for a scored job (3 variants)."""
        job_id = body.get("job_id", "")
        if not job_id:
            self._send_json({"error": "job_id required"}, status=400)
            return
        job = self._resolve_scored_job(job_id)
        if not job:
            self._send_json({"error": f"Job {job_id} not found"}, status=404)
            return
        try:
            results = self._produce_pdfs(
                jd_text=(job.get("description") or ""),
                company=job.get("companyName", ""),
                title=job.get("title", ""),
                include_photo=bool(body.get("include_photo", True)),
            )
        except RuntimeError as e:
            self._send_json({"error": str(e)}, status=500)
            return
        except ValueError as e:
            self._send_json({"error": str(e)}, status=400)
            return
        except Exception as e:
            self._send_json({"error": f"{type(e).__name__}: {e}"}, status=500)
            return
        self._send_json({
            "status": "ok",
            "job": {
                "title": job.get("title", ""),
                "company": job.get("companyName", ""),
                "location": job.get("location", ""),
            },
            "pdfs": results,
        })

    def _handle_tailor_preview(self, body):
        """Fast preview: return the markdown brief for a pasted JD without
        rendering any PDF. Used by the /paste page."""
        jd_text = body.get("jd_text", "")
        variant_key = body.get("variant") or "metrics"
        if not jd_text or len(jd_text.strip()) < 20:
            self._send_json({"error": "jd_text required (at least a paragraph)"}, status=400)
            return
        try:
            corpus, cfg = self._ensure_corpus()
        except RuntimeError as e:
            self._send_json({"error": str(e)}, status=500)
            return
        if not any(v["key"] == variant_key for v in cfg["variants"]):
            self._send_json({"error": f"Unknown variant '{variant_key}'"}, status=400)
            return
        variant = build_variant(jd_text, corpus, cfg, variant_key)
        self._send_json({
            "status": "ok",
            "source": "local_retrieval",
            "variant": variant["variant"],
            "variant_label": variant["variant_label"],
            "profile": variant["profile"],
            "profile_label": variant["profile_label"],
            "tailoring": build_brief(variant),
        })

    def _handle_render_draft(self, body):
        """Render one drafts/Eiselt_*.md against one header variant.

        Body:
          {
            "draft": "Eiselt_ITGovernance.md",
            "header_key": "germany",
            "include_photo": true,
            "format": "pdf" | "docx"   # default pdf
          }

        The draft is the editorial source of truth; we do not re-rank.
        Header swap is the only per-cell variable beyond photo on/off.
        """
        draft_filename = (body.get("draft") or "").strip()
        header_key = (body.get("header_key") or "").strip()
        fmt = (body.get("format") or "pdf").strip().lower()
        include_photo = bool(body.get("include_photo", True))
        if not draft_filename:
            self._send_json({"error": "draft required"}, status=400)
            return
        if not header_key:
            self._send_json({"error": "header_key required"}, status=400)
            return
        try:
            corpus, _cfg = self._ensure_corpus()
        except RuntimeError as e:
            self._send_json({"error": str(e)}, status=500)
            return
        header = corpus.get("header_variants", {}).get(header_key)
        if not header:
            self._send_json({"error": f"unknown header variant '{header_key}'"}, status=400)
            return
        label = draft_filename.replace("Eiselt_", "").replace(".md", "")
        try:
            tailored = draft_build_tailored(draft_filename, header, draft_label=label)
        except FileNotFoundError as e:
            self._send_json({"error": str(e)}, status=404)
            return
        # Filename: Eiselt__Library__{draft}__{header}.{ext}
        stem = f"Eiselt__Library__{label}__{header_key}"
        try:
            if fmt == "docx":
                out = render_docx(tailored, TAILORED_DIR, stem, include_photo=include_photo)
            else:
                out = render_pdf(tailored, TAILORED_DIR, stem, include_photo=include_photo)
        except Exception as e:
            self._send_json({"error": f"{type(e).__name__}: {e}"}, status=500)
            return
        self._send_json({
            "status": "ok",
            "draft": draft_filename,
            "header": header_key,
            "format": fmt,
            "filename": out.name,
            "url": f"/api/tailored/{out.name}",
            "size_bytes": out.stat().st_size,
        })

    def _handle_batch_generate(self, body):
        """Produce a library of baseline PDFs: every role_target × every
        selected header variant. The body may specify subsets to limit work:
          {
            "target_keys": ["it_governance_manager", ...],  # optional, default = all
            "header_keys": ["germany", ...],                # optional, default = all
          }
        Each combination renders one PDF using the role_target's
        configured profile + variant. Returns a list of {target, header,
        filename, url, size_bytes, error?}.
        """
        try:
            corpus, cfg = self._ensure_corpus()
        except RuntimeError as e:
            self._send_json({"error": str(e)}, status=500)
            return
        targets = cfg.get("role_targets", [])
        if not targets:
            self._send_json({"error": "No role_targets defined in profiles.json"}, status=400)
            return
        all_header_keys = list(corpus.get("header_variants", {}).keys())
        if not all_header_keys:
            self._send_json({"error": "No header variants defined in master.md"}, status=400)
            return

        wanted_targets = set(body.get("target_keys") or [t["key"] for t in targets])
        wanted_headers = set(body.get("header_keys") or all_header_keys)
        valid_variants = {v["key"] for v in cfg["variants"]}
        company_label = (body.get("company") or "Library").strip()
        company_slug = slugify(company_label)
        include_photo = bool(body.get("include_photo", True))

        results = []
        for tgt in targets:
            if tgt["key"] not in wanted_targets:
                continue
            variant_key = tgt.get("variant") or "leadership"
            if variant_key not in valid_variants:
                variant_key = next(iter(valid_variants))
            for hk in all_header_keys:
                if hk not in wanted_headers:
                    continue
                try:
                    variant = build_variant(tgt["seed_jd"], corpus, cfg, variant_key)
                    variant["header"] = corpus["header_variants"][hk]
                    stem = f"Eiselt__{company_slug}__{tgt['key']}__{hk}__{variant_key}"
                    pdf = render_pdf(variant, TAILORED_DIR, stem, include_photo=include_photo)
                    results.append({
                        "target": tgt["key"],
                        "target_label": tgt["label"],
                        "header": hk,
                        "variant": variant_key,
                        "filename": pdf.name,
                        "url": f"/api/tailored/{pdf.name}",
                        "size_bytes": pdf.stat().st_size,
                    })
                except Exception as e:
                    results.append({
                        "target": tgt["key"],
                        "header": hk,
                        "variant": variant_key,
                        "error": f"{type(e).__name__}: {e}",
                    })
        self._send_json({
            "status": "ok",
            "pdfs": results,
            "total": len(results),
        })

    def _handle_tailor_docx_from_edits(self, body):
        """Same shape as /api/tailor_pdf_from_edits but writes a .docx via
        python-docx. ATS-friendly format per research_2026.md."""
        company = (body.get("company", "") or "Unknown").strip()
        title = (body.get("title", "") or "Role").strip()
        variant_key = (body.get("variant", "") or "metrics").strip()
        edits = body.get("edits") or {}
        if not edits.get("roles") and not edits.get("skill_ids"):
            self._send_json({"error": "edits.roles and edits.skill_ids cannot both be empty"}, status=400)
            return
        try:
            corpus, cfg = self._ensure_corpus()
        except RuntimeError as e:
            self._send_json({"error": str(e)}, status=500)
            return
        valid_variant_keys = {v["key"] for v in cfg["variants"]}
        if variant_key not in valid_variant_keys:
            self._send_json({"error": f"unknown variant '{variant_key}'"}, status=400)
            return
        edits["variant"] = variant_key
        edits["variant_label"] = next(v["label"] for v in cfg["variants"] if v["key"] == variant_key)
        composition = composition_from_edits(edits)
        company_slug = slugify(company)
        title_slug = slugify(title)
        header_key = edits.get("header_key") or ""
        include_photo = bool(body.get("include_photo", True))
        if header_key:
            stem = f"Eiselt__{company_slug}__{title_slug}__{header_key}__{variant_key}"
        else:
            stem = f"Eiselt__{company_slug}__{title_slug}__{variant_key}"
        try:
            docx_path = render_docx(composition, TAILORED_DIR, stem, include_photo=include_photo)
        except Exception as e:
            self._send_json({"error": f"{type(e).__name__}: {e}"}, status=500)
            return
        self._send_json({
            "status": "ok",
            "variant": variant_key,
            "filename": docx_path.name,
            "url": f"/api/tailored/{docx_path.name}",
            "size_bytes": docx_path.stat().st_size,
            "format": "docx",
        })

    def _handle_master_bullet(self, body):
        """Append a free-typed bullet to the master sentences markdown.

        Body:
          { "section": "skills" | "role", "role_key": "<key>"?,
            "text": "the bullet" }

        Writes to the master file in-place, then triggers a corpus rebuild
        so the new bullet is immediately available to all future renders.
        Returns the canonical id assigned by the extractor.
        """
        section = (body.get("section") or "").strip()
        text = (body.get("text") or "").strip()
        role_key = (body.get("role_key") or "").strip()
        if not text or len(text) < 3:
            self._send_json({"error": "text required"}, status=400)
            return
        if section not in ("skills", "role"):
            self._send_json({"error": "section must be 'skills' or 'role'"}, status=400)
            return
        if section == "role" and not role_key:
            self._send_json({"error": "role_key required when section='role'"}, status=400)
            return

        master_path = MASTER_PATH
        if not master_path.exists():
            self._send_json({"error": f"master file missing at {master_path}"}, status=500)
            return
        original = master_path.read_text(encoding="utf-8")
        lines = original.splitlines(keepends=False)

        if section == "skills":
            # Append under "## CORE COMPETENCIES" at the end of its bullet list.
            target_anchor = "## CORE COMPETENCIES"
            new_lines = self._insert_bullet_under_section(lines, target_anchor, text)
        else:
            # Append under "### <position>" header matching the role_key in
            # CANONICAL_ROLES — match on the role_key keywords.
            from tailor.extract_corpus import CANONICAL_ROLES
            role = next((r for r in CANONICAL_ROLES if r["key"] == role_key), None)
            if not role:
                self._send_json({"error": f"unknown role_key '{role_key}'"}, status=400)
                return
            new_lines = self._insert_bullet_under_role(lines, role, text)

        if new_lines is None:
            self._send_json({"error": f"could not find insertion point for section={section}"}, status=500)
            return
        master_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

        # Re-run extraction so the bullet exists in corpus.json with a stable id.
        proc = subprocess.run(
            [sys.executable, str(HERE / "tailor" / "extract_corpus.py")],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode != 0:
            self._send_json({"error": "corpus rebuild failed", "stderr": proc.stderr[:400]}, status=500)
            return

        # Look up the new bullet's assigned id by scanning the fresh corpus.
        # The extractor normalises em-dashes, smart quotes, and whitespace —
        # so we use the same normaliser to compare.
        from tailor.extract_corpus import normalise as _normalise
        target = _normalise(text)
        corpus = load_corpus(CORPUS_PATH)
        new_id = None
        if section == "skills":
            for b in corpus.get("skills_pool", []):
                if _normalise(b["text"]) == target:
                    new_id = b["id"]; break
        else:
            for r in corpus.get("roles", []):
                if r["key"] != role_key:
                    continue
                for b in r.get("highlights_pool", []):
                    if _normalise(b["text"]) == target:
                        new_id = b["id"]; break
                break
        self._send_json({"status": "ok", "id": new_id, "persisted": True})

    def _insert_bullet_under_section(self, lines, anchor, bullet_text):
        try:
            idx = next(i for i, ln in enumerate(lines) if ln.strip() == anchor)
        except StopIteration:
            return None
        # Find end of section's bullet block — first blank line followed by
        # next ## heading, or just the next non-bullet line.
        insert_at = len(lines)
        for j in range(idx + 1, len(lines)):
            s = lines[j].strip()
            if s.startswith("## "):
                insert_at = j
                break
        # Trim back any trailing blanks before insert_at so the new bullet
        # stays inside the section.
        while insert_at > 0 and lines[insert_at - 1].strip() == "":
            insert_at -= 1
        return lines[:insert_at] + [f"- {bullet_text}"] + lines[insert_at:]

    def _insert_bullet_under_role(self, lines, role, bullet_text):
        """Insert a bullet under the role's ### heading inside ## EXPERIENCE."""
        # Find ## EXPERIENCE first to scope the search.
        try:
            exp_start = next(i for i, ln in enumerate(lines) if ln.strip() == "## EXPERIENCE")
        except StopIteration:
            return None
        # Find the role's ### heading by matching keywords.
        role_idx = None
        for j in range(exp_start + 1, len(lines)):
            ln = lines[j]
            if ln.strip().startswith("### "):
                low = ln.lower()
                if any(kw in low for kw in role["match_keywords"]):
                    role_idx = j; break
            if ln.strip().startswith("## "):
                break
        if role_idx is None:
            return None
        # Find end of this role's bullet block (next ### or ## heading).
        end = len(lines)
        for j in range(role_idx + 1, len(lines)):
            s = lines[j].strip()
            if s.startswith("### ") or s.startswith("## "):
                end = j; break
        # Trim back trailing blanks.
        while end > 0 and lines[end - 1].strip() == "":
            end -= 1
        return lines[:end] + [f"- {bullet_text}"] + lines[end:]

    def _handle_jd_analyze(self, body):
        """Spec §10 endpoint for the v2 tailored page.

        Given a pasted JD text, return:
          - Skills demanded by the JD (canonical labels from the registry)
          - Closest matching role_target (so the page can preselect a mask)
          - Detected listing title hint (best-effort regex; the page lets
            the user override)
          - Optional coverage block when `composition` is supplied — letting
            the page show live coverage as the user edits without a second
            round trip
        """
        jd_text = body.get("jd_text", "")
        if not jd_text or len(jd_text.strip()) < 20:
            self._send_json({"error": "jd_text required (at least a paragraph)"}, status=400)
            return
        try:
            corpus, cfg = self._ensure_corpus()
        except RuntimeError as e:
            self._send_json({"error": str(e)}, status=500)
            return

        jd_skills = extract_skills(jd_text)

        # Closest role target — keyword-overlap score against each target's seed JD.
        targets = cfg.get("role_targets", [])
        target_scores: list[tuple[float, dict]] = []
        for tgt in targets:
            seed_skills = set(extract_skills(tgt.get("seed_jd", "")))
            jd_set = set(jd_skills)
            overlap = len(jd_set & seed_skills) / max(1, len(jd_set | seed_skills))
            target_scores.append((overlap, tgt))
        target_scores.sort(key=lambda x: -x[0])
        top_target = target_scores[0][1] if target_scores else None

        # Title hint — first 8 words of the JD's first non-empty line, with
        # "Senior" / "Lead" / "Manager" / "Owner" boosted as likely title tokens.
        title_hint = ""
        for raw in jd_text.splitlines():
            s = raw.strip()
            if s and len(s.split()) <= 12 and any(c.isupper() for c in s):
                title_hint = s.rstrip(".,:;")
                break

        # Optional live coverage against a supplied composition.
        cov = None
        composition = body.get("composition") or {}
        if composition:
            cv_texts = self._composition_to_texts(composition)
            cov = skill_coverage(jd_text, cv_texts)

        self._send_json({
            "status": "ok",
            "title_hint": title_hint,
            "jd_skills": jd_skills,
            "top_role_target": top_target["key"] if top_target else None,
            "top_role_target_label": top_target["label"] if top_target else None,
            "all_role_targets_ranked": [
                {"key": t["key"], "label": t["label"], "score": round(s, 3)}
                for s, t in target_scores
            ],
            "coverage": cov,
        })

    def _composition_to_texts(self, composition: dict) -> list[str]:
        """Flatten a composition (summary + skills + per-role highlights)
        into a flat list of strings for skill matching."""
        out: list[str] = []
        if composition.get("summary"):
            out.append(composition["summary"])
        out.extend(composition.get("skills", []) or [])
        for r in composition.get("roles", []) or []:
            out.append(r.get("position", ""))
            out.append(r.get("company", ""))
            out.extend(r.get("highlights", []) or [])
        return out

    def _handle_coverage(self, body):
        """Lightweight coverage-only endpoint — same payload as jd_analyze
        but skips title / target detection, for tight UI loops."""
        jd_text = body.get("jd_text", "")
        composition = body.get("composition") or {}
        if not jd_text:
            self._send_json({"error": "jd_text required"}, status=400)
            return
        cv_texts = self._composition_to_texts(composition)
        self._send_json({"status": "ok", "coverage": skill_coverage(jd_text, cv_texts)})

    def _handle_tailor_view_freeform(self, body):
        """Structured editable view for a pasted JD (same shape as the
        /api/tailor response used by the dashboard modal, but no job_id
        required)."""
        jd_text = body.get("jd_text", "")
        company = (body.get("company", "") or "").strip()
        title = (body.get("title", "") or "").strip()
        variant_key = body.get("variant") or "metrics"
        if not jd_text or len(jd_text.strip()) < 20:
            self._send_json({"error": "jd_text required (at least a paragraph)"}, status=400)
            return
        try:
            corpus, cfg = self._ensure_corpus()
        except RuntimeError as e:
            self._send_json({"error": str(e)}, status=500)
            return
        if not any(v["key"] == variant_key for v in cfg["variants"]):
            self._send_json({"error": f"Unknown variant '{variant_key}'"}, status=400)
            return
        view = build_editable_view(jd_text, corpus, cfg, variant_key)
        self._send_json({
            "status": "ok",
            "source": "local_retrieval",
            "job": {"title": title, "company": company, "location": ""},
            "view": view,
        })

    def _handle_tailor_pdf_from_edits(self, body):
        """Render a PDF from a user-edited composition. Used by the editable
        modal. The variant name is just a filename label here — the engine
        renders whatever the user has selected.

        Expected body:
          {
            "company": "...", "title": "...",
            "variant": "metrics" | "leadership" | "tooling",
            "edits": { profile, profile_label, summary_id, skill_ids[],
                       roles: [ {key, highlight_ids[]} ] }
          }
        """
        company = (body.get("company", "") or "Unknown").strip()
        title = (body.get("title", "") or "Role").strip()
        variant_key = (body.get("variant", "") or "metrics").strip()
        edits = body.get("edits") or {}
        if not edits.get("roles") and not edits.get("skill_ids"):
            self._send_json({"error": "edits.roles and edits.skill_ids cannot both be empty"}, status=400)
            return
        try:
            corpus, cfg = self._ensure_corpus()
        except RuntimeError as e:
            self._send_json({"error": str(e)}, status=500)
            return
        valid_variant_keys = {v["key"] for v in cfg["variants"]}
        if variant_key not in valid_variant_keys:
            self._send_json({"error": f"unknown variant '{variant_key}'"}, status=400)
            return
        # Carry profile label through so it appears in the PDF metadata trace.
        edits["variant"] = variant_key
        edits["variant_label"] = next(v["label"] for v in cfg["variants"] if v["key"] == variant_key)
        composition = composition_from_edits(edits)
        company_slug = slugify(company)
        title_slug = slugify(title)
        header_key = edits.get("header_key") or ""
        include_photo = bool(body.get("include_photo", True))
        if header_key:
            stem = f"Eiselt__{company_slug}__{title_slug}__{header_key}__{variant_key}"
        else:
            stem = f"Eiselt__{company_slug}__{title_slug}__{variant_key}"
        try:
            pdf = render_pdf(composition, TAILORED_DIR, stem, include_photo=include_photo)
        except Exception as e:
            self._send_json({"error": f"{type(e).__name__}: {e}"}, status=500)
            return
        self._send_json({
            "status": "ok",
            "variant": variant_key,
            "filename": pdf.name,
            "url": f"/api/tailored/{pdf.name}",
            "size_bytes": pdf.stat().st_size,
        })

    def _handle_tailor_pdf_freeform(self, body):
        """Produce PDFs for a pasted JD."""
        jd_text = body.get("jd_text", "") or body.get("description", "")
        company = (body.get("company", "") or "Unknown").strip()
        title = (body.get("title", "") or "Role").strip()
        header_key = (body.get("header_key", "") or "").strip() or None
        include_photo = bool(body.get("include_photo", True))
        if not jd_text:
            self._send_json({"error": "jd_text required"}, status=400)
            return
        try:
            results = self._produce_pdfs(jd_text=jd_text, company=company, title=title,
                                         header_key=header_key, include_photo=include_photo)
        except RuntimeError as e:
            self._send_json({"error": str(e)}, status=500)
            return
        except ValueError as e:
            self._send_json({"error": str(e)}, status=400)
            return
        except Exception as e:
            self._send_json({"error": f"{type(e).__name__}: {e}"}, status=500)
            return
        self._send_json({
            "status": "ok",
            "job": {"title": title, "company": company, "location": ""},
            "header_key": header_key,
            "pdfs": results,
        })

    def _handle_rebuild_corpus(self):
        """Re-run the corpus extractor as a subprocess."""
        task_id = uuid.uuid4().hex[:10]
        t = threading.Thread(
            target=run_subprocess_task,
            args=(task_id, "rebuild_corpus", [sys.executable, str(HERE / "tailor" / "extract_corpus.py")]),
            daemon=True,
        )
        t.start()
        self._send_json({"task_id": task_id, "kind": "rebuild_corpus"})

    def _serve_tailored_pdf(self, filename):
        """Stream a previously generated PDF or .docx from results/tailored/."""
        candidate = (TAILORED_DIR / filename).resolve()
        try:
            candidate.relative_to(TAILORED_DIR.resolve())
        except ValueError:
            self.send_error(403)
            return
        if not candidate.exists() or not candidate.is_file():
            self.send_error(404)
            return
        data = candidate.read_bytes()
        mime = "application/pdf"
        disposition = "inline"
        if candidate.suffix.lower() == ".docx":
            mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            disposition = "attachment"  # browsers can't preview docx
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header(
            "Content-Disposition",
            f'{disposition}; filename="{candidate.name}"',
        )
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/dashboard.html"):
            self._send_file(DASHBOARD_PATH, "text/html; charset=utf-8")
        elif path in ("/paste", "/paste.html"):
            self._send_file(PASTE_PATH, "text/html; charset=utf-8")
        elif path in ("/library", "/library.html"):
            self._send_file(LIBRARY_PATH, "text/html; charset=utf-8")
        elif path.startswith("/api/tailored/"):
            filename = path[len("/api/tailored/"):]
            self._serve_tailored_pdf(filename)
        elif path == "/api/header_variants":
            try:
                corpus, _ = self._ensure_corpus()
            except RuntimeError as e:
                self._send_json({"error": str(e)}, status=500)
                return
            self._send_json({
                "default": corpus.get("default_header_key", "germany"),
                "variants": corpus.get("header_variants", {}),
            })
        elif path == "/api/role_targets":
            try:
                corpus, cfg = self._ensure_corpus()
            except RuntimeError as e:
                self._send_json({"error": str(e)}, status=500)
                return
            self._send_json({
                "targets": cfg.get("role_targets", []),
                "header_variants": list(corpus.get("header_variants", {}).keys()),
            })
        elif path == "/api/drafts":
            try:
                corpus, _ = self._ensure_corpus()
            except RuntimeError as e:
                self._send_json({"error": str(e)}, status=500)
                return
            self._send_json({
                "drafts": list_drafts(),
                "header_variants": list(corpus.get("header_variants", {}).keys()),
            })
        elif path == "/api/tailored":
            # List previously generated PDFs.
            if not TAILORED_DIR.exists():
                self._send_json({"pdfs": []})
                return
            pdfs = sorted(
                ({"filename": p.name, "url": f"/api/tailored/{p.name}",
                  "size_bytes": p.stat().st_size, "mtime": int(p.stat().st_mtime)}
                 for p in TAILORED_DIR.glob("*.pdf")),
                key=lambda x: -x["mtime"],
            )
            self._send_json({"pdfs": list(pdfs)})
        elif path == "/api/scored":
            if SCORED_PATH.exists():
                self._send_file(SCORED_PATH, "application/json; charset=utf-8")
            else:
                self._send_json({"jobs": [], "scored_count": 0, "note": "No scored data yet. Run scrape + score."})
        elif path == "/api/config":
            if CONFIG_PATH.exists():
                cfg = json.loads(CONFIG_PATH.read_text())
                # Hide token from frontend
                if "apify_token" in cfg:
                    cfg["apify_token_masked"] = cfg["apify_token"][:14] + "..." + cfg["apify_token"][-4:]
                    cfg["apify_token"] = ""
                self._send_json(cfg)
            else:
                self._send_json({})
        elif path.startswith("/api/task/"):
            task_id = path.rsplit("/", 1)[1]
            with TASKS_LOCK:
                task = TASKS.get(task_id)
            if not task:
                self._send_json({"status": "unknown"}, status=404)
            else:
                self._send_json(task)
        elif path == "/api/raw_meta":
            if RAW_PATH.exists():
                raw = json.loads(RAW_PATH.read_text())
                meta = {k: v for k, v in raw.items() if k != "jobs"}
                meta["jobs_count"] = len(raw.get("jobs", []))
                self._send_json(meta)
            else:
                self._send_json({"note": "No raw data yet."})
        else:
            self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_json_body()

        if path == "/api/scrape":
            # Optional: override results_wanted and hours_old in config first
            updates = {}
            for key in ("results_wanted", "hours_old", "count_per_url"):
                if key in body:
                    try:
                        updates[key] = int(body[key])
                    except (ValueError, TypeError):
                        pass
            if updates and CONFIG_PATH.exists():
                cfg = json.loads(CONFIG_PATH.read_text())
                cfg.update(updates)
                CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
            task_id = uuid.uuid4().hex[:10]
            t = threading.Thread(
                target=run_subprocess_task,
                args=(task_id, "scrape", [sys.executable, str(HERE / "scrape_jobs.py")]),
                daemon=True,
            )
            t.start()
            self._send_json({"task_id": task_id, "kind": "scrape"})

        elif path == "/api/score":
            task_id = uuid.uuid4().hex[:10]
            t = threading.Thread(
                target=run_subprocess_task,
                args=(task_id, "score", [sys.executable, str(HERE / "score_jobs.py")]),
                daemon=True,
            )
            t.start()
            self._send_json({"task_id": task_id, "kind": "score"})

        elif path == "/api/score_v2":
            task_id = uuid.uuid4().hex[:10]
            t = threading.Thread(
                target=run_subprocess_task,
                args=(task_id, "score_v2", [sys.executable, str(HERE / "score_jobs_v2.py")]),
                daemon=True,
            )
            t.start()
            self._send_json({"task_id": task_id, "kind": "score_v2"})

        elif path == "/api/shutdown":
            self._send_json({"status": "shutting_down"})
            # Schedule shutdown so the response can be flushed first
            def _shutdown():
                import time as _t
                _t.sleep(0.4)
                if _server_ref is not None:
                    _server_ref.shutdown()
            threading.Thread(target=_shutdown, daemon=True).start()

        elif path == "/api/tailor":
            self._handle_tailor(body)

        elif path == "/api/tailor_pdf":
            self._handle_tailor_pdf(body)

        elif path == "/api/tailor_pdf_freeform":
            self._handle_tailor_pdf_freeform(body)

        elif path == "/api/tailor_pdf_from_edits":
            self._handle_tailor_pdf_from_edits(body)

        elif path == "/api/tailor_docx_from_edits":
            self._handle_tailor_docx_from_edits(body)

        elif path == "/api/tailor_preview":
            self._handle_tailor_preview(body)

        elif path == "/api/tailor_view_freeform":
            self._handle_tailor_view_freeform(body)

        elif path == "/api/jd_analyze":
            self._handle_jd_analyze(body)

        elif path == "/api/coverage":
            self._handle_coverage(body)

        elif path == "/api/master/bullet":
            self._handle_master_bullet(body)

        elif path == "/api/batch_generate":
            self._handle_batch_generate(body)

        elif path == "/api/render_draft":
            self._handle_render_draft(body)

        elif path == "/api/rebuild_corpus":
            self._handle_rebuild_corpus()

        elif path == "/api/config":
            if not CONFIG_PATH.exists():
                self._send_json({"error": "config.json missing"}, status=500)
                return
            cfg = json.loads(CONFIG_PATH.read_text())
            # Allow updating only safe keys
            for key in ("search_terms", "locations", "sites", "results_wanted",
                        "hours_old", "ignore_companies", "count_per_url",
                        "actor_id", "search_urls"):
                if key in body:
                    cfg[key] = body[key]
            CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
            self._send_json({"status": "ok", "config": cfg})

        else:
            self.send_error(404)


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    global _server_ref
    print(f"Job Finder server starting on http://localhost:{PORT}")
    print(f"Dashboard:  http://localhost:{PORT}")
    print(f"Working dir: {HERE}")
    print("Ctrl+C to stop, or click 'Stop server' in the dashboard.\n")

    server = ThreadingServer(("127.0.0.1", PORT), Handler)
    _server_ref = server
    threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
