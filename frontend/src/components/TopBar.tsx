import { useEffect, useState } from 'react';
import { Menu, ShieldCheck, Cloud, AlertCircle } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { getCloudAccounts, type CloudAccount } from '../lib/api';

const PAGE_TITLES: Record<string, string> = {
  '/':          'Dashboard',
  '/scan':      'Run Scan',
  '/report':    'Scan Report',
  '/history':   'History',
  '/anomalies': 'Anomalies',
  '/budgets':   'Budgets & Alerts',
  '/quarantine': 'Quarantine & Safe Actions',
};

interface TopBarProps {
  onMenuClick: () => void;
}

export default function TopBar({ onMenuClick }: TopBarProps) {
  const location = useLocation();
  const title = PAGE_TITLES[location.pathname] ?? 'Cloud Cost Detective';

  const [accounts, setAccounts] = useState<CloudAccount[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchAccounts = async () => {
    try {
      const res = await getCloudAccounts();
      setAccounts(res.accounts || []);
    } catch {
      setAccounts([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAccounts();

    const handleAccountsUpdated = () => {
      fetchAccounts();
    };

    window.addEventListener('cloud-accounts-updated', handleAccountsUpdated);
    return () => {
      window.removeEventListener('cloud-accounts-updated', handleAccountsUpdated);
    };
  }, []);

  const activeAccount = accounts.length > 0 ? accounts[0] : null;

  return (
    <header className="sticky top-0 z-20 flex items-center justify-between gap-4 px-4 md:px-6 h-14 bg-darkBg border-b border-zinc-800/60 backdrop-blur-sm">
      {/* Left: Mobile hamburger + Page title */}
      <div className="flex items-center gap-3 min-w-0">
        <button
          onClick={onMenuClick}
          className="md:hidden p-2 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/60 transition-colors"
          aria-label="Open navigation"
        >
          <Menu className="w-5 h-5" />
        </button>

        <h1 className="text-sm font-semibold text-white truncate">{title}</h1>
      </div>

      {/* Right: Connected AWS Account Status & Badge */}
      <div className="flex items-center gap-3">
        {!loading && (
          activeAccount ? (
            <div className="flex items-center gap-2 px-3 py-1 bg-emerald-950/40 border border-emerald-500/30 rounded-full text-xs text-emerald-300 shadow-sm shadow-emerald-900/20">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <Cloud className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              <span className="font-semibold">{activeAccount.account_alias}</span>
              <span className="font-mono text-zinc-400 hidden sm:inline">({activeAccount.aws_account_id})</span>
              <span className="text-[10px] bg-emerald-500/20 text-emerald-300 px-1.5 py-0.5 rounded font-mono hidden md:inline">STS</span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 px-3 py-1 bg-amber-950/30 border border-amber-500/30 rounded-full text-xs text-amber-300">
              <AlertCircle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
              <span>No AWS Account Connected</span>
            </div>
          )
        )}

        <div className="hidden lg:flex items-center gap-1.5 text-[11px] text-zinc-500 font-mono pl-2 border-l border-zinc-800">
          <ShieldCheck className="w-3.5 h-3.5 text-indigo-400" />
          <span>STS AssumeRole</span>
        </div>
      </div>
    </header>
  );
}

