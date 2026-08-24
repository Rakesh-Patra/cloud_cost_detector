import { type ReactNode } from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface KpiCardProps {
  label: string;
  value: string | number;
  icon: ReactNode;
  /** Optional change value. Positive = good/green, negative = bad/red, undefined = neutral */
  change?: number;
  /** Description text below the value */
  sub?: string;
  /** Override the change direction interpretation. Set to 'inverted' if higher = worse (e.g., anomaly count). */
  changeMode?: 'normal' | 'inverted';
  loading?: boolean;
  className?: string;
}

export function KpiCard({
  label,
  value,
  icon,
  change,
  sub,
  changeMode = 'normal',
  loading = false,
  className = '',
}: KpiCardProps) {
  const isPositive = change !== undefined && change > 0;
  const isNegative = change !== undefined && change < 0;
  const isNeutral = change === undefined || change === 0;

  // For inverted mode (e.g., anomaly count), up = bad, down = good
  const trendGood = changeMode === 'inverted' ? isNegative : isPositive;
  const trendBad  = changeMode === 'inverted' ? isPositive : isNegative;

  if (loading) {
    return (
      <div className={`bg-darkCard border border-zinc-800 rounded-xl p-3.5 sm:p-5 animate-pulse ${className}`}>
        <div className="flex items-center justify-between mb-3 sm:mb-4">
          <div className="h-3 w-20 sm:w-28 bg-zinc-800 rounded" />
          <div className="h-7 w-7 sm:h-8 sm:w-8 bg-zinc-800 rounded-lg" />
        </div>
        <div className="h-7 sm:h-9 w-24 sm:w-36 bg-zinc-700/60 rounded mb-2" />
        <div className="h-3 w-16 sm:w-20 bg-zinc-800 rounded" />
      </div>
    );
  }

  return (
    <div className={`bg-darkCard border border-zinc-800 rounded-xl p-3.5 sm:p-5 hover:border-zinc-700 transition-colors ${className}`}>
      <div className="flex items-center justify-between mb-2.5 sm:mb-4">
        <span className="text-[10px] sm:text-xs font-medium text-zinc-500 uppercase tracking-wide truncate">{label}</span>
        <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 shrink-0">
          {icon}
        </div>
      </div>

      <div className="text-xl sm:text-2xl lg:text-3xl font-bold text-white tracking-tight mb-1.5 sm:mb-2 truncate">{value}</div>

      <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
        {!isNeutral && (
          <span className={`flex items-center gap-0.5 text-[11px] sm:text-xs font-semibold ${
            trendGood ? 'text-emerald-400' : trendBad ? 'text-red-400' : 'text-zinc-500'
          }`}>
            {trendGood && <TrendingUp className="w-3 h-3" />}
            {trendBad && <TrendingDown className="w-3 h-3" />}
            {isNeutral && <Minus className="w-3 h-3" />}
            {change !== undefined ? `${change > 0 ? '+' : ''}${change.toFixed(0)}%` : ''}
          </span>
        )}
        {sub && <span className="text-[10px] sm:text-xs text-zinc-500 truncate">{sub}</span>}
      </div>
    </div>
  );
}
