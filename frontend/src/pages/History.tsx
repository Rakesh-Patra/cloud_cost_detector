import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { History as HistoryIcon, RefreshCw, ExternalLink, Search } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { formatDateTime, parseSavingsString, formatCurrency } from '../lib/format';
import { StatusBadge } from '../components/ui/Badge';
import { Card, CardHeader } from '../components/ui/Card';
import { ErrorState } from '../components/ui/ErrorState';
import { EmptyState } from '../components/ui/EmptyState';
import { SkeletonRow } from '../components/ui/Skeleton';

interface HistoryItem {
  id: string;
  region: string;
  resources_scanned: number;
  issues_found: number;
  estimated_savings: string;
  status: 'completed' | 'failed' | 'running';
  analysis_result: any;
  created_at: string;
}

export default function History() {
  const navigate = useNavigate();
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');

  const fetchHistory = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await apiFetch<HistoryItem[]>('/api/history');
      setHistory(data || []);
    } catch (err: any) {
      setError(err.message || 'Failed to load audit history.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchHistory(); }, []);

  const handleViewReport = (item: HistoryItem) => {
    if (item.status !== 'completed') return;
    navigate('/report', {
      state: {
        scanResult: {
          analysis_id: item.id,
          region: item.region,
          count: item.resources_scanned,
          analysis: item.analysis_result,
        },
      },
    });
  };

  const filtered = history.filter(h =>
    !search || h.region.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-3.5 sm:p-5 md:p-6 max-w-5xl mx-auto space-y-4 sm:space-y-6">
      <Card>
        <CardHeader
          title="Audit History"
          description="Past AWS cost optimization scans"
          icon={<HistoryIcon className="w-4 h-4" />}
          action={
            <div className="flex items-center gap-2">
              {/* Search */}
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-zinc-600" />
                <input
                  type="text"
                  placeholder="Filter by region…"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  className="pl-8 pr-3 py-2 text-xs bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-300 placeholder-zinc-600 focus:outline-none focus:border-indigo-500 transition-colors w-44"
                />
              </div>
              <button
                onClick={fetchHistory}
                disabled={loading}
                className="p-2 rounded-lg border border-zinc-800 text-zinc-500 hover:text-zinc-300 hover:border-zinc-700 transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          }
        />

        {error ? (
          <ErrorState
            message={error}
            onRetry={fetchHistory}
            className="py-12"
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-zinc-800 bg-zinc-900/40">
                <tr>
                  <th className="px-5 py-3 text-left text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Region</th>
                  <th className="px-5 py-3 text-left text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Date</th>
                  <th className="px-5 py-3 text-right text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Scanned</th>
                  <th className="px-5 py-3 text-right text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Issues</th>
                  <th className="px-5 py-3 text-right text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Savings</th>
                  <th className="px-5 py-3 text-center text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Status</th>
                  <th className="px-5 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60">
                {loading ? (
                  Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} cols={7} />)
                ) : filtered.length === 0 ? (
                  <tr>
                    <td colSpan={7}>
                      <EmptyState
                        icon={<HistoryIcon className="w-6 h-6" />}
                        title={search ? 'No results match your filter' : 'No audit records yet'}
                        description={search ? 'Try a different region name.' : 'Run a scan from the Dashboard to start tracking history.'}
                      />
                    </td>
                  </tr>
                ) : (
                  filtered.map(item => {
                    const savings = parseSavingsString(item.estimated_savings);
                    return (
                      <tr
                        key={item.id}
                        onClick={() => handleViewReport(item)}
                        className={`text-zinc-300 hover:bg-zinc-900/40 transition-colors ${
                          item.status === 'completed' ? 'cursor-pointer' : 'opacity-60'
                        }`}
                      >
                        <td className="px-5 py-3.5 font-mono text-xs font-semibold text-white uppercase">{item.region}</td>
                        <td className="px-5 py-3.5 text-xs text-zinc-500 whitespace-nowrap">{formatDateTime(item.created_at)}</td>
                        <td className="px-5 py-3.5 text-xs text-right tabular-nums">{item.resources_scanned.toLocaleString()}</td>
                        <td className="px-5 py-3.5 text-xs text-right tabular-nums text-amber-400 font-semibold">{item.issues_found}</td>
                        <td className="px-5 py-3.5 text-xs text-right tabular-nums text-emerald-400 font-semibold">
                          {savings > 0 ? formatCurrency(savings) : '—'}
                        </td>
                        <td className="px-5 py-3.5 text-center">
                          <StatusBadge status={item.status} />
                        </td>
                        <td className="px-5 py-3.5 text-zinc-600">
                          {item.status === 'completed' && <ExternalLink className="w-3.5 h-3.5" />}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
