// Shared type definitions for the v2 tailored editor.
// Mirrors the shapes the Python server returns on /api/tailor_view_freeform
// and /api/jd_analyze. Kept here so every component imports the same
// vocabulary.

export type Bullet = {
  id: string;
  text: string;
  tags: string[];
};

export type HeaderVariant = {
  name: string;
  headline: string;
  location: string;
  email: string;
  phone: string;
  website: string;
  linkedin: string;
};

export type RoleView = {
  key: string;
  position: string;
  company: string;
  start_date: string;
  end_date: string;
  location: string;
  highlights_picked: Bullet[];
  highlights_unpicked: Bullet[];
};

export type View = {
  profile: string;
  profile_label: string;
  variant: string;
  variant_label: string;
  runner_up_profile: string | null;
  header: HeaderVariant;
  header_variants: Record<string, HeaderVariant>;
  default_header_key: string;
  summary: { picked: Bullet[]; unpicked: Bullet[] };
  skills: { picked: Bullet[]; unpicked: Bullet[] };
  roles: RoleView[];
  projects: Array<{ name: string; summary?: string }>;
  education: string[];
  certifications: string[];
  languages: string[];
  available_variants: Array<{ key: string; label: string }>;
};

export type CustomBullet = { id: string; text: string };

export type EditsRole = {
  key: string;
  position?: string;
  position_override?: string;
  company?: string;
  start_date?: string;
  end_date?: string;
  location?: string;
  highlight_ids: string[];
  custom_highlights?: CustomBullet[];
};

export type Edits = {
  profile: string;
  profile_label: string;
  header_key: string;
  include_photo: boolean;
  summary_id: string | null;
  custom_summary?: string;
  skill_ids: string[];
  custom_skills?: CustomBullet[];
  roles: EditsRole[];
};

export type Coverage = {
  jd_skills: string[];
  present: string[];
  missing: string[];
  coverage_pct: number;
  by_category: Record<string, { present: string[]; missing: string[] }>;
};

export type JdAnalysis = {
  title_hint: string;
  jd_skills: string[];
  top_role_target: string | null;
  top_role_target_label: string | null;
  all_role_targets_ranked: Array<{ key: string; label: string; score: number }>;
  coverage: Coverage | null;
};
