import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Play, Loader2, CloudLightning, DollarSign,
  Cpu, AlertCircle, BarChart3, History, PlusCircle, Shield
} from 'lucide-react';
import { apiFetch, getWsBaseUrl, getCloudAccounts, type CloudAccount } from '../lib/api';
import { formatCurrency, parseSavingsString, formatDateTime } from '../lib/format';
import { KpiCard } from '../components/ui/KpiCard';
import { Card, CardHeader, CardContent } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorState';
import { StatusBadge } from '../components/ui/Badge';
import ProgressTracker from '../components/ProgressTracker';
import { ConnectCloudModal } from '../components/ConnectCloudModal';
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

interface DashboardProps {
  /** When true, scrolls to / focuses the scan launcher on mount */
  scanMode?: boolean;
}

const DEFAULT_REGIONS = [
  'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
  'ap-south-1', 'ap-northeast-1', 'ap-southeast-1', 'eu-west-1', 'eu-central-1',
];

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export default function Dashboard({ scanMode: _scanMode }: DashboardProps) {
  const navigate = useNavigate();

  // Multi-tenant cloud accounts
  const [cloudAccounts, setCloudAccounts] = useState<CloudAccount[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  const [isConnectModalOpen, setIsConnectModalOpen] = useState(false);

  // Scan state
  const [regions, setRegions] = useState<string[]>([]);
  const [selectedRegion, setSelectedRegion] = useState('us-east-1');
  const [loadingRegions, setLoadingRegions] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [progressLogs, setProgressLogs] = useState<string[]>([]);
  const [scanError, setScanError] = useState(false);
  const [scanErrorMsg, setScanErrorMsg] = useState('');

  // History / KPI state
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);

  const loadAccounts = async () => {
    try {
      const res = await getCloudAccounts();
      const rawAccs = res.accounts || [];
      const accs = Array.from(new Map(rawAccs.map(a => [a.id, a])).values());
      setCloudAccounts(accs);
      if (accs.length > 0) {
        setSelectedAccountId(prev => (prev && accs.some(a => a.id === prev) ? prev : accs[0].id));
      } else {
        setSelectedAccountId('');
      }
    } catch {
      setCloudAccounts([]);
      setSelectedAccountId('');
    }
  };

  useEffect(() => {
    const loadRegions = async () => {
      try {
        setLoadingRegions(true);
        const data = await apiFetch<{ regions: string[] }>('/api/regions');
        const list = data?.regions?.length ? data.regions : DEFAULT_REGIONS;
        setRegions(list);
        setSelectedRegion(list.includes('us-east-1') ? 'us-east-1' : list[0]);
      } catch {
        setRegions(DEFAULT_REGIONS);
        setSelectedRegion('us-east-1');
      } finally {
        setLoadingRegions(false);
      }
    };

    const loadHistory = async () => {
      try {
        setLoadingHistory(true);
        const data = await apiFetch<HistoryItem[]>('/api/history');
        setHistory(data || []);
      } catch {
        setHistory([]);
      } finally {
        setLoadingHistory(false);
      }
    };

    loadAccounts();
    loadRegions();
    loadHistory();

    const handleAccountsUpdated = () => {
      loadAccounts();
    };

    window.addEventListener('cloud-accounts-updated', handleAccountsUpdated);
    return () => {
      window.removeEventListener('cloud-accounts-updated', handleAccountsUpdated);
    };
  }, []);

  // Derive KPIs from history
  const completedScans = history.filter(h => h.status === 'completed');
  const totalResources = completedScans.reduce((s, h) => s + (h.resources_scanned || 0), 0);
  const totalIssues = completedScans.reduce((s, h) => s + (h.issues_found || 0), 0);
  const totalSavings = completedScans.reduce((s, h) => s + parseSavingsString(h.estimated_savings), 0);

  const handleStartScan = async () => {
    if (!selectedRegion || scanning) return;
    setScanning(true);
    setScanError(false);
    setScanErrorMsg('');
    setProgressLogs(['Initializing AWS clients...']);

    const analysisId = crypto.randomUUID();

    // WebSocket for live progress (best-effort, with heartbeat handling)
    let ws: WebSocket | null = null;
    try {
      const token = (insforge as any).tokenManager.getAccessToken() || '';
      const wsBase = getWsBaseUrl();
      ws = new WebSocket(`${wsBase}/ws/progress/${analysisId}?token=${token}`);
      ws.onopen = () => {
        // Send initial ping to confirm bidirectional channel
        try { ws?.send('ping'); } catch {}
      };
      ws.onmessage = (e) => {
        if (typeof e.data === 'string') {
          // Filter out heartbeat ping frames
          if (e.data.includes('"type": "ping"') || e.data === 'pong') {
            try { ws?.send('pong'); } catch {}
            return;
          }
          setProgressLogs(prev => [...prev, e.data]);
          if (e.data.toLowerCase().includes('fail') || e.data.toLowerCase().includes('error')) {
            setScanError(true);
          }
        }
      };
      ws.onerror = () => console.warn('WS progress unavailable');
    } catch {
      console.warn('WebSocket setup failed — scan proceeds without live progress');
    }

    // Progressive step timers to ensure smooth visual feedback
    const timer1 = setTimeout(() => {
      setProgressLogs(prev => [...prev, `Scanning EC2, EBS, and RDS resources in ${selectedRegion}...`]);
    }, 2000);
    const timer2 = setTimeout(() => {
      setProgressLogs(prev => [...prev, 'Generating structured cost analysis via Gemini AI...']);
    }, 5000);
    const timer3 = setTimeout(() => {
      setProgressLogs(prev => [...prev, 'Persisting audit metrics to InsForge Cloud...']);
    }, 8000);

    try {
      const payloadBody: any = { region: selectedRegion, analysis_id: analysisId };
      if (selectedAccountId) {
        payloadBody.account_id = selectedAccountId;
      }

      const data = await apiFetch('/api/analyze', {
        method: 'POST',
        body: JSON.stringify(payloadBody),
      });

      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);
      setProgressLogs(prev => [...prev, 'Analysis complete']);

      sessionStorage.setItem('latestScanResult', JSON.stringify(data));
      navigate('/report', { state: { scanResult: data } });
    } catch (err: any) {
      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);
      setScanError(true);
      const msg = err.message || 'An error occurred during scanning.';
      setScanErrorMsg(msg);
      setProgressLogs(prev => [...prev, `Analysis failed: ${msg}`]);
    } finally {
      setScanning(false);
      try { ws?.close(); } catch {}
    }
  };

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

  return (
    <div className="p-3.5 sm:p-5 md:p-6 space-y-4 sm:space-y-6 max-w-7xl mx-auto">

      {/* KPI Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5 sm:gap-4">
        <KpiCard
          label="Total Scans"
          value={loadingHistory ? '—' : history.length}
          icon={<History className="w-4 h-4" />}
          loading={loadingHistory}
          sub="all time"
        />
        <KpiCard
          label="Resources Scanned"
          value={loadingHistory ? '—' : totalResources.toLocaleString()}
          icon={<Cpu className="w-4 h-4" />}
          loading={loadingHistory}
          sub="across all scans"
        />
        <KpiCard
          label="Potential Savings"
          value={loadingHistory ? '—' : formatCurrency(totalSavings)}
          icon={<DollarSign className="w-4 h-4" />}
          loading={loadingHistory}
          sub="identified so far"
        />
        <KpiCard
          label="Issues Found"
          value={loadingHistory ? '—' : totalIssues}
          icon={<AlertCircle className="w-4 h-4" />}
          loading={loadingHistory}
          changeMode="inverted"
          sub="optimization gaps"
        />
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-1 xl:grid-cols-5 gap-4 sm:gap-6">

        {/* Scan Launcher */}
        <div className="xl:col-span-3">
          <Card>
            <CardHeader
              title="Run AWS Cost Scan"
              description="AI-powered audit of EC2, EBS, RDS, and S3 resources"
              icon={<CloudLightning className="w-4 h-4" />}
            />
            <CardContent className="space-y-6">
              {scanErrorMsg && <ErrorBanner message={scanErrorMsg} />}

              {/* Cloud Account selector (Multi-Tenant STS) */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
                    Connected AWS Account
                  </label>
                  <button
                    type="button"
                    onClick={() => setIsConnectModalOpen(true)}
                    className="text-xs text-indigo-400 hover:text-indigo-300 font-medium flex items-center gap-1 transition"
                  >
                    <PlusCircle className="w-3.5 h-3.5" />
                    <span>Connect AWS (1-Click)</span>
                  </button>
                </div>

                <select
                  value={selectedAccountId}
                  onChange={e => setSelectedAccountId(e.target.value)}
                  disabled={scanning || cloudAccounts.length === 0}
                  className="w-full px-3 py-2.5 bg-zinc-900 border border-zinc-800 rounded-lg text-sm text-white focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors disabled:opacity-50"
                >
                  {cloudAccounts.length === 0 ? (
                    <option value="">No AWS Account Connected — Click "+ Connect AWS" above</option>
                  ) : (
                    cloudAccounts.map(acc => (
                      <option key={acc.id} value={acc.id}>
                        {acc.account_alias} ({acc.aws_account_id}) — STS AssumeRole
                      </option>
                    ))
                  )}
                </select>

                {cloudAccounts.length === 0 && (
                  <div className="p-3 bg-indigo-950/30 border border-indigo-500/20 rounded-lg flex items-start gap-2.5 text-xs text-indigo-200">
                    <Shield className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-semibold text-indigo-300">Multi-Tenant Isolation:</span> Please connect your AWS Cloud Account via 1-Click CloudFormation before initiating an audit. No permanent AWS root keys are stored.
                    </div>
                  </div>
                )}
              </div>

              {/* Region selector */}
              <div className="space-y-2">
                <label className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
                  Target AWS Region
                </label>
                {loadingRegions ? (
                  <div className="h-10 bg-zinc-900 border border-zinc-800 rounded-lg animate-pulse" />
                ) : (
                  <select
                    value={selectedRegion}
                    onChange={e => setSelectedRegion(e.target.value)}
                    disabled={scanning}
                    className="w-full px-3 py-2.5 bg-zinc-900 border border-zinc-800 rounded-lg text-sm text-white focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors disabled:opacity-50"
                  >
                    {regions.map(r => (
                      <option key={r} value={r}>{r}</option>
                    ))}
                  </select>
                )}
              </div>

              {/* Progress tracker shown while scanning */}
              {scanning && (
                <ProgressTracker
                  progressLogs={progressLogs}
                  isError={scanError}
                  region={selectedRegion}
                />
              )}

              {/* Start button */}
              <button
                onClick={handleStartScan}
                disabled={scanning || loadingRegions || !selectedRegion || !selectedAccountId}
                className="w-full py-3 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-lg flex items-center justify-center gap-2 transition-colors disabled:opacity-50 disabled:pointer-events-none shadow-lg shadow-indigo-500/15"
              >
                {scanning ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Scanning…
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 fill-current" />
                    {cloudAccounts.length === 0 ? 'Connect AWS Account to Scan' : 'Run Optimization Analysis'}
                  </>
                )}
              </button>
            </CardContent>
          </Card>
        </div>

        {/* Recent scans */}
        <div className="xl:col-span-2">
          <Card className="h-full">
            <CardHeader
              title="Recent Scans"
              description="Last 5 audit runs"
              icon={<BarChart3 className="w-4 h-4" />}
            />
            <CardContent className="p-0">
              {loadingHistory ? (
                <div className="divide-y divide-zinc-800">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="flex items-center justify-between px-5 py-3 animate-pulse">
                      <div className="space-y-1.5">
                        <div className="h-3 w-24 bg-zinc-800 rounded" />
                        <div className="h-2.5 w-16 bg-zinc-900 rounded" />
                      </div>
                      <div className="h-4 w-14 bg-zinc-800 rounded" />
                    </div>
                  ))}
                </div>
              ) : history.length === 0 ? (
                <EmptyState
                  icon={<History className="w-6 h-6" />}
                  title="No scans yet"
                  description="Run your first cost audit using the scan launcher."
                />
              ) : (
                <div className="divide-y divide-zinc-800/60">
                  {history.slice(0, 5).map(item => (
                    <button
                      key={item.id}
                      onClick={() => handleViewReport(item)}
                      disabled={item.status !== 'completed'}
                      className="w-full flex items-center justify-between px-5 py-3 hover:bg-zinc-900/40 transition-colors disabled:opacity-60 disabled:pointer-events-none text-left"
                    >
                      <div className="min-w-0">
                        <p className="text-xs font-semibold text-white font-mono uppercase">{item.region}</p>
                        <p className="text-[11px] text-zinc-500 mt-0.5">{formatDateTime(item.created_at)}</p>
                      </div>
                      <div className="flex items-center gap-3 shrink-0">
                        {item.status === 'completed' && (
                          <span className="text-xs font-semibold text-emerald-400">
                            {item.estimated_savings}
                          </span>
                        )}
                        <StatusBadge status={item.status} />
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* 1-Click AWS Connect Modal */}
      <ConnectCloudModal
        isOpen={isConnectModalOpen}
        onClose={() => setIsConnectModalOpen(false)}
        onAccountConnected={(acc) => {
          setCloudAccounts(prev => [acc, ...prev]);
          setSelectedAccountId(acc.id);
        }}
      />
    </div>
  );
}
