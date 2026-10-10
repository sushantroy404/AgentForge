import type { RuntimeTrace, SmokeReport } from "../../types/agentforge";
import SmokeTestList from "./SmokeTestList";

interface Props { trace: RuntimeTrace | null; status: string; report: SmokeReport | null; rerun: () => void; rerunning: boolean }

const GATE: Record<string, string> = { input_filter: "Blocked by the input filter", scope_gate: "Refused by the scope gate", model: "Declined by the model" };

export default function TraceSidebar({ trace, status, report, rerun, rerunning }: Props) {
  const tone = status === "verified" ? "bg-trace-wash text-trace" : status === "failed" ? "bg-stop-wash text-stop" : "bg-flag-wash text-flag";
  return (
    <aside className="scroll-thin h-full space-y-5 overflow-y-auto bg-sheet px-5 py-5" aria-label="How the last answer was produced">
      <section>
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Safety checks</h3>
          <span className={`rounded-full px-2.5 py-0.5 text-xs ${tone}`}>{status.replace("_", " ")}</span>
        </div>
        {report && <div className="mt-2"><SmokeTestList report={report} /></div>}
        <button onClick={rerun} disabled={rerunning} className="mt-2 rounded border border-rule px-2.5 py-1 text-sm hover:border-trace disabled:opacity-40">
          {rerunning ? "Running tests…" : "Re-run tests"}</button>
      </section>
      <section>
        <h3 className="mb-1.5 text-sm font-semibold">Last answer</h3>
        {!trace ? <p className="text-sm text-ink-soft">Ask a question to see which gates, documents and tools were used.</p> : (
          <div className="space-y-3 text-sm">
            {trace.gate && <p className="rounded bg-stop-wash px-2.5 py-1.5 text-stop">{GATE[trace.gate]}</p>}
            <p className="text-ink-soft">{trace.latency_ms} ms. {trace.scope.s_in !== undefined && `Scope match ${trace.scope.s_in} in, ${trace.scope.s_out} out.`}</p>
            {trace.flags.length > 0 && <p className="text-flag">Flags: {trace.flags.join(", ")}</p>}
            <div>
              <p className="font-medium">Documents used (cutoff {trace.threshold})</p>
              {trace.retrieved_chunks.length === 0 ? <p className="text-ink-soft">None matched.</p> : trace.retrieved_chunks.map((c) => (
                <details key={c.chunk_id} className="mt-1 rounded border border-rule px-2 py-1">
                  <summary className="cursor-pointer">{c.source_file}, score {c.score.toFixed(2)}</summary>
                  <p className="mt-1 whitespace-pre-wrap font-mono text-xs text-ink-soft">{c.text}</p>
                </details>
              ))}
            </div>
            <div>
              <p className="font-medium">Tools called</p>
              {trace.tool_calls.length === 0 ? <p className="text-ink-soft">None.</p> : trace.tool_calls.map((t, i) => (
                <details key={i} className="mt-1 rounded border border-rule px-2 py-1" open>
                  <summary className="cursor-pointer">{t.tool_id}{t.error ? " (blocked)" : ""}</summary>
                  <pre className="mt-1 overflow-x-auto font-mono text-xs text-ink-soft">{JSON.stringify(t.error ?? { args: t.args, result: t.result }, null, 2)}</pre>
                </details>
              ))}
            </div>
          </div>
        )}
      </section>
    </aside>
  );
}
