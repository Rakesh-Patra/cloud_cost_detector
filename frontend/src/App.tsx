import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { insforge } from './insforge';
import Sidebar from './components/Sidebar';
import TopBar from './components/TopBar';
import FinOpsChat from './components/FinOpsChat';

// Pages
import Login from './pages/Login';
import Signup from './pages/Signup';
import Verify from './pages/Verify';
import Dashboard from './pages/Dashboard';
import Report from './pages/Report';
import History from './pages/History';
import Budgets from './pages/Budgets';
import Anomalies from './pages/Anomalies';
import { Quarantine } from './pages/Quarantine';
import { AuditLogs } from './pages/AuditLogs';

/** Full-app protected layout: sidebar + topbar + content area */
function ProtectedLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="min-h-screen bg-darkBg text-slate-100 flex">
      <Sidebar mobileOpen={mobileOpen} onMobileClose={() => setMobileOpen(false)} />

      {/* Main content — offset by sidebar width on desktop */}
      <div className="flex flex-col flex-1 min-w-0 md:ml-56 transition-[margin] duration-200">
        <TopBar onMenuClick={() => setMobileOpen(true)} />

        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>

      {/* Floating AI Chat assistant */}
      <FinOpsChat />
    </div>
  );
}

/** Session loading screen */
function SessionLoader() {
  return (
    <div className="min-h-screen bg-darkBg flex flex-col items-center justify-center gap-3">
      <Loader2 className="w-8 h-8 text-indigo-500 animate-spin" />
      <span className="text-zinc-500 text-sm font-medium">Resolving session…</span>
    </div>
  );
}

/** Route guard — redirects unauthenticated users to /login */
function ProtectedRoute({ user, loading }: { user: any; loading: boolean }) {
  if (loading) return <SessionLoader />;
  return user ? <Outlet /> : <Navigate to="/login" replace />;
}

export default function App() {
  const [user, setUser] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    const resolveSession = async () => {
      // 1. Check in-memory user first
      const memUser = (insforge as any).tokenManager?.getUser?.();
      if (memUser) {
        if (isMounted) {
          setUser(memUser);
          setLoading(false);
        }
        return;
      }

      // 2. Asynchronously verify / refresh session via SDK (reads refresh cookie/token)
      try {
        const { data, error } = await insforge.auth.getCurrentUser();
        if (isMounted) {
          if (data?.user && !error) {
            setUser(data.user);
          } else {
            setUser(null);
          }
        }
      } catch {
        if (isMounted) setUser(null);
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    resolveSession();

    if ((insforge as any).tokenManager) {
      (insforge as any).tokenManager.onTokenChange = () => {
        const currentUser = (insforge as any).tokenManager?.getUser?.();
        setUser(currentUser ?? null);
      };
    }

    return () => {
      isMounted = false;
      if ((insforge as any).tokenManager) {
        (insforge as any).tokenManager.onTokenChange = null;
      }
    };
  }, []);

  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes */}
        <Route path="/login"  element={user ? <Navigate to="/" replace /> : <Login />} />
        <Route path="/signup" element={user ? <Navigate to="/" replace /> : <Signup />} />
        <Route path="/verify" element={user ? <Navigate to="/" replace /> : <Verify />} />

        {/* Protected routes */}
        <Route element={<ProtectedRoute user={user} loading={loading} />}>
          <Route element={<ProtectedLayout />}>
            <Route path="/"          element={<Dashboard />} />
            <Route path="/scan"      element={<Dashboard scanMode />} />
            <Route path="/report"    element={<Report />} />
            <Route path="/history"   element={<History />} />
            <Route path="/anomalies" element={<Anomalies />} />
            <Route path="/budgets"   element={<Budgets />} />
            <Route path="/quarantine" element={<Quarantine />} />
            <Route path="/audit"     element={<AuditLogs />} />
          </Route>
        </Route>

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
