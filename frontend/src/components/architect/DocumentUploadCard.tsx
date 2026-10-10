import { useEffect, useRef, useState } from "react";
import { FileText } from "lucide-react";
import { client } from "../../api/client";
import { useJob } from "../../hooks/usePolling";

interface Props { sessionId: string; docs: { filename: string; chunk_count: number; warnings: string[] }[]; onDone: () => void }

const STAGE_LABEL: Record<string, string> = {
  parse: "Reading file", sanitise: "Checking for hidden instructions", chunk: "Splitting into sections",
  embed: "Creating embeddings", write: "Saving to the knowledge base", probe_facts: "Finding key facts",
  architect_confirm: "Asking the Architect to confirm",
};

export default function DocumentUploadCard({ sessionId, docs, onDone }: Props) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const { job, error } = useJob(jobId);
  const finished = useRef<string | null>(null);

  useEffect(() => {
    if (job && job.status !== "running" && finished.current !== job.job_id) {
      finished.current = job.job_id;
      if (job.status === "done") onDone();
    }
  }, [job]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = async (file: File) => {
    setErr(null);
    try { setJobId((await client.upload(sessionId, file)).job_id); } catch (e) { setErr((e as Error).message); }
  };
  const useDemo = async (name: string) => {
    const r = await fetch(`/demo/${name}`);
    start(new File([await r.blob()], name, { type: "text/markdown" }));
  };

  const running = job?.status === "running" || (jobId && !job && !error);
  const warnings: string[] = job?.status === "done" ? job.result?.warnings ?? [] : docs.flatMap((d) => d.warnings);

  return (
    <div className="rounded-md border border-rule bg-white p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <FileText size={16} className="text-ink-soft" />
        <span className="font-medium">Knowledge document</span>
        <button onClick={() => input.current?.click()} disabled={!!running} className="rounded border border-rule px-2 py-1 hover:border-trace disabled:opacity-40">Upload file</button>
        <button onClick={() => useDemo("acme_refund_policy.md")} disabled={!!running} className="rounded border border-rule px-2 py-1 hover:border-trace disabled:opacity-40">Use demo policy</button>
        <button onClick={() => useDemo("injected_doc.md")} disabled={!!running} className="rounded border border-rule px-2 py-1 text-ink-soft hover:border-flag disabled:opacity-40">Use trap document</button>
        <input ref={input} type="file" accept=".pdf,.md,.txt" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) start(f); e.target.value = ""; }} />
      </div>
      {docs.length > 0 && !running && <p className="mt-2 text-ink-soft">Indexed: {docs.map((d) => `${d.filename} (${d.chunk_count} sections)`).join(", ")}</p>}
      {running && job && <p className="mt-2 text-ink-soft">{STAGE_LABEL[job.stages.find((s) => s.status === "running")?.name ?? ""] ?? "Working"}…</p>}
      {(err || error || job?.status === "failed") && <p role="alert" className="mt-2 text-stop">{err ?? error ?? job?.error}</p>}
      {warnings.map((w, i) => <p key={i} className="mt-2 rounded bg-flag-wash px-2 py-1 text-flag">{w}</p>)}
    </div>
  );
}
