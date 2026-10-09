import { Check, X } from "lucide-react";
import type { SmokeReport } from "../../types/agentforge";

const LABEL: Record<string, string> = { in_scope: "In scope", out_of_scope: "Out of scope", prompt_injection: "Injection attempt" };

export default function SmokeTestList({ report }: { report: SmokeReport }) {
  return (
    <ul className="space-y-1.5 text-sm">
      {report.results.map((r) => (
        <li key={r.id} className="flex gap-2">
          {r.passed ? <Check size={16} className="mt-0.5 shrink-0 text-trace" aria-label="passed" /> : <X size={16} className="mt-0.5 shrink-0 text-stop" aria-label="failed" />}
          <div>
            <p><span className="font-medium">{LABEL[r.category] ?? r.category}</span> <span className="text-ink-soft">({r.kind})</span></p>
            <p className="text-ink-soft">{r.prompt}</p>
            {!r.passed && <p className="text-stop">{r.reason}</p>}
          </div>
        </li>
      ))}
    </ul>
  );
}
