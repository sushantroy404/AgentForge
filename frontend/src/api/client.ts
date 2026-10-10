import type { Health, JobRecord, RuntimeTrace, SessionView, SpecialistDetail, SpecialistItem, TurnResponse, DraftSpec, MissingReport, Assumption } from "../types/agentforge";

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api";

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: any) { super(message); }
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, init);
  } catch {
    throw new ApiError(0, "Cannot reach the AgentForge backend. Is it running on port 8000?");
  }
  if (!res.ok) {
    let body: any = null;
    try { body = await res.json(); } catch { /* not json */ }
    const d = body?.detail;
    const msg = typeof d === "string" ? d : d ? JSON.stringify(d) : `Request failed (${res.status})`;
    throw new ApiError(res.status, msg, body);
  }
  return res.json() as Promise<T>;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body),
});

export const client = {
  health: () => api<Health>("/health"),
  createSession: () => api<SessionView>("/architect/sessions", json("POST", {})),
  getSession: (id: string) => api<SessionView>(`/architect/sessions/${id}`),
  chat: (id: string, message: string) => api<TurnResponse>(`/architect/sessions/${id}/chat`, json("POST", { message })),
  upload: (id: string, file: File) => {
    const fd = new FormData(); fd.append("file", file);
    return api<{ job_id: string }>(`/architect/sessions/${id}/documents`, { method: "POST", body: fd });
  },
  fillDefaults: (id: string) => api<{ draft_spec: DraftSpec; missing_report: MissingReport; new_assumptions: Assumption[] }>(`/architect/sessions/${id}/fill-defaults`, json("POST")),
  patch: (id: string, ops: { op: string; path: string; value: any }[]) =>
    api<{ draft_spec: DraftSpec; missing_report: MissingReport; applied_paths: string[]; rejected_ops: any[] }>(`/architect/sessions/${id}/patch`, json("POST", { ops })),
  finalize: (id: string) => api<{ job_id: string }>(`/architect/sessions/${id}/finalize`, json("POST", { run_smoke_tests: true })),
  job: (id: string) => api<JobRecord>(`/jobs/${id}`),
  specialists: () => api<SpecialistItem[]>("/specialists"),
  specialist: (id: string) => api<SpecialistDetail>(`/specialists/${id}`),
  specialistChat: (id: string, message: string, history: { role: string; content: string }[]) =>
    api<{ reply: string; trace: RuntimeTrace }>(`/specialists/${id}/chat`, json("POST", { message, history })),
  smokeTest: (id: string) => api<{ job_id: string }>(`/specialists/${id}/smoke-test`, json("POST")),
};

export function store(key: string, value?: string | null): string | null {
  try {
    if (value === undefined) return localStorage.getItem(key);
    if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value);
  } catch { /* storage unavailable */ }
  return null;
}
