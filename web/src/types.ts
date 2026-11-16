export type Status = "met" | "not_met" | "insufficient";
export type Verdict = "likely_eligible" | "needs_more_data" | "not_eligible" | "insufficient_data";

export interface Lab {
  name: string;
  value: number;
  unit: string;
}

export interface Profile {
  age: number | null;
  sex: string | null;
  diagnoses: string[];
  medications: string[];
  labs: Lab[];
  history: string[];
  absent: string[];
}

export interface Trial {
  nct_id: string;
  title: string;
  conditions: string[];
  status: string;
}

export interface Criterion {
  id: string;
  kind: "inclusion" | "exclusion";
  text: string;
  screening_only: boolean;
  group?: string;
  group_needed?: number;
  conditional?: boolean;
  cohort?: string;
}

export interface Check {
  criterion_id: string;
  status: Status;
  evidence: string;
  reasoning: string;
  source: string;
}

export interface TrialVerdict {
  trial: Trial;
  verdict: Verdict;
  score: number;
  criteria: Criterion[];
  checks: Check[];
  blockers: string[];
  missing: string[];
  fallback: boolean;
}

export interface MatchResult {
  safety: { action: "proceed" | "ask_diagnosis" | "refuse" | "urgent"; message: string };
  profile: Profile | null;
  query: string;
  candidates: number;
  verdicts: TrialVerdict[];
  questions: string[];
  note: string;
  fallback: boolean;
}

export interface Progress {
  stage: "profile" | "search" | "check";
  done?: number;
  total?: number;
  query?: string;
  candidates?: number;
}

export interface TrialBrief {
  nct_id: string;
  title: string;
  conditions: string[];
  status: string;
  min_age: number | null;
  max_age: number | null;
  sex: string;
}

export interface TrialDetails extends TrialBrief {
  summary: string;
  criteria: Criterion[];
}

export interface Vignette {
  id: string;
  text: string;
  source: "synthetic" | "published";
  title?: string;
  pmid?: string;
  patient_uid?: string;
  year?: string;
  url?: string;
  credit?: string;
}

export interface AppStatus {
  mode: "model" | "offline";
  model: string | null;
}

export interface TraceEvent {
  ts: number;
  component: string;
  kind: string;
  [key: string]: unknown;
}

export interface CaseReport extends Vignette {
  age: number | null;
  sex: string | null;
  score: number;
  why: string;
}

export interface CaseReportSearch {
  available: boolean;
  searched: number;
  ruled_out: number;
  candidates: CaseReport[];
}
