/**
 * Centralized API fetch helper.
 *
 * All backend requests go through this function so:
 * - Authorization headers are consistently applied
 * - Errors are normalized before bubbling up
 * - The backend base URL is resolved once
 *
 * SECURITY: Tokens are read from insforge.tokenManager at call-time,
 * never stored in module scope or localStorage.
 */
import { insforge } from '../insforge';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || '';

/** Normalized API error that never exposes raw server stack traces. */
export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

/** Extract a clean user-facing message from a FastAPI error body. */
function extractErrorMessage(body: unknown, fallback: string): string {
  if (typeof body !== 'object' || body === null) return fallback;
  const b = body as Record<string, unknown>;
  if (typeof b.detail === 'string') return b.detail;
  if (typeof b.detail === 'object' && b.detail !== null) {
    const d = b.detail as Record<string, unknown>;
    return typeof d.message === 'string' ? d.message : JSON.stringify(d);
  }
  if (typeof b.message === 'string') return b.message;
  return fallback;
}

export async function apiFetch<T = unknown>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  const token = (insforge as any).tokenManager.getAccessToken();

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const response = await fetch(`${BACKEND_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let body: unknown;
    try { body = await response.json(); } catch { body = null; }
    const msg = extractErrorMessage(body, `API request failed (HTTP ${response.status})`);
    throw new ApiError(msg, response.status);
  }

  return response.json() as Promise<T>;
}

/** Resolve the WebSocket base URL from env or derive from current origin. */
export function getWsBaseUrl(): string {
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL;
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}`;
}

// --- Cloud Accounts API ---

export interface CloudAccount {
  id: string;
  org_id: string;
  account_alias: string;
  aws_account_id: string;
  role_arn: string;
  external_id: string;
  status: string;
  regions: string[];
  created_at: string;
  last_scanned_at?: string;
  expires_at?: string | null;
}

export interface CfnTemplateResponse {
  external_id: string;
  saas_account_id: string;
  cfn_yaml: string;
  quick_create_url: string;
  mode?: string;
  duration_days?: number | null;
}

export async function getCfnTemplate(
  mode: 'readonly' | 'remediation' | 'admin' = 'readonly',
  durationDays?: number | null
): Promise<CfnTemplateResponse> {
  const query = new URLSearchParams({ mode });
  if (durationDays && durationDays > 0) {
    query.set('duration_days', durationDays.toString());
  }
  return apiFetch<CfnTemplateResponse>(`/api/v1/accounts/cfn-template?${query.toString()}`);
}

export async function getCloudAccounts(): Promise<{ accounts: CloudAccount[] }> {
  return apiFetch<{ accounts: CloudAccount[] }>('/api/v1/accounts');
}

export async function connectCloudAccount(data: {
  account_alias: string;
  aws_account_id: string;
  role_arn: string;
  external_id: string;
  regions?: string[];
  duration_days?: number | null;
}): Promise<CloudAccount> {
  return apiFetch<CloudAccount>('/api/v1/accounts/connect', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function deleteCloudAccount(accountId: string): Promise<{ success: boolean }> {
  return apiFetch<{ success: boolean }>(`/api/v1/accounts/${accountId}`, {
    method: 'DELETE',
  });
}

// --- Quarantine & Safe Actions API ---

export interface QuarantineItem {
  id: string;
  org_id: string;
  account_id: string;
  resource_id: string;
  resource_type: string;
  region: string;
  reason: string;
  snapshot_id?: string;
  quarantine_until: string;
  status: 'quarantined' | 'restored' | 'deleted';
  created_at: string;
}

export async function getQuarantineItems(statusFilter?: string): Promise<{ items: QuarantineItem[] }> {
  const query = statusFilter ? `?status_filter=${statusFilter}` : '';
  return apiFetch<{ items: QuarantineItem[] }>(`/api/v1/quarantine/items${query}`);
}

export async function applyQuarantine(data: {
  resource_id: string;
  resource_type: string;
  region: string;
  reason: string;
  account_id?: string;
  quarantine_days?: number;
}): Promise<QuarantineItem> {
  return apiFetch<QuarantineItem>('/api/v1/quarantine/apply', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function dismissQuarantine(data: {
  item_id: string;
  resource_id: string;
  region: string;
  account_id?: string;
}): Promise<{ success: boolean; message: string }> {
  return apiFetch<{ success: boolean; message: string }>('/api/v1/quarantine/dismiss', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function safeDeleteQuarantine(data: {
  item_id: string;
  resource_id: string;
  region: string;
  account_id?: string;
}): Promise<{ success: boolean; snapshot_id: string; message: string }> {
  return apiFetch<{ success: boolean; snapshot_id: string; message: string }>('/api/v1/quarantine/safe-delete', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// --- Audit & Security Log APIs ---

export interface AuditLogItem {
  id: string;
  timestamp: string;
  user_id: string;
  user_email: string;
  org_id: string;
  action: string;
  target_arn?: string;
  tier?: string;
  approval_chain?: string;
  result: string;
  details?: Record<string, any>;
}

export interface SecurityEventItem {
  id: string;
  timestamp: string;
  event_type: string;
  user_id: string;
  org_id: string;
  target_arn?: string;
  ip_address?: string;
  details?: Record<string, any>;
  severity: string;
}

export interface RemediationApprovalItem {
  id: string;
  org_id: string;
  requester_id: string;
  requester_email: string;
  approver_id?: string;
  approver_email?: string;
  action: string;
  resource_id: string;
  resource_arn?: string;
  region: string;
  account_id?: string;
  environment: string;
  status: 'pending' | 'approved' | 'rejected';
  reason?: string;
  requested_at: string;
  reviewed_at?: string;
  executed_at?: string;
}

export interface OrgUserItem {
  user_id: string;
  email: string;
  org_id: string;
  role: string;
  status: string;
  domain_verified: boolean;
  created_at: string;
  updated_at: string;
}

export async function getAuditLogs(limit: number = 100): Promise<{ logs: AuditLogItem[]; viewer_role: string }> {
  return apiFetch<{ logs: AuditLogItem[]; viewer_role: string }>(`/api/v1/audit/logs?limit=${limit}`);
}

export async function getSecurityEvents(limit: number = 50): Promise<{ events: SecurityEventItem[] }> {
  return apiFetch<{ events: SecurityEventItem[] }>(`/api/v1/audit/security-events?limit=${limit}`);
}

export async function listRemediationApprovals(statusFilter?: string): Promise<{ approvals: RemediationApprovalItem[] }> {
  const url = statusFilter ? `/api/v1/approvals?status_filter=${statusFilter}` : '/api/v1/approvals';
  return apiFetch<{ approvals: RemediationApprovalItem[] }>(url);
}

export async function reviewRemediationApproval(approvalId: string, decision: 'approved' | 'rejected'): Promise<RemediationApprovalItem> {
  return apiFetch<RemediationApprovalItem>(`/api/v1/approvals/${approvalId}/review`, {
    method: 'POST',
    body: JSON.stringify({ decision }),
  });
}

export async function executeRemediationApproval(approvalId: string): Promise<{ success: boolean; approval_id: string; result: any }> {
  return apiFetch<{ success: boolean; approval_id: string; result: any }>(`/api/v1/approvals/${approvalId}/execute`, {
    method: 'POST',
  });
}

export async function listOrgUsers(): Promise<{ users: OrgUserItem[] }> {
  return apiFetch<{ users: OrgUserItem[] }>('/api/v1/org/users');
}

export async function promoteOrgUser(userId: string, newRole: string, reason: string = ''): Promise<{ success: boolean; message: string }> {
  return apiFetch<{ success: boolean; message: string }>('/api/v1/org/promote', {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, new_role: newRole, reason }),
  });
}


