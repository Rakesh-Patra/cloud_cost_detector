import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LayoutDashboard, Play, CloudLightning, Loader2, AlertCircle } from 'lucide-react';
import { insforge } from '../insforge';
import ProgressTracker from '../components/ProgressTracker';

export default function Dashboard() {
  const [regions, setRegions] = useState<string[]>([]);
  const [selectedRegion, setSelectedRegion] = useState('');
  const [loadingRegions, setLoadingRegions] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [progressLogs, setProgressLogs] = useState<string[]>([]);
  const [scanError, setScanError] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const navigate = useNavigate();

  // Helper function to fetch from backend with InsForge Authorization header
  const apiFetch = async (endpoint: string, options: RequestInit = {}) => {
    const token = (insforge as any).tokenManager.getAccessToken();
    
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    };

    const backendUrl = import.meta.env.VITE_BACKEND_URL || `${window.location.protocol}//${window.location.hostname}:8000`;
    const response = await fetch(`${backendUrl}${endpoint}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: 'API request failed' }));
      throw new Error(errorData.detail?.message || errorData.detail || 'API request failed');
    }

    return response.json();
  };

  useEffect(() => {
    const loadRegions = async () => {
      try {
        setLoadingRegions(true);
        const data = await apiFetch('/api/regions');
        if (data?.regions) {
          setRegions(data.regions);
          // Default to us-east-1 if available, otherwise first region
          if (data.regions.includes('us-east-1')) {
            setSelectedRegion('us-east-1');
          } else if (data.regions.length > 0) {
            setSelectedRegion(data.regions[0]);
          }
        }
      } catch (err: any) {
        console.error('Error loading regions:', err);
        setErrorMsg(err.message || 'Failed to fetch active AWS regions. Please check credentials.');
      } finally {
        setLoadingRegions(false);
      }
    };

    loadRegions();
  }, []);

  const handleStartScan = async () => {
    if (!selectedRegion) return;
    
    setScanning(true);
    setScanError(false);
    setProgressLogs(['Initializing AWS clients...']);
    
    const analysisId = crypto.randomUUID();

    // Connect WebSocket for progress updates (best-effort, non-blocking)
    try {
      const wsUrl = import.meta.env.VITE_WS_URL || `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;
      const ws = new WebSocket(`${wsUrl}/ws/progress/${analysisId}`);
      
      ws.onopen = () => console.log('WebSocket connected for progress updates');

      ws.onmessage = (event) => {
        console.log('WS Progress update:', event.data);
        setProgressLogs((prev) => [...prev, event.data]);
        if (event.data.toLowerCase().includes('fail') || event.data.toLowerCase().includes('error')) {
          setScanError(true);
        }
      };

      ws.onerror = (err) => {
        console.error('WS Error (progress updates may be unavailable):', err);
      };

      ws.onclose = () => {
        console.log('WS Connection closed');
      };
    } catch (wsErr) {
      console.warn('WebSocket connection failed, scan will proceed without live progress:', wsErr);
    }

    // Trigger the backend analyze request immediately (do NOT wait for WebSocket)
    try {
      const data = await apiFetch('/api/analyze', {
        method: 'POST',
        body: JSON.stringify({
          region: selectedRegion,
          analysis_id: analysisId,
        }),
      });

      // Store the result in localStorage for FinOpsChat accessibility
      localStorage.setItem('latestScanResult', JSON.stringify(data));

      // Redirect to report page passing scan results as route state
      navigate('/report', { state: { scanResult: data } });
    } catch (err: any) {
      console.error('Scan API failed:', err);
      setScanError(true);
      setProgressLogs((prev) => [...prev, `Analysis failed: ${err.message || 'An error occurred during scanning.'}`]);
    }
  };

  return (
    <div className="min-h-[calc(100vh-73px)] bg-darkBg text-slate-100 p-8 relative overflow-hidden select-none">
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-brandIndigo/5 rounded-full blur-3xl" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-brandPurple/5 rounded-full blur-3xl" />

      <div className="max-w-4xl mx-auto relative z-10">
        <div className="flex items-center gap-4 mb-8">
          <div className="w-12 h-12 bg-brandIndigo/10 border border-brandIndigo/25 rounded-2xl flex items-center justify-center shadow-lg shadow-brandIndigo/5">
            <LayoutDashboard className="w-6 h-6 text-brandIndigo" />
          </div>
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-white">Cost Detective Dashboard</h1>
            <p className="text-zinc-400 text-sm mt-0.5">Select a region to run an AI-powered cost audit</p>
          </div>
        </div>

        {errorMsg && (
          <div className="mb-8 p-4 bg-red-950/30 border border-red-900/40 rounded-2xl flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
            <div>
              <h4 className="text-red-300 font-semibold text-sm">Failed to connect to AWS</h4>
              <p className="text-red-400/80 text-xs mt-0.5">{errorMsg}</p>
              <p className="text-zinc-500 text-xs mt-2">
                Make sure your backend server has access to AWS credentials. You can set them in `backend/.env`.
              </p>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {/* Main Controls Card */}
          <div className="md:col-span-2 bg-darkCard/50 backdrop-blur-xl border border-zinc-800/80 rounded-3xl p-8 shadow-2xl flex flex-col justify-between min-h-[300px]">
            <div className="space-y-6">
              <div className="flex items-center gap-3">
                <CloudLightning className="w-6 h-6 text-brandIndigo" />
                <h2 className="text-lg font-bold text-white">AWS Configuration</h2>
              </div>
              <p className="text-zinc-400 text-sm leading-relaxed">
                Our AI Cost Detective will audit your environment, identifying orphaned storage volumes, idle instances, outdated storage tiers, and suggest automated remediation.
              </p>

              <div className="space-y-2">
                <label className="text-xs font-semibold uppercase tracking-wider text-zinc-400">AWS Target Region</label>
                {loadingRegions ? (
                  <div className="flex items-center gap-3 py-3 px-4 bg-zinc-900 border border-zinc-800 rounded-xl">
                    <Loader2 className="w-4 h-4 text-brandIndigo animate-spin" />
                    <span className="text-zinc-500 text-sm">Loading regions...</span>
                  </div>
                ) : (
                  <select
                    value={selectedRegion}
                    onChange={(e) => setSelectedRegion(e.target.value)}
                    disabled={scanning}
                    className="w-full px-4 py-3 bg-zinc-900/80 border border-zinc-800 rounded-xl text-white focus:outline-none focus:border-brandIndigo focus:ring-1 focus:ring-brandIndigo transition-all disabled:opacity-50"
                  >
                    {regions.map((region) => (
                      <option key={region} value={region}>
                        {region}
                      </option>
                    ))}
                  </select>
                )}
              </div>
            </div>

            <div className="mt-8">
              <button
                onClick={handleStartScan}
                disabled={scanning || loadingRegions || !selectedRegion}
                className="w-full py-4 bg-gradient-to-r from-brandIndigo to-brandPurple hover:from-brandIndigo/90 hover:to-brandPurple/90 text-white font-medium rounded-xl flex items-center justify-center gap-3 shadow-lg shadow-brandIndigo/25 active:scale-[0.98] transition-all disabled:opacity-50 disabled:pointer-events-none"
              >
                {scanning ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Scanning Region...
                  </>
                ) : (
                  <>
                    <Play className="w-5 h-5 fill-current" />
                    Run Optimization Analysis
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Progress Tracker side panel */}
          <div className="md:col-span-1">
            {scanning ? (
            <ProgressTracker
              progressLogs={progressLogs}
              isError={scanError}
              region={selectedRegion}
            />
          ) : (
              <div className="h-full bg-zinc-900/20 border border-zinc-800/40 border-dashed rounded-3xl p-6 flex flex-col items-center justify-center text-center text-zinc-500 min-h-[300px]">
                <CloudLightning className="w-8 h-8 text-zinc-700 mb-2 animate-bounce" />
                <span className="text-sm font-medium">Ready for cost audit</span>
                <span className="text-xs text-zinc-600 mt-1 max-w-[200px]">
                  Select region and launch scan to track real-time audit milestones
                </span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
