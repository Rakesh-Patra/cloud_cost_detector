import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { History as HistoryIcon, Loader2, AlertCircle, Calendar, ExternalLink, RefreshCw } from 'lucide-react';
import { insforge } from '../insforge';

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
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const fetchHistory = async () => {
    try {
      setLoading(true);
      setError('');
      
      const token = (insforge as any).tokenManager.getAccessToken();
      
      const headers = {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      };

      const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
      const response = await fetch(`${backendUrl}/api/history`, { headers });

      if (!response.ok) {
        throw new Error('Failed to retrieve history logs');
      }

      const data = await response.json();
      setHistory(data || []);
    } catch (err: any) {
      console.error('Error fetching history:', err);
      setError(err.message || 'Failed to load cost history.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  const handleViewReport = (item: HistoryItem) => {
    if (item.status !== 'completed') return;
    
    // Structure matches scanResult format
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

  const formatDate = (isoString: string) => {
    try {
      const date = new Date(isoString);
      return date.toLocaleString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch (e) {
      return isoString;
    }
  };

  return (
    <div className="min-h-[calc(100vh-73px)] bg-darkBg text-slate-100 p-8 relative overflow-hidden select-none">
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-brandIndigo/5 rounded-full blur-3xl" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-brandPurple/5 rounded-full blur-3xl" />

      <div className="max-w-4xl mx-auto relative z-10">
        {/* Title */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 bg-brandIndigo/10 border border-brandIndigo/25 rounded-2xl flex items-center justify-center shadow-lg shadow-brandIndigo/5">
              <HistoryIcon className="w-6 h-6 text-brandIndigo" />
            </div>
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-white">Cost Audit History</h1>
              <p className="text-zinc-400 text-sm mt-0.5">Review and compare past cloud optimization reports</p>
            </div>
          </div>

          <button
            onClick={fetchHistory}
            disabled={loading}
            className="p-2.5 bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-zinc-200 rounded-xl transition-all disabled:opacity-50"
            title="Refresh History"
          >
            <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {error && (
          <div className="mb-8 p-4 bg-red-950/30 border border-red-900/40 rounded-2xl flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-400 shrink-0" />
            <span className="text-red-300 text-sm font-medium">{error}</span>
          </div>
        )}

        {loading ? (
          <div className="h-64 flex flex-col items-center justify-center gap-3">
            <Loader2 className="w-8 h-8 text-brandIndigo animate-spin" />
            <span className="text-zinc-500 text-sm font-medium">Querying database logs...</span>
          </div>
        ) : history.length === 0 ? (
          <div className="p-12 text-center bg-zinc-900/20 border border-dashed border-zinc-800 rounded-3xl text-zinc-500">
            <HistoryIcon className="w-12 h-12 text-zinc-700 mx-auto mb-3" />
            <h4 className="text-white font-semibold">No Audit Records Found</h4>
            <p className="text-xs text-zinc-500 mt-1">Start a scan on the dashboard to populate logs.</p>
          </div>
        ) : (
          <div className="space-y-4">
            {history.map((item) => {
              const isCompleted = item.status === 'completed';
              const isRunning = item.status === 'running';
              const isFailed = item.status === 'failed';

              return (
                <div
                  key={item.id}
                  onClick={() => handleViewReport(item)}
                  className={`bg-darkCard/40 border border-zinc-800/80 rounded-2xl p-6 flex flex-wrap md:flex-nowrap items-center justify-between gap-6 transition-all ${
                    isCompleted
                      ? 'hover:border-zinc-700 hover:bg-darkCard/60 cursor-pointer'
                      : 'opacity-70 pointer-events-none'
                  }`}
                >
                  <div className="space-y-3 shrink-0">
                    <div className="flex items-center gap-3">
                      <span className="text-sm font-bold text-white uppercase font-mono">
                        {item.region}
                      </span>
                      
                      {/* Status badge */}
                      {isCompleted && (
                        <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 uppercase">
                          Completed
                        </span>
                      )}
                      {isRunning && (
                        <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-orange-500/10 text-orange-400 border border-orange-500/20 uppercase">
                          Running
                        </span>
                      )}
                      {isFailed && (
                        <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-red-500/10 text-red-400 border border-red-500/20 uppercase">
                          Failed
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-2 text-zinc-500 text-xs font-medium">
                      <Calendar className="w-3.5 h-3.5" />
                      <span>{formatDate(item.created_at)}</span>
                    </div>
                  </div>

                  {/* Summary Metrics */}
                  <div className="flex items-center gap-6 md:gap-12 flex-wrap">
                    <div className="text-center md:text-left">
                      <div className="text-[10px] uppercase font-bold tracking-wider text-zinc-500 font-mono">Scanned</div>
                      <div className="text-base font-bold text-zinc-300 mt-0.5">{item.resources_scanned} resources</div>
                    </div>

                    <div className="text-center md:text-left">
                      <div className="text-[10px] uppercase font-bold tracking-wider text-zinc-500 font-mono">Warnings</div>
                      <div className="text-base font-bold text-orange-400 mt-0.5">{item.issues_found} issues</div>
                    </div>

                    <div className="text-center md:text-left">
                      <div className="text-[10px] uppercase font-bold tracking-wider text-zinc-500 font-mono">Savings</div>
                      <div className="text-base font-bold text-emerald-400 mt-0.5">{item.estimated_savings}</div>
                    </div>
                  </div>

                  {/* External view indicator */}
                  {isCompleted && (
                    <div className="p-2 border border-zinc-800 bg-zinc-900/60 text-zinc-400 rounded-xl group-hover:text-zinc-200 group-hover:border-zinc-700 shrink-0">
                      <ExternalLink className="w-4 h-4" />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
