import type { Assumption } from "../../types/agentforge";

export default function AssumptionList({ items }: { items: Assumption[] }) {
  if (items.length === 0) return null;
  return (
    <section>
      <h3 className="mb-1.5 text-sm font-semibold">Assumptions to check</h3>
      <ul className="space-y-1.5 text-sm">
        {items.map((a, i) => (
          <li key={i} className="rounded border border-flag/40 bg-flag-wash/60 px-2.5 py-1.5">
            <p><span className="font-medium">{a.field}</span>: {a.value}</p>
            <p className="text-xs text-ink-soft">{a.source === "default" ? "Filled in by default" : "Guessed by the Architect"}{a.reason ? `. ${a.reason}` : ""}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
