import { useEffect, useState, useRef } from 'react';
import { 
  TrendingUp, Plus, Trash2, Save, RefreshCw, AlertCircle, 
  CheckCircle2, Calendar, DollarSign, Mail, Play, Loader2, Bell
} from 'lucide-react';
import { insforge } from '../insforge';

interface BudgetConfig {
  threshold: number;
  emails: string[];
}

interface AlertLog {
  id: string;
  date: string;
  details: {
    amount: number;
    average: number;
    percent_increase: number;
  };
  status: string;
  channels: string[];
  created_at: string;
}

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

export default function Budgets() {
  const [config, setConfig] = useState<BudgetConfig>({ threshold: 1000.0, emails: [] });
  const [logs, setLogs] = useState<AlertLog[]>([]);
  const [spendData, setSpendData] = useState<SpendDay[]>([]);
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [isSimulated, setIsSimulated] = useState(false);
  
  const [loadingConfig, setLoadingConfig] = useState(true);
  const [loadingSpend, setLoadingSpend] = useState(true);
  const [saving, setSaving] = useState(false);
  const [scanning, setScanning] = useState(false);
  
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [scanResult, setScanResult] = useState<any>(null);
  
  // Custom tooltip state for the SVG chart
  const [hoveredPoint, setHoveredPoint] = useState<{ x: number; y: number; date: string; amount: number } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [chartWidth, setChartWidth] = useState(600);

  // Resize listener for responsive SVG
  useEffect(() => {
    if (!containerRef.current) return;
    const resizeObserver = new ResizeObserver((entries) => {
      for (let entry of entries) {
        setChartWidth(entry.contentRect.width);
      }
    });
    resizeObserver.observe(containerRef.current);
    return () => resizeObserver.disconnect();
  }, []);

  const apiFetch = async (endpoint: string, options: RequestInit = {}) => {
    const token = (insforge as any).tokenManager.getAccessToken();
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    };

    const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
    const response = await fetch(`${backendUrl}${endpoint}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(errorData.detail?.message || errorData.detail || 'Request failed');
    }

    return response.json();
  };

  const loadBudgetsAndLogs = async () => {
    try {
      setLoadingConfig(true);
      setErrorMsg('');
      const data = await apiFetch('/api/budgets');
      if (data) {
        const user = (insforge as any).tokenManager.getUser();
        const userEmail = user?.email || '';
        
        const loadedConfig = data.config || { threshold: 1000.0, emails: [] };
        if (!loadedConfig.emails || loadedConfig.emails.length === 0) {
          loadedConfig.emails = userEmail ? [userEmail] : [];
        }
        
        setConfig(loadedConfig);
        setLogs(data.logs || []);
      }
    } catch (err: any) {
      console.error('Error loading budget config:', err);
      setErrorMsg(err.message || 'Failed to retrieve budget settings.');
    } finally {
      setLoadingConfig(false);
    }
  };

  const loadSpendData = async () => {
    try {
      setLoadingSpend(true);
      const data = await apiFetch('/api/budgets/spend');
      if (data) {
        setSpendData(data.spend_data || []);
        setAnomalies(data.anomalies || []);
        setIsSimulated(!!data.is_simulated);
      }
    } catch (err: any) {
      console.error('Error loading spend data:', err);
    } finally {
      setLoadingSpend(false);
    }
  };

  useEffect(() => {
    loadBudgetsAndLogs();
    loadSpendData();
  }, []);

  // Slack alert channel removed per user requirements

  const handleAddEmail = () => {
    setConfig(prev => ({
      ...prev,
      emails: [...prev.emails, '']
    }));
  };

  const handleUpdateEmail = (index: number, val: string) => {
    const updated = [...config.emails];
    updated[index] = val;
    setConfig(prev => ({ ...prev, emails: updated }));
  };

  const handleRemoveEmail = (index: number) => {
    setConfig(prev => ({
      ...prev,
      emails: prev.emails.filter((_, i) => i !== index)
    }));
  };

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setErrorMsg('');
    setSuccessMsg('');
    
    // Clean inputs
    const cleanEmails = config.emails.map(em => em.trim()).filter(Boolean);

    try {
      await apiFetch('/api/budgets', {
        method: 'POST',
        body: JSON.stringify({
          threshold: config.threshold,
          emails: cleanEmails
        })
      });
      setSuccessMsg('Budget configurations saved successfully.');
      setConfig(prev => ({ ...prev, emails: cleanEmails }));
      // Clear message after 4s
      setTimeout(() => setSuccessMsg(''), 4000);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to save budget settings.');
    } finally {
      setSaving(false);
    }
  };

  const handleTriggerScan = async () => {
    setScanning(true);
    setScanResult(null);
    setErrorMsg('');
    setSuccessMsg('');
    try {
      const result = await apiFetch('/api/budgets/trigger-scan', { method: 'POST' });
      setScanResult(result);
      if (result.success) {
        setSuccessMsg(result.message || 'Scan completed.');
        // Reload logs to show new entry
        await loadBudgetsAndLogs();
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Manual anomaly scan failed.');
    } finally {
      setScanning(false);
    }
  };

  // Helper to draw custom SVG line chart
  const renderSVGChart = () => {
    if (spendData.length === 0) {
      return (
        <div className="h-48 flex items-center justify-center text-zinc-500 text-sm">
          No historical spend data loaded.
        </div>
      );
    }

    const height = 240;
    const paddingLeft = 45;
    const paddingRight = 20;
    const paddingTop = 20;
    const paddingBottom = 30;

    const values = spendData.map(d => d.amount);
    const maxVal = Math.max(...values, 20) * 1.15; // 15% padding
    const minVal = Math.max(0, Math.min(...values, 0) * 0.85);

    // Compute coordinate points
    const points = spendData.map((d, i) => {
      const x = paddingLeft + (i * (chartWidth - paddingLeft - paddingRight)) / (spendData.length - 1);
      const y = height - paddingBottom - ((d.amount - minVal) * (height - paddingTop - paddingBottom)) / (maxVal - minVal);
      return { x, y, date: d.date, amount: d.amount };
    });

    const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
    const areaPath = `
      ${points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')}
      L ${points[points.length - 1].x} ${height - paddingBottom}
      L ${points[0].x} ${height - paddingBottom}
      Z
    `;

    // 4 horizontal grid lines
    const gridRows = 4;
    const gridLines = Array.from({ length: gridRows }).map((_, i) => {
      const ratio = i / (gridRows - 1);
      const y = paddingTop + ratio * (height - paddingTop - paddingBottom);
      const val = maxVal - ratio * (maxVal - minVal);
      return { y, val };
    });

    return (
      <div className="relative" ref={containerRef}>
        <svg width={chartWidth} height={height} className="overflow-visible select-none">
          <defs>
            <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#6366f1" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#8b5cf6" stopOpacity="0.0" />
            </linearGradient>
            <linearGradient id="lineGrad" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#6366f1" />
              <stop offset="100%" stopColor="#8b5cf6" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          {gridLines.map((line, idx) => (
            <g key={idx}>
              <line 
                x1={paddingLeft} 
                y1={line.y} 
                x2={chartWidth - paddingRight} 
                y2={line.y} 
                stroke="#1f2937" 
                strokeDasharray="4 4" 
                strokeWidth="1"
              />
              <text 
                x={paddingLeft - 8} 
                y={line.y + 4} 
                fill="#71717a" 
                fontSize="10" 
                textAnchor="end" 
                fontFamily="monospace"
              >
                ${line.val.toFixed(0)}
              </text>
            </g>
          ))}

          {/* Area Fill */}
          <path d={areaPath} fill="url(#areaGrad)" />

          {/* Line Path */}
          <path d={linePath} fill="none" stroke="url(#lineGrad)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />

          {/* Data Points */}
          {points.map((p, idx) => {
            const isSpike = anomalies.some(a => a.date === p.date);
            const isHovered = hoveredPoint?.date === p.date;

            return (
              <g key={idx}>
                {/* Invisible hover catcher */}
                <circle 
                  cx={p.x} 
                  cy={p.y} 
                  r="12" 
                  fill="transparent" 
                  className="cursor-pointer"
                  onMouseEnter={() => {
                    // Position tooltip
                    setHoveredPoint({ x: p.x, y: p.y, date: p.date, amount: p.amount });
                  }}
                  onMouseLeave={() => setHoveredPoint(null)}
                />

                {isSpike ? (
                  <g>
                    {/* Pulsing warning halo for anomaly */}
                    <circle cx={p.x} cy={p.y} r="8" fill="#ef4444" opacity="0.35" className="animate-ping" />
                    <circle 
                      cx={p.x} 
                      cy={p.y} 
                      r="5.5" 
                      fill="#ef4444" 
                      stroke="#090a0f" 
                      strokeWidth="1.5"
                    />
                  </g>
                ) : (
                  isHovered && (
                    <circle 
                      cx={p.x} 
                      cy={p.y} 
                      r="4" 
                      fill="#6366f1" 
                      stroke="#fff" 
                      strokeWidth="1.5"
                    />
                  )
                )}
              </g>
            );
          })}

          {/* X Axis Date labels (alternate to prevent crowding) */}
          {points.map((p, idx) => {
            if (idx % 2 !== 0 && idx !== points.length - 1) return null;
            const dateObj = new Date(p.date);
            const displayDate = dateObj.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
            return (
              <text 
                key={idx} 
                x={p.x} 
                y={height - 8} 
                fill="#71717a" 
                fontSize="10" 
                textAnchor="middle"
              >
                {displayDate}
              </text>
            );
          })}
        </svg>

        {/* Hover Tooltip Overlay */}
        {hoveredPoint && (
          <div 
            className="absolute z-20 pointer-events-none bg-zinc-950/95 border border-zinc-800 rounded-xl p-3 shadow-xl text-xs flex flex-col gap-1 backdrop-blur-md"
            style={{ 
              left: `${hoveredPoint.x - 60}px`, 
              top: `${hoveredPoint.y - 65}px` 
            }}
          >
            <span className="text-zinc-400 font-medium">{new Date(hoveredPoint.date).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}</span>
            <span className="text-white font-bold text-sm">${hoveredPoint.amount.toFixed(2)}</span>
            {anomalies.some(a => a.date === hoveredPoint.date) && (
              <span className="text-red-400 font-semibold uppercase text-[9px] tracking-wider mt-0.5 flex items-center gap-1">
                <AlertCircle className="w-2.5 h-2.5" /> Anomaly Flagged
              </span>
            )}
          </div>
        )}
      </div>
    );
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'success':
        return (
          <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 uppercase font-mono">
            Delivered
          </span>
        );
      case 'simulated':
        return (
          <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 uppercase font-mono">
            Simulated
          </span>
        );
      case 'partial_failure':
        return (
          <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 uppercase font-mono">
            Partially Sent
          </span>
        );
      case 'no_channels':
        return (
          <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-zinc-800 text-zinc-400 border border-zinc-700 uppercase font-mono">
            No Channels Configured
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-red-500/10 text-red-400 border border-red-500/20 uppercase font-mono">
            Failed
          </span>
        );
    }
  };

  return (
    <div className="min-h-[calc(100vh-73px)] bg-darkBg text-slate-100 p-8 relative select-none">
      {/* Background radial glows */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-brandIndigo/5 rounded-full blur-3xl" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-brandPurple/5 rounded-full blur-3xl" />

      <div className="max-w-6xl mx-auto relative z-10 space-y-8">
        
        {/* Header Title */}
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 bg-brandIndigo/10 border border-brandIndigo/25 rounded-2xl flex items-center justify-center shadow-lg shadow-brandIndigo/5">
            <TrendingUp className="w-6 h-6 text-brandIndigo" />
          </div>
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-white">Budgets & Spend Anomalies</h1>
            <p className="text-zinc-400 text-sm mt-0.5">Define cost guards, alert channels, and review rolling anomalies</p>
          </div>
        </div>

        {/* Notifications and messages */}
        {errorMsg && (
          <div className="p-4 bg-red-950/20 border border-red-900/40 rounded-2xl flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-400 shrink-0" />
            <span className="text-red-300 text-sm font-medium">{errorMsg}</span>
          </div>
        )}

        {successMsg && (
          <div className="p-4 bg-emerald-950/20 border border-emerald-900/40 rounded-2xl flex items-center gap-3">
            <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
            <span className="text-emerald-300 text-sm font-medium">{successMsg}</span>
          </div>
        )}

        {isSimulated && (
          <div className="p-4 bg-amber-950/20 border border-amber-900/40 rounded-2xl flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <span className="text-amber-300 text-sm font-semibold block">Simulated Spend Data Active</span>
              <p className="text-zinc-400 text-xs leading-relaxed">
                AWS Cost Explorer is currently unavailable (your newly enabled Cost Explorer service is preparing data, which can take up to 24 hours). The charts, calculations, and email alerts are temporarily running on high-fidelity simulated costs scaled to your Monthly Cap.
              </p>
            </div>
          </div>
        )}

        {/* Main Grid Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-8">
          
          {/* LEFT: Setup Form Card (col-span-2) */}
          <div className="lg:col-span-2 bg-darkCard/50 backdrop-blur-xl border border-zinc-800/80 rounded-3xl p-6 shadow-2xl space-y-6 flex flex-col justify-between">
            <form onSubmit={handleSaveConfig} className="space-y-6 flex-1">
              <div>
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <DollarSign className="w-5 h-5 text-brandIndigo" /> Threshold Rules
                </h3>
                <p className="text-zinc-500 text-xs mt-1">Configure your monthly cost guardrail limits and alerts</p>
              </div>

              {/* Monthly Budget Input */}
              <div className="space-y-2">
                <label className="text-xs font-bold uppercase tracking-wider text-zinc-400">Monthly Cap (USD)</label>
                <div className="relative">
                  <span className="absolute left-4 top-3 text-zinc-500 font-medium">$</span>
                  <input 
                    type="number"
                    value={config.threshold || ''}
                    onChange={(e) => setConfig(prev => ({ ...prev, threshold: parseFloat(e.target.value) || 0 }))}
                    disabled={loadingConfig}
                    className="w-full pl-8 pr-4 py-3 bg-zinc-900/80 border border-zinc-800 rounded-xl text-white font-medium focus:outline-none focus:border-brandIndigo focus:ring-1 focus:ring-brandIndigo transition-all disabled:opacity-50"
                    placeholder="1000.00"
                  />
                </div>
              </div>

              {/* Slack notifications removed per user requirements */}

              {/* Emails input array */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-bold uppercase tracking-wider text-zinc-400 flex items-center gap-1.5">
                    <Mail className="w-3.5 h-3.5 text-zinc-400" /> Email Notifications
                  </label>
                  <button 
                    type="button" 
                    onClick={handleAddEmail}
                    className="text-xs font-bold text-brandIndigo hover:text-brandPurple transition-colors flex items-center gap-1"
                  >
                    <Plus className="w-3.5 h-3.5" /> Add Email
                  </button>
                </div>

                <div className="space-y-2 max-h-40 overflow-y-auto pr-1">
                  {config.emails.length === 0 ? (
                    <span className="text-zinc-600 text-xs block italic">No notification emails added.</span>
                  ) : (
                    config.emails.map((email, i) => (
                      <div key={i} className="flex gap-2">
                        <input 
                          type="email"
                          value={email}
                          onChange={(e) => handleUpdateEmail(i, e.target.value)}
                          className="flex-1 px-3 py-2 bg-zinc-900/60 border border-zinc-800 rounded-lg text-xs text-white focus:outline-none focus:border-brandIndigo focus:ring-1 focus:ring-brandIndigo transition-all"
                          placeholder="user@domain.com"
                        />
                        <button 
                          type="button" 
                          onClick={() => handleRemoveEmail(i)}
                          className="p-2 bg-red-950/20 text-red-400 border border-red-950/30 hover:border-red-900/40 rounded-lg transition-colors"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </form>

            <div className="mt-8 pt-4 border-t border-zinc-800/80">
              <button 
                type="submit"
                onClick={handleSaveConfig}
                disabled={saving || loadingConfig}
                className="w-full py-3 bg-gradient-to-r from-brandIndigo to-brandPurple hover:from-brandIndigo/95 hover:to-brandPurple/95 text-white font-medium rounded-xl flex items-center justify-center gap-2 shadow-lg shadow-brandIndigo/25 active:scale-[0.98] transition-all disabled:opacity-50"
              >
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                Save Guard Configuration
              </button>
            </div>
          </div>

          {/* RIGHT: Chart and Actions Card (col-span-3) */}
          <div className="lg:col-span-3 space-y-8 flex flex-col justify-between">
            
            {/* Daily Spend Chart Panel */}
            <div className="bg-darkCard/50 backdrop-blur-xl border border-zinc-800/80 rounded-3xl p-6 shadow-2xl space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-bold text-white flex items-center gap-2">
                    <Calendar className="w-5 h-5 text-brandIndigo" /> 14-Day Spend Trends
                  </h3>
                  <p className="text-zinc-500 text-xs mt-1">Highlighted red dots indicate spend exceeding 7-day averages by &gt; 20%</p>
                </div>
                <button 
                  onClick={loadSpendData} 
                  disabled={loadingSpend}
                  className="p-2 bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-zinc-200 rounded-lg transition-all"
                  title="Reload spend data"
                >
                  <RefreshCw className={`w-4 h-4 ${loadingSpend ? 'animate-spin' : ''}`} />
                </button>
              </div>

              <div className="border border-zinc-800/60 bg-zinc-950/40 rounded-2xl p-4">
                {loadingSpend ? (
                  <div className="h-48 flex flex-col items-center justify-center gap-2">
                    <Loader2 className="w-6 h-6 text-brandIndigo animate-spin" />
                    <span className="text-zinc-500 text-xs">Querying Cost Explorer...</span>
                  </div>
                ) : (
                  renderSVGChart()
                )}
              </div>
            </div>

            {/* Test Trigger Actions */}
            <div className="bg-darkCard/50 backdrop-blur-xl border border-zinc-800/80 rounded-3xl p-6 shadow-2xl space-y-4">
              <div>
                <h4 className="text-sm font-bold text-white flex items-center gap-1.5">
                  <Play className="w-4 h-4 text-brandIndigo" /> Alerts Integration Tester
                </h4>
                <p className="text-zinc-500 text-xs mt-0.5">
                  Manually trigger an anomaly check scan. If no cost spike is detected, it will dispatch a test payload to verify channels.
                </p>
              </div>

              <div className="flex gap-4 items-center">
                <button 
                  onClick={handleTriggerScan}
                  disabled={scanning}
                  className="px-5 py-3 bg-zinc-900 border border-zinc-800 text-zinc-200 hover:bg-zinc-800/80 text-xs font-semibold rounded-xl flex items-center gap-2 transition-all disabled:opacity-50"
                >
                  {scanning ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Bell className="w-3.5 h-3.5 text-brandIndigo" />}
                  Trigger Alert Scan (Test)
                </button>

                {scanResult && (
                  <div className="flex-1 p-2 px-3 bg-zinc-950/60 border border-zinc-800 rounded-xl text-xs space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-zinc-400 font-semibold">Test Scan Status:</span>
                      <span className="text-zinc-400 font-mono text-[10px]">{scanResult.status}</span>
                    </div>
                    {scanResult.notified && scanResult.notified.length > 0 ? (
                      <div className="text-[10px] text-emerald-400">
                        Delivered alert notifications to: {scanResult.notified.join(', ')}
                      </div>
                    ) : (
                      <div className="text-[10px] text-zinc-500 italic">No webhooks or emails notified (empty channels configuration).</div>
                    )}
                  </div>
                )}
              </div>
            </div>

          </div>

        </div>

        {/* BOTTOM: Alert Logs History Table */}
        <div className="bg-darkCard/50 backdrop-blur-xl border border-zinc-800/80 rounded-3xl p-6 shadow-2xl space-y-4">
          <div className="flex items-center gap-2">
            <Bell className="w-5 h-5 text-brandIndigo" />
            <div>
              <h3 className="text-lg font-bold text-white">Alert Log History</h3>
              <p className="text-zinc-500 text-xs mt-0.5">Historical log of audit alerts triggered and active notifications sent</p>
            </div>
          </div>

          <div className="overflow-x-auto rounded-2xl border border-zinc-800/60">
            <table className="w-full border-collapse text-left text-xs">
              <thead className="bg-zinc-950/40 text-zinc-400 uppercase font-mono tracking-wider font-bold border-b border-zinc-800/80">
                <tr>
                  <th className="p-4">Date</th>
                  <th className="p-4">Alert Description</th>
                  <th className="p-4">Status</th>
                  <th className="p-4">Channels Notified</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60 text-zinc-300">
                {logs.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="p-8 text-center text-zinc-500 italic">
                      No alert history logs recorded. Modify threshold rules or trigger a manual scan to verify.
                    </td>
                  </tr>
                ) : (
                  logs.map((log) => {
                    const dateObj = new Date(log.created_at || log.date);
                    const localDateStr = dateObj.toLocaleString(undefined, {
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit'
                    });

                    return (
                      <tr key={log.id} className="hover:bg-zinc-900/10">
                        <td className="p-4 whitespace-nowrap font-medium text-zinc-400">
                          {localDateStr}
                        </td>
                        <td className="p-4">
                          Cost spike on {log.date} flagged at <span className="font-semibold text-white">${log.details.amount.toFixed(2)}</span> (exceeded rolling average of ${log.details.average.toFixed(2)} by +{log.details.percent_increase.toFixed(1)}%)
                        </td>
                        <td className="p-4 whitespace-nowrap">
                          {getStatusBadge(log.status)}
                        </td>
                        <td className="p-4 text-zinc-400">
                          {log.channels && log.channels.length > 0 ? (
                            <div className="flex flex-wrap gap-1">
                              {log.channels.map((chan, idx) => (
                                <span key={idx} className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-[10px] text-zinc-400 font-mono">
                                  {chan}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span className="italic text-zinc-600">None</span>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </div>
  );
}
