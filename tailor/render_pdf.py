#!/usr/bin/env python3
"""
Turn a tailored CV structure (from retrieval.build_variant) into a PDF via
RenderCV + Typst.

Workflow per render:
  1. Build a RenderCV YAML dict from the tailored structure.
  2. Write it to a temp folder.
  3. Run `rendercv render` against that YAML, telling RenderCV to drop only
     the PDF into a specific output folder.
  4. Rename the produced PDF to the requested filename and clean up.

Public API:
    render_pdf(tailored, output_dir, filename_stem) -> Path  (the produced PDF)
    render_all_variants(jd_text, company, job_title, *, jd_id=None) -> list[Path]

CLI:
    python tailor/render_pdf.py --jd path/to/jd.txt --company Acme --title "PPM"
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

import ruamel.yaml

# Allow `python tailor/render_pdf.py` from the project root as well as
# `python -m tailor.render_pdf` import paths.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tailor.retrieval import build_all_variants, load_corpus, load_profiles  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
TAILORED_DIR = HERE / "results" / "tailored"
RENDERCV_BIN = HERE / ".venv" / "bin" / "rendercv"
ASSETS_DIR = HERE / "assets"
PHOTO_CANDIDATES = [
    ASSETS_DIR / "photo.jpg",
    ASSETS_DIR / "photo.jpeg",
    ASSETS_DIR / "photo.png",
]
# 4:5 portrait crop is the standard headshot ratio (LinkedIn, Instagram
# portrait). Cache filename includes the ratio so changing it forces a
# re-crop on next render.
PHOTO_CACHE = ASSETS_DIR / ".cache_photo_4x5.jpg"


# Round-trip mode (default) preserves dict insertion order. The 'safe' typ
# sorts mapping keys alphabetically when dumping, which scrambles the
# section order we set on the CV.
_yaml = ruamel.yaml.YAML()
_yaml.default_flow_style = False
_yaml.width = 4096
_yaml.indent(mapping=2, sequence=4, offset=2)


def slugify(text: str, max_len: int = 60) -> str:
    """Filesystem-safe label. Underscores survive intact so internal stable
    keys like `it_governance_manager` round-trip through the renderer
    cleanly (otherwise the batch path and the edit path produce different
    filenames for the same cell)."""
    if not text:
        return "untitled"
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9_]+", "-", text).strip("-")
    return (text or "untitled")[:max_len]


def _date_str(d: str) -> str | None:
    """Pass YYYY or YYYY-MM through unchanged; map 'present' to None (RenderCV
    treats end_date=None as ongoing if start_date is set, but to render
    'present' explicitly we return the string 'present')."""
    if not d:
        return None
    if d.lower() == "present":
        return "present"
    return d


def build_rendercv_yaml(tailored: dict, include_photo: bool = True) -> dict:
    """Construct a v2 RenderCV YAML dict from the tailored structure.

    `include_photo` controls whether the renderer attaches the headshot from
    assets/. When False, the photo field is omitted even if a source image
    exists on disk — useful for US/UK-style applications that omit photos."""
    h = tailored["header"]

    # RenderCV's `phone` field is strict E.164 single-value. When the header
    # has more than one phone (e.g. the Taiwan variant carries both VN and DE
    # numbers), the primary goes into cv.phone and extras get appended to the
    # location line — that's where multi-phone resumes typically display them
    # in print anyway, and avoids fighting RenderCV's HttpUrl-required
    # custom_connections schema.
    primary_phone, extra_phones = _split_phones(h.get("phone", ""))
    location = (h.get("location", "") or "").strip()
    if extra_phones:
        suffix = "  ·  " + "  ·  ".join(extra_phones)
        location = (location + suffix) if location else suffix.lstrip(" ·")
    # Split address vs availability onto separate lines (ATS-friendly).
    location = _format_location_for_typst(location)
    cv = {
        "name": h.get("name", "Philipp Eiselt"),
        "location": location or None,
        "email": h.get("email", "") or None,
        "phone": primary_phone or None,
        "website": _normalise_url(h.get("website", "")),
        "social_networks": _social_networks(h),
        "sections": {},
    }
    photo_path = find_photo() if include_photo else None
    if photo_path:
        cv["photo"] = str(photo_path)
    if tailored.get("profile_label"):
        cv["headline"] = h.get("headline", "") or "Senior IT Project & Portfolio Manager"
    elif h.get("headline"):
        cv["headline"] = h["headline"]

    # Default section order: Summary → Experience → Education → Projects →
    # Languages → Core Competencies → Certifications.
    # If the draft sets `projects_first: True` (engineering / developer
    # drafts where the personal products are the primary evidence), the
    # Personal Software Projects section moves to the second slot, above
    # Experience.
    # RenderCV preserves the insertion order of the sections dict.

    # Pre-build each section's value once so the only thing that varies
    # is the insertion order.
    summary_value = [tailored["summary"]] if tailored.get("summary") else None

    experience_entries = []
    for r in tailored["roles"]:
        if not r["highlights"]:
            continue
        experience_entries.append({
            "company": r["company"],
            "position": r["position"],
            "location": r["location"],
            "start_date": _date_str(r["start_date"]),
            "end_date": _date_str(r["end_date"]),
            "highlights": list(r["highlights"]),
        })

    project_entries = None
    if tailored.get("projects"):
        project_entries = []
        for p in tailored["projects"]:
            entry = {"name": p["name"]}
            if p.get("summary"):
                entry["summary"] = p["summary"]
            project_entries.append(entry)

    sections: dict = {}
    if summary_value is not None:
        sections["Summary"] = summary_value

    if tailored.get("projects_first") and project_entries:
        sections["Personal Software Projects"] = project_entries

    if experience_entries:
        sections["Experience"] = experience_entries

    if tailored.get("education"):
        sections["Education"] = list(tailored["education"])

    if not tailored.get("projects_first") and project_entries:
        sections["Personal Software Projects"] = project_entries

    if tailored.get("languages"):
        sections["Languages"] = list(tailored["languages"])

    if tailored.get("skills"):
        sections["Core Competencies"] = list(tailored["skills"])

    if tailored.get("certifications"):
        sections["Certifications"] = list(tailored["certifications"])

    cv["sections"] = sections

    return {
        "cv": cv,
        "design": {
            "theme": "engineeringresumes",
            "page": {
                "size": "a4",
                "top_margin": "0.7in",
                "bottom_margin": "0.7in",
                "left_margin": "0.7in",
                "right_margin": "0.7in",
                "show_top_note": False,
            },
            # `entries.allow_page_break: False` is the default. We tried
            # True earlier to close the page-1 white gap that appears
            # when a long role gets pushed to page 2, but Typst then
            # orphans the role heading on page 1 with all bullets on
            # page 2 - worse than the gap. Per-draft content tuning is
            # the right lever; keep this False.
            "entries": {
                "allow_page_break": False,
            },
            "header": {
                "connections": {
                    "phone_number_format": "international",
                },
                # When a photo is present, left-align the header text so it
                # doesn't visually fight with the right-edge headshot.
                # Without a photo, center alignment (RenderCV default) is fine.
                **({
                    "alignment": "left",
                    "photo_position": "right",
                    "photo_width": "2.8cm",
                    "photo_space_left": "0.4cm",
                    "photo_space_right": "0cm",
                } if photo_path else {}),
            },
        },
        "locale": {"language": "english"},
        "settings": {
            "current_date": "today",
            "pdf_title": f"{h.get('name', 'CV')} - CV",
        },
    }


def find_photo() -> Path | None:
    """Locate a source photo in assets/ and return a cached, 4:5-cropped
    copy ready for RenderCV. Returns None if no photo is configured.

    The original portrait is left untouched. The cache is invalidated when
    the source mtime is newer than the cache mtime.
    """
    source = next((p for p in PHOTO_CANDIDATES if p.exists()), None)
    if not source:
        return None
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        # Reuse cache only if source hasn't been replaced since.
        if PHOTO_CACHE.exists() and PHOTO_CACHE.stat().st_mtime >= source.stat().st_mtime:
            return PHOTO_CACHE
        with Image.open(source) as img:
            img = img.convert("RGB")
            w, h = img.size
            # 4:5 portrait (width:height). Take the widest possible 4:5 crop
            # the source can support, centered horizontally, with a slight
            # upward bias so the face (usually in the upper portion of a
            # portrait) stays in frame.
            target_w = min(w, (h * 4) // 5)
            target_h = (target_w * 5) // 4
            if target_h > h:
                target_h = h
                target_w = (target_h * 4) // 5
            left = (w - target_w) // 2
            top = max(0, int((h - target_h) * 0.18))
            box = (left, top, left + target_w, top + target_h)
            cropped = img.crop(box)
            # 480x600 keeps print quality at 3 cm wide while keeping the
            # PDF small.
            if target_w > 480:
                cropped = cropped.resize((480, 600), Image.LANCZOS)
            PHOTO_CACHE.parent.mkdir(parents=True, exist_ok=True)
            cropped.save(PHOTO_CACHE, "JPEG", quality=88, optimize=True)
        return PHOTO_CACHE
    except Exception:
        return None


def _format_location_for_typst(raw: str) -> str:
    """Convert a header location like
        "Obere-Tiefenbach-Str. 10, 83734 Hausham, Germany · Open to relocate within EMEA - on-site or hybrid"
    into Typst-formatted content where the first `·`-separated segment is
    the postal address (line 1) and the rest joins with commas onto a new
    line. The whole thing is boxed at 100 % page width so the trailing
    contacts (email / phone / website) are forced onto their own line
    rather than running onto the relocation line.

    Three reasons to bake this in:
      - ATS parsers prefer simple commas over middle dots.
      - "EMEA - on-site or hybrid" reads as a stray hyphen for ATS; comma is
        unambiguous.
      - Wrapping locations cleanly is what makes a header look professional.
    Falls back to the raw string when there's only one segment.
    """
    if not raw:
        return raw
    parts = [p.strip() for p in raw.split(" · ") if p.strip()]
    if len(parts) <= 1:
        return raw
    addr = parts[0].rstrip(",")
    rest = ", ".join(re.sub(r"\s+-\s+", ", ", p) for p in parts[1:])
    return f"#pad(right: 0pt, box(width: 100%)[{addr}, #linebreak() {rest}])"


def _split_phones(text: str) -> tuple[str | None, list[str]]:
    """Split a phone string that may contain multiple numbers (separated by ` · `
    or `|`) into (primary, [extras]). Each returned phone is whitespace-collapsed."""
    if not text:
        return None, []
    parts = [p.strip() for p in re.split(r"\s+·\s+|\s+\|\s+|\s+/\s+", text) if p.strip()]
    if not parts:
        return None, []
    primary = re.sub(r"\s+", " ", parts[0])
    extras = [re.sub(r"\s+", " ", p) for p in parts[1:]]
    return primary, extras


def _normalise_url(text: str) -> str | None:
    if not text:
        return None
    t = text.strip()
    if not t.startswith(("http://", "https://")):
        t = "https://" + t
    return t


def _social_networks(header: dict) -> list[dict]:
    """LinkedIn + GitHub rendered as RenderCV social_networks entries.
    Both expose a `username` extracted from whatever URL form the
    header variant stored (linkedin.com/in/<u> or github.com/<u>)."""
    out = []
    li = header.get("linkedin", "")
    if li:
        m = re.search(r"linkedin\.com/in/([A-Za-z0-9\-_.]+)", li)
        username = m.group(1) if m else li.strip().rstrip("/").rsplit("/", 1)[-1]
        out.append({"network": "LinkedIn", "username": username})
    gh = header.get("github", "")
    if gh:
        m = re.search(r"github\.com/([A-Za-z0-9\-_.]+)", gh)
        username = m.group(1) if m else gh.strip().rstrip("/").rsplit("/", 1)[-1]
        out.append({"network": "GitHub", "username": username})
    return out


def render_pdf(tailored: dict, output_dir: Path, filename_stem: str, *, include_photo: bool = True) -> Path:
    """Run RenderCV and return the path to the produced PDF, renamed to
    `<filename_stem>.pdf` inside `output_dir`. Set include_photo=False to
    omit the headshot for this render."""
    output_dir.mkdir(parents=True, exist_ok=True)
    rcv_yaml = build_rendercv_yaml(tailored, include_photo=include_photo)
    with tempfile.TemporaryDirectory(prefix="rendercv_") as tmpdir:
        tmp = Path(tmpdir)
        yaml_path = tmp / "cv.yaml"
        with yaml_path.open("w", encoding="utf-8") as fh:
            _yaml.dump(rcv_yaml, fh)
        out_folder = tmp / "out"
        out_folder.mkdir()
        # Invoke rendercv via `python -m` so the call survives a project
        # move: the .venv/bin/rendercv shim has a baked-in shebang
        # pointing at the install-time python path, which breaks once
        # the venv has been relocated. sys.executable here is whichever
        # python loaded the server (the bootstrap already pinned it to
        # the project's .venv).
        cmd = [
            sys.executable, "-m", "rendercv", "render", str(yaml_path),
            "--output-folder", str(out_folder),
            "--dont-generate-markdown",
            "--dont-generate-html",
            "--dont-generate-png",
        ]
        proc = subprocess.run(
            cmd,
            cwd=tmp,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            # Persist the failing YAML for inspection.
            debug_dir = HERE / "results" / "tailored" / "_debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_yaml = debug_dir / f"failed_{filename_stem}.yaml"
            shutil.copy(yaml_path, debug_yaml)
            raise RuntimeError(
                f"rendercv render failed (exit {proc.returncode}):\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}\n"
                f"YAML preserved at: {debug_yaml}"
            )
        # Find the produced PDF.
        produced = sorted(out_folder.glob("*.pdf"))
        if not produced:
            raise RuntimeError(
                f"rendercv produced no PDF. Output dir contents: {[p.name for p in out_folder.iterdir()]}"
            )
        target = output_dir / f"{filename_stem}.pdf"
        if target.exists():
            target.unlink()
        shutil.move(str(produced[0]), str(target))
        return target


def render_all_variants(
    jd_text: str,
    company: str,
    job_title: str,
    *,
    output_dir: Path = TAILORED_DIR,
    only_variants: list[str] | None = None,
    include_photo: bool = True,
) -> list[dict]:
    """Run every variant defined in profiles.json and produce a PDF for each.

    Returns a list of {variant, profile, pdf_path, trace} dicts."""
    variants = build_all_variants(jd_text)
    company_slug = slugify(company or "Unknown")
    title_slug = slugify(job_title or "Role")
    output_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for v in variants:
        if only_variants and v["variant"] not in only_variants:
            continue
        stem = f"Eiselt__{company_slug}__{title_slug}__{v['variant']}"
        pdf = render_pdf(v, output_dir, stem, include_photo=include_photo)
        out.append({
            "variant": v["variant"],
            "variant_label": v["variant_label"],
            "profile": v["profile"],
            "profile_label": v["profile_label"],
            "pdf_path": str(pdf),
            "pdf_name": pdf.name,
            "trace": v["trace"],
        })
    return out


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--jd", required=True, help="Path to a JD text file (or raw text)")
    p.add_argument("--company", default="Acme")
    p.add_argument("--title", default="Senior Project Portfolio Manager")
    p.add_argument("--variant", default=None, help="Comma-separated subset, e.g. metrics,tooling")
    args = p.parse_args()
    jd = args.jd
    if Path(jd).exists():
        jd = Path(jd).read_text(encoding="utf-8")
    only = args.variant.split(",") if args.variant else None
    results = render_all_variants(jd, args.company, args.title, only_variants=only)
    print(json.dumps([{k: v for k, v in r.items() if k != "trace"} for r in results], indent=2))
