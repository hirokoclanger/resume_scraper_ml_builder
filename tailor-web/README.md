# tailor-web — Next.js v2 editor

React rebuild of `/paste`, anchored to
[`SPEC_v2_tailored.md`](../SPEC_v2_tailored.md) and the editorial rules in
[`WRITER_GUIDE.md`](../WRITER_GUIDE.md). The Python server in the repo
root powers every endpoint this app consumes — there is no logic
duplicated here, only the UI.

## Run locally

```sh
cd tailor-web
npm install
npm run dev    # http://localhost:3000
```

In a separate terminal, keep the Python server running on the default
port:

```sh
cd ..
python3 server.py   # http://localhost:8765 (bootstraps through .venv)
```

`next.config.js` proxies every `/api/*` call from this Next.js app to the
Python server, so the front-end never talks to a different origin.

## What this app implements

All four v2 phases from the spec are wired:

| Spec § | Feature | Lives in |
|---|---|---|
| §2.1, §6.1 | Title-match badge | `components/Analytics.tsx` |
| §2.2, §6.2 | Coverage gauge | `components/Analytics.tsx` |
| §2.3, §6.3 | Missing-keyword list | `components/Analytics.tsx` |
| §2.4 | In-page editing | `components/Editor.tsx` |
| §2.5, §7 | Free-typed bullets (use-here / save-to-master) | `components/Editor.tsx` FreeTypeRow |
| §2.6 | Header geography swap | `components/Editor.tsx` |
| §2.7 | Photo toggle | `components/Editor.tsx` |
| §2.8 | PDF + `.docx` export | `components/ExportBar.tsx` |

## File layout

```
tailor-web/
├── package.json                # Next.js 15 / React 19 / Tailwind 4
├── next.config.js              # /api/* proxy → http://localhost:8765
├── tsconfig.json
├── postcss.config.js
└── src/
    ├── api.ts                  # typed wrappers over every Python endpoint
    ├── types.ts                # View, Edits, Coverage, JdAnalysis types
    ├── styles.css              # Tailwind entry + a few CSS vars
    ├── pages/
    │   ├── _app.tsx
    │   └── index.tsx           # the editor page
    └── components/
        ├── JdInput.tsx         # top form: company, title, JD textarea
        ├── Editor.tsx          # editable composition (header + summary + skills + roles)
        ├── Analytics.tsx       # sticky right panel: ATS gauge + missing skills
        └── ExportBar.tsx       # bottom: PDF variants + .docx export
```

## What's intentionally not here

- No retrieval logic — every bullet ranking decision lives in the Python
  engine (`tailor/retrieval.py`).
- No skill registry — single source of truth is `tailor/skills.py`.
- No PDF / docx rendering — both are server-side
  (`tailor/render_pdf.py`, `tailor/render_docx.py`).
- No editorial rules — those live in `WRITER_GUIDE.md` and are
  consulted by the human / agent operating the page, not enforced in
  JS.
- No authentication — single-user local tool.
- No scraping — that's `/` in the existing dashboard.

## Things the dev team should validate before shipping

1. **Tailwind v4** is new (Dec 2024) and changed the postcss plugin
   surface; the `@tailwindcss/postcss` package replaces the v3
   `tailwindcss` PostCSS plugin. If `npm install` complains, drop to
   Tailwind v3 (`tailwindcss@^3.4.0`, plain `tailwindcss` plugin in
   postcss config).
2. **Coverage debounce** is currently 200 ms. If the page feels laggy
   on large JDs, raise it.
3. **Custom-bullet "Use here only" ids** are timestamp-based. They
   collide if the user adds two bullets in the same millisecond. Swap
   to `crypto.randomUUID()` if production-grade.
4. **Photo toggle default** is true. Per the writer guide, US/UK
   geographies should default to false — wire that to the header_key.
5. **Title-match enforcement scope** (spec §13.5 decision 4) allows
   editing position-title strings in history, but this UI currently only
   exposes the *header headline* via the geography variant. Add a
   per-role "edit position title" button if Philipp confirms he wants
   that surface.
