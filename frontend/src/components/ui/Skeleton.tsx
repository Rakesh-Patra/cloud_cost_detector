/** Skeleton loading placeholders — used while API data is loading. */

export function SkeletonLine({ className = '' }: { className?: string }) {
  return (
    <div className={`h-4 bg-zinc-800/70 rounded animate-pulse ${className}`} />
  );
}

export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="bg-darkCard border border-zinc-800 rounded-xl p-5 space-y-3 animate-pulse">
      <div className="flex items-center justify-between">
        <div className="h-3 w-24 bg-zinc-800 rounded" />
        <div className="h-7 w-7 bg-zinc-800 rounded-lg" />
      </div>
      <div className="h-8 w-32 bg-zinc-700/60 rounded" />
      {Array.from({ length: lines - 2 }).map((_, i) => (
        <div key={i} className="h-3 bg-zinc-800 rounded" style={{ width: `${60 + (i % 3) * 15}%` }} />
      ))}
    </div>
  );
}

export function SkeletonKpiCard() {
  return (
    <div className="bg-darkCard border border-zinc-800 rounded-xl p-5 animate-pulse">
      <div className="flex items-center justify-between mb-4">
        <div className="h-3 w-28 bg-zinc-800 rounded" />
        <div className="h-8 w-8 bg-zinc-800 rounded-lg" />
      </div>
      <div className="h-9 w-36 bg-zinc-700/60 rounded mb-2" />
      <div className="h-3 w-20 bg-zinc-800 rounded" />
    </div>
  );
}

export function SkeletonRow({ cols = 4 }: { cols?: number }) {
  return (
    <tr className="border-b border-zinc-800/60">
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <div className="h-3 bg-zinc-800 rounded animate-pulse" style={{ width: `${50 + (i % 3) * 20}%` }} />
        </td>
      ))}
    </tr>
  );
}

export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="overflow-hidden rounded-xl border border-zinc-800">
      <table className="w-full">
        <thead className="bg-zinc-900/50">
          <tr>
            {Array.from({ length: cols }).map((_, i) => (
              <th key={i} className="px-4 py-3">
                <div className="h-3 w-16 bg-zinc-800 rounded animate-pulse" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }).map((_, i) => (
            <SkeletonRow key={i} cols={cols} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
