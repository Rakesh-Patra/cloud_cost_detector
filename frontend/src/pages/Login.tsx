import { useState, useEffect } from 'react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { Shield, Mail, Lock, Loader2, AlertTriangle } from 'lucide-react';
import { insforge } from '../insforge';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (location.state?.verifiedEmail) {
      setEmail(location.state.verifiedEmail);
    }
  }, [location]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const { error: authError } = await insforge.auth.signInWithPassword({
        email: email.trim(),
        password,
      });

      if (authError) {
        setError(authError.message || 'Authentication failed');
      } else {
        // Successful login
        navigate('/');
      }
    } catch (err: any) {
      setError(err.message || 'An unexpected error occurred');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-darkBg text-slate-100 flex items-center justify-center p-4 relative overflow-hidden select-none">
      {/* Background glow effects */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-brandIndigo/10 rounded-full blur-3xl" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-brandPurple/10 rounded-full blur-3xl" />

      <div className="w-full max-w-md bg-darkCard/50 backdrop-blur-xl border border-zinc-800/80 rounded-2xl p-8 relative z-10 shadow-2xl">
        <div className="flex flex-col items-center mb-8">
          <div className="w-16 h-16 bg-brandIndigo/10 border border-brandIndigo/30 rounded-2xl flex items-center justify-center mb-4 shadow-lg shadow-brandIndigo/5">
            <Shield className="w-8 h-8 text-brandIndigo animate-pulse" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white">AI Cloud Cost Detective</h1>
          <p className="text-zinc-400 text-sm mt-1">Sign in to scan and optimize your AWS cloud</p>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-950/40 border border-red-900/50 rounded-xl flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
            <span className="text-red-300 text-sm font-medium">
              {error}
              {error.toLowerCase().includes('verification') && (
                <div className="mt-2">
                  <Link
                    to={`/verify?email=${encodeURIComponent(email)}`}
                    className="text-brandIndigo hover:text-brandPurple underline font-semibold transition-colors"
                  >
                    Click here to enter your verification code
                  </Link>
                </div>
              )}
            </span>
          </div>
        )}

        <form onSubmit={handleLogin} className="space-y-6">
          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Email Address</label>
            <div className="relative">
              <Mail className="absolute left-3.5 top-3.5 w-5 h-5 text-zinc-500" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full pl-11 pr-4 py-3 bg-zinc-900/80 border border-zinc-800 rounded-xl text-white placeholder-zinc-500 focus:outline-none focus:border-brandIndigo focus:ring-1 focus:ring-brandIndigo transition-all"
                disabled={loading}
              />
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Password</label>
            <div className="relative">
              <Lock className="absolute left-3.5 top-3.5 w-5 h-5 text-zinc-500" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full pl-11 pr-4 py-3 bg-zinc-900/80 border border-zinc-800 rounded-xl text-white placeholder-zinc-500 focus:outline-none focus:border-brandIndigo focus:ring-1 focus:ring-brandIndigo transition-all"
                disabled={loading}
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3.5 bg-gradient-to-r from-brandIndigo to-brandPurple hover:from-brandIndigo/90 hover:to-brandPurple/90 text-white font-medium rounded-xl flex items-center justify-center gap-2 shadow-lg shadow-brandIndigo/25 active:scale-[0.98] transition-all disabled:opacity-50 disabled:pointer-events-none"
          >
            {loading ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                Signing in...
              </>
            ) : (
              'Sign In'
            )}
          </button>
        </form>

        <div className="mt-8 text-center text-sm text-zinc-400">
          Don't have an account?{' '}
          <Link to="/signup" className="text-brandIndigo hover:text-brandPurple font-medium transition-colors">
            Create an account
          </Link>
        </div>
      </div>
    </div>
  );
}
