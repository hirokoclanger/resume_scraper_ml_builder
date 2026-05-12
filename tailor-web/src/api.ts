// Thin typed client over the Python server endpoints. Every function
// here mirrors a server route documented in SPEC_v2_tailored.md §10.

import type { View, Coverage, JdAnalysis, Edits } from "./types";

async function jsonPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.json())?.error ?? ""; } catch { /* ignore */ }
    throw new Error(`${res.status} ${res.statusText}${detail ? `: ${detail}` : ""}`);
  }
  return (await res.json()) as T;
}

async function jsonGet<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

export async function fetchHeaderVariants() {
  return jsonGet<{ default: string; variants: Record<string, unknown> }>("/api/header_variants");
}

export async function fetchRoleTargets() {
  return jsonGet<{ targets: Array<{ key: string; label: string; profile: string; variant: string; seed_jd: string }>; header_variants: string[] }>("/api/role_targets");
}

export async function buildView(jd: string, opts: { variant?: string; company?: string; title?: string } = {}): Promise<View> {
  const r = await jsonPost<{ view: View }>("/api/tailor_view_freeform", {
    jd_text: jd,
    variant: opts.variant ?? "leadership",
    company: opts.company ?? "",
    title: opts.title ?? "",
  });
  return r.view;
}

export async function analyzeJd(jd: string): Promise<JdAnalysis> {
  return jsonPost<JdAnalysis>("/api/jd_analyze", { jd_text: jd });
}

export type CompositionTexts = {
  summary: string;
  skills: string[];
  roles: Array<{ position: string; company: string; highlights: string[] }>;
};

export async function refreshCoverage(jd: string, composition: CompositionTexts): Promise<Coverage> {
  const r = await jsonPost<{ coverage: Coverage }>("/api/coverage", {
    jd_text: jd,
    composition,
  });
  return r.coverage;
}

export async function saveMasterBullet(args: {
  section: "skills" | "role";
  role_key?: string;
  text: string;
}): Promise<{ id: string | null; persisted: true }> {
  return jsonPost("/api/master/bullet", args);
}

export async function renderPdf(args: {
  company: string;
  title: string;
  variant: string;
  include_photo: boolean;
  edits: Edits;
}) {
  return jsonPost<{ filename: string; url: string; size_bytes: number }>(
    "/api/tailor_pdf_from_edits", args,
  );
}

export async function renderDocx(args: {
  company: string;
  title: string;
  variant: string;
  include_photo: boolean;
  edits: Edits;
}) {
  return jsonPost<{ filename: string; url: string; size_bytes: number }>(
    "/api/tailor_docx_from_edits", args,
  );
}
