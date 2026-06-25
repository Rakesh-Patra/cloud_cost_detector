import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { insforge } from './insforge';
import Navbar from './components/Navbar';
import FinOpsChat from './components/FinOpsChat';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Verify from './pages/Verify';
import Dashboard from './pages/Dashboard';
import Report from './pages/Report';
import History from './pages/History';
import Budgets from './pages/Budgets';

// Layout wrapper including navbar for protected pages
function ProtectedLayout() {
  return (
    <div className="min-h-screen bg-darkBg text-slate-100 flex flex-col font-sans relative">
      <Navbar />
      <main className="flex-1 pt-[73px]">
        <Outlet />
      </main>
      <FinOpsChat />
    </div>
  );
}

// Router guard to redirect unauthenticated users to login page
interface ProtectedRouteProps {
  user: any;
  loading: boolean;
}

function ProtectedRoute({ user, loading }: ProtectedRouteProps) {
  if (loading) {
    return (
      <div className="min-h-screen bg-darkBg flex flex-col items-center justify-center gap-3">
        <Loader2 className="w-8 h-8 text-brandIndigo animate-spin" />
        <span className="text-zinc-500 text-sm font-medium">Resolving user session...</span>
      </div>
    );
  }
  return user ? <Outlet /> : <Navigate to="/login" replace />;
}

export default function App() {
  const [user, setUser] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const resolveSession = async () => {
      try {
        // Retrieve active user directly from TokenManager
        const currentUser = (insforge as any).tokenManager.getUser();
        setUser(currentUser || null);
      } catch (e) {
        console.error('Error resolving session:', e);
      } finally {
        setLoading(false);
      }
    };
    resolveSession();

    // Subscribe to session state changes via TokenManager onTokenChange
    const updateSession = () => {
      const currentUser = (insforge as any).tokenManager.getUser();
      setUser(currentUser || null);
      setLoading(false);
    };

    (insforge as any).tokenManager.onTokenChange = updateSession;

    return () => {
      (insforge as any).tokenManager.onTokenChange = null;
    };
  }, []);

  return (
    <BrowserRouter>
      <Routes>
        {/* Public Routes */}
        <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
        <Route path="/signup" element={user ? <Navigate to="/" replace /> : <Signup />} />
        <Route path="/verify" element={user ? <Navigate to="/" replace /> : <Verify />} />

        {/* Protected Routes */}
        <Route element={<ProtectedRoute user={user} loading={loading} />}>
          <Route element={<ProtectedLayout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/report" element={<Report />} />
            <Route path="/history" element={<History />} />
            <Route path="/budgets" element={<Budgets />} />
          </Route>
        </Route>

        {/* Catch-all fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
