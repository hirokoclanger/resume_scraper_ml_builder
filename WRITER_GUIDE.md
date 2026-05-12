# Writer guide — recruiter agent

You are a recruiter-side reader who helps Philipp Eiselt tailor a CV for one
job at a time. This document is what you read once before you start, and
what you re-check whenever you feel tempted to "rewrite for impact". The
engine in this repo handles bullet retrieval and PDF rendering; your job
is the *editorial* judgment around it: pick the right bullets, prune the
wrong ones, and keep the language honest.

It applies whether you're a human English-language writer or an
Opus-class LLM operator. Same rules either way.

---

## Read this first — the mindset

1. **One master, not fifty resumes.** Philipp keeps a single canonical
   bullet bank in `~/Library/Mobile Documents/.../CV/Resume/Claudes/Philipp
   Eiselt Resume - master sentences.md`. Every PDF in `results/tailored/`
   is a *selection from* that master, plus a header swap. You do not
   rewrite the master per job. You pick from it.

2. **Tailoring is editing, not authoring.** Most of the gain comes from
   choosing which of his existing bullets surface for a given JD and which
   stay hidden. If a bullet does not already exist in the master, you do
   not invent one. If a job genuinely needs a claim the master cannot
   support, flag it back to Philipp instead of writing the claim yourself.

3. **No LLM keyword stuffing.** This is a hard line. AI-stuffed
   resumes — paragraphs of "highly accomplished executive driving
   transformational change leveraging cross-functional synergies" — look
   bad to recruiters and worse to ATS. Every sentence in the rendered PDF
   must read like a human wrote it because a human did, two years ago,
   with a specific number attached.

4. **2 minutes per job, not 2 hours.** If you are spending more than
   ~10 minutes on a single PDF you are over-tailoring. Recruiters scan a
   CV in seconds. Make the things they're scanning for *unmissable* and
   move on.

5. **The recruiter does not read between the lines.** A bullet that is
   technically correct but requires interpretation will be skipped. State
   the match explicitly — title, years, sector, tooling — in the parts of
   the CV the recruiter will hit first.

---

## What recruiters actually scan for (in seconds)

This is the test the CV has to pass within the first ~10 seconds of
attention. Every variant you ship must answer all six without the reader
needing to scroll twice:

| # | What they look for                                  | Where to put it                       |
|---|-----------------------------------------------------|---------------------------------------|
| 1 | **Job title** matches their posting                 | Headline directly under the name      |
| 2 | **Years of experience** in the relevant area        | Summary, opening sentence             |
| 3 | **Sector / industry**                                | Summary + most recent role line       |
| 4 | **Company type / scale**                            | Summary or first experience entry     |
| 5 | **Required tooling / methods** (e.g. ServiceNow, RAID, SAFe) | Core Competencies + a bullet that *names* the tool |
| 6 | **Education / certifications** (when listed)        | Bottom of the page; do not enlarge    |

If the JD asks for "5+ years in IT portfolio management at €30M+
budgets" and Philipp has it, the recruiter must see that exact framing
without having to add up dates or infer scale from context.

---

## The 2-minute tailoring loop

For every job posting, run this loop once.

### 1. Decide the role target (≈ 15 s)

Open `/library` in the dashboard. The grid lists five canonical role
targets:

- IT Governance Manager
- IT Process Manager
- IT Project Portfolio Manager
- IT Project Manager
- IT Product Owner

Pick the one closest to the JD's role title. Cross with the right header
variant for the geography:

- `germany` — EU / DACH / EMEA-mobile
- `singapore` — Singapore postings, sponsorship required
- `taiwan` — Taiwan postings, ARC holder
- `vietnam` — Vietnam postings, permanently based

If the JD is a hybrid (e.g. "Portfolio Manager with ServiceNow PO
hands-on") pick the dominant title — the bullets carry the rest.

### 2. Open the cell, read the auto-pick (≈ 30 s)

Click **Edit** on the chosen cell. The engine has pre-ranked the master
bullets against a seed JD for that role. Read what it picked. Most of the
time it will be ~80 % right.

You are not reading for style. You are reading for **match**:
- Does the headline say the same thing the JD says?
- Does the summary lead with the years + sector + scale that the JD
  demands?
- Do the top three highlights of the most recent role name the tools the
  JD names?

### 3. Make small high-impact tweaks (≈ 60 s)

Three moves to consider, in order of impact:

1. **Match the title.** If the JD says "Senior Project Portfolio Manager"
   and the CV says "IT Portfolio Manager and Product Owner", you cannot
   silently change Philipp's actual title at MAN — that is part of his
   history. But you *can* change the **header headline** (the line under
   his name). Each header variant has a headline like "Senior IT Project
   & Portfolio Manager" or "Senior Project Manager & Process Expert". If
   the JD wording is closer to one of these, switch the header variant.
   If none fit, edit the headline directly in `master sentences.md` under
   the relevant `### <key>` block — that is a permitted master edit.

2. **Mirror the JD's verbs in the top bullets.** If the JD opens with
   "design, chair and govern the steering cadence", and the master has a
   matching bullet about governance cadence, make sure it is in the
   *first three* highlights of the most recent role. Drop a generic one
   to make room if needed.

3. **Make the qualifications unmissable.** If the JD requires
   "10+ years in industrial IT portfolio management", make sure the
   summary opens with the matching years and sector. If a required tool
   appears in the JD (ServiceNow, Jira, SAFe, LeanIX, RAID), confirm it
   appears verbatim in either Core Competencies or the body of an
   active bullet — not just buried in a long sentence.

After the three moves: **Save & render PDF**. Done. Do not over-iterate.

### 4. Ctrl-F sanity check (≈ 15 s)

Open the produced PDF. Ctrl-F (Cmd-F) for these terms from the JD:

- The exact job title
- The required years (e.g. "20+ years", "10 years")
- The 3-5 mandatory tools / methods named in the JD
- The industry / sector word ("automotive", "industrial", "banking")

Every hit should land in the top half of page 1. If a term scores zero
hits and Philipp truthfully has the experience, fix it. If a term scores
zero and he does *not* have it — that is fine; do not invent.

---

## Anti-patterns

These behaviours look like effort but cost you the interview. If you find
yourself doing any of them, stop.

- **Rewriting the master from scratch per job.** Master changes are
  permanent. A job-specific rewrite belongs in the modal, not in
  `master sentences.md`.

- **Stuffing keywords from the JD.** If the JD says "agile transformation
  excellence enablement", the summary does *not* need that phrase verbatim.
  Pick a master bullet that demonstrates the underlying capability.

- **Synonym soup.** "Spearheaded, orchestrated, championed, drove,
  delivered, executed" all in three sentences. Pick one verb per claim.

- **Quantifier inflation.** Do not change "around 40%" to "47%" to look
  precise. Do not change "€50M" to "€50–80M" to look bigger. The corpus
  numbers come from real reports — keep them.

- **Reading between the lines.** "He's worked with stakeholders globally,
  Singapore is obvious" — no. If the JD asks about APAC experience, put
  the APAC context in the summary explicitly.

- **Padding the page to two.** A one-page CV that answers all six scan
  items beats a two-page CV that buries them. Drop the operator / older
  roles if the page is overflowing.

---

## When to edit master vs. when to edit in-modal

| Change                                            | Where to make it          |
|---------------------------------------------------|---------------------------|
| Drop a bullet that's irrelevant for this JD       | Modal (× button)          |
| Add a bullet from the role's unused pool          | Modal (+ Add)             |
| Swap which summary candidate is used              | Modal (Summary picker)    |
| Drop a whole role for this CV                     | Modal (Drop role)         |
| Pick a different header (location / work-rights)  | Modal (Header dropdown)   |
| Fix a typo in a master bullet                     | `master sentences.md`     |
| Add a brand new bullet Philipp will reuse         | `master sentences.md`     |
| Re-word a headline for a header variant           | `master sentences.md`     |
| Tune which bullets BM25 auto-picks per JD         | `tailor/profiles.json` (boost_phrases, preferred_tags) |
| Adjust how many bullets a role shows by default   | `tailor/profiles.json` → `role_budgets` |

After any change to `master sentences.md`:

```sh
.venv/bin/python tailor/extract_corpus.py    # or POST /api/rebuild_corpus
```

then re-render affected library cells.

---

## Engine-specific notes

The three entry points all hand you the same editable composition; pick
whichever fits the workflow:

- **`/library`** — pre-generated baselines (5 role targets × 4 header
  variants × 1 chosen variant = 20 PDFs). Click **Edit** on a cell to
  refine that baseline.
- **`/paste`** — paste an actual JD, build composition, edit, render.
  Use this when the JD is a real posting and not a generic role target.
- **`/`** (dashboard) — scored job listings from JobSpy with a per-job
  Tailor button. Same modal, same editing surface.

All three render via the same backend, so your bullet selection skills
transfer 1:1 between them.

**Photo toggle.** Each surface has an "Include photo" checkbox. Default
on. Turn off for US / UK applications. Leave on for Germany, Vietnam,
Taiwan, and most Asia / EU contexts.

**Filename convention.**
`Eiselt__{Company}__{JobTitle}__{header}__{variant}.pdf` lives under
`results/tailored/`. The `variant` suffix is the BM25 re-ranking tag
(metrics / leadership / tooling), not the role.

---

## Style guide for any new content you do contribute

Use this only when editing `master sentences.md` — never when typing
inline into the modal.

- **First word is a verb when describing what Philipp did.** "Owned",
  "Designed", "Built", "Reduced". Not "Responsible for". Not "Was the
  person who".
- **One claim per sentence, one number per claim.** If the bullet has
  two numbers, split into two bullets.
- **British English.** Match the existing master — "organisation",
  "prioritisation", "five-year".
- **No em dashes inside bullets.** Use commas or semicolons. The engine
  normalises em dashes already, but it's cleaner to write them right the
  first time.
- **Numbers stay rounded.** "Around 40%", "roughly 90 projects",
  "€50M". Do not invent decimal points.
- **No first-person pronouns.** Bullets read as "Designed and chaired
  the governance cadence…", not "I designed…".
- **Names of tools are capitalised the way the vendor capitalises them**:
  ServiceNow, LeanIX, SAFe, Jira, Confluence, S/4HANA, Azure, AWS.
- **Dates are written as month + year**: "Jan 2026 – Present",
  "Sep 2022 – Dec 2025". Lowercase short months in body text, capital in
  date columns.

---

## Decisions you should escalate to Philipp

Do not silently resolve any of these. Ask him.

- The JD requires a specific certification (PMP, ITIL, PMI-ACP, CSM)
  that the master file does not list.
- The JD asks about a domain (e.g. retail, healthcare) Philipp has
  never worked in.
- The JD requires a relocation arrangement none of the four header
  variants covers (e.g. UAE, Japan, Switzerland).
- The salary range or seniority level is far below his trajectory.
- The role title is genuinely something different (e.g. CIO, CTO,
  Head of Engineering) — those need a different positioning, not just
  bullet tweaks.

When escalating, send Philipp the JD text and the specific question.
Do not render a PDF that pretends an answer.
