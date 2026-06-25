import { CheckCircle2, Circle, Loader2, AlertCircle } from 'lucide-react';

interface ProgressTrackerProps {
  progressLogs: string[];
  isError: boolean;
  region: string;
}

export default function ProgressTracker({ progressLogs, isError, region }: ProgressTrackerProps) {
  const steps = [
    { key: 'init', label: 'Initializing AWS clients...' },
    { key: 'scan', label: `Scanning EC2, EBS, and RDS resources in ${region || 'region'}...` },
    { key: 'gemini', label: 'Generating structured cost analysis via Gemini AI...' },
    { key: 'persist', label: 'Persisting audit metrics to InsForge Cloud...' },
    { key: 'complete', label: 'Analysis complete' }
  ];

  // Determine step status based on historical log array
  const getStepStatus = (index: number) => {
    const isStepInLogs = (stepIndex: number) => {
      const keyword = steps[stepIndex].key;
      return progressLogs.some(log => {
        const logLower = log.toLowerCase();
        if (keyword === 'init') return logLower.includes('init') || logLower.includes('client');
        if (keyword === 'scan') return logLower.includes('scan') || logLower.includes('ec2') || logLower.includes('ebs');
        if (keyword === 'gemini') return logLower.includes('gemini') || logLower.includes('generat');
        if (keyword === 'persist') return logLower.includes('persist') || logLower.includes('insforge');
        if (keyword === 'complete') return logLower.includes('complete');
        return false;
      });
    };

    const stepSeen = isStepInLogs(index);
    if (!stepSeen) {
      return 'pending';
    }

    // Check if any subsequent steps have already been initialized
    const laterStepSeen = Array.from({ length: steps.length - index - 1 }, (_, i) => index + i + 1)
      .some(laterIdx => isStepInLogs(laterIdx));

    if (laterStepSeen) {
      return 'completed';
    }

    // If it's the current active step and there's a failure flag
    if (isError) {
      return 'failed';
    }

    // Special case for complete step
    if (index === 4 && progressLogs.some(log => log.toLowerCase().includes('complete'))) {
      return 'completed';
    }

    return 'active';
  };

  const lastLog = progressLogs[progressLogs.length - 1] || 'Running...';

  return (
    <div className="w-full bg-zinc-900/40 border border-zinc-800 rounded-2xl p-6 shadow-xl backdrop-blur-md">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-brandIndigo mb-6">Scan Process Tracker</h3>
      <div className="space-y-6">
        {steps.map((step, idx) => {
          const status = getStepStatus(idx);
          return (
            <div key={step.key} className="flex items-center gap-4 relative">
              {/* Connector line between steps */}
              {idx < steps.length - 1 && (
                <div
                  className={`absolute left-5 top-10 w-[2px] h-8 -z-10 transition-colors duration-500 ${
                    status === 'completed' ? 'bg-emerald-500' : 'bg-zinc-800'
                  }`}
                />
              )}

              {/* Status Icons */}
              <div className="flex items-center justify-center w-10 h-10 rounded-full shrink-0 z-10 transition-all duration-300">
                {status === 'completed' && (
                  <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 p-2 rounded-full shadow-lg shadow-emerald-500/10">
                    <CheckCircle2 className="w-5 h-5" />
                  </div>
                )}
                {status === 'active' && (
                  <div className="bg-brandIndigo/10 border border-brandIndigo/40 text-brandIndigo p-2 rounded-full shadow-lg shadow-brandIndigo/15 animate-pulse">
                    <Loader2 className="w-5 h-5 animate-spin" />
                  </div>
                )}
                {status === 'failed' && (
                  <div className="bg-red-500/10 border border-red-500/30 text-red-400 p-2 rounded-full shadow-lg shadow-red-500/10">
                    <AlertCircle className="w-5 h-5" />
                  </div>
                )}
                {status === 'pending' && (
                  <div className="text-zinc-600 p-2 rounded-full">
                    <Circle className="w-5 h-5" />
                  </div>
                )}
              </div>

              {/* Text Label */}
              <div className="flex flex-col max-w-[calc(100%-3rem)]">
                <span
                  className={`text-sm font-medium transition-colors truncate ${
                    status === 'completed'
                      ? 'text-zinc-300 line-through decoration-zinc-700/50'
                      : status === 'active'
                      ? 'text-white font-semibold'
                      : status === 'failed'
                      ? 'text-red-400 font-semibold'
                      : 'text-zinc-500'
                  }`}
                >
                  {step.label}
                </span>
                {status === 'active' && (
                  <span className="text-[10px] text-zinc-400 mt-0.5 animate-pulse">
                    Processing...
                  </span>
                )}
                {status === 'failed' && (
                  <span className="text-xs text-red-300 mt-1 bg-red-950/20 border border-red-900/35 rounded-lg px-3 py-1 font-mono break-words whitespace-pre-wrap">
                    {lastLog}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
