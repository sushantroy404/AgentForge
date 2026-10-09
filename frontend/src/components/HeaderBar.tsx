import type { Health, SpecialistItem } from "../types/agentforge";

interface Props {
  view: "architect" | "specialist";
  setView: (v: "architect" | "specialist") => void;
  health: Health | null;
  healthError: boolean;
  specialists: SpecialistItem[];
  specialistId: string | null;
  onPick: (id: string) => void;
  onNew: () => void;
}

function Pill({ health, err }: { health: Health | null; err: boolean }) {
  if (err || !health) return <span className="rounded-full bg-stop-wash px-2.5 py-1 text-xs text-stop" title="Backend unreachable">Backend offline</span>;
  if (health.demo_mode === "replay") return <span className="rounded-full bg-flag-wash px-2.5 py-1 text-xs text-flag" title="Scripted answers, no Ollama">Demo mode</span>;
  const ok = health.ollama === true && Object.values(health.models_present).every(Boolean);
  return ok
    ? <span className="rounded-full bg-trace-wash px-2.5 py-1 text-xs text-trace">Ollama ready</span>
    : <span className="rounded-full bg-flag-wash px-2.5 py-1 text-xs text-flag" title="Run: ollama serve, then pull the models in .env">
        {health.ollama ? "Model missing" : "Start Ollama"}{health.demo_mode === "auto" ? " (replay fallback on)" : ""}
      </span>;
}

export default function HeaderBar({ view, setView, health, healthError, specialists, specialistId, onPick, onNew }: Props) {
  const tab = (v: "architect" | "specialist", label: string) => (
    <button onClick={() => setView(v)} aria-pressed={view === v}
      className={`rounded-md px-3 py-1.5 text-sm font-medium ${view === v ? "bg-ink text-sheet" : "text-ink-soft hover:bg-rule/50"}`}>{label}</button>
  );
  return (
    <header className="flex flex-wrap items-center gap-3 border-b border-rule bg-sheet px-5 py-2.5">
      <h1 className="text-lg font-bold tracking-tight">AgentForge</h1>
      <nav className="flex gap-1" aria-label="Views">{tab("architect", "Build")}{tab("specialist", "Try a Specialist")}</nav>
      <div className="ml-auto flex items-center gap-3">
        {view === "specialist" && (
          <select value={specialistId ?? ""} onChange={(e) => onPick(e.target.value)} aria-label="Choose a Specialist"
            className="rounded-md border border-rule bg-white px-2 py-1.5 text-sm">
            {specialists.length === 0 && <option value="">No Specialists yet</option>}
            {specialists.map((s) => <option key={s.id} value={s.id}>{s.name}: {s.role} ({s.status})</option>)}
          </select>
        )}
        <button onClick={onNew} className="rounded-md border border-rule px-3 py-1.5 text-sm hover:bg-rule/40">New Specialist</button>
        <Pill health={health} err={healthError} />
      </div>
    </header>
  );
}
