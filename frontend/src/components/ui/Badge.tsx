import { type ReactNode } from 'react';

type BadgeVariant =
  | 'default'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info'
  | 'muted'
  | 'indigo';

const variantStyles: Record<BadgeVariant, string> = {
  default:  'bg-zinc-800 text-zinc-300 border-zinc-700',
  success:  'bg-emerald-500/10 text-emerald-400 border-emerald-500/25',
  warning:  'bg-amber-500/10 text-amber-400 border-amber-500/25',
  danger:   'bg-red-500/10 text-red-400 border-red-500/25',
  info:     'bg-blue-500/10 text-blue-400 border-blue-500/25',
  muted:    'bg-zinc-900 text-zinc-500 border-zinc-800',
  indigo:   'bg-indigo-500/10 text-indigo-400 border-indigo-500/25',
};

interface BadgeProps {
  variant?: BadgeVariant;
  children: ReactNode;
  className?: string;
  mono?: boolean;
}

export function Badge({ variant = 'default', children, className = '', mono = false }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-semibold rounded border ${mono ? 'font-mono tracking-wide uppercase' : ''} ${variantStyles[variant]} ${className}`}
    >
      {children}
    </span>
  );
}

/** Severity badge derived from severity string */
export function SeverityBadge({ severity }: { severity: 'critical' | 'high' | 'medium' | 'low' | string }) {
  const map: Record<string, BadgeVariant> = {
    critical: 'danger',
    high: 'danger',
    medium: 'warning',
    low: 'success',
  };
  const variant = map[severity?.toLowerCase()] ?? 'muted';
  return <Badge variant={variant} mono>{severity}</Badge>;
}

/** Status badge for analysis history items */
export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, BadgeVariant> = {
    completed: 'success',
    running: 'warning',
    failed: 'danger',
    success: 'success',
    simulated: 'warning',
    partial_failure: 'warning',
    no_channels: 'muted',
    failure: 'danger',
  };
  const variant = map[status?.toLowerCase()] ?? 'muted';
  const label = status === 'partial_failure' ? 'Partial' : status === 'no_channels' ? 'No Channels' : status;
  return <Badge variant={variant} mono>{label}</Badge>;
}
