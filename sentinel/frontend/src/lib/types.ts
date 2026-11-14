export type Role = "admin" | "analyst";

export interface User {
  id: number;
  email: string;
  name: string;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
  created_at?: string;
  last_login_at?: string | null;
}

export interface Summary {
  headline?: string;
  summary?: string;
  key_points?: string[];
  action_items?: string[];
  effective_date?: string | null;
  deadline?: string | null;
  applicability?: { verdict: string; reason: string };
  priority?: string;
  priority_reason?: string;
  tags?: string[];
  impacted_functions?: string[];
  generated_by?: string;
  rules_view?: { priority: string; applicability: { verdict: string; reason: string } };
  model_view?: { priority?: string; applicability?: { verdict: string; reason: string } };
}

export interface CircularBrief {
  id: number;
  title: string;
  source: string;
  url: string;
  pdf_url: string | null;
  published_at: string | null;
  rbi_ref: string | null;
  dept_ref: string | null;
  department: string | null;
  addressees: string | null;
  priority: string;
  applicability: string;
  tags: string[];
  status: string;
  summary: Summary | null;
  chunk_count: number;
  notified_at: string | null;
  ingest_trace_id: string | null;
  listing_group: string | null;
  financial_year: string | null;
  superseded_by: number | null;
  ai_summary: boolean;
  revision: number;
  updated_at: string | null;
}

export interface CircularDetail extends CircularBrief {
  text: string;
  signatory: string | null;
  created_at: string;
  summary_model: string | null;
  emails: { ts: string; kind: string; status: string; recipients: string[] }[];
}

export interface Source {
  n: number;
  chunk_id: number | null;
  circular_id: number;
  title: string;
  url: string;
  rbi_ref: string | null;
  source: string;
  published_at: string | null;
  text: string;
  score?: number;
  dense_rank?: number | null;
  bm25_rank?: number | null;
  dense_score?: number | null;
  bm25_score?: number | null;
  rerank_score?: number | null;
  priority?: string;
  superseded?: boolean;
}

export interface Verification {
  verdict: string;
  score: number | null;
  grounding?: number;
  citation_coverage?: number;
  cited_sentences?: number;
  uncited_sentences?: number;
  invalid_citations?: number[];
  method?: string;
  detail?: string;
  sentences: { sentence: string; citations: number[]; support: number | null }[];
}

export interface StepEvent {
  agent: string;
  label: string;
  status: "running" | "done" | "error";
  detail?: any;
  ms?: number | null;
}

export interface ChatMessage {
  id: number | string;
  role: "user" | "assistant";
  content: string;
  citations: Source[];
  meta: { intent?: string; verification?: Verification | null; actions?: any[]; route?: any; model?: string };
  trace_id: string | null;
  created_at?: string;
  // client-side only
  steps?: StepEvent[];
  streaming?: boolean;
  notice?: string;
}

export interface Conversation {
  id: number;
  title: string;
  updated_at: string;
  has_summary: boolean;
}

export interface TraceRow {
  id: string;
  kind: string;
  name: string;
  actor: string | null;
  status: string;
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  tokens_in: number;
  tokens_out: number;
  error: string | null;
  spans?: number;
}

export interface SpanRow {
  id: string;
  parent_id: string | null;
  agent: string;
  name: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  input: any;
  output: any;
  attributes: Record<string, any> | null;
  error: string | null;
}

export interface TraceDetail extends Omit<TraceRow, "spans"> {
  input: any;
  output: any;
  attributes: any;
  spans: SpanRow[];
  audit: { ts: string; actor: string; action: string; resource: string }[];
}
