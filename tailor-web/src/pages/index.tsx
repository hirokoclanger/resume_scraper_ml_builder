/**
 * v2 Tailored CV editor — entry page.
 *
 * Layout: top form (JD textarea, company, title, header variant) →
 *         two-column body (editor + analytics) → bottom export row.
 *
 * This is the React rebuild of `/paste` (job-finder/paste.html). All
 * editorial logic — what to surface, what to discourage, when to escalate
 * — lives in WRITER_GUIDE.md and the 2026 research file at the repo root.
 * Components below only render and dispatch; they do not encode product
 * judgment beyond the wireframe in SPEC_v2_tailored.md §8.
 */
import { useEffect, useState } from "react";
import { JdInput } from "../components/JdInput";
import { Editor } from "../components/Editor";
import { Analytics } from "../components/Analytics";
import { ExportBar } from "../components/ExportBar";
import {
  buildView, analyzeJd, refreshCoverage, fetchHeaderVariants,
  renderPdf, renderDocx,
} from "../api";
import type { View, Edits, Coverage, JdAnalysis, HeaderVariant } from "../types";

export default function Home() {
  const [jd, setJd] = useState("");
  const [company, setCompany] = useState("");
  const [title, setTitle] = useState("");
  const [view, setView] = useState<View | null>(null);
  const [edits, setEdits] = useState<Edits | null>(null);
  const [analysis, setAnalysis] = useState<JdAnalysis | null>(null);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [headerVariants, setHeaderVariants] = useState<Record<string, HeaderVariant>>({});
  const [defaultHeaderKey, setDefaultHeaderKey] = useState("germany");
  const [busy, setBusy] = useState(false);
  const [lastRender, setLastRender] = useState<string | null>(null);

  // Load header variants on first paint.
  useEffect(() => {
    fetchHeaderVariants().then((r) => {
      setHeaderVariants(r.variants as Record<string, HeaderVariant>);
      setDefaultHeaderKey(r.default ?? "germany");
    }).catch(() => { /* ignore */ });
  }, []);

  async function handleBuild() {
    if (jd.trim().length < 20) return;
    setBusy(true);
    try {
      const [v, a] = await Promise.all([
        buildView(jd, { variant: "leadership", company, title }),
        analyzeJd(jd),
      ]);
      setView(v);
      setAnalysis(a);
      setEdits(editsFromView(v, defaultHeaderKey));
    } finally {
      setBusy(false);
    }
  }

  // Debounced coverage refresh on every edit.
  useEffect(() => {
    if (!view || !edits || !jd) return;
    const handle = setTimeout(async () => {
      try {
        const c = await refreshCoverage(jd, compositionTexts(view, edits));
        setCoverage(c);
      } catch { /* offline-safe */ }
    }, 200);
    return () => clearTimeout(handle);
  }, [edits, view, jd]);

  async function handleRender(fmt: "pdf" | "docx", variant: string) {
    if (!edits) return;
    setBusy(true);
    setLastRender(null);
    try {
      const fn = fmt === "docx" ? renderDocx : renderPdf;
      const r = await fn({
        company: company || "Unknown",
        title: title || "Role",
        variant,
        include_photo: edits.include_photo,
        edits,
      });
      setLastRender(r.filename);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-7xl p-6">
      <header className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Tailor CV — v2</h1>
          <p className="text-sm text-gray-500">Per-JD editor · pure local retrieval · no LLM rewriting</p>
        </div>
        <nav className="flex gap-3 text-sm">
          <a href="/library" className="text-purple-700 underline">Library</a>
          <a href="/paste" className="text-purple-700 underline">Legacy /paste</a>
        </nav>
      </header>

      <JdInput
        jd={jd} setJd={setJd}
        company={company} setCompany={setCompany}
        title={title} setTitle={setTitle}
        onBuild={handleBuild}
        busy={busy}
      />

      {view && edits && (
        <div className="grid grid-cols-1 md:grid-cols-[1fr_300px] gap-4 mt-6 items-start">
          <Editor
            view={view}
            edits={edits}
            setEdits={setEdits}
            headerVariants={headerVariants}
            onCustomBulletSaved={async () => {
              // Refresh the view so freshly saved master bullets show in unpicked pools.
              const v = await buildView(jd, { variant: view.variant, company, title });
              setView(v);
            }}
          />
          <Analytics
            analysis={analysis}
            coverage={coverage}
            titleInput={title}
            onCopyTitleToInput={() => analysis?.title_hint && setTitle(analysis.title_hint)}
          />
        </div>
      )}

      {view && edits && (
        <ExportBar
          busy={busy}
          onRender={handleRender}
          lastRender={lastRender}
        />
      )}
    </main>
  );
}

// ---- helpers ----

function editsFromView(view: View, defaultHeaderKey: string): Edits {
  return {
    profile: view.profile,
    profile_label: view.profile_label,
    header_key: view.default_header_key || defaultHeaderKey,
    include_photo: true,
    summary_id: view.summary.picked[0]?.id ?? null,
    skill_ids: view.skills.picked.map((b) => b.id),
    custom_skills: [],
    roles: view.roles.map((r) => ({
      key: r.key,
      highlight_ids: r.highlights_picked.map((b) => b.id),
      custom_highlights: [],
    })),
  };
}

function compositionTexts(view: View, edits: Edits) {
  const lookup = (id: string, pool: { id: string; text: string }[]) =>
    pool.find((b) => b.id === id)?.text ?? "";
  const summaryPool = [...view.summary.picked, ...view.summary.unpicked];
  const skillsPool = [...view.skills.picked, ...view.skills.unpicked];
  return {
    summary: edits.summary_id ? lookup(edits.summary_id, summaryPool) : "",
    skills: edits.skill_ids.map((id) => {
      const corp = lookup(id, skillsPool);
      if (corp) return corp;
      return (edits.custom_skills ?? []).find((b) => b.id === id)?.text ?? "";
    }).filter(Boolean),
    roles: edits.roles.map((re) => {
      const rv = view.roles.find((r) => r.key === re.key);
      const hlPool = rv ? [...rv.highlights_picked, ...rv.highlights_unpicked] : [];
      return {
        position: rv?.position ?? "",
        company: rv?.company ?? "",
        highlights: re.highlight_ids.map((id) => {
          const corp = lookup(id, hlPool);
          if (corp) return corp;
          return (re.custom_highlights ?? []).find((b) => b.id === id)?.text ?? "";
        }).filter(Boolean),
      };
    }),
  };
}
