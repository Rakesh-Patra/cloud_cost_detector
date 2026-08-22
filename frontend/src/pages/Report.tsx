import { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, DollarSign, Cpu, AlertCircle,
  Copy, Check, Terminal, CheckCircle2, Loader2, Sparkles, Search, FileText
} from 'lucide-react';
import { apiFetch } from '../lib/api';
import { formatCurrency } from '../lib/format';
import { SeverityBadge } from '../components/ui/Badge';
import { Card, CardHeader, CardContent } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorState';
import { Toast, ToastContainer } from '../components/ui/Toast';

interface Recommendation {
  resource_id: string;
  issue_type: string;
  severity: 'high' | 'medium' | 'low';
  estimated_savings: number;
  remediation_command: string;
  terraform_code?: string;
  remediated?: boolean;
  remediated_at?: string;
}

type SeverityFilter = 'all' | 'high' | 'medium' | 'low';

export default function Report() {
  const location = useLocation();
  const navigate = useNavigate();
  const scanResult = location.state?.scanResult;

  const [localRecs, setLocalRecs] = useState<Recommendation[]>(
    () => scanResult?.analysis?.recommendations || []
  );
  const [remediationStatus, setRemediationStatus] = useState<
    Record<string, { loading: boolean; error: string | null }>
  >({});
  const [quarantineLoading, setQuarantineLoading] = useState<Record<string, boolean>>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ title: string; message: string } | null>(null);
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all');
  const [search, setSearch] = useState('');

  // Keep sessionStorage in sync with remediated state
  useEffect(() => {
    if (!scanResult) return;
    const updated = { ...scanResult, analysis: { ...scanResult.analysis, recommendations: localRecs } };
    sessionStorage.setItem('latestScanResult', JSON.stringify(updated));
  }, [scanResult, localRecs]);

  if (!scanResult) {
    return (
      <div className="p-6 max-w-2xl mx-auto">
        <EmptyState
          icon={<FileText className="w-6 h-6" />}
          title="No scan report found"
          description="Run a cost audit from the Dashboard to generate a report."
          action={
            <button
              onClick={() => navigate('/')}
              className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Go to Dashboard
            </button>
          }
        />
      </div>
    );
  }

  const { analysis_id, region, count, analysis, account_id } = scanResult;
  const executiveSummary: string = analysis?.executive_summary || '';

  const totalSavings = localRecs
    .filter(r => !r.remediated)
    .reduce((s, r) => s + (r.estimated_savings || 0), 0);

  const activeIssues = localRecs.filter(r => !r.remediated).length;

  // Filter + search
  const severityOrder = { high: 0, medium: 1, low: 2 };
  const filtered = [...localRecs]
    .sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity])
    .filter(r => severityFilter === 'all' || r.severity === severityFilter)
    .filter(r =>
      !search ||
      r.resource_id.toLowerCase().includes(search.toLowerCase()) ||
      r.issue_type.toLowerCase().includes(search.toLowerCase())
    );

  const handleRemediate = async (rec: Recommendation) => {
    if (!analysis_id) {
      setRemediationStatus(p => ({ ...p, [rec.resource_id]: { loading: false, error: 'Missing Analysis ID.' } }));
      return;
    }
    setRemediationStatus(p => ({ ...p, [rec.resource_id]: { loading: true, error: null } }));

    try {
      const data = await apiFetch<{ message: string; remediated_at: string }>('/api/remediate', {
        method: 'POST',
        body: JSON.stringify({
          analysis_id,
          resource_id: rec.resource_id,
          issue_type: rec.issue_type,
          region,
          account_id,
        }),
      });

      setLocalRecs(prev =>
        prev.map(r =>
          r.resource_id === rec.resource_id
            ? { ...r, remediated: true, remediated_at: data.remediated_at }
            : r
        )
      );
      setRemediationStatus(p => ({ ...p, [rec.resource_id]: { loading: false, error: null } }));
      setToast({ title: 'Remediation Applied', message: data.message || `Resource ${rec.resource_id} remediated.` });
    } catch (err: any) {
      setRemediationStatus(p => ({ ...p, [rec.resource_id]: { loading: false, error: err.message || 'Remediation failed.' } }));
    }
  };

  const handleQuarantine = async (rec: Recommendation) => {
    setQuarantineLoading(p => ({ ...p, [rec.resource_id]: true }));
    try {
      const rType = rec.issue_type.includes('Volume') ? 'EBS Volume' : 'EC2 Instance';
      await apiFetch('/api/v1/quarantine/apply', {
        method: 'POST',
        body: JSON.stringify({
          resource_id: rec.resource_id,
          resource_type: rType,
          region,
          reason: rec.issue_type,
          account_id,
          quarantine_days: 7,
        }),
      });

      setToast({
        title: 'Resource Quarantined',
        message: `Tagged ${rec.resource_id} with a 7-day grace period.`,
      });
    } catch (err: any) {
      alert(`Failed to quarantine resource: ${err.message}`);
    } finally {
      setQuarantineLoading(p => ({ ...p, [rec.resource_id]: false }));
    }
  };

  const handleCopy = (command: string, id: string) => {
    navigator.clipboard.writeText(command);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const SEVERITY_TABS: { value: SeverityFilter; label: string }[] = [
    { value: 'all', label: `All (${localRecs.length})` },
    { value: 'high', label: `High (${localRecs.filter(r => r.severity === 'high').length})` },
    { value: 'medium', label: `Medium (${localRecs.filter(r => r.severity === 'medium').length})` },
    { value: 'low', label: `Low (${localRecs.filter(r => r.severity === 'low').length})` },
  ];

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">

      {/* Breadcrumb / Back */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2 text-xs font-medium text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Dashboard
        </button>
        <span className="text-xs font-mono text-zinc-600 bg-zinc-900 border border-zinc-800 px-3 py-1 rounded-lg">
          {region?.toUpperCase()}
        </span>
      </div>

      {/* KPI Summary Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-darkCard border border-zinc-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-zinc-500 uppercase tracking-wide">Potential Savings</span>
            <div className="w-7 h-7 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
              <DollarSign className="w-3.5 h-3.5 text-emerald-400" />
            </div>
          </div>
          <div className="text-2xl font-bold text-emerald-400">{formatCurrency(totalSavings)}</div>
          <p className="text-[11px] text-zinc-600 mt-1">across remaining issues</p>
        </div>

        <div className="bg-darkCard border border-zinc-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-zinc-500 uppercase tracking-wide">Resources Scanned</span>
            <div className="w-7 h-7 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center">
              <Cpu className="w-3.5 h-3.5 text-indigo-400" />
            </div>
          </div>
          <div className="text-2xl font-bold text-white">{count}</div>
          <p className="text-[11px] text-zinc-600 mt-1">EC2, EBS, RDS, S3</p>
        </div>

        <div className="bg-darkCard border border-zinc-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-zinc-500 uppercase tracking-wide">Open Issues</span>
            <div className="w-7 h-7 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
              <AlertCircle className="w-3.5 h-3.5 text-amber-400" />
            </div>
          </div>
          <div className="text-2xl font-bold text-amber-400">{activeIssues}</div>
          <p className="text-[11px] text-zinc-600 mt-1">
            {localRecs.length - activeIssues} remediated
          </p>
        </div>
      </div>

      {/* Executive Summary */}
      {executiveSummary && (
        <Card>
          <CardHeader title="Executive Summary" icon={<FileText className="w-4 h-4" />} />
          <CardContent>
            <p className="text-sm text-zinc-300 leading-relaxed border-l-2 border-indigo-500/50 pl-4">
              {executiveSummary}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Recommendations */}
      <Card>
        <CardHeader
          title="Optimization Recommendations"
          description="AI-generated remediation actions ranked by severity"
          icon={<Sparkles className="w-4 h-4" />}
        />
        <CardContent className="space-y-4">
          {/* Filters row */}
          <div className="flex flex-col sm:flex-row gap-3">
            {/* Severity tabs */}
            <div className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 rounded-lg p-1">
              {SEVERITY_TABS.map(tab => (
                <button
                  key={tab.value}
                  onClick={() => setSeverityFilter(tab.value)}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors whitespace-nowrap ${
                    severityFilter === tab.value
                      ? 'bg-indigo-600 text-white'
                      : 'text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Search */}
            <div className="relative flex-1 min-w-0">
              <Search className="absolute left-3 top-2.5 w-3.5 h-3.5 text-zinc-600" />
              <input
                type="text"
                placeholder="Search by resource ID or issue type…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="w-full pl-9 pr-4 py-2 bg-zinc-900 border border-zinc-800 rounded-lg text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-indigo-500 transition-colors"
              />
            </div>
          </div>

          {/* Recommendation list */}
          {filtered.length === 0 ? (
            <EmptyState
              icon={<CheckCircle2 className="w-6 h-6" />}
              title="No issues match your filters"
              description={localRecs.length === 0 ? 'This region is fully optimized — no issues found.' : 'Try adjusting the severity filter or search term.'}
            />
          ) : (
            <div className="space-y-3">
              {filtered.map((rec, i) => {
                const id = `rec-${i}`;
                const isCopied = copiedId === id;
                const status = remediationStatus[rec.resource_id];

                return (
                  <div
                    key={id}
                    className={`border rounded-xl p-5 transition-all ${
                      rec.remediated
                        ? 'bg-emerald-500/4 border-emerald-500/15 opacity-70'
                        : 'bg-zinc-900/30 border-zinc-800 hover:border-zinc-700'
                    }`}
                  >
                    {/* Header row */}
                    <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
                      <div className="flex items-center gap-2 flex-wrap">
                        <SeverityBadge severity={rec.severity} />
                        <span className="text-[11px] text-zinc-500 font-mono">
                          {rec.resource_id}
                        </span>
                      </div>
                      <span className="text-xs font-bold text-emerald-400 bg-emerald-500/8 border border-emerald-500/15 px-2.5 py-1 rounded-lg">
                        Save {formatCurrency(rec.estimated_savings)}/mo
                      </span>
                    </div>

                    <h4 className="text-sm font-semibold text-white mb-3">{rec.issue_type}</h4>

                    {/* CLI command + action */}
                    <div className="flex flex-col md:flex-row gap-3">
                      {rec.remediation_command && (
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5 text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-1.5 font-mono">
                            <Terminal className="w-3 h-3" />
                            AWS CLI Command
                          </div>
                          <div className="flex items-center gap-3 bg-black/50 border border-zinc-800 rounded-lg px-4 py-3 font-mono text-xs text-emerald-400">
                            <code className="flex-1 truncate">{rec.remediation_command}</code>
                            <button
                              onClick={() => handleCopy(rec.remediation_command, id)}
                              className={`shrink-0 p-1.5 rounded-md border transition-colors ${
                                isCopied
                                  ? 'bg-emerald-500/10 border-emerald-500/25 text-emerald-400'
                                  : 'border-zinc-800 text-zinc-500 hover:text-zinc-300 hover:border-zinc-700'
                              }`}
                            >
                              {isCopied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                            </button>
                          </div>
                        </div>
                      )}

                      {/* Action buttons */}
                      <div className="shrink-0 md:w-56 flex flex-col justify-end gap-2">
                        {rec.remediated ? (
                          <div className="flex items-center justify-center gap-2 py-3 text-sm text-emerald-400 font-medium">
                            <CheckCircle2 className="w-4 h-4" />
                            Remediated
                          </div>
                        ) : (
                          <div className="flex flex-col gap-2">
                            <button
                              onClick={() => handleRemediate(rec)}
                              disabled={status?.loading}
                              className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50"
                            >
                              {status?.loading ? (
                                <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Applying…</>
                              ) : (
                                <><Sparkles className="w-3.5 h-3.5" /> Apply Fix</>
                              )}
                            </button>
                            <button
                              onClick={() => handleQuarantine(rec)}
                              disabled={quarantineLoading[rec.resource_id]}
                              className="w-full py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 text-xs font-medium rounded-lg flex items-center justify-center gap-1 transition-colors disabled:opacity-50"
                            >
                              {quarantineLoading[rec.resource_id] ? (
                                <><Loader2 className="w-3 h-3 animate-spin" /> Tagging…</>
                              ) : (
                                <span>🛡️ 7-Day Quarantine</span>
                              )}
                            </button>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Optional Terraform Code Snippet */}
                    {rec.terraform_code && (
                      <div className="mt-3 pt-3 border-t border-zinc-800/80">
                        <div className="flex items-center justify-between text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-1 font-mono">
                          <span>Terraform IaC Fix</span>
                          <button
                            onClick={() => handleCopy(rec.terraform_code || '', `${id}-tf`)}
                            className="text-indigo-400 hover:text-indigo-300 text-[10px] flex items-center gap-1"
                          >
                            {copiedId === `${id}-tf` ? 'Copied' : 'Copy HCL'}
                          </button>
                        </div>
                        <pre className="bg-black/60 border border-zinc-800/60 rounded-lg p-2.5 font-mono text-[11px] text-purple-300 overflow-x-auto">
                          {rec.terraform_code}
                        </pre>
                      </div>
                    )}

                    {/* Error under action */}
                    {status?.error && (
                      <ErrorBanner message={`Remediation failed: ${status.error}`} className="mt-3" />
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Toast notifications */}
      {toast && (
        <ToastContainer>
          <Toast
            type="success"
            title={toast.title}
            message={toast.message}
            onDismiss={() => setToast(null)}
          />
        </ToastContainer>
      )}
    </div>
  );
}
