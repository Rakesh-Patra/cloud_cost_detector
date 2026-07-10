import { useState, useEffect } from 'react';
import { useLocation, Link, useNavigate } from 'react-router-dom';
import { FileText, ArrowLeft, DollarSign, Cpu, AlertCircle, Copy, Check, Terminal, CheckCircle2, Loader2, Sparkles } from 'lucide-react';
import { insforge } from '../insforge';

interface Recommendation {
  resource_id: string;
  issue_type: string;
  severity: 'high' | 'medium' | 'low';
  estimated_savings: number;
  remediation_command: string;
  remediated?: boolean;
  remediated_at?: string;
}

export default function Report() {
  const location = useLocation();
  const navigate = useNavigate();
  const scanResult = location.state?.scanResult;
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [localRecommendations, setLocalRecommendations] = useState<Recommendation[]>(
    () => (scanResult?.analysis?.recommendations || [])
  );
  const [remediationStatus, setRemediationStatus] = useState<Record<string, { loading: boolean; error: string | null }>>({});
  const [toast, setToast] = useState<{ show: boolean; message: string } | null>(null);

  useEffect(() => {
    if (scanResult) {
      const updatedResult = {
        ...scanResult,
        analysis: {
          ...scanResult.analysis,
          recommendations: localRecommendations
        }
      };
      localStorage.setItem('latestScanResult', JSON.stringify(updatedResult));
    }
  }, [scanResult, localRecommendations]);

  if (!scanResult) {
    return (
      <div className="min-h-[calc(100vh-73px)] bg-darkBg text-slate-100 p-8 flex flex-col items-center justify-center text-center">
        <AlertCircle className="w-12 h-12 text-zinc-600 mb-4" />
        <h2 className="text-xl font-bold text-white">No active report found</h2>
        <p className="text-zinc-500 text-sm mt-1 max-w-sm">
          Please run a new cost optimization audit from the dashboard.
        </p>
        <Link
          to="/"
          className="mt-6 px-6 py-3 bg-brandIndigo hover:bg-brandIndigo/90 text-white font-medium rounded-xl flex items-center gap-2 transition-all shadow-lg shadow-brandIndigo/10"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Dashboard
        </Link>
      </div>
    );
  }

  const { analysis_id, region, count, analysis } = scanResult;
  const executiveSummary = analysis?.executive_summary || 'No summary generated.';

  // Sum up estimated savings of non-remediated items
  const totalSavings = localRecommendations
    .filter(item => !item.remediated)
    .reduce((sum, item) => sum + (item.estimated_savings || 0), 0);

  // Sort recommendations by severity: high -> medium -> low
  const severityOrder = { high: 0, medium: 1, low: 2 };
  const sortedRecommendations = [...localRecommendations].sort(
    (a, b) => severityOrder[a.severity] - severityOrder[b.severity]
  );

  const handleRemediate = async (rec: Recommendation) => {
    if (!analysis_id) {
      setRemediationStatus(prev => ({
        ...prev,
        [rec.resource_id]: { loading: false, error: 'Cannot remediate: Missing Analysis ID.' }
      }));
      return;
    }

    setRemediationStatus(prev => ({
      ...prev,
      [rec.resource_id]: { loading: true, error: null }
    }));

    try {
      const token = (insforge as any).tokenManager.getAccessToken();
      const headers = {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      };

      const backendUrl = import.meta.env.VITE_BACKEND_URL || '';
      const response = await fetch(`${backendUrl}/api/remediate`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          analysis_id,
          resource_id: rec.resource_id,
          issue_type: rec.issue_type,
          region,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Remediation request failed' }));
        const detailMsg = typeof errorData.detail === 'object'
          ? (errorData.detail.message || errorData.detail.error || JSON.stringify(errorData.detail))
          : (errorData.detail || 'Remediation failed');
        throw new Error(detailMsg);
      }

      const responseData = await response.json();

      // On success: update local state
      setLocalRecommendations(prev =>
        prev.map(item => {
          if (item.resource_id === rec.resource_id) {
            return { ...item, remediated: true, remediated_at: responseData.remediated_at };
          }
          return item;
        })
      );

      setRemediationStatus(prev => ({
        ...prev,
        [rec.resource_id]: { loading: false, error: null }
      }));

      // Trigger success toast
      setToast({
        show: true,
        message: responseData.message || `Successfully remediated resource ${rec.resource_id}.`
      });
      setTimeout(() => {
        setToast(null);
      }, 5000);

    } catch (err: any) {
      console.error('Error applying remediation:', err);
      setRemediationStatus(prev => ({
        ...prev,
        [rec.resource_id]: { loading: false, error: err.message || 'Access Denied' }
      }));
    }
  };

  const handleCopy = (command: string, idxStr: string) => {
    navigator.clipboard.writeText(command);
    setCopiedId(idxStr);
    setTimeout(() => {
      setCopiedId(null);
    }, 2000);
  };

  return (
    <div className="min-h-[calc(100vh-73px)] bg-darkBg text-slate-100 p-8 relative overflow-hidden select-none">
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-brandIndigo/5 rounded-full blur-3xl" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-brandPurple/5 rounded-full blur-3xl" />

      <div className="max-w-5xl mx-auto relative z-10">
        {/* Navigation header */}
        <div className="flex items-center justify-between mb-8">
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-2 px-4 py-2 border border-zinc-800 bg-zinc-900/40 hover:bg-zinc-900 rounded-xl text-sm font-medium text-zinc-400 hover:text-zinc-200 transition-all"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Dashboard
          </button>
          
          <div className="flex items-center gap-2 text-zinc-500 text-xs font-semibold bg-zinc-900/50 border border-zinc-800 rounded-xl px-4 py-2 font-mono">
            REGION: <span className="text-brandIndigo">{region.toUpperCase()}</span>
          </div>
        </div>

        {/* Title */}
        <div className="flex items-center gap-4 mb-8">
          <div className="w-12 h-12 bg-brandPurple/10 border border-brandPurple/25 rounded-2xl flex items-center justify-center shadow-lg shadow-brandPurple/5">
            <FileText className="w-6 h-6 text-brandPurple" />
          </div>
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-white">Analysis Cost Report</h1>
            <p className="text-zinc-400 text-sm mt-0.5">AI-powered recommendations based on resource utilization</p>
          </div>
        </div>

        {/* Overview Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          {/* Card 1: Total Savings */}
          <div className="bg-darkCard/50 backdrop-blur-xl border border-zinc-800 rounded-2xl p-6 shadow-xl relative overflow-hidden group">
            <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-500/5 rounded-full blur-2xl group-hover:bg-emerald-500/10 transition-colors" />
            <div className="flex items-center justify-between mb-4">
              <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Monthly Potential Savings</span>
              <div className="p-2 bg-emerald-500/10 text-emerald-400 rounded-lg border border-emerald-500/20">
                <DollarSign className="w-4 h-4" />
              </div>
            </div>
            <div className="text-3xl font-bold text-emerald-400">${totalSavings.toFixed(2)}</div>
            <p className="text-[10px] text-zinc-500 mt-2 font-medium">Estimated savings after applying all scripts</p>
          </div>

          {/* Card 2: Scanned Resources */}
          <div className="bg-darkCard/50 backdrop-blur-xl border border-zinc-800 rounded-2xl p-6 shadow-xl relative overflow-hidden group">
            <div className="absolute top-0 right-0 w-24 h-24 bg-brandIndigo/5 rounded-full blur-2xl group-hover:bg-brandIndigo/10 transition-colors" />
            <div className="flex items-center justify-between mb-4">
              <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Scanned Resources</span>
              <div className="p-2 bg-brandIndigo/10 text-brandIndigo rounded-lg border border-brandIndigo/25">
                <Cpu className="w-4 h-4" />
              </div>
            </div>
            <div className="text-3xl font-bold text-white">{count}</div>
            <p className="text-[10px] text-zinc-500 mt-2 font-medium">EC2 instances, EBS volumes, RDS, S3 audited</p>
          </div>

          {/* Card 3: Detected Issues */}
          <div className="bg-darkCard/50 backdrop-blur-xl border border-zinc-800 rounded-2xl p-6 shadow-xl relative overflow-hidden group">
            <div className="absolute top-0 right-0 w-24 h-24 bg-orange-500/5 rounded-full blur-2xl group-hover:bg-orange-500/10 transition-colors" />
            <div className="flex items-center justify-between mb-4">
              <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Cost Warnings</span>
              <div className="p-2 bg-orange-500/10 text-orange-400 rounded-lg border border-orange-500/20">
                <AlertCircle className="w-4 h-4" />
              </div>
            </div>
            <div className="text-3xl font-bold text-orange-400">
              {localRecommendations.filter(r => !r.remediated).length}
            </div>
            <p className="text-[10px] text-zinc-500 mt-2 font-medium">Actions requiring optimization review</p>
          </div>
        </div>

        {/* Executive Summary */}
        <div className="bg-darkCard/50 backdrop-blur-xl border border-zinc-800 rounded-3xl p-8 shadow-2xl mb-8">
          <h2 className="text-lg font-bold text-white mb-4">Executive Summary</h2>
          <div className="text-sm text-zinc-300 leading-relaxed border-l-2 border-brandIndigo pl-4">
            {executiveSummary}
          </div>
        </div>

        {/* Recommendations Section */}
        <div>
          <h2 className="text-xl font-bold text-white mb-6">Optimization Action Checklist</h2>
          
          {sortedRecommendations.length === 0 ? (
            <div className="p-12 text-center bg-zinc-900/20 border border-dashed border-zinc-800 rounded-3xl text-zinc-500">
              <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto mb-3" />
              <h4 className="text-white font-semibold">100% Cost Optimized!</h4>
              <p className="text-xs text-zinc-500 mt-1">No optimization issues were found in this region.</p>
            </div>
          ) : (
            <div className="space-y-6">
              {sortedRecommendations.map((rec, index) => {
                const idxStr = `rec-${index}`;
                const isCopied = copiedId === idxStr;

                return (
                  <div
                    key={idxStr}
                    className="bg-darkCard/30 border border-zinc-800 rounded-2xl p-6 shadow-lg hover:border-zinc-700/80 transition-all"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-4 mb-4">
                      <div className="flex items-center gap-3">
                        {/* Severity Badges */}
                        {rec.severity === 'high' && (
                          <span className="px-3 py-1 text-xs font-semibold rounded-lg bg-red-500/10 text-red-400 border border-red-500/20 uppercase font-mono">
                            High Severity
                          </span>
                        )}
                        {rec.severity === 'medium' && (
                          <span className="px-3 py-1 text-xs font-semibold rounded-lg bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 uppercase font-mono">
                            Medium Severity
                          </span>
                        )}
                        {rec.severity === 'low' && (
                          <span className="px-3 py-1 text-xs font-semibold rounded-lg bg-green-500/10 text-green-400 border border-green-500/20 uppercase font-mono">
                            Low Severity
                          </span>
                        )}
                        
                        <span className="text-zinc-500 text-xs font-semibold font-mono">
                          ID: <span className="text-zinc-300 font-sans">{rec.resource_id}</span>
                        </span>
                      </div>

                      {/* Savings Badge */}
                      <span className="px-3.5 py-1.5 text-xs font-bold rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        Save ${rec.estimated_savings.toFixed(2)}/mo
                      </span>
                    </div>

                    <h3 className="text-base font-bold text-white mb-2">{rec.issue_type}</h3>

                    <div className="mt-4 flex flex-col md:flex-row gap-4 items-stretch md:items-end">
                      {/* Remediation AWS CLI command terminal */}
                      {rec.remediation_command && (
                        <div className="flex-1 min-w-0 space-y-2">
                          <span className="text-[10px] uppercase font-bold tracking-wider text-zinc-400 flex items-center gap-1.5 font-mono">
                            <Terminal className="w-3.5 h-3.5 text-zinc-500" />
                            Remediation AWS CLI Command
                          </span>
                          
                          <div className="bg-black/60 border border-zinc-800 rounded-xl p-4 flex items-center justify-between gap-4 font-mono text-xs text-emerald-400 overflow-x-auto shadow-inner">
                            <code className="whitespace-nowrap pr-4">{rec.remediation_command}</code>
                            <button
                              onClick={() => handleCopy(rec.remediation_command, idxStr)}
                              className={`p-2 border rounded-lg shrink-0 transition-all ${
                                isCopied
                                  ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-400'
                                  : 'bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-200 hover:border-zinc-700'
                              }`}
                              title="Copy Command"
                            >
                              {isCopied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                            </button>
                          </div>
                        </div>
                      )}

                      {/* Action Button Container */}
                      <div className="flex flex-col justify-end shrink-0 md:w-44">
                        {rec.remediated ? (
                          <button
                            disabled
                            className="w-full py-3.5 bg-emerald-500/10 border border-emerald-500/35 text-emerald-400 font-semibold rounded-xl text-sm flex items-center justify-center gap-2 cursor-not-allowed select-none"
                          >
                            <CheckCircle2 className="w-4 h-4" />
                            Remediated ✓
                          </button>
                        ) : (
                          <button
                            onClick={() => handleRemediate(rec)}
                            disabled={remediationStatus[rec.resource_id]?.loading}
                            className="w-full py-3.5 bg-gradient-to-r from-brandIndigo to-brandPurple hover:from-brandIndigo/90 hover:to-brandPurple/90 text-white font-medium rounded-xl text-sm flex items-center justify-center gap-2 shadow-lg shadow-brandIndigo/15 active:scale-[0.98] transition-all disabled:opacity-50 disabled:pointer-events-none"
                          >
                            {remediationStatus[rec.resource_id]?.loading ? (
                              <>
                                <Loader2 className="w-4 h-4 animate-spin" />
                                Applying Fix...
                              </>
                            ) : (
                              <>
                                <Sparkles className="w-4 h-4" />
                                Apply Fix
                              </>
                            )}
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Error message under/next to the terminal */}
                    {remediationStatus[rec.resource_id]?.error && (
                      <div className="mt-3 p-3 bg-red-950/20 border border-red-900/30 rounded-xl flex items-center gap-2 text-xs text-red-400">
                        <AlertCircle className="w-4 h-4 shrink-0" />
                        <span>
                          <strong>Remediation Failed:</strong> {remediationStatus[rec.resource_id]?.error}
                        </span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Toast Notification */}
      {toast?.show && (
        <div className="fixed bottom-6 right-6 z-50 bg-zinc-950/90 backdrop-blur-xl border border-emerald-500/35 p-4 rounded-2xl shadow-2xl flex items-start gap-3 max-w-md animate-in fade-in slide-in-from-bottom-5">
          <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
          <div>
            <h5 className="text-sm font-bold text-white">Remediation Successful</h5>
            <p className="text-zinc-400 text-xs mt-0.5 leading-normal">{toast.message}</p>
          </div>
        </div>
      )}
    </div>
  );
}
