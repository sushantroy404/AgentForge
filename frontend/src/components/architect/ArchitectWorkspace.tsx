import { useCallback, useEffect, useRef, useState } from "react";
import { client, store } from "../../api/client";
import type { Assumption, DraftSpec, MissingReport, SessionView } from "../../types/agentforge";
import ChatPanel from "../shared/ChatPanel";
import AssumptionList from "./AssumptionList";
import BuildProgressModal from "./BuildProgressModal";
import CompletenessMeter from "./CompletenessMeter";
import DocumentUploadCard from "./DocumentUploadCard";
import FinalizeBar from "./FinalizeBar";
import LiveSpecInspector from "./LiveSpecInspector";
import QuickFillPills from "./QuickFillPills";

export default function ArchitectWorkspace({ onOpenSpecialist }: { onOpenSpecialist: (id: string) => void }) {
  const [session, setSession] = useState<SessionView | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [changed, setChanged] = useState<Set<string>>(new Set());
  const [prefill, setPrefill] = useState<{ text: string; n: number } | null>(null);
  const [build, setBuild] = useState<{ fill: boolean } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const saved = store("agentforge.session");
        let s: SessionView;
        try { s = saved ? await client.getSession(saved) : await client.createSession(); }
        catch { s = await client.createSession(); }
        store("agentforge.session", s.session_id);
        if (!cancelled) setSession(s);
      } catch (e) { if (!cancelled) setError((e as Error).message); }
    })();
    return () => { cancelled = true; };
  }, []);

  const flash = (paths: string[]) => {
    setChanged(new Set(paths));
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setChanged(new Set()), 2600);
  };

  const refresh = useCallback(async () => {
    if (!session) return;
    const s = await client.getSession(session.session_id);
    setSession(s);
    flash(["knowledge.collection_id"]);
  }, [session?.session_id]); // eslint-disable-line react-hooks/exhaustive-deps

  const send = async (text: string): Promise<boolean> => {
    if (!session) return false;
    setBusy(true); setError(null);
    try {
      const r = await client.chat(session.session_id, text);
      setSession((s) => s && ({
        ...s, draft_spec: r.draft_spec, missing_report: r.missing_report,
        assumptions: [...s.assumptions, ...r.new_assumptions],
        messages: [...s.messages, { role: "user", content: text }, r.assistant_message],
      }));
      flash(r.applied_paths);
      if (r.rejected_ops.length) setError(`Some edits were rejected: ${r.rejected_ops.map((o) => `${o.path} (${o.error})`).join("; ")}`);
      return true;
    } catch (e) { setError((e as Error).message); return false; }
    finally { setBusy(false); }
  };

  const onDefaults = (a: Assumption[], d: DraftSpec, m: MissingReport) => {
    setSession((s) => s && ({ ...s, draft_spec: d, missing_report: m, assumptions: [...s.assumptions, ...a] }));
    flash(a.map((x) => x.field));
  };

  if (!session) {
    return <p className="p-6 text-ink-soft" role={error ? "alert" : undefined}>{error ?? "Starting a session…"}</p>;
  }

  return (
    <div className="grid h-full min-h-0 grid-cols-1 md:grid-cols-[minmax(0,1fr)_26rem]">
      <div className="min-h-0 border-r border-rule bg-paper">
        <ChatPanel who="The Architect" messages={session.messages} busy={busy} error={error} onSend={send} prefill={prefill}
          placeholder="Describe the Specialist you want to build…"
          above={<>
            <QuickFillPills onPick={(t) => setPrefill({ text: t, n: Date.now() })} />
            <div className="mb-3"><DocumentUploadCard sessionId={session.session_id} docs={session.documents} onDone={refresh} /></div>
          </>} />
      </div>
      <aside className="scroll-thin min-h-0 space-y-5 overflow-y-auto bg-sheet px-5 py-5" aria-label="Specialist definition">
        <CompletenessMeter pct={session.missing_report.completeness_pct} missingCount={session.missing_report.missing_required.length} />
        <LiveSpecInspector draft={session.draft_spec} missing={session.missing_report} changed={changed} />
        <AssumptionList items={session.assumptions} />
        <FinalizeBar missing={session.missing_report} hasDocs={session.draft_spec.knowledge.document_names.length > 0}
          busy={busy} onBuild={(fill) => setBuild({ fill })} />
      </aside>
      {build && (
        <BuildProgressModal sessionId={session.session_id} fillFirst={build.fill} onDefaults={onDefaults}
          onOpen={(id) => { setBuild(null); onOpenSpecialist(id); }} onClose={() => setBuild(null)} />
      )}
    </div>
  );
}
