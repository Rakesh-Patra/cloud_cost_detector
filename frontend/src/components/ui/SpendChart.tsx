import { useRef, useState, useEffect, type ReactNode } from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';

interface SpendDay {
  date: string;
  amount: number;
}

interface Anomaly {
  date: string;
  amount: number;
  average: number;
  percent_increase: number;
}

interface SpendChartProps {
  spendData: SpendDay[];
  anomalies?: Anomaly[];
  /** Threshold line to show on chart (monthly budget / 30) */
  dailyThreshold?: number;
  emptyMessage?: string;
}

type HoveredPoint = { x: number; y: number; date: string; amount: number } | null;

export function SpendChart({ spendData, anomalies = [], dailyThreshold, emptyMessage }: SpendChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [chartWidth, setChartWidth] = useState(600);
  const [hoveredPoint, setHoveredPoint] = useState<HoveredPoint>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(entries => {
      for (const entry of entries) setChartWidth(entry.contentRect.width);
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  if (!spendData || spendData.length === 0) {
    return (
      <div className="h-48 flex flex-col items-center justify-center gap-2 text-zinc-500">
        <AlertCircle className="w-5 h-5 text-zinc-700" />
        <span className="text-xs">{emptyMessage ?? 'No spend data available.'}</span>
      </div>
    );
  }

  const height = 220;
  const pad = { left: 50, right: 16, top: 16, bottom: 28 };
  const plotW = chartWidth - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const values = spendData.map(d => d.amount);
  const maxVal = Math.max(...values, dailyThreshold ?? 0, 1) * 1.18;
  const minVal = 0;

  const toX = (i: number) => pad.left + (i * plotW) / Math.max(spendData.length - 1, 1);
  const toY = (v: number) => pad.top + plotH - ((v - minVal) * plotH) / (maxVal - minVal);

  const points = spendData.map((d, i) => ({ x: toX(i), y: toY(d.amount), date: d.date, amount: d.amount }));

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
  const areaPath = [
    ...points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`),
    `L ${points[points.length - 1].x.toFixed(1)} ${(pad.top + plotH).toFixed(1)}`,
    `L ${points[0].x.toFixed(1)} ${(pad.top + plotH).toFixed(1)}`,
    'Z',
  ].join(' ');

  const gridCount = 4;
  const gridLines = Array.from({ length: gridCount }, (_, i) => {
    const ratio = i / (gridCount - 1);
    return { y: pad.top + ratio * plotH, val: maxVal - ratio * (maxVal - minVal) };
  });

  const anomalyDates = new Set(anomalies.map(a => a.date));

  const thresholdY = dailyThreshold !== undefined ? toY(dailyThreshold) : null;

  return (
    <div className="relative select-none" ref={containerRef}>
      <svg width={chartWidth} height={height} className="overflow-visible">
        <defs>
          <linearGradient id="spendAreaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#6366f1" stopOpacity="0.20" />
            <stop offset="100%" stopColor="#6366f1" stopOpacity="0.00" />
          </linearGradient>
        </defs>

        {/* Grid lines */}
        {gridLines.map((gl, i) => (
          <g key={i}>
            <line
              x1={pad.left} y1={gl.y.toFixed(1)}
              x2={chartWidth - pad.right} y2={gl.y.toFixed(1)}
              stroke="#27272a" strokeDasharray="3 4" strokeWidth="1"
            />
            <text
              x={pad.left - 6} y={(gl.y + 4).toFixed(1)}
              fill="#52525b" fontSize="9" textAnchor="end" fontFamily="monospace"
            >
              ${gl.val.toFixed(0)}
            </text>
          </g>
        ))}

        {/* Daily threshold line */}
        {thresholdY !== null && (
          <>
            <line
              x1={pad.left} y1={thresholdY!.toFixed(1)}
              x2={chartWidth - pad.right} y2={thresholdY!.toFixed(1)}
              stroke="#f59e0b" strokeDasharray="5 4" strokeWidth="1.5" opacity="0.6"
            />
            <text x={chartWidth - pad.right + 4} y={(thresholdY! + 4).toFixed(1)}
              fill="#f59e0b" fontSize="9" fontFamily="monospace" opacity="0.8"
            >cap</text>
          </>
        )}

        {/* Area fill */}
        <path d={areaPath} fill="url(#spendAreaGrad)" />

        {/* Line */}
        <path d={linePath} fill="none" stroke="#6366f1" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />

        {/* Data points */}
        {points.map((p, i) => {
          const isAnomaly = anomalyDates.has(p.date);
          const isHovered = hoveredPoint?.date === p.date;
          return (
            <g key={i}>
              <circle
                cx={p.x} cy={p.y} r={14} fill="transparent" className="cursor-pointer"
                onMouseEnter={() => setHoveredPoint(p)}
                onMouseLeave={() => setHoveredPoint(null)}
              />
              {isAnomaly ? (
                <>
                  <circle cx={p.x} cy={p.y} r={8} fill="#ef4444" opacity="0.25" className="animate-ping" />
                  <circle cx={p.x} cy={p.y} r={5} fill="#ef4444" stroke="#090a0f" strokeWidth="1.5" />
                </>
              ) : isHovered ? (
                <circle cx={p.x} cy={p.y} r={4} fill="#6366f1" stroke="#fff" strokeWidth="1.5" />
              ) : null}
            </g>
          );
        })}

        {/* X-axis labels */}
        {points.map((p, i) => {
          if (i % 2 !== 0 && i !== points.length - 1) return null;
          const d = new Date(p.date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
          return (
            <text key={i} x={p.x} y={height - 6} fill="#52525b" fontSize="9" textAnchor="middle">
              {d}
            </text>
          );
        })}
      </svg>

      {/* Tooltip */}
      {hoveredPoint && (
        <div
          className="absolute z-20 pointer-events-none bg-zinc-950/95 border border-zinc-800 rounded-xl p-3 shadow-xl text-xs flex flex-col gap-1 backdrop-blur-md min-w-[130px]"
          style={{ left: `${hoveredPoint.x - 65}px`, top: `${hoveredPoint.y - 72}px` }}
        >
          <span className="text-zinc-400">
            {new Date(hoveredPoint.date).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}
          </span>
          <span className="text-white font-bold text-sm">${hoveredPoint.amount.toFixed(2)}</span>
          {anomalyDates.has(hoveredPoint.date) && (
            <span className="text-red-400 font-semibold text-[10px] uppercase tracking-wide flex items-center gap-1">
              <AlertCircle className="w-2.5 h-2.5" /> Anomaly
            </span>
          )}
        </div>
      )}
    </div>
  );
}

interface SpendChartCardProps extends SpendChartProps {
  title?: string;
  description?: string;
  loading?: boolean;
  onRefresh?: () => void;
  isSimulated?: boolean;
  children?: ReactNode;
}

export function SpendChartCard({
  title = '14-Day Spend Trend',
  description,
  loading = false,
  onRefresh,
  isSimulated,
  children,
  ...chartProps
}: SpendChartCardProps) {
  return (
    <div className="bg-darkCard border border-zinc-800 rounded-xl">
      <div className="flex items-start justify-between gap-4 p-5 border-b border-zinc-800">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-white">{title}</h3>
            {isSimulated && (
              <span className="px-1.5 py-0.5 text-[10px] font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded font-mono">
                SIMULATED
              </span>
            )}
          </div>
          {description && <p className="text-xs text-zinc-500 mt-0.5">{description}</p>}
        </div>
        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={loading}
            className="p-1.5 rounded-lg border border-zinc-800 text-zinc-500 hover:text-zinc-300 hover:border-zinc-700 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        )}
      </div>

      <div className="p-5">
        {loading ? (
          <div className="h-[220px] flex items-center justify-center">
            <div className="h-full w-full bg-zinc-900/40 rounded-lg animate-pulse" />
          </div>
        ) : (
          <SpendChart {...chartProps} />
        )}
        {children}
      </div>
    </div>
  );
}
