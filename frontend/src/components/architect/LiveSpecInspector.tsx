import type { DraftSpec, MissingReport } from "../../types/agentforge";

type Row = { path: string; label: string; value: string | string[] | null };

function rows(d: DraftSpec): { title: string; rows: Row[] }[] {
  return [
    { title: "Identity", rows: [
      { path: "identity.name", label: "Name", value: d.identity.name },
      { path: "identity.role", label: "Role", value: d.identity.role },
      { path: "identity.company", label: "Company", value: d.identity.company },
      { path: "identity.target_audience", label: "Audience", value: d.identity.target_audience }] },
    { title: "Voice", rows: [
      { path: "persona.tone", label: "Tone", value: d.persona.tone },
      { path: "persona.greeting_message", label: "Greeting", value: d.persona.greeting_message }] },
    { title: "Job", rows: [
      { path: "mission.primary_goal", label: "Goal", value: d.mission.primary_goal },
      { path: "mission.in_scope_topics", label: "Handles", value: d.mission.in_scope_topics },
      { path: "mission.out_of_scope_topics", label: "Refuses", value: d.mission.out_of_scope_topics },
      { path: "mission.escalation_triggers", label: "Escalates when", value: d.mission.escalation_triggers }] },
    { title: "Limits", rows: [
      { path: "guardrails.never_do_rules", label: "Never", value: d.guardrails.never_do_rules },
      { path: "guardrails.blocked_phrases", label: "Blocked phrases", value: d.guardrails.blocked_phrases }] },
    { title: "Tools and knowledge", rows: [
      { path: "tools", label: "Tools", value: d.tools },
      { path: "knowledge.collection_id", label: "Documents", value: d.knowledge.document_names.length ? d.knowledge.document_names : null }] },
  ];
}

export default function LiveSpecInspector({ draft, missing, changed }: { draft: DraftSpec; missing: MissingReport; changed: Set<string> }) {
  const req = new Set(missing.missing_required);
  return (
    <div className="space-y-5">
      {rows(draft).map((sec) => (
        <section key={sec.title}>
          <h3 className="mb-1.5 text-sm font-semibold">{sec.title}</h3>
          <dl className="space-y-1">
            {sec.rows.map((r) => {
              const empty = r.value === null || (Array.isArray(r.value) && r.value.length === 0);
              const state = !empty ? "filled" : req.has(r.path) ? "required" : "optional";
              const hint = missing.hints[r.path];
              return (
                <div key={r.path} data-state={state} data-path={r.path}
                  className={`ledger-row grid grid-cols-[7rem_1fr] gap-2 rounded-r px-2.5 py-1.5 text-sm ${changed.has(r.path) ? "just-written" : ""}`}>
                  <dt className="text-ink-soft">{r.label}</dt>
                  <dd>
                    {empty ? (
                      <span className={state === "required" ? "text-flag" : "text-ink-soft"}>
                        {state === "required" ? "Needed" : "Optional"}{hint ? `: ${hint}` : ""}
                      </span>
                    ) : Array.isArray(r.value) ? (
                      <span className="flex flex-wrap gap-1">
                        {r.value.map((v) => <span key={v} className="rounded bg-trace-wash px-1.5 py-0.5 text-[13px] text-trace">{v}</span>)}
                      </span>
                    ) : r.value}
                  </dd>
                </div>
              );
            })}
          </dl>
        </section>
      ))}
    </div>
  );
}
