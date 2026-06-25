import { useEffect, useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { Shield, LayoutDashboard, History, LogOut, User, TrendingUp } from 'lucide-react';
import { insforge } from '../insforge';

export default function Navbar() {
  const [userEmail, setUserEmail] = useState<string>('');
  const navigate = useNavigate();

  useEffect(() => {
    const fetchUser = () => {
      const user = (insforge as any).tokenManager.getUser();
      if (user) {
        setUserEmail(user.email || 'User');
      }
    };
    fetchUser();

    // Subscribe to auth state updates via TokenManager
    const updateSession = () => {
      const user = (insforge as any).tokenManager.getUser();
      if (user) {
        setUserEmail(user.email || 'User');
      } else {
        setUserEmail('');
      }
    };

    (insforge as any).tokenManager.onTokenChange = updateSession;

    return () => {
      (insforge as any).tokenManager.onTokenChange = null;
    };
  }, []);

  const handleLogout = async () => {
    await insforge.auth.signOut();
    navigate('/login');
  };

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-darkCard/80 backdrop-blur-md border-b border-zinc-800/80 px-6 py-4 flex items-center justify-between text-slate-100 shadow-lg">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-brandIndigo/10 border border-brandIndigo/25 rounded-xl flex items-center justify-center shadow-md">
          <Shield className="w-5 h-5 text-brandIndigo" />
        </div>
        <div>
          <span className="font-bold text-white text-base tracking-tight">AI Cloud Cost Detective</span>
          <span className="text-[10px] uppercase font-bold tracking-widest text-brandIndigo block -mt-1 font-mono">Scanner v1.0</span>
        </div>
      </div>

      <div className="flex items-center gap-8">
        <div className="flex items-center gap-2">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              `flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                isActive
                  ? 'bg-zinc-950 border border-zinc-800 text-white shadow-inner shadow-black/40'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`
            }
          >
            <LayoutDashboard className="w-4 h-4" />
            Dashboard
          </NavLink>

          <NavLink
            to="/history"
            className={({ isActive }) =>
              `flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                isActive
                  ? 'bg-zinc-950 border border-zinc-800 text-white shadow-inner shadow-black/40'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`
            }
          >
            <History className="w-4 h-4" />
            History
          </NavLink>

          <NavLink
            to="/budgets"
            className={({ isActive }) =>
              `flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                isActive
                  ? 'bg-zinc-950 border border-zinc-800 text-white shadow-inner shadow-black/40'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`
            }
          >
            <TrendingUp className="w-4 h-4" />
            Budgets & Alerts
          </NavLink>
        </div>

        {userEmail && (
          <div className="h-6 w-[1px] bg-zinc-800" />
        )}

        {userEmail && (
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 bg-zinc-900 border border-zinc-800/80 rounded-xl px-4 py-2 text-sm text-zinc-300 font-medium">
              <User className="w-4 h-4 text-brandIndigo" />
              <span className="max-w-[150px] truncate">{userEmail}</span>
            </div>

            <button
              onClick={handleLogout}
              className="p-2 hover:bg-red-950/20 hover:text-red-400 text-zinc-400 border border-transparent hover:border-red-900/30 rounded-xl transition-all"
              title="Log Out"
            >
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        )}
      </div>
    </nav>
  );
}
