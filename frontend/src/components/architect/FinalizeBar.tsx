import type { MissingReport } from "../../types/agentforge";

interface Props { missing: MissingReport; hasDocs: boolean; busy: boolean; onBuild: (fillFirst: boolean) => void }

export default function FinalizeBar({ missing, hasDocs, busy, onBuild }: Props) {
  const ready = missing.missing_required.length === 0;
  const core = ["identity.name", "identity.role", "identity.company", "mission.primary_goal", "mission.in_scope_topics"];
  const canDefault = core.every((p) => !missing.missing_required.includes(p));
  return (
    <div className="space-y-2">
      {ready ? (
        <button onClick={() => onBuild(false)} disabled={busy} className="w-full rounded-md bg-trace px-4 py-2.5 font-medium text-white disabled:opacity-40">Build Specialist</button>
      ) : (
        <button onClick={() => onBuild(true)} disabled={busy || !canDefault}
          className="w-full rounded-md bg-ink px-4 py-2.5 font-medium text-sheet disabled:opacity-40">Fill defaults and build</button>
      )}
      {!ready && <p className="text-xs text-ink-soft">
        {canDefault ? `Defaults will be recorded as assumptions for: ${missing.missing_required.map((p) => p.split(".").pop()).join(", ")}.`
          : "Describe the name, role, company, goal and what it handles first. Those can't be guessed."}</p>}
      {!hasDocs && <p className="text-xs text-ink-soft">No document attached. The Specialist will rely on its instructions and tools only.</p>}
    </div>
  );
}
