export default function CompletenessMeter({ pct, missingCount }: { pct: number; missingCount: number }) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-sm">
        <span className="font-medium">{pct}% defined</span>
        <span className="text-ink-soft">{missingCount === 0 ? "Everything required is set" : `${missingCount} required left`}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded bg-rule" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className="h-full bg-trace transition-[width] duration-500" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
