# Spec — Tailored CV (v2)

> Written by the recruiter agent operating per
> [`WRITER_GUIDE.md`](WRITER_GUIDE.md), informed by the 2026 ATS research
> (`research_2026.md` summary inlined below). Intended audience: the dev
> team that will implement this as a React page after the editorial
> validation pass. Read the writer guide first; it sets editorial rules
> the dev team must not silently override.

---

## 0. Two product modes — why v2 is separate

The product has two distinct modes. They share an engine, not a page.

| | **Ready-made (v1, `/library`)** | **Tailored (v2, this spec)** |
|---|---|---|
| Trigger | Pre-generated baseline per role × geography | One real JD at a time |
| Bullet picking | BM25 against the role target's static seed JD | BM25 against the actual JD text |
| Title in header | Generic — "Senior Project Manager" | **Mirrors the listing title verbatim** |
| Keyword target | n/a | **70–80 %** of the listing's keywords present |
| Output cadence | Batch (the 8 × 4 grid, generated once) | Per application |
| Where applicants land | Cold blasts where you don't have a JD | Real applications, ATS-screened |
| File output | PDF | **PDF + `.docx`** (`.docx` is phase 2) |
| Use case | "I'll apply to the next portfolio role I see" | "This Wavestone S/4HANA PM role at €110 k, sponsored, Munich" |

v1 stays. v2 is what you use when an interview actually matters.

---

## 1. Why v2 exists (research summary)

From 2026 ATS reality, distilled — every claim here is a measurable
target for v2:

- **99.7 %** of recruiters use ATS filters; **98.4 %** of Fortune 500 do.
- **76.4 %** filter by skills first, **55.3 %** by exact job title,
  **50.6 %** by certifications. (Source: Jobscan State of the Job Search
  2025.)
- **10.6×** interview rate boost when the resume's job-title line matches
  the listing's title exactly.
- **40–60 %** higher ATS score for a tailored version of the same
  resume vs. the generic version.

The old "ATS rejects 75 %" framing is wrong. ATS doesn't reject — it
**ranks**. The real failure mode is being buried under candidates whose
resume mirrors the listing better. v2's job is to make Philipp's CV mirror
each listing better than 80 % of competing applicants.

---

## 2. Hard goals for v2

These are the *measurable* outcomes the v2 page must support. Treat them
as acceptance criteria for the React build.

1. **Exact title match.** The job-title line under the candidate's name
   must be editable to mirror the listing's title verbatim. The page
   must show a green check when they match and a warning when they
   don't.
2. **Keyword coverage gauge.** The page must compute (% of the
   listing's high-value keywords present in the rendered CV) and update
   live as the user edits. Target band: **70 – 80 %**. Yellow above 80 %
   (over-stuffing risk).
3. **Missing-keyword surface.** Show the 5 most impactful JD keywords
   that are *missing* from the current CV. Clicking one scrolls to the
   bullet or skill most likely to absorb it.
4. **In-page editing.** The user can edit every field on the page —
   summary, skills, role highlights, header headline, header location —
   without leaving for a separate modal. This is a single-page editor.
5. **Free-typed bullets.** The user can type a new bullet in-place when
   the master doesn't have what the JD demands. Two save modes:
   *Use here only* and *Save to master* (the latter appends to
   `master sentences.md`). Default is *Use here only*.
6. **Header swap.** Geography header swap (Germany / Singapore /
   Taiwan / Vietnam) without rebuilding the composition. Single click.
7. **Photo toggle.** Per-render on/off. Default on. Off-state hint
   reminds the user when geography typically omits photos
   (US / UK / Canada).
8. **Export PDF + `.docx`** (`.docx` is phase 2). Filename:
   `Eiselt_<RoleMask>_<Geo>[_nophoto]_<JDtitleSlug>.pdf`.

---

## 3. Workflow (single user flow)

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. JD input                                                         │
│    - Paste JD text  OR  pick a scored job from /                    │
│    - Optional: company, listing URL, listing title                  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 2. Auto-analysis (≤ 1 s)                                            │
│    - Detect listing title                                           │
│    - Detect top-30 keywords                                         │
│    - Map to closest role mask (1 of 8)                              │
│    - Build initial composition via build_editable_view              │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 3. Editor opens with the composition + analytics overlay            │
│    Left:  Header / Summary / Skills / Roles  (editable)             │
│    Right: Coverage gauge, missing keywords, title-match badge       │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 4. User edits (target: < 10 min)                                    │
│    - 3 moves from WRITER_GUIDE §2-min loop                          │
│    - Free-typed bullets allowed where master is thin                │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 5. Export                                                           │
│    - Pick geography header (G / T / V / S)                          │
│    - Photo toggle                                                   │
│    - Render PDF (or .docx, phase 2)                                 │
└─────────────────────────────────────────────────────────────────────┘
```

If the user re-pastes a different JD, the editor offers two paths:
*Start over from new auto-pick* (lose edits) or *Keep my composition,
just re-score* (keeps edits, updates the coverage gauge).

---

## 4. Role masks v2 supports

Same eight roles Philipp asked about, expanded over the v1 set:

| key                         | label                            | profile (BM25 boost) | default variant |
|-----------------------------|----------------------------------|----------------------|-----------------|
| `it_governance_manager`     | IT Governance Manager            | governance_pm        | leadership      |
| `it_project_manager`        | IT Project Manager               | it_project_manager   | leadership      |
| `it_project_portfolio_manager` | IT Project Portfolio Manager  | portfolio_pm         | metrics         |
| `it_process_manager`        | IT Process Manager               | it_process_manager   | tooling         |
| `product_manager`           | Product Manager                  | product_manager      | leadership      |
| `it_product_owner`          | IT Product Owner                 | product_owner        | tooling         |
| `ai_governance`             | AI Governance                    | ai_governance        | leadership      |
| `ai_evaluation_manager`     | AI Evaluation / AI Management    | ai_evaluation        | metrics         |

Two new detection profiles `product_manager`, `ai_governance` and
`ai_evaluation` will need to be added to `tailor/profiles.json` (and seed
JDs for the three new role targets — `product_manager`, `ai_governance`,
`ai_evaluation_manager`). Spec change only here; copy will come from
Philipp.

---

## 5. Geography suffixes (filenames)

| Header variant | Suffix | Example filename                                     |
|----------------|--------|------------------------------------------------------|
| germany        | `_G`   | `Eiselt_PortfolioManager_G_metrics.pdf`              |
| taiwan         | `_T`   | `Eiselt_PortfolioManager_T_metrics.pdf`              |
| vietnam        | `_V`   | `Eiselt_PortfolioManager_V_metrics.pdf`              |
| singapore      | `_S`   | `Eiselt_PortfolioManager_S_metrics.pdf`              |

Optional infixes, in this order if present: `_nophoto`, `_v2`.
Trailing variant tag is the BM25 reranking (`_metrics` / `_leadership` /
`_tooling`) and may be omitted in v2 once the variant is implicit per
role mask.

For tailored v2 PDFs that derive from a specific JD, the filename
appends a slug of the listing title and (optionally) a date stamp:

`Eiselt_PortfolioManager_G_Wavestone-Senior-S4HANA-PM_2026-05-12.pdf`

---

## 6. Analytics overlay (the recruiter-agent eye)

The right column of the editor renders these widgets, all live-updating.

### 6.1 Title-match badge

- Green check + "Title matches listing" when the headline (under the
  candidate name) equals the listing title (case-insensitive, hyphen
  / em-dash normalised).
- Yellow warning + "Headline differs" with a one-click "use listing
  title" button.

### 6.2 Coverage gauge

- Sweep 0 – 100 %. Bands:
  - 0 – 50 % red ("under-tailored")
  - 50 – 70 % amber
  - **70 – 80 % green ("target band")**
  - 80 – 90 % amber ("over-mirroring risk")
  - 90 – 100 % red ("keyword stuffing")
- The "keyword stuffing" upper band exists *because* of
  `WRITER_GUIDE.md` §"Anti-patterns": pushing past 80 % usually means
  the user is stuffing JD phrases verbatim. The gauge is the
  enforcement.

### 6.3 Missing-keywords list

- Top 5 keywords present in the JD but absent from the current CV.
- Ranked by impact: `freq_in_JD × weight_for_role_profile`.
- Hover shows where in the CV they'd fit best (which role's highlight
  pool has a match, or "no candidate — consider adding to master").
- Click jumps to that location.

### 6.4 ATS format checks (static)

- `.docx` parses most reliably (research §"Format rules").
- ✅ no tables / columns / text boxes (Typst output already clean).
- ✅ action verbs at bullet start (style guide enforced).
- ⚠️ over 2 pages (warn).
- ✅ plain-text round-trip survives (auto-run on each render —
  rendercv already produces markdown alongside PDF; diff against
  composition).

---

## 7. Free-typed bullets

The single biggest scope expansion over v1. Three rules:

1. **Truth check.** When the user types a new bullet, surface a soft
   prompt: "Can you back this up with a specific number or named
   project?" — research §"Use AI for the boring layer, not the
   high-stakes layer". This is a hint, not a block.
2. **No AI rewrite.** The page never sends typed text to an LLM. What
   the user typed is what gets rendered, verbatim. Same hard rule as
   `WRITER_GUIDE.md` §"No LLM keyword stuffing".
3. **Two save modes per new bullet:**
   - *Use here only* — bullet exists in the current composition's
     edits, not persisted.
   - *Save to master* — bullet appended to the appropriate section of
     `master sentences.md` (with provenance: source = "free-typed
     <date>"), then a corpus rebuild fires. Confirmation dialog warns
     this is a permanent master edit.

---

## 8. Editor layout (wireframe)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  CV Tailored  •  Wavestone  •  Senior PM S/4HANA Finance Transformation │
│  [paste new JD]  [load from /scored]                                    │
├──────────────────────────────────────────────┬──────────────────────────┤
│                                              │  ATS analytics           │
│  ┌─ Header ─────────────────────────────┐    │                          │
│  │ Headline: [Senior IT Project & PM] ✏ │    │  Title match:    ⚠       │
│  │ Geo:      [G][T][V][S]               │    │  Coverage:       72 %    │
│  │ Photo:    ☑ include                  │    │   ▰▰▰▰▰▰▰▰▱▱  green     │
│  └──────────────────────────────────────┘    │                          │
│                                              │  Missing keywords:       │
│  ┌─ Summary ────────────────────────────┐    │   • S/4HANA Finance      │
│  │ [picker] [free-type override]        │    │   • CIO transformation   │
│  └──────────────────────────────────────┘    │   • Wavestone consult.   │
│                                              │   • SAP FI / CO          │
│  ┌─ Core Competencies ──────────────────┐    │   • RAID + steering      │
│  │ • IT portfolio governance           ×│    │                          │
│  │ • ServiceNow / LeanIX               ×│    │  Format checks:          │
│  │ • + Add  |  + Type new               │    │   ✅ no columns          │
│  └──────────────────────────────────────┘    │   ✅ action verbs        │
│                                              │   ✅ ≤ 2 pages           │
│  ┌─ Experience ─────────────────────────┐    │   ✅ plain-text safe     │
│  │ AIXXEN Solo Founder    [drop ×]      │    │                          │
│  │   • bullet 1                      ×  │    │                          │
│  │   • bullet 2                      ×  │    │                          │
│  │   • + Add  |  + Type new             │    │                          │
│  │   …                                  │    │                          │
│  │ MAN Portfolio Manager   [drop ×]     │    │                          │
│  │   …                                  │    │                          │
│  └──────────────────────────────────────┘    │                          │
├──────────────────────────────────────────────┴──────────────────────────┤
│  [Render PDF]  [Render .docx (phase 2)]      [Last rendered: 30 s ago]  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 9. Component breakdown (React)

```
<App>
  <TopBar>  // JD input, listing metadata
  <Editor>
    <HeaderSection>
      <HeadlineEditor>
      <GeoPicker>
      <PhotoToggle>
    </HeaderSection>
    <SummarySection>
      <SummaryPicker>
      <FreeTypeBox>
    </SummarySection>
    <SkillsSection>
      <SkillList sortable>
      <AddCandidateMenu>
      <FreeTypeBox>
    </SkillsSection>
    <RolesSection>
      <RoleCard×N>
        <RoleHeader>
        <HighlightList sortable>
        <AddCandidateMenu>
        <FreeTypeBox>
      </RoleCard>
    </RolesSection>
  </Editor>
  <Analytics sticky-right>
    <TitleMatchBadge>
    <CoverageGauge>
    <MissingKeywordsList>
    <FormatChecks>
  </Analytics>
  <ExportBar sticky-bottom>
    <RenderPdfButton>
    <RenderDocxButton disabled-until-phase-2>
  </ExportBar>
</App>
```

Suggested stack: Vite + React + TypeScript + Tailwind. State managed in
component-local hooks (no Redux — composition state is single-tree). One
debounced effect (`useEffect`) drives the analytics overlay on any
state change.

---

## 10. API additions

The existing tailor engine covers ~80 % of v2. New endpoints needed:

| Endpoint                          | Method | Body                          | Returns                                              |
|-----------------------------------|--------|-------------------------------|------------------------------------------------------|
| `/api/jd_analyze`                 | POST   | `{jd_text}`                   | `{title, keywords[], top_role_mask, coverage_seed}`  |
| `/api/coverage`                   | POST   | `{jd_text, composition}`      | `{coverage_pct, missing[], present[]}`               |
| `/api/master/bullet`              | POST   | `{section, role_key?, text}`  | `{id, persisted: true}`                              |
| `/api/export_docx`                | POST   | same as `tailor_pdf_from_edits` | `{filename, url}` (phase 2)                        |

Existing endpoints (`/api/tailor_view_freeform`, `/api/header_variants`,
`/api/role_targets`, `/api/tailor_pdf_from_edits`, `/api/tailored`)
remain unchanged and continue to back both v1 and v2.

---

## 11. ATS format rules baked in

From research §"Format Rules That Still Matter", these are enforced by
the engine (not user-toggleable):

- No tables in CV body. (Typst layout uses flow text — already
  compliant.)
- No text boxes / columns / headers-footers carrying key info. (Same.)
- No graphics except the optional headshot.
- Plain-text round-trip preserves order and content. (Rendercv markdown
  output is auto-checked on each render; mismatches surface in the
  Format checks panel.)
- Output as both PDF (today) and `.docx` (phase 2). `.docx` parses most
  reliably in 2026.
- Professional summary, not "objective".
- Action verbs at bullet start.
- ≤ 2 pages for senior profiles (Philipp's case).

---

## 12. What stays out of v2

Locking the perimeter so the build is tractable:

- **Job scraping.** v2 takes a pasted JD or a scored-job id; it does
  not crawl. (Existing dashboard at `/` is the scraper.)
- **LLM rewriting of any field.** Hard rule. The page never sends text
  to a remote LLM. Only the local BM25 retrieval engine runs.
- **Cover-letter generation.** Separate concern.
- **Multi-user / accounts / sharing.** Single-user local tool.
- **Mobile.** Desktop-only.
- **Auto-apply.** Manual hit-submit is the boundary.
- **Non-IT roles.** Out of scope.

---

## 13. Phase plan

Each phase is independently shippable. Phase 0 is what's running now.

| Phase | Scope                                                                                   | Status  |
|-------|-----------------------------------------------------------------------------------------|---------|
| 0     | Engine + HTML dashboard + library + editable paste + photo toggle + 2-line header       | shipped |
| 0.5   | Add 3 new role masks (`product_manager`, `ai_governance`, `ai_evaluation_manager`) + seed JDs to `profiles.json` | next    |
| 1     | Extend existing `/paste` page with coverage gauge, title-match badge, missing-kw list   | dev     |
| 2     | React rebuild of v2 as a new `/tailor` page with the layout in §8                       | dev     |
| 3     | `.docx` export (rendercv markdown → pandoc → docx, or python-docx direct write)         | dev     |
| 4     | Free-typed bullets with both *use-here-only* and *save-to-master* modes                 | dev     |
| 5     | Keyword-graph view: how each JD keyword maps to corpus tags                             | future  |

Phase 0.5 is a 30-minute job for the engine; the dev team doesn't
touch it. Phases 1 – 4 are React + Python work.

---

## 14. Decision points for Philipp before dev starts

The recruiter agent flags these as the points that need a human call,
not a code decision:

1. **`.docx` urgency.** Research says `.docx` parses most reliably in
   2026. Promote it from Phase 3 to Phase 1?
2. **Default save behaviour for free-typed bullets.** *Use here only*
   keeps master clean. *Save to master* compounds over time. Pick one.
3. **JD source.** Paste-only, or also auto-detect when arriving from a
   scored job click on `/`?
4. **Listing-title editing.** Should the title-match enforcement edit
   *Philipp's actual position titles* in his history, or only the
   *headline* under his name? (`WRITER_GUIDE.md` §"The 2-minute loop"
   says headline only — confirm.)
5. **Phase 0.5 role names — exact label wording for the three new
   role masks** (Product Manager, AI Governance, AI
   Evaluation/Management). The role labels are filename-stable
   identifiers; they need Philipp's wording.

---

## 15. References

- [`WRITER_GUIDE.md`](WRITER_GUIDE.md) — editorial rules. Authoritative
  for any conflict between this spec and "what the agent should write".
- 2026 ATS research (Jobscan State of the Job Search 2025, Fortune 500
  ATS audit) — embedded in §1 and §11 above.
- The Career-Coach 2-minute loop video — encoded in
  `WRITER_GUIDE.md` §"The 2-minute tailoring loop".
- Existing engine entry points: `/library` (v1),
  `/paste` (current tailored), `/` (scraper).
