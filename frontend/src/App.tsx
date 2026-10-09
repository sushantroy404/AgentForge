import { useCallback, useEffect, useState } from "react";
import { client, store } from "./api/client";
import ArchitectWorkspace from "./components/architect/ArchitectWorkspace";
import HeaderBar from "./components/HeaderBar";
import SpecialistWorkspace from "./components/specialist/SpecialistWorkspace";
import type { Health, SpecialistItem } from "./types/agentforge";

export default function App() {
  const [view, setView] = useState<"architect" | "specialist">("architect");
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [specialists, setSpecialists] = useState<SpecialistItem[]>([]);
  const [specialistId, setSpecialistId] = useState<string | null>(store("agentforge.specialist"));
  const [architectKey, setArchitectKey] = useState(0);

  const loadSpecialists = useCallback(async () => {
    try {
      const list = await client.specialists();
      setSpecialists(list);
      setSpecialistId((cur) => (cur && list.some((s) => s.id === cur) ? cur : list[list.length - 1]?.id ?? null));
    } catch { /* surfaced by the health pill */ }
  }, []);

  useEffect(() => {
    const check = () => client.health().then((h) => { setHealth(h); setHealthError(false); }).catch(() => setHealthError(true));
    check();
    loadSpecialists();
    const t = setInterval(check, 10000);
    return () => clearInterval(t);
  }, [loadSpecialists]);

  useEffect(() => { store("agentforge.specialist", specialistId); }, [specialistId]);

  const open = async (id: string) => { await loadSpecialists(); setSpecialistId(id); setView("specialist"); };
  const startNew = () => { store("agentforge.session", null); setArchitectKey((k) => k + 1); setView("architect"); };

  return (
    <div className="flex h-full flex-col">
      <HeaderBar view={view} setView={(v) => { if (v === "specialist") loadSpecialists(); setView(v); }} health={health}
        healthError={healthError} specialists={specialists} specialistId={specialistId} onPick={setSpecialistId} onNew={startNew} />
      <main className="min-h-0 flex-1">
        {view === "architect"
          ? <ArchitectWorkspace key={architectKey} onOpenSpecialist={open} />
          : specialistId
            ? <SpecialistWorkspace key={specialistId} specialistId={specialistId} />
            : <p className="p-6 text-ink-soft">No Specialist yet. Build one first, then come back to try it.</p>}
      </main>
    </div>
  );
}
