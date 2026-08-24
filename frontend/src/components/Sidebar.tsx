import { useState, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import {
  Shield,
  ShieldCheck,
  LayoutDashboard,
  History,
  TrendingUp,
  AlertTriangle,
  Scan,
  LogOut,
  ChevronLeft,
  ChevronRight,
  User,
  X,
} from 'lucide-react';
import { insforge } from '../insforge';

interface NavItem {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  end?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: '/',          label: 'Dashboard',     icon: LayoutDashboard, end: true },
  { to: '/scan',      label: 'Run Scan',      icon: Scan },
  { to: '/quarantine', label: 'Quarantine',   icon: Shield },
  { to: '/audit',     label: 'Audit & RBAC',  icon: ShieldCheck },
  { to: '/history',   label: 'History',       icon: History },
  { to: '/anomalies', label: 'Anomalies',     icon: AlertTriangle },
  { to: '/budgets',   label: 'Budgets',       icon: TrendingUp },
];

interface SidebarProps {
  mobileOpen: boolean;
  onMobileClose: () => void;
}

export default function Sidebar({ mobileOpen, onMobileClose }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [userEmail, setUserEmail] = useState('');


  useEffect(() => {
    const fetchUser = async () => {
      const u = (insforge as any).tokenManager?.getUser?.();
      if (u?.email) {
        setUserEmail(u.email);
        return;
      }
      try {
        const { data } = await insforge.auth.getCurrentUser();
        if (data?.user?.email) {
          setUserEmail(data.user.email);
        }
      } catch {}
    };
    fetchUser();
  }, []);

  const handleLogout = async () => {
    sessionStorage.clear();
    localStorage.clear();
    try {
      await insforge.auth.signOut();
    } catch (e) {
      console.warn('Sign out error:', e);
    }
    window.location.href = '/login';
  };

  const NavContent = () => (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className={`flex items-center gap-3 px-4 py-5 border-b border-zinc-800 ${collapsed ? 'justify-center' : ''}`}>
        <div className="w-8 h-8 rounded-lg bg-indigo-500/15 border border-indigo-500/25 flex items-center justify-center shrink-0">
          <Shield className="w-4 h-4 text-indigo-400" />
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <span className="block text-sm font-bold text-white tracking-tight leading-tight">Cloud Cost</span>
            <span className="block text-[10px] font-semibold text-indigo-400 uppercase tracking-widest leading-tight">Detective</span>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 py-4 space-y-0.5 overflow-y-auto">
        {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={onMobileClose}
            title={collapsed ? label : undefined}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors group relative ${
                isActive
                  ? 'bg-indigo-500/12 text-indigo-400 border border-indigo-500/20'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60'
              } ${collapsed ? 'justify-center' : ''}`
            }
          >
            {({ isActive }) => (
              <>
                <Icon className={`w-4 h-4 shrink-0 ${isActive ? 'text-indigo-400' : ''}`} />
                {!collapsed && <span>{label}</span>}
                {/* Tooltip when collapsed */}
                {collapsed && (
                  <span className="absolute left-full ml-3 px-2.5 py-1 bg-zinc-900 border border-zinc-800 text-xs text-white rounded-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50 shadow-xl">
                    {label}
                  </span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Bottom: user + collapse */}
      <div className="border-t border-zinc-800 p-2 space-y-1">
        {/* User row */}
        {userEmail && (
          <div className={`flex items-center gap-3 px-3 py-2.5 rounded-lg ${collapsed ? 'justify-center' : ''}`}>
            <div className="w-7 h-7 rounded-full bg-indigo-500/15 border border-indigo-500/20 flex items-center justify-center shrink-0">
              <User className="w-3.5 h-3.5 text-indigo-400" />
            </div>
            {!collapsed && (
              <span className="text-xs text-zinc-400 font-medium truncate flex-1">{userEmail}</span>
            )}
          </div>
        )}

        {/* Logout */}
        <button
          onClick={handleLogout}
          title={collapsed ? 'Log out' : undefined}
          className={`flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-500 hover:text-red-400 hover:bg-red-500/8 transition-colors ${collapsed ? 'justify-center' : ''}`}
        >
          <LogOut className="w-4 h-4 shrink-0" />
          {!collapsed && <span>Log out</span>}
        </button>

        {/* Collapse toggle (desktop only) */}
        <button
          onClick={() => setCollapsed(c => !c)}
          className="hidden md:flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm font-medium text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800/40 transition-colors justify-center"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          {!collapsed && <span className="text-xs">Collapse</span>}
        </button>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop sidebar */}
      <aside
        className={`hidden md:flex flex-col fixed inset-y-0 left-0 z-30 bg-darkCard border-r border-zinc-800 transition-all duration-200 ${
          collapsed ? 'w-16' : 'w-56'
        }`}
      >
        <NavContent />
      </aside>

      {/* Mobile: backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm md:hidden"
          onClick={onMobileClose}
        />
      )}

      {/* Mobile: drawer */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-64 bg-darkCard border-r border-zinc-800 flex flex-col md:hidden transition-transform duration-200 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Close button */}
        <button
          onClick={onMobileClose}
          className="absolute top-4 right-4 p-1 text-zinc-500 hover:text-zinc-300"
        >
          <X className="w-5 h-5" />
        </button>
        <NavContent />
      </aside>
    </>
  );
}
