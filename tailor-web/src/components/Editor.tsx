// Editable composition view — mirrors paste.html's left column.
// State lives in the parent (index.tsx); this component dispatches edits.

import { useState } from "react";
import type { View, Edits, HeaderVariant } from "../types";
import { saveMasterBullet } from "../api";

type Props = {
  view: View;
  edits: Edits;
  setEdits: (e: Edits) => void;
  headerVariants: Record<string, HeaderVariant>;
  onCustomBulletSaved: () => Promise<void>;
};

export function Editor({ view, edits, setEdits, headerVariants, onCustomBulletSaved }: Props) {
  const activeHeader = headerVariants[edits.header_key] ?? view.header;
  const summaryPool = [...view.summary.picked, ...view.summary.unpicked];
  const currentSummary = summaryPool.find((b) => b.id === edits.summary_id);
  const skillsAll = [...view.skills.picked, ...view.skills.unpicked];
  const pickedSkillIds = new Set(edits.skill_ids);
  const pickedSkills = edits.skill_ids
    .map((id) => skillsAll.find((b) => b.id === id) ?? (edits.custom_skills ?? []).find((b) => b.id === id))
    .filter(Boolean) as { id: string; text: string }[];
  const unpickedSkills = skillsAll.filter((b) => !pickedSkillIds.has(b.id));

  return (
    <div className="bg-white rounded-lg border p-4 space-y-4">
      {/* Header / geography */}
      <section className="bg-purple-50 border border-purple-100 rounded p-3 text-sm">
        <div className="flex flex-wrap items-center gap-3">
          <strong className="text-purple-700">Header variant:</strong>
          <select
            className="px-2 py-1 text-xs border rounded bg-white"
            value={edits.header_key}
            onChange={(e) => setEdits({ ...edits, header_key: e.target.value })}
          >
            {Object.keys(headerVariants).map((k) => (
              <option key={k} value={k}>{k}</option>
            ))}
          </select>
          <label className="flex items-center gap-1 text-xs">
            <input
              type="checkbox"
              checked={edits.include_photo}
              onChange={(e) => setEdits({ ...edits, include_photo: e.target.checked })}
            />
            Include photo
          </label>
        </div>
        <div className="text-xs text-gray-600 mt-2">
          {activeHeader?.headline}<br/>{activeHeader?.location}
        </div>
      </section>

      {/* Summary */}
      <SectionTitle>Summary</SectionTitle>
      <div className="bg-gray-50 border rounded p-3 text-sm">
        <div className="mb-2">{currentSummary?.text ?? <em className="text-gray-400">No summary picked.</em>}</div>
        {summaryPool.length > 1 && (
          <select
            className="text-xs border rounded p-1 w-full max-w-md"
            value={edits.summary_id ?? ""}
            onChange={(e) => setEdits({ ...edits, summary_id: e.target.value || null })}
          >
            <option value="">— pick summary —</option>
            {summaryPool.map((b) => (
              <option key={b.id} value={b.id}>{b.text.slice(0, 80)}…</option>
            ))}
          </select>
        )}
      </div>

      {/* Skills */}
      <SectionTitle>Core Competencies ({pickedSkills.length})</SectionTitle>
      <BulletList
        items={pickedSkills}
        onRemove={(id) => setEdits({ ...edits, skill_ids: edits.skill_ids.filter((x) => x !== id) })}
      />
      <AddRow
        unpicked={unpickedSkills}
        placeholder="+ Add skill candidate…"
        onAdd={(id) => setEdits({ ...edits, skill_ids: [...edits.skill_ids, id] })}
      />
      <FreeTypeRow
        placeholder="+ Type a new skill / bullet…"
        onUseHere={(text) => {
          const id = `custom-skl-${Date.now()}`;
          setEdits({
            ...edits,
            skill_ids: [...edits.skill_ids, id],
            custom_skills: [...(edits.custom_skills ?? []), { id, text }],
          });
        }}
        onSaveToMaster={async (text) => {
          const r = await saveMasterBullet({ section: "skills", text });
          if (r.id) {
            setEdits({ ...edits, skill_ids: [...edits.skill_ids, r.id] });
            await onCustomBulletSaved();
          }
        }}
      />

      {/* Roles */}
      <SectionTitle>Experience</SectionTitle>
      {view.roles.map((rv) => {
        const re = edits.roles.find((r) => r.key === rv.key);
        const removed = !re;
        const allHl = [...rv.highlights_picked, ...rv.highlights_unpicked];
        const pickedIds = new Set(re?.highlight_ids ?? []);
        const pickedBullets = (re?.highlight_ids ?? [])
          .map((id) => allHl.find((b) => b.id === id) ?? (re?.custom_highlights ?? []).find((b) => b.id === id))
          .filter(Boolean) as { id: string; text: string }[];
        const unpicked = allHl.filter((b) => !pickedIds.has(b.id));

        return (
          <div key={rv.key} className={`border rounded p-3 ${removed ? "opacity-50 bg-gray-50" : ""}`}>
            <div className="flex justify-between items-start gap-2 mb-2">
              <div className="text-sm">
                <strong>{rv.position}</strong>
                <div className="text-xs text-gray-500">{rv.company} · {rv.start_date} – {rv.end_date}</div>
              </div>
              {removed ? (
                <button
                  className="text-xs px-2 py-1 border rounded"
                  onClick={() => {
                    setEdits({
                      ...edits,
                      roles: [...edits.roles, {
                        key: rv.key,
                        highlight_ids: rv.highlights_picked.map((b) => b.id),
                        custom_highlights: [],
                      }].sort((a, b) => {
                        const order = view.roles.map((r) => r.key);
                        return order.indexOf(a.key) - order.indexOf(b.key);
                      }),
                    });
                  }}
                >Restore role</button>
              ) : (
                <button
                  className="text-xs px-2 py-1 border border-red-200 text-red-600 rounded"
                  onClick={() => setEdits({ ...edits, roles: edits.roles.filter((r) => r.key !== rv.key) })}
                >Drop role</button>
              )}
            </div>
            {!removed && (
              <>
                <BulletList
                  items={pickedBullets}
                  onRemove={(id) => setEdits({
                    ...edits,
                    roles: edits.roles.map((r) =>
                      r.key === rv.key ? { ...r, highlight_ids: r.highlight_ids.filter((x) => x !== id) } : r),
                  })}
                />
                <AddRow
                  unpicked={unpicked}
                  placeholder="+ Add bullet from this role's pool…"
                  onAdd={(id) => setEdits({
                    ...edits,
                    roles: edits.roles.map((r) =>
                      r.key === rv.key ? { ...r, highlight_ids: [...r.highlight_ids, id] } : r),
                  })}
                />
                <FreeTypeRow
                  placeholder="+ Type a new bullet for this role…"
                  onUseHere={(text) => {
                    const id = `custom-${rv.key}-${Date.now()}`;
                    setEdits({
                      ...edits,
                      roles: edits.roles.map((r) =>
                        r.key === rv.key ? {
                          ...r,
                          highlight_ids: [...r.highlight_ids, id],
                          custom_highlights: [...(r.custom_highlights ?? []), { id, text }],
                        } : r),
                    });
                  }}
                  onSaveToMaster={async (text) => {
                    const r2 = await saveMasterBullet({ section: "role", role_key: rv.key, text });
                    if (r2.id) {
                      setEdits({
                        ...edits,
                        roles: edits.roles.map((r) =>
                          r.key === rv.key ? { ...r, highlight_ids: [...r.highlight_ids, r2.id!] } : r),
                      });
                      await onCustomBulletSaved();
                    }
                  }}
                />
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-xs uppercase tracking-wide text-purple-700 border-b border-purple-100 pb-1 pt-2 font-semibold">{children}</h3>
  );
}

function BulletList({ items, onRemove }: { items: { id: string; text: string }[]; onRemove: (id: string) => void }) {
  if (!items.length) return <p className="text-xs italic text-gray-400">none</p>;
  return (
    <ul className="space-y-1">
      {items.map((b) => (
        <li key={b.id} className="flex items-start gap-2 group text-sm">
          <span className="flex-1">{b.text}</span>
          <button className="text-red-600 hover:bg-red-50 px-2 rounded opacity-0 group-hover:opacity-100" onClick={() => onRemove(b.id)}>×</button>
        </li>
      ))}
    </ul>
  );
}

function AddRow({ unpicked, placeholder, onAdd }: { unpicked: { id: string; text: string }[]; placeholder: string; onAdd: (id: string) => void }) {
  const [val, setVal] = useState("");
  if (!unpicked.length) return null;
  return (
    <div className="flex gap-2 items-center text-xs mt-1">
      <select className="flex-1 border rounded px-1 py-0.5 bg-white" value={val} onChange={(e) => setVal(e.target.value)}>
        <option value="">{placeholder}</option>
        {unpicked.map((b) => <option key={b.id} value={b.id}>{b.text.slice(0, 100)}</option>)}
      </select>
      <button
        className="bg-purple-600 text-white px-3 rounded"
        onClick={() => { if (val) { onAdd(val); setVal(""); } }}
      >Add</button>
    </div>
  );
}

function FreeTypeRow({
  placeholder, onUseHere, onSaveToMaster,
}: {
  placeholder: string;
  onUseHere: (text: string) => void;
  onSaveToMaster: (text: string) => Promise<void>;
}) {
  const [val, setVal] = useState("");
  return (
    <div className="flex gap-2 items-center text-xs mt-1">
      <input
        className="flex-1 border rounded px-2 py-1"
        placeholder={placeholder}
        value={val}
        onChange={(e) => setVal(e.target.value)}
      />
      <button
        className="bg-purple-600 text-white px-3 py-1 rounded"
        title="Add to this CV only"
        onClick={() => { if (val.trim()) { onUseHere(val.trim()); setVal(""); } }}
      >Use here</button>
      <button
        className="bg-green-600 text-white px-3 py-1 rounded"
        title="Append to master.md"
        onClick={async () => { if (val.trim()) { await onSaveToMaster(val.trim()); setVal(""); } }}
      >Save to master</button>
    </div>
  );
}
