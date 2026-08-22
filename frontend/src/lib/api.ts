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
}

export interface CfnTemplateResponse {
  external_id: string;
  saas_account_id: string;
  cfn_yaml: string;
  quick_create_url: string;
}

export async function getCfnTemplate(): Promise<CfnTemplateResponse> {
  return apiFetch<CfnTemplateResponse>('/api/v1/accounts/cfn-template');
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

