export interface DraftSpec {
  identity: { name: string | null; role: string | null; company: string | null; target_audience: string | null };
  persona: { tone: string[]; style_guidelines: string[]; greeting_message: string | null };
  mission: { primary_goal: string | null; in_scope_topics: string[]; out_of_scope_topics: string[]; escalation_triggers: string[] };
  guardrails: { blocked_phrases: string[]; never_do_rules: string[]; fallback_out_of_scope_response: string | null };
  knowledge: { collection_id: string | null; document_names: string[]; top_k: number; score_threshold: number };
  tools: string[];
}
export interface Assumption { field: string; value: string; reason: string; source: "architect" | "default" }
export interface MissingReport { completeness_pct: number; missing_required: string[]; missing_recommended: string[]; hints: Record<string, string> }
export interface ChatMsg { role: "user" | "assistant" | "event"; content: string }
export interface SessionView {
  session_id: string; messages: ChatMsg[]; draft_spec: DraftSpec; assumptions: Assumption[];
  missing_report: MissingReport; documents: { filename: string; chunk_count: number; warnings: string[] }[];
  specialist_id: string | null;
}
export interface TurnResponse {
  assistant_message: ChatMsg; applied_paths: string[]; rejected_ops: { path: string; error: string }[];
  new_assumptions: Assumption[]; request_upload: boolean; ready_to_finalize: boolean;
  draft_spec: DraftSpec; missing_report: MissingReport;
}
export interface JobStage { name: string; status: "pending" | "running" | "done" | "failed" | "skipped"; detail: string }
export interface JobRecord { job_id: string; kind: string; status: "running" | "done" | "failed"; stages: JobStage[]; result: any; error: string | null }
export interface SmokeResult { id: string; category: string; kind: string; prompt: string; passed: boolean; reason: string; reply: string; attempts: number }
export interface SmokeReport { passed: number; total: number; results: SmokeResult[]; status: string }
export interface RetrievedChunk { chunk_id: string; source_file: string; score: number; text: string }
export interface RuntimeTrace {
  status: string; gate: string | null; input_guardrail_passed: boolean; scope: { s_in?: number; s_out?: number; refused?: boolean };
  threshold: number; retrieved_chunks: RetrievedChunk[]; confidence_check_passed: boolean;
  tool_calls: { tool_id: string; args: Record<string, unknown>; result: unknown; error: string | null }[];
  flags: string[]; output_guardrail_passed: boolean; latency_ms: number;
}
export interface SpecialistItem { id: string; name: string; role: string; status: string }
export interface SpecialistDetail {
  manifest: { specialist_id: string; identity: { name: string; role: string; company: string };
    persona: { greeting_message: string }; tools: { tool_id: string }[];
    provenance: { assumptions_made: string[] } };
  sha256: string; status: string; smoke_report: SmokeReport | null;
}
export interface Health { ollama: boolean; models_present: Record<string, boolean>; lancedb: boolean }
