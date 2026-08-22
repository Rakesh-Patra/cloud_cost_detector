import { useEffect, useState } from 'react';
import { CheckCircle2, AlertCircle, X } from 'lucide-react';

type ToastType = 'success' | 'error' | 'info';

interface ToastProps {
  message: string;
  title?: string;
  type?: ToastType;
  duration?: number;
  onDismiss?: () => void;
}

const icons: Record<ToastType, typeof CheckCircle2> = {
  success: CheckCircle2,
  error: AlertCircle,
  info: AlertCircle,
};

const styles: Record<ToastType, string> = {
  success: 'border-emerald-500/30 text-emerald-400',
  error:   'border-red-500/30 text-red-400',
  info:    'border-indigo-500/30 text-indigo-400',
};

export function Toast({ message, title, type = 'success', duration = 5000, onDismiss }: ToastProps) {
  const [visible, setVisible] = useState(true);
  const Icon = icons[type];

  useEffect(() => {
    const t = setTimeout(() => {
      setVisible(false);
      setTimeout(() => onDismiss?.(), 300);
    }, duration);
    return () => clearTimeout(t);
  }, [duration, onDismiss]);

  return (
    <div
      className={`flex items-start gap-3 bg-zinc-950/95 backdrop-blur-md border rounded-xl p-4 shadow-2xl max-w-sm transition-all duration-300 ${styles[type]} ${
        visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2'
      }`}
    >
      <Icon className="w-5 h-5 shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        {title && <p className="text-sm font-semibold text-white mb-0.5">{title}</p>}
        <p className="text-xs text-zinc-400 leading-relaxed">{message}</p>
      </div>
      <button
        onClick={() => { setVisible(false); setTimeout(() => onDismiss?.(), 300); }}
        className="shrink-0 text-zinc-600 hover:text-zinc-400 transition-colors"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}

/** Fixed toast container — rendered at the bottom-right corner */
export function ToastContainer({ children }: { children: React.ReactNode }) {
  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-3">
      {children}
    </div>
  );
}
