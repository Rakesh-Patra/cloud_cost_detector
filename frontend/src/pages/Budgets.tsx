import { useEffect, useState } from 'react';
import {
  Plus, Trash2, Save, Bell, Play, Loader2, Mail, DollarSign, AlertCircle
} from 'lucide-react';
import { apiFetch } from '../lib/api';
import { insforge } from '../insforge';
import { Card, CardHeader, CardContent } from '../components/ui/Card';
import { StatusBadge } from '../components/ui/Badge';
import { ErrorBanner } from '../components/ui/ErrorState';
import { EmptyState } from '../components/ui/EmptyState';
import { Toast, ToastContainer } from '../components/ui/Toast';
import { SpendChartCard } from '../components/ui/SpendChart';
import { SkeletonRow } from '../components/ui/Skeleton';

interface BudgetConfig { threshold: number; emails: string[] }
interface AlertLog {
  id: string; date: string;
  details: { amount: number; average: number; percent_increase: number };
  status: string; channels: string[]; created_at: string;
}
interface SpendDay { date: string; amount: number }
interface Anomaly { date: string; amount: number; average: number; percent_increase: number }

export default function Budgets() {
  const [config, setConfig] = useState<BudgetConfig>({ threshold: 1000, emails: [] });
  const [logs, setLogs] = useState<AlertLog[]>([]);
  const [spendData, setSpendData] = useState<SpendDay[]>([]);
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [isSimulated, setIsSimulated] = useState(false);

  const [loadingConfig, setLoadingConfig] = useState(true);
  const [loadingSpend, setLoadingSpend] = useState(true);
  const [saving, setSaving] = useState(false);
  const [scanning, setScanning] = useState(false);

  const [error, setError] = useState('');
  const [toast, setToast] = useState<{ title: string; message: string; type?: 'success' | 'info' } | null>(null);
  const [scanResult, setScanResult] = useState<any>(null);

  const loadBudgets = async () => {
    setLoadingConfig(true);
    setError('');
    try {
      const data = await apiFetch<{ config: BudgetConfig; logs: AlertLog[] }>('/api/budgets');
      const loadedConfig = data.config || { threshold: 1000, emails: [] };
      if (!loadedConfig.emails?.length) {
        const u = (insforge as any).tokenManager.getUser();
        if (u?.email) loadedConfig.emails = [u.email];
      }
      setConfig(loadedConfig);
      setLogs(data.logs || []);
    } catch (err: any) {
      setError(err.message || 'Failed to load budget configuration.');
    } finally {
      setLoadingConfig(false);
    }
  };

  const loadSpend = async () => {
    setLoadingSpend(true);
    try {
      const data = await apiFetch<{ spend_data: SpendDay[]; anomalies: Anomaly[]; is_simulated: boolean }>('/api/budgets/spend');
      setSpendData(data.spend_data || []);
      setAnomalies(data.anomalies || []);
      setIsSimulated(!!data.is_simulated);
    } catch { /* non-critical */ }
    finally { setLoadingSpend(false); }
  };

  useEffect(() => { loadBudgets(); loadSpend(); }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    const cleanEmails = config.emails.map(e => e.trim()).filter(Boolean);
    try {
      await apiFetch('/api/budgets', {
        method: 'POST',
        body: JSON.stringify({ threshold: config.threshold, emails: cleanEmails }),
      });
      setConfig(p => ({ ...p, emails: cleanEmails }));
      setToast({ title: 'Configuration Saved', message: 'Budget threshold and alert channels updated.' });
    } catch (err: any) {
      setError(err.message || 'Failed to save budget settings.');
    } finally {
      setSaving(false);
    }
  };

  const handleTriggerScan = async () => {
    setScanning(true);
    setError('');
    setScanResult(null);
    try {
      const result = await apiFetch<any>('/api/budgets/trigger-scan', { method: 'POST' });
      setScanResult(result);
      if (result.success) {
        setToast({ title: 'Scan Complete', message: result.message || 'Anomaly scan finished.' });
        await loadBudgets();
      }
    } catch (err: any) {
      setError(err.message || 'Manual scan failed.');
    } finally {
      setScanning(false);
    }
  };

  const dailyThreshold = config.threshold > 0 ? config.threshold / 30 : undefined;

  return (
    <div className="p-3.5 sm:p-5 md:p-6 max-w-6xl mx-auto space-y-4 sm:space-y-6">

      {error && <ErrorBanner message={error} />}

      {isSimulated && (
        <div className="flex items-start gap-2.5 sm:gap-3 p-3 sm:p-4 rounded-lg bg-amber-500/8 border border-amber-500/20">
          <AlertCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <div>
            <p className="text-xs font-semibold text-amber-400">Simulated Spend Data</p>
            <p className="text-[11px] sm:text-xs text-zinc-500 mt-0.5 leading-relaxed">
              AWS Cost Explorer is preparing data (up to 24 hours). Charts and alerts are running on high-fidelity simulated data scaled to your monthly cap.
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 sm:gap-6">

        {/* Budget Config Form */}
        <div className="lg:col-span-2">
          <Card className="h-full">
            <CardHeader
              title="Budget Configuration"
              description="Set monthly spend cap and alert channels"
              icon={<DollarSign className="w-4 h-4" />}
            />
            <CardContent>
              <form onSubmit={handleSave} className="space-y-6">
                {/* Threshold */}
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
                    Monthly Cap (USD)
                  </label>
                  <div className="relative">
                    <span className="absolute left-3 top-2.5 text-zinc-500 text-sm">$</span>
                    <input
                      type="number"
                      value={config.threshold || ''}
                      onChange={e => setConfig(p => ({ ...p, threshold: parseFloat(e.target.value) || 0 }))}
                      disabled={loadingConfig}
                      placeholder="1000.00"
                      className="w-full pl-7 pr-4 py-2.5 bg-zinc-900 border border-zinc-800 rounded-lg text-sm text-white focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors disabled:opacity-50"
                    />
                  </div>
                </div>

                {/* Email list */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold uppercase tracking-wide text-zinc-500 flex items-center gap-1.5">
                      <Mail className="w-3 h-3" /> Alert Emails
                    </label>
                    <button
                      type="button"
                      onClick={() => setConfig(p => ({ ...p, emails: [...p.emails, ''] }))}
                      className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 transition-colors"
                    >
                      <Plus className="w-3 h-3" /> Add
                    </button>
                  </div>

                  <div className="space-y-2 max-h-40 overflow-y-auto">
                    {config.emails.length === 0 ? (
                      <p className="text-xs text-zinc-600 italic">No emails configured.</p>
                    ) : (
                      config.emails.map((email, i) => (
                        <div key={i} className="flex gap-2">
                          <input
                            type="email"
                            value={email}
                            onChange={e => {
                              const updated = [...config.emails];
                              updated[i] = e.target.value;
                              setConfig(p => ({ ...p, emails: updated }));
                            }}
                            placeholder="user@domain.com"
                            className="flex-1 px-3 py-2 bg-zinc-900 border border-zinc-800 rounded-lg text-xs text-white placeholder-zinc-600 focus:outline-none focus:border-indigo-500 transition-colors"
                          />
                          <button
                            type="button"
                            onClick={() => setConfig(p => ({ ...p, emails: p.emails.filter((_, j) => j !== i) }))}
                            className="p-2 text-zinc-600 hover:text-red-400 hover:bg-red-500/8 rounded-lg transition-colors"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={saving || loadingConfig}
                  className="w-full py-3 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold rounded-lg flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
                >
                  {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                  Save Configuration
                </button>
              </form>

              {/* Alert tester */}
              <div className="mt-6 pt-5 border-t border-zinc-800 space-y-3">
                <div>
                  <h4 className="text-xs font-semibold text-zinc-400 flex items-center gap-1.5">
                    <Bell className="w-3.5 h-3.5 text-indigo-400" /> Alert Integration Test
                  </h4>
                  <p className="text-[11px] text-zinc-600 mt-1">
                    Manually trigger an anomaly check. Sends a test alert if no real spike is found.
                  </p>
                </div>

                <button
                  onClick={handleTriggerScan}
                  disabled={scanning}
                  className="w-full py-2.5 bg-zinc-900 border border-zinc-800 hover:border-zinc-700 text-zinc-300 text-xs font-semibold rounded-lg flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
                >
                  {scanning ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5 text-indigo-400" />}
                  Trigger Alert Scan
                </button>

                {scanResult && (
                  <div className="p-3 bg-zinc-900/60 border border-zinc-800 rounded-lg text-xs space-y-1">
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Status</span>
                      <span className="text-zinc-300 font-mono">{scanResult.status}</span>
                    </div>
                    {scanResult.notified?.length > 0 ? (
                      <div className="text-emerald-400">
                        Notified: {scanResult.notified.join(', ')}
                      </div>
                    ) : (
                      <div className="text-zinc-600 italic">No channels were notified.</div>
                    )}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right: Spend Chart */}
        <div className="lg:col-span-3">
          <SpendChartCard
            title="14-Day Spend Trend"
            description="Red dots indicate spikes > 20% above 7-day average"
            spendData={spendData}
            anomalies={anomalies}
            dailyThreshold={dailyThreshold}
            isSimulated={isSimulated}
            loading={loadingSpend}
            onRefresh={loadSpend}
          />
        </div>
      </div>

      {/* Alert Log Table */}
      <Card>
        <CardHeader
          title="Alert Log History"
          description="Historical record of anomaly alerts dispatched"
          icon={<Bell className="w-4 h-4" />}
        />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-zinc-800 bg-zinc-900/40">
              <tr>
                <th className="px-5 py-3 text-left text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Date</th>
                <th className="px-5 py-3 text-left text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Description</th>
                <th className="px-5 py-3 text-center text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Status</th>
                <th className="px-5 py-3 text-left text-[11px] font-semibold text-zinc-500 uppercase tracking-wide">Channels</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {loadingConfig ? (
                Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} cols={4} />)
              ) : logs.length === 0 ? (
                <tr>
                  <td colSpan={4}>
                    <EmptyState
                      icon={<Bell className="w-5 h-5" />}
                      title="No alert logs yet"
                      description="Trigger a manual scan or wait for the scheduled daily check."
                    />
                  </td>
                </tr>
              ) : (
                logs.map(log => (
                  <tr key={log.id} className="text-zinc-300 hover:bg-zinc-900/30 transition-colors">
                    <td className="px-5 py-3.5 text-xs text-zinc-500 whitespace-nowrap">
                      {new Date(log.created_at || log.date).toLocaleString(undefined, {
                        month: 'short', day: 'numeric', year: 'numeric',
                        hour: '2-digit', minute: '2-digit'
                      })}
                    </td>
                    <td className="px-5 py-3.5 text-xs">
                      Cost spike on <span className="text-zinc-400">{log.date}</span> at{' '}
                      <span className="font-semibold text-white">${log.details.amount.toFixed(2)}</span>
                      {' '}(avg ${log.details.average.toFixed(2)}, +{log.details.percent_increase.toFixed(1)}%)
                    </td>
                    <td className="px-5 py-3.5 text-center">
                      <StatusBadge status={log.status} />
                    </td>
                    <td className="px-5 py-3.5">
                      {log.channels?.length ? (
                        <div className="flex flex-wrap gap-1">
                          {log.channels.map((c, i) => (
                            <span key={i} className="px-1.5 py-0.5 text-[10px] bg-zinc-900 border border-zinc-800 rounded font-mono text-zinc-400">{c}</span>
                          ))}
                        </div>
                      ) : <span className="text-zinc-600 text-xs italic">None</span>}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {toast && (
        <ToastContainer>
          <Toast type={toast.type ?? 'success'} title={toast.title} message={toast.message} onDismiss={() => setToast(null)} />
        </ToastContainer>
      )}
    </div>
  );
}
