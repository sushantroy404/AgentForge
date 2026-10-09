import { useEffect, useRef, useState } from "react";
import { client } from "../../api/client";
import { useJob } from "../../hooks/usePolling";
import SmokeTestList from "../specialist/SmokeTestList";
import type { Assumption, DraftSpec, MissingReport } from "../../types/agentforge";

interface Props {
  sessionId: string;
  fillFirst: boolean;
  onDefaults: (a: Assumption[], d: DraftSpec, m: MissingReport) => void;
  onOpen: (specialistId: string) => void;
  onClose: () => void;
}

const LABEL: Record<string, string> = {
  validate_draft: "Checking the definition", validate_tools: "Checking tools", validate_knowledge: "Checking the knowledge base",
  build_tests: "Writing test questions", validate_suite: "Validating the tests", compile: "Compiling the Specialist",
  persist: "Saving", finalize_status: "Recording the result",
};
const stageLabel = (n: string) => LABEL[n] ?? `Running test ${n.replace("smoke_", "")} of 5`;

export default function BuildProgressModal({ sessionId, fillFirst, onDefaults, onOpen, onClose }: Props) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const started = useRef(false);
  const { job, error } = useJob(jobId);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    (async () => {
      try {
        if (fillFirst) {
          const r = await client.fillDefaults(sessionId);
          onDefaults(r.new_assumptions, r.draft_spec, r.missing_report);
        }
        setJobId((await client.finalize(sessionId)).job_id);
      } catch (e) { setErr((e as Error).message); }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const done = job?.status === "done";
  const failed = job?.status === "failed" || err || error;
  const report = done ? job!.result?.smoke_report : null;
  const status: string | undefined = done ? job!.result?.status : undefined;

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-ink/40 p-4" role="dialog" aria-modal="true" aria-label="Building Specialist">
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg bg-sheet p-5 shadow-xl">
        <h2 className="mb-3 text-lg font-semibold">{done ? (status === "verified" ? "Specialist verified" : status === "needs_review" ? "Specialist built, review needed" : "Specialist blocked") : failed ? "Build failed" : "Building your Specialist"}</h2>
        <ol className="mb-4 space-y-1 text-sm">
          {(job?.stages ?? []).map((s) => (
            <li key={s.name} className="flex items-baseline gap-2">
              <span className={`w-16 text-xs ${s.status === "done" ? "text-trace" : s.status === "failed" ? "text-stop" : s.status === "running" ? "text-flag" : "text-ink-soft"}`}>{s.status}</span>
              <span>{stageLabel(s.name)}</span>
              {s.detail && s.status !== "pending" && <span className="truncate text-xs text-ink-soft">{s.detail}</span>}
            </li>
          ))}
        </ol>
        {failed && <p role="alert" className="mb-3 rounded border border-stop bg-stop-wash px-3 py-2 text-sm text-stop">{err ?? error ?? job?.error}</p>}
        {report && <div className="mb-4"><SmokeTestList report={report} /></div>}
        {status === "needs_review" && <p className="mb-3 rounded bg-flag-wash px-3 py-2 text-sm text-flag">The safety checks passed but an in-scope test failed. You can still try it, then re-run the tests.</p>}
        {status === "failed" && <p className="mb-3 rounded bg-stop-wash px-3 py-2 text-sm text-stop">A safety test failed, so this Specialist can't be used. Adjust the definition and build again.</p>}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-md border border-rule px-3 py-1.5 text-sm">{done || failed ? "Close" : "Hide"}</button>
          {done && status !== "failed" && <button onClick={() => onOpen(job!.result.specialist_id)} className="rounded-md bg-trace px-3 py-1.5 text-sm font-medium text-white">Open Specialist</button>}
        </div>
      </div>
    </div>
  );
}
