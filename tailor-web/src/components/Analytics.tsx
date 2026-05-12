// Right sidebar: title-match badge, coverage gauge, missing/present
// skill pills, closest role-mask hint. Wireframe: SPEC_v2_tailored.md §6.

import type { Coverage, JdAnalysis } from "../types";

type Props = {
  analysis: JdAnalysis | null;
  coverage: Coverage | null;
  titleInput: string;
  onCopyTitleToInput: () => void;
};

export function Analytics({ analysis, coverage, titleInput, onCopyTitleToInput }: Props) {
  const titleMatch = computeTitleMatch(analysis?.title_hint ?? "", titleInput);
  const band = coverageBand(coverage?.coverage_pct ?? 0);
  return (
    <aside className="bg-purple-50 border border-purple-100 rounded-lg p-4 sticky top-4 self-start text-xs">
      <h4 className="uppercase tracking-wide text-purple-700 font-semibold mb-2">ATS analytics</h4>

      <div className="flex justify-between items-center mb-2">
        <span>Title match</span>
        <span className={`px-2 py-0.5 rounded-full font-medium ${titleMatch.cls}`}>{titleMatch.label}</span>
      </div>
      {analysis?.title_hint && (
        <div className="text-[11px] text-gray-600 mb-2">
          JD: <strong>{analysis.title_hint}</strong>{" "}
          {!titleInput && (
            <button className="ml-1 bg-purple-600 text-white rounded px-1.5 py-0.5 text-[10px]" onClick={onCopyTitleToInput}>copy</button>
          )}
        </div>
      )}

      <h4 className="uppercase tracking-wide text-purple-700 font-semibold mt-3 mb-1">Coverage</h4>
      <div className="text-sm font-semibold">
        {coverage ? `${coverage.coverage_pct.toFixed(0)}%` : "—"}
        <span className="text-[11px] font-normal text-gray-500 ml-2">
          {coverage ? `(${coverage.present.length}/${coverage.jd_skills.length})` : ""}
        </span>
      </div>
      <div className="h-2 bg-purple-100 rounded overflow-hidden my-1">
        <div className={`h-full ${band.bg}`} style={{ width: `${Math.min(100, coverage?.coverage_pct ?? 0)}%` }} />
      </div>
      <p className="text-[10px] text-gray-500 mb-2">Target band 70–80 %. Over 80 % risks keyword stuffing.</p>

      <h4 className="uppercase tracking-wide text-purple-700 font-semibold mt-3 mb-1">Missing JD skills</h4>
      <div className="flex flex-wrap gap-1">
        {(coverage?.missing ?? []).slice(0, 10).map((s) => (
          <span key={s} className="bg-red-100 text-red-700 px-2 py-0.5 rounded text-[11px]">{s}</span>
        ))}
        {!coverage?.missing?.length && <em className="text-gray-500">none — every JD skill is in your CV</em>}
      </div>

      <h4 className="uppercase tracking-wide text-purple-700 font-semibold mt-3 mb-1">Already covered</h4>
      <div className="flex flex-wrap gap-1">
        {(coverage?.present ?? []).map((s) => (
          <span key={s} className="bg-green-100 text-green-700 px-2 py-0.5 rounded text-[11px]">{s}</span>
        ))}
      </div>

      <h4 className="uppercase tracking-wide text-purple-700 font-semibold mt-3 mb-1">Closest role mask</h4>
      <div className="text-gray-700">
        {analysis?.top_role_target_label ?? "—"}
        {analysis?.top_role_target && <span className="text-gray-400"> ({analysis.top_role_target})</span>}
      </div>
    </aside>
  );
}

function computeTitleMatch(hint: string, input: string) {
  const h = hint.trim().toLowerCase();
  const i = input.trim().toLowerCase();
  if (!h) return { cls: "bg-gray-200 text-gray-600", label: "no JD title" };
  if (!i) return { cls: "bg-yellow-100 text-yellow-700", label: "no input" };
  return h.includes(i) || i.includes(h)
    ? { cls: "bg-green-100 text-green-700", label: "matches" }
    : { cls: "bg-yellow-100 text-yellow-700", label: "differs" };
}

function coverageBand(pct: number) {
  if (pct < 50) return { bg: "bg-red-500" };
  if (pct < 70) return { bg: "bg-yellow-500" };
  if (pct <= 80) return { bg: "bg-green-500" };
  if (pct <= 90) return { bg: "bg-yellow-500" };
  return { bg: "bg-red-500" };
}
