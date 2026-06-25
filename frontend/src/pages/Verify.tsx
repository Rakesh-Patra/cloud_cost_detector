import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { Key, Loader2, AlertTriangle, CheckCircle2, RefreshCw } from 'lucide-react';
import { insforge } from '../insforge';

export default function Verify() {
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const [resendMessage, setResendMessage] = useState('');
  const [countdown, setCountdown] = useState(0);
  const navigate = useNavigate();

  // Prefill email from query parameters
  useEffect(() => {
    const emailParam = searchParams.get('email');
    if (emailParam) {
      setEmail(emailParam);
    }
  }, [searchParams]);

  // Countdown timer for resending OTP
  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [countdown]);

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setResendMessage('');
    setLoading(true);

    if (!email.trim()) {
      setError('Please provide your email address.');
      setLoading(false);
      return;
    }

    if (!otp.trim() || otp.trim().length < 4) {
      setError('Please enter a valid verification code.');
      setLoading(false);
      return;
    }

    try {
      const { error: authError } = await insforge.auth.verifyEmail({
        email: email.trim(),
        otp: otp.trim(),
      });

      if (authError) {
        setError(authError.message || 'Verification failed. Please check the code and try again.');
      } else {
        setSuccess(true);
        setTimeout(() => {
          navigate('/login', { state: { verifiedEmail: email } });
        }, 3000);
      }
    } catch (err: any) {
      if (err.message?.includes('fetch') || err.message?.includes('network') || err.name === 'TypeError') {
        setError('Network request failed: Could not connect to the authentication server.');
      } else {
        setError(err.message || 'An unexpected error occurred during verification.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    if (countdown > 0 || resending) return;
    
    setError('');
    setResendMessage('');
    
    if (!email.trim()) {
      setError('Please enter your email address to resend the code.');
      return;
    }

    setResending(true);
    try {
      const { error: authError } = await insforge.auth.resendVerificationEmail({
        email: email.trim(),
      });

      if (authError) {
        setError(authError.message || 'Failed to resend verification email.');
      } else {
        setResendMessage('Verification code has been resent to your email.');
        setCountdown(60); // 60 seconds cooldown
      }
    } catch (err: any) {
      setError(err.message || 'An unexpected error occurred while resending the code.');
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="min-h-screen bg-darkBg text-slate-100 flex items-center justify-center p-4 relative overflow-hidden select-none">
      {/* Background glows */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-brandIndigo/10 rounded-full blur-3xl" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-brandPurple/10 rounded-full blur-3xl" />

      <div className="w-full max-w-md bg-darkCard/50 backdrop-blur-xl border border-zinc-800/80 rounded-2xl p-8 relative z-10 shadow-2xl">
        <div className="flex flex-col items-center mb-8">
          <div className="w-16 h-16 bg-brandIndigo/10 border border-brandIndigo/30 rounded-2xl flex items-center justify-center mb-4 shadow-lg shadow-brandIndigo/5">
            <Key className="w-8 h-8 text-brandIndigo animate-pulse" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white font-sans">Verify Your Email</h1>
          <p className="text-zinc-400 text-sm mt-1 text-center">
            Enter the confirmation code sent to your email
          </p>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-950/40 border border-red-900/50 rounded-xl flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
            <span className="text-red-300 text-sm font-medium">{error}</span>
          </div>
        )}

        {resendMessage && (
          <div className="mb-6 p-4 bg-emerald-950/40 border border-emerald-900/50 rounded-xl flex items-start gap-3">
            <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
            <span className="text-emerald-300 text-sm font-medium">{resendMessage}</span>
          </div>
        )}

        {success ? (
          <div className="p-6 bg-emerald-950/40 border border-emerald-900/50 rounded-xl flex flex-col items-center text-center gap-3">
            <CheckCircle2 className="w-10 h-10 text-emerald-400" />
            <h3 className="text-emerald-300 font-semibold text-lg">Email Verified Successfully</h3>
            <p className="text-emerald-400/80 text-sm">
              Your email has been verified. Redirecting to login page...
            </p>
          </div>
        ) : (
          <form onSubmit={handleVerify} className="space-y-5">
            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Email Address</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full px-4 py-3 bg-zinc-900/80 border border-zinc-800 rounded-xl text-white placeholder-zinc-500 focus:outline-none focus:border-brandIndigo focus:ring-1 focus:ring-brandIndigo transition-all"
                disabled={loading}
              />
            </div>

            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <label className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Verification Code</label>
                <button
                  type="button"
                  onClick={handleResend}
                  disabled={countdown > 0 || resending || loading}
                  className="text-xs text-brandIndigo hover:text-brandPurple transition-colors font-medium flex items-center gap-1 disabled:opacity-50 disabled:pointer-events-none"
                >
                  {resending ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <RefreshCw className="w-3 h-3" />
                  )}
                  {countdown > 0 ? `Resend in ${countdown}s` : 'Resend Code'}
                </button>
              </div>
              <input
                type="text"
                required
                maxLength={10}
                value={otp}
                onChange={(e) => setOtp(e.target.value.replace(/[^a-zA-Z0-9]/g, ''))}
                placeholder="Enter verification code"
                className="w-full px-4 py-3 bg-zinc-900/80 border border-zinc-800 rounded-xl text-white text-center font-mono tracking-widest text-lg placeholder-zinc-500 focus:outline-none focus:border-brandIndigo focus:ring-1 focus:ring-brandIndigo transition-all"
                disabled={loading}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3.5 bg-gradient-to-r from-brandIndigo to-brandPurple hover:from-brandIndigo/90 hover:to-brandPurple/90 text-white font-medium rounded-xl flex items-center justify-center gap-2 shadow-lg shadow-brandIndigo/25 active:scale-[0.98] transition-all disabled:opacity-50 disabled:pointer-events-none"
            >
              {loading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Verifying...
                </>
              ) : (
                'Verify & Continue'
              )}
            </button>
          </form>
        )}

        <div className="mt-8 text-center text-sm text-zinc-400">
          Back to{' '}
          <Link to="/login" className="text-brandIndigo hover:text-brandPurple font-medium transition-colors">
            Sign In
          </Link>
        </div>
      </div>
    </div>
  );
}
