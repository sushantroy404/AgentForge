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

interface Props {
  draft: DraftSpec;
  missing: MissingReport;
  changed: Set<string>;
  onUpdateLanguages?: (supported: string[], defLang: string) => void;
}

const ALL_LANGUAGES = [
  { code: "en", label: "English (EN)" },
  { code: "ne", label: "नेपाली (Devanagari)" },
  { code: "ne_roman", label: "Roman Nepali" },
];

export default function LiveSpecInspector({ draft, missing, changed, onUpdateLanguages }: Props) {
  const req = new Set(missing.missing_required);
  const supported = draft.persona.supported_languages || ["en", "ne", "ne_roman"];
  const defaultLang = draft.persona.default_language || "en";

  const handleToggleLang = (code: string) => {
    let next: string[];
    if (supported.includes(code)) {
      if (supported.length <= 1) return; // keep at least one
      next = supported.filter((c) => c !== code);
    } else {
      next = [...supported, code];
    }
    const nextDef = next.includes(defaultLang) ? defaultLang : next[0];
    onUpdateLanguages?.(next, nextDef);
  };

  const handleSetDefault = (code: string) => {
    if (supported.includes(code)) {
      onUpdateLanguages?.(supported, code);
    }
  };

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

      {/* Languages Builder Control */}
      <section className="rounded-lg border border-rule/80 bg-white p-3.5 shadow-xs">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-ink">Supported Languages</h3>
          <span className="text-xs text-ink-soft">Builder Control</span>
        </div>
        <p className="mb-3 text-xs text-ink-soft">
          Choose which languages the Specialist can respond in. Users writing in other languages will receive a polite refusal in the default language.
        </p>

        <div className="space-y-2.5">
          {ALL_LANGUAGES.map((lang) => {
            const checked = supported.includes(lang.code);
            const isDefault = defaultLang === lang.code;
            return (
              <div key={lang.code} className="flex items-center justify-between rounded-md border border-rule/50 px-2.5 py-1.5 hover:bg-sheet/60 transition-colors">
                <label className="flex items-center gap-2 text-sm text-ink cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => handleToggleLang(lang.code)}
                    disabled={checked && supported.length <= 1}
                    className="h-4 w-4 rounded border-rule text-trace focus:ring-trace"
                  />
                  <span>{lang.label}</span>
                </label>
                {checked && (
                  <button
                    type="button"
                    onClick={() => handleSetDefault(lang.code)}
                    className={`rounded px-2 py-0.5 text-xs font-medium transition-all ${
                      isDefault
                        ? "bg-trace text-white"
                        : "border border-rule/80 text-ink-soft hover:border-trace hover:text-trace"
                    }`}
                    title={isDefault ? "Default language" : "Click to set as default language"}
                  >
                    {isDefault ? "★ Default" : "Set default"}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
