import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Shield, Mail, Lock, Loader2, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { insforge } from '../insforge';

function GoogleIcon() {
  return (
    <svg className="w-5 h-5 shrink-0" viewBox="0 0 24 24">
      <path
        fill="#4285F4"
        d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.665-5.17 3.665-9.17Z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.25v3.15C3.26 21.36 7.33 24 12 24Z"
      />
      <path
        fill="#FBBC05"
        d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.25C.45 8.18 0 9.99 0 12s.45 3.82 1.25 5.42l4.03-3.15Z"
      />
      <path
        fill="#EA4335"
        d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.33 0 3.26 2.64 1.25 6.58l4.03 3.15c.95-2.83 3.6-4.93 6.72-4.93Z"
      />
    </svg>
  );
}

export default function Signup() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const navigate = useNavigate();

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      setLoading(false);
      return;
    }

    try {
      const { error: authError } = await insforge.auth.signUp({
        email: email.trim(),
        password,
      });

      if (authError) {
        setError(authError.message || 'Registration failed');
      } else {
        setSuccess(true);
        setTimeout(() => {
          navigate(`/verify?email=${encodeURIComponent(email.trim())}`);
        }, 3000);
      }
    } catch (err: any) {
      if (err.message?.includes('fetch') || err.message?.includes('network') || err.name === 'TypeError') {
        setError('Network request failed: Could not connect to the authentication server. Please check your internet connection and try again.');
      } else {
        setError(err.message || 'An unexpected error occurred');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSignup = async () => {
    setError('');
    setGoogleLoading(true);

    try {
      const { data, error: oauthError } = await insforge.auth.signInWithOAuth('google', {
        redirectTo: window.location.origin,
      });

      if (oauthError) {
        setError(oauthError.message || 'Google sign-up failed');
        setGoogleLoading(false);
      } else if (data?.url) {
        window.location.href = data.url;
      }
    } catch (err: any) {
      setError(err.message || 'Failed to initiate Google authentication');
      setGoogleLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-darkBg text-slate-100 flex items-center justify-center p-4 relative overflow-hidden select-none">
      {/* Background glows */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-brandIndigo/10 rounded-full blur-3xl" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-brandPurple/10 rounded-full blur-3xl" />

      <div className="w-full max-w-md bg-darkCard/50 backdrop-blur-xl border border-zinc-800/80 rounded-2xl p-8 relative z-10 shadow-2xl">
        <div className="flex flex-col items-center mb-8">
          <div className="w-16 h-16 bg-brandPurple/10 border border-brandPurple/30 rounded-2xl flex items-center justify-center mb-4 shadow-lg shadow-brandPurple/5">
            <Shield className="w-8 h-8 text-brandPurple animate-pulse" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Create Account</h1>
          <p className="text-zinc-400 text-sm mt-1">Register to start managing your cloud costs</p>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-950/40 border border-red-900/50 rounded-xl flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
            <span className="text-red-300 text-sm font-medium">{error}</span>
          </div>
        )}

        {success ? (
          <div className="p-6 bg-emerald-950/40 border border-emerald-900/50 rounded-xl flex flex-col items-center text-center gap-3">
            <CheckCircle2 className="w-10 h-10 text-emerald-400" />
            <h3 className="text-emerald-300 font-semibold text-lg">Registration Successful</h3>
            <p className="text-emerald-400/80 text-sm">
              Your account has been created. Redirecting to verification page...
            </p>
          </div>
        ) : (
          <>
            <button
              type="button"
              onClick={handleGoogleSignup}
              disabled={googleLoading || loading}
              className="w-full py-3 px-4 bg-zinc-900 hover:bg-zinc-800/90 border border-zinc-700/80 hover:border-zinc-600 text-zinc-100 font-medium rounded-xl flex items-center justify-center gap-3 shadow-md hover:shadow-lg transition-all active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none mb-6"
            >
              {googleLoading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin text-zinc-400" />
                  <span>Connecting to Google...</span>
                </>
              ) : (
                <>
                  <GoogleIcon />
                  <span>Sign up with Google</span>
                </>
              )}
            </button>

            <div className="relative flex items-center justify-center mb-6">
              <div className="border-t border-zinc-800 w-full" />
              <span className="bg-[#14151a] px-3 text-xs font-medium uppercase tracking-wider text-zinc-500 absolute">
                or register with email
              </span>
            </div>

            <form onSubmit={handleSignup} className="space-y-5">
              <div className="space-y-2">
                <label htmlFor="signup-email" className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Email Address</label>
                <div className="relative">
                  <Mail className="absolute left-3.5 top-3.5 w-5 h-5 text-zinc-500" />
                  <input
                    id="signup-email"
                    name="email"
                    type="email"
                    autoComplete="username email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    className="w-full pl-11 pr-4 py-3 bg-zinc-900/80 border border-zinc-800 rounded-xl text-white placeholder-zinc-500 focus:outline-none focus:border-brandIndigo focus:ring-1 focus:ring-brandIndigo transition-all"
                    disabled={loading || googleLoading}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label htmlFor="signup-password" className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Password</label>
                <div className="relative">
                  <Lock className="absolute left-3.5 top-3.5 w-5 h-5 text-zinc-500" />
                  <input
                    id="signup-password"
                    name="password"
                    type="password"
                    autoComplete="new-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Minimum 6 characters"
                    className="w-full pl-11 pr-4 py-3 bg-zinc-900/80 border border-zinc-800 rounded-xl text-white placeholder-zinc-500 focus:outline-none focus:border-brandIndigo focus:ring-1 focus:ring-brandIndigo transition-all"
                    disabled={loading || googleLoading}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label htmlFor="signup-confirm-password" className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Confirm Password</label>
                <div className="relative">
                  <Lock className="absolute left-3.5 top-3.5 w-5 h-5 text-zinc-500" />
                  <input
                    id="signup-confirm-password"
                    name="confirmPassword"
                    type="password"
                    autoComplete="new-password"
                    required
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Repeat password"
                    className="w-full pl-11 pr-4 py-3 bg-zinc-900/80 border border-zinc-800 rounded-xl text-white placeholder-zinc-500 focus:outline-none focus:border-brandIndigo focus:ring-1 focus:ring-brandIndigo transition-all"
                    disabled={loading || googleLoading}
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading || googleLoading}
                className="w-full py-3.5 bg-gradient-to-r from-brandPurple to-brandIndigo hover:from-brandPurple/90 hover:to-brandIndigo/90 text-white font-medium rounded-xl flex items-center justify-center gap-2 shadow-lg shadow-brandPurple/25 active:scale-[0.98] transition-all disabled:opacity-50 disabled:pointer-events-none"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Creating account...
                  </>
                ) : (
                  'Create Account'
                )}
              </button>
            </form>
          </>
        )}

        {!success && (
          <div className="mt-8 text-center text-sm text-zinc-400">
            Already have an account?{' '}
            <Link to="/login" className="text-brandPurple hover:text-brandIndigo font-medium transition-colors">
              Sign in
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
