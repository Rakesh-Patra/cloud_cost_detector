import { useEffect, useState } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { formatCurrency, formatDate } from '../lib/format';
import { Card, CardHeader } from '../components/ui/Card';
import { SpendChartCard } from '../components/ui/SpendChart';
import { ErrorState } from '../components/ui/ErrorState';
import { EmptyState } from '../components/ui/EmptyState';
import { SkeletonRow } from '../components/ui/Skeleton';

interface SpendDay { date: string; amount: number }
interface Anomaly {
  date: string;
  amount: number;
  average: number;
  percent_increase: number;
}

type Severity = 'critical' | 'high' | 'medium' | 'low';

function getSeverity(percentIncrease: number): Severity {
  if (percentIncrease >= 100) return 'critical';
  if (percentIncrease >= 50)  return 'high';
  if (percentIncrease >= 20)  return 'medium';
  return 'low';
}

const SEVERITY_STYLES: Record<Severity, string> = {
  critical: 'bg-red-500/10 text-red-400 border-red-500/25',
  high:     'bg-orange-500/10 text-orange-400 border-orange-500/25',
  medium:   'bg-amber-500/10 text-amber-400 border-amber-500/25',
  low:      'bg-zinc-800 text-zinc-400 border-zinc-700',
};

type SeverityFilter = 'all' | Severity;

export default function Anomalies() {
  const [spendData, setSpendData] = useState<SpendDay[]>([]);
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [isSimulated, setIsSimulated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<SeverityFilter>('all');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await apiFetch<{
        spend_data: SpendDay[];
        anomalies: Anomaly[];
        is_simulated: boolean;
      }>('/api/budgets/spend');
      setSpendData(data.spend_data || []);
      setAnomalies(data.anomalies || []);
      setIsSimulated(!!data.is_simulated);
    } catch (err: any) {
      setError(err.message || 'Failed to load anomaly data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const enriched = anomalies.map(a => ({
    ...a,
    severity: getSeverity(a.percent_increase),
    difference: a.amount - a.average,
  }));

  const filtered = filter === 'all'
    ? enriched
    : enriched.filter(a => a.severity === filter);

  const counts = {
    critical: enriched.filter(a => a.severity === 'critical').length,
    high:     enriched.filter(a => a.severity === 'high').length,
    medium:   enriched.filter(a => a.severity === 'medium').length,
    low:      enriched.filter(a => a.severity === 'low').length,
  };

  const FILTERS: { value: SeverityFilter; label: string; count?: number }[] = [
    { value: 'all',      label: 'All',      count: enriched.length },
    { value: 'critical', label: 'Critical', count: counts.critical },
    { value: 'high',     label: 'High',     count: counts.high },
    { value: 'medium',   label: 'Medium',   count: counts.medium },
    { value: 'low',      label: 'Low',      count: counts.low },
  ];

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">

      {/* Summary KPI row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {(['critical', 'high', 'medium', 'low'] as Severity[]).map(sev => (
          <div
            key={sev}
            className={`bg-darkCard border rounded-xl p-4 cursor-pointer transition-all ${
              filter === sev ? 'ring-1 ring-indigo-500/50 border-indigo-500/30' : 'border-zinc-800 hover:border-zinc-700'
            }`}
            onClick={() => setFilter(f => f === sev ? 'all' : sev)}
          >
            <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500 capitalize mb-2">{sev}</p>
            <p className={`text-2xl font-bold ${
              sev === 'critical' ? 'text-red-400'
              : sev === 'high' ? 'text-orange-400'
              : sev === 'medium' ? 'text-amber-400'
              : 'text-zinc-400'
            }`}>{counts[sev]}</p>
            <p className="text-[11px] text-zinc-600 mt-1">anomalies</p>
          </div>
        ))}
      </div>

      {/* Spend chart */}
      <SpendChartCard
        title="Spend Timeline with Anomalies"
        description="Red markers indicate detected cost spikes"
        spendData={spendData}
        anomalies={anomalies}
        isSimulated={isSimulated}
        loading={loading}
        onRefresh={load}
      />

      {/* Anomaly detail table */}
      <Card>
        <CardHeader
          title="Anomaly Details"
          description="Cost spikes exceeding rolling 7-day baseline by >20%"
          icon={<AlertTriangle className="w-4 h-4" />}
          action={
            <div className="flex items-center gap-2">
              {/* Severity filters */}
              <div className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 rounded-lg p-1">
                {FILTERS.map(f => (
                  <button
                    key={f.value}
                    onClick={() => setFilter(f.value)}
                    className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-colors ${
                      filter === f.value
                        ? 'bg-indigo-600 text-white'
                        : 'text-zinc-500 hover:text-zinc-300'
                    }`}
                  >
                    {f.label}
                    {f.count !== undefined && f.count > 0 && (
                      <span className="ml-1 opacity-70">({f.count})</span>
                    )}
                  </button>
                ))}
              </div>
              <button
                onClick={load}
                disabled={loading}
                className="p-1.5 rounded-lg border border-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          }
        />

        {error ? (
          <ErrorState message={error} onRetry={load} className="py-12" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-zinc-800 bg-zinc-900/40">
                <tr>
                  <th className="px-5 py-3 text-left text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Date</th>
                  <th className="px-5 py-3 text-right text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Actual Spend</th>
                  <th className="px-5 py-3 text-right text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Expected</th>
                  <th className="px-5 py-3 text-right text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Difference</th>
                  <th className="px-5 py-3 text-right text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">% Increase</th>
                  <th className="px-5 py-3 text-center text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Severity</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60">
                {loading ? (
                  Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} cols={6} />)
                ) : filtered.length === 0 ? (
                  <tr>
                    <td colSpan={6}>
                      <EmptyState
                        icon={<AlertTriangle className="w-6 h-6" />}
                        title="No anomalies detected"
                        description={
                          filter !== 'all'
                            ? `No ${filter} severity anomalies in the last 14 days.`
                            : 'Your cloud spend looks stable over the past 14 days. Great job!'
                        }
                      />
                    </td>
                  </tr>
                ) : (
                  filtered.map((a, i) => (
                    <tr key={i} className="text-zinc-300 hover:bg-zinc-900/30 transition-colors">
                      <td className="px-5 py-3.5 text-xs font-medium">{formatDate(a.date)}</td>
                      <td className="px-5 py-3.5 text-xs text-right font-semibold text-white tabular-nums">
                        {formatCurrency(a.amount)}
                      </td>
                      <td className="px-5 py-3.5 text-xs text-right text-zinc-500 tabular-nums">
                        {formatCurrency(a.average)}
                      </td>
                      <td className="px-5 py-3.5 text-xs text-right text-red-400 font-semibold tabular-nums">
                        +{formatCurrency(a.difference)}
                      </td>
                      <td className="px-5 py-3.5 text-xs text-right text-red-400 font-semibold tabular-nums">
                        +{a.percent_increase.toFixed(1)}%
                      </td>
                      <td className="px-5 py-3.5 text-center">
                        <span className={`inline-flex items-center px-2 py-0.5 text-[11px] font-semibold rounded border ${SEVERITY_STYLES[a.severity]} font-mono uppercase`}>
                          {a.severity}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
