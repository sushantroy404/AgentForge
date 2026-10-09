const SCRIPT = [
  { label: "Describe Aria", text: "We are Acme Cloud. Build a Customer Support Specialist named Aria for Acme customers asking about hardware orders, returns and refunds. Warm, concise, factual." },
  { label: "Scope, tools and rules", text: "In scope: order status, refund eligibility, damaged shipments, escalating refunds over $500. Out of scope: competitor comparisons, tax or legal advice, custom discounts. Enable lookup_order and escalate_to_human. Never invent order details or promise refunds outside the policy." },
];

export default function QuickFillPills({ onPick }: { onPick: (t: string) => void }) {
  return (
    <div className="mb-2 flex flex-wrap items-center gap-2">
      <span className="text-xs text-ink-soft">Demo script</span>
      {SCRIPT.map((s) => (
        <button key={s.label} onClick={() => onPick(s.text)}
          className="rounded-full border border-rule bg-white px-3 py-1 text-xs hover:border-trace hover:text-trace">{s.label}</button>
      ))}
    </div>
  );
}
