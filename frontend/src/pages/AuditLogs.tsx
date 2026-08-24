import React, { useState, useEffect } from 'react';
import {
  ShieldAlert,
  History,
  CheckCircle2,
  Clock,
  Lock,
  ArrowUpRight,
  AlertTriangle,
  RefreshCw,
  Users,
  Search
} from 'lucide-react';
import {
  getAuditLogs,
  getSecurityEvents,
  listRemediationApprovals,
  reviewRemediationApproval,
  executeRemediationApproval,
  listOrgUsers,
  promoteOrgUser,
} from '../lib/api';
import type {
  AuditLogItem,
  SecurityEventItem,
  RemediationApprovalItem,
  OrgUserItem
} from '../lib/api';

export const AuditLogs: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'activity' | 'approvals' | 'security' | 'team'>('activity');
  const [activityLogs, setActivityLogs] = useState<AuditLogItem[]>([]);
  const [securityEvents, setSecurityEvents] = useState<SecurityEventItem[]>([]);
  const [approvals, setApprovals] = useState<RemediationApprovalItem[]>([]);
  const [users, setUsers] = useState<OrgUserItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [viewerRole, setViewerRole] = useState<string>('finops');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [selectedDetails, setSelectedDetails] = useState<any | null>(null);

  // Promotion modal state
  const [promoteModalUser, setPromoteModalUser] = useState<OrgUserItem | null>(null);
  const [newRole, setNewRole] = useState<string>('devops');
  const [promoteReason, setPromoteReason] = useState<string>('');
  const [actionLoading, setActionLoading] = useState<boolean>(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [logsRes, apprRes] = await Promise.all([
        getAuditLogs(100).catch(() => ({ logs: [], viewer_role: 'finops' })),
        listRemediationApprovals().catch(() => ({ approvals: [] })),
      ]);
      setActivityLogs(logsRes.logs || []);
      setViewerRole(logsRes.viewer_role || 'finops');
      setApprovals(apprRes.approvals || []);

      if (logsRes.viewer_role === 'admin') {
        const [secRes, usersRes] = await Promise.all([
          getSecurityEvents(50).catch(() => ({ events: [] })),
          listOrgUsers().catch(() => ({ users: [] })),
        ]);
        setSecurityEvents(secRes.events || []);
        setUsers(usersRes.users || []);
      }
    } catch (err) {
      console.error('Error fetching audit records:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleReviewApproval = async (id: string, decision: 'approved' | 'rejected') => {
    setActionLoading(true);
    try {
      await reviewRemediationApproval(id, decision);
      await fetchData();
    } catch (err: any) {
      alert(`Approval Review Error: ${err.message || 'Failed to review request.'}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleExecuteApproval = async (id: string) => {
    setActionLoading(true);
    try {
      await executeRemediationApproval(id);
      await fetchData();
      alert('Remediation action executed successfully under approved dual-control!');
    } catch (err: any) {
      alert(`Execution Error: ${err.message || 'Failed to execute remediation.'}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handlePromoteSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!promoteModalUser) return;
    setActionLoading(true);
    try {
      await promoteOrgUser(promoteModalUser.user_id, newRole, promoteReason);
      setPromoteModalUser(null);
      setPromoteReason('');
      await fetchData();
    } catch (err: any) {
      alert(`Role Update Error: ${err.message || 'Failed to update role.'}`);
    } finally {
      setActionLoading(false);
    }
  };

  const filteredLogs = activityLogs.filter(
    (l) =>
      l.action.toLowerCase().includes(searchTerm.toLowerCase()) ||
      l.user_email.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (l.target_arn && l.target_arn.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  return (
    <div className="p-3.5 sm:p-5 md:p-6 max-w-7xl mx-auto space-y-4 sm:space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 sm:gap-4">
        <div>
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 sm:h-6 sm:w-6 md:h-7 md:w-7 text-indigo-400 shrink-0" />
            <h1 className="text-lg sm:text-xl md:text-2xl font-bold text-slate-100">Security, RBAC & Audit Trail</h1>
          </div>
          <p className="text-xs sm:text-sm text-slate-400 mt-1">
            Immutable activity ledger, dual-control approvals, and least-privilege role management.
          </p>
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          className="self-start md:self-auto flex items-center gap-2 px-3 py-1.5 sm:py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs sm:text-sm border border-slate-700 transition"
        >
          <RefreshCw className={`h-3.5 w-3.5 sm:h-4 sm:w-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-800 gap-1.5 sm:gap-2 overflow-x-auto">
        <button
          onClick={() => setActiveTab('activity')}
          className={`flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-2 sm:py-3 text-xs sm:text-sm font-medium border-b-2 transition whitespace-nowrap ${
            activeTab === 'activity'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <History className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
          Activity Audit Trail ({activityLogs.length})
        </button>
        <button
          onClick={() => setActiveTab('approvals')}
          className={`flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-2 sm:py-3 text-xs sm:text-sm font-medium border-b-2 transition whitespace-nowrap ${
            activeTab === 'approvals'
              ? 'border-amber-500 text-amber-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Clock className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
          Dual-Control Approvals ({approvals.filter((a) => a.status === 'pending').length} Pending)
        </button>
        {viewerRole === 'admin' && (
          <>
            <button
              onClick={() => setActiveTab('security')}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition whitespace-nowrap ${
                activeTab === 'security'
                  ? 'border-rose-500 text-rose-400'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <AlertTriangle className="h-4 w-4" />
              Security Events ({securityEvents.length})
            </button>
            <button
              onClick={() => setActiveTab('team')}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition whitespace-nowrap ${
                activeTab === 'team'
                  ? 'border-emerald-500 text-emerald-400'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <Users className="h-4 w-4" />
              Org Roles & Members ({users.length})
            </button>
          </>
        )}
      </div>

      {/* Tab 1: Activity Audit Trail */}
      {activeTab === 'activity' && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 max-w-md">
            <Search className="h-4 w-4 text-slate-500" />
            <input
              type="text"
              placeholder="Filter by action, user, or target ARN..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="bg-transparent text-sm text-slate-200 outline-none w-full"
            />
          </div>

          <div className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-slate-300">
                <thead className="bg-slate-800/80 text-xs uppercase text-slate-400 border-b border-slate-700/50">
                  <tr>
                    <th className="px-4 py-3 font-semibold">Timestamp</th>
                    <th className="px-4 py-3 font-semibold">User</th>
                    <th className="px-4 py-3 font-semibold">Action</th>
                    <th className="px-4 py-3 font-semibold">Target / ARN</th>
                    <th className="px-4 py-3 font-semibold">Tier</th>
                    <th className="px-4 py-3 font-semibold">Result</th>
                    <th className="px-4 py-3 font-semibold text-right">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {filteredLogs.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                        No activity audit records found.
                      </td>
                    </tr>
                  ) : (
                    filteredLogs.map((log) => (
                      <tr key={log.id} className="hover:bg-slate-800/40 transition">
                        <td className="px-4 py-3 whitespace-nowrap text-xs text-slate-400 font-mono">
                          {new Date(log.timestamp).toLocaleString()}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-xs text-indigo-300 font-medium">
                          {log.user_email}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-medium bg-slate-800 text-slate-200 border border-slate-700">
                            {log.action}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-xs font-mono text-slate-400 max-w-xs truncate">
                          {log.target_arn || '—'}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-xs">
                          {log.tier ? (
                            <span className="capitalize px-2 py-0.5 rounded text-xs bg-indigo-950/60 text-indigo-400 border border-indigo-800/40">
                              {log.tier}
                            </span>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${
                              log.result === 'success' || log.result === 'approved'
                                ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-800/40'
                                : log.result === 'pending_approval'
                                ? 'bg-amber-950/60 text-amber-400 border border-amber-800/40'
                                : 'bg-rose-950/60 text-rose-400 border border-rose-800/40'
                            }`}
                          >
                            {log.result}
                          </span>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-right">
                          {log.details && Object.keys(log.details).length > 0 ? (
                            <button
                              onClick={() => setSelectedDetails(log.details)}
                              className="text-xs text-indigo-400 hover:text-indigo-300 underline"
                            >
                              View JSON
                            </button>
                          ) : (
                            <span className="text-slate-600 text-xs">—</span>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Dual-Control Approvals */}
      {activeTab === 'approvals' && (
        <div className="space-y-4">
          <div className="bg-amber-950/20 border border-amber-800/40 rounded-xl p-4 flex items-start gap-3">
            <Lock className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
            <div className="text-xs text-slate-300">
              <span className="font-semibold text-amber-300">Dual-Control Security Policy:</span> High-risk
              actions targeting Production environments require an explicit second approval. The requester is
              cryptographically blocked from approving their own request.
            </div>
          </div>

          <div className="grid gap-4">
            {approvals.length === 0 ? (
              <div className="p-12 text-center text-slate-500 bg-slate-900 border border-slate-800 rounded-xl">
                No dual-control approval requests at this time.
              </div>
            ) : (
              approvals.map((appr) => (
                <div
                  key={appr.id}
                  className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex items-center gap-3">
                      <span
                        className={`px-2.5 py-1 rounded text-xs font-semibold uppercase tracking-wider ${
                          appr.status === 'pending'
                            ? 'bg-amber-950 text-amber-400 border border-amber-700'
                            : appr.status === 'approved'
                            ? 'bg-emerald-950 text-emerald-400 border border-emerald-700'
                            : 'bg-rose-950 text-rose-400 border border-rose-700'
                        }`}
                      >
                        {appr.status}
                      </span>
                      <span className="text-sm font-semibold text-slate-100 font-mono">
                        {appr.action}
                      </span>
                      <span className="text-xs px-2 py-0.5 rounded bg-rose-950/40 text-rose-400 border border-rose-800/30">
                        {appr.environment}
                      </span>
                    </div>
                    <span className="text-xs text-slate-400 font-mono">
                      Requested: {new Date(appr.requested_at).toLocaleString()}
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs bg-slate-950/60 p-3 rounded-lg border border-slate-800 font-mono text-slate-300">
                    <div>
                      <span className="text-slate-500 block">Target Resource:</span>
                      {appr.resource_id}
                    </div>
                    <div>
                      <span className="text-slate-500 block">Requester:</span>
                      {appr.requester_email}
                    </div>
                    <div>
                      <span className="text-slate-500 block">Reviewer / Approver:</span>
                      {appr.approver_email || 'Awaiting peer approval'}
                    </div>
                  </div>

                  {appr.reason && (
                    <div className="text-xs text-slate-400 italic bg-slate-950/30 p-2.5 rounded border border-slate-800/60">
                      Justification: "{appr.reason}"
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex items-center justify-end gap-2 pt-2">
                    {appr.status === 'pending' && (
                      <>
                        <button
                          onClick={() => handleReviewApproval(appr.id, 'rejected')}
                          disabled={actionLoading}
                          className="px-3 py-1.5 bg-rose-950 hover:bg-rose-900 text-rose-200 border border-rose-800 rounded text-xs font-medium transition"
                        >
                          Reject
                        </button>
                        <button
                          onClick={() => handleReviewApproval(appr.id, 'approved')}
                          disabled={actionLoading}
                          className="px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 text-white rounded text-xs font-medium transition flex items-center gap-1.5"
                        >
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          Approve Request
                        </button>
                      </>
                    )}
                    {appr.status === 'approved' && (
                      <button
                        onClick={() => handleExecuteApproval(appr.id)}
                        disabled={actionLoading}
                        className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-xs font-medium transition flex items-center gap-1.5"
                      >
                        <ArrowUpRight className="h-3.5 w-3.5" />
                        Execute Approved Remediation
                      </button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Tab 3: Security Audit Events */}
      {activeTab === 'security' && (
        <div className="space-y-4">
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
            <table className="w-full text-left text-sm text-slate-300">
              <thead className="bg-slate-800/80 text-xs uppercase text-slate-400 border-b border-slate-700/50">
                <tr>
                  <th className="px-4 py-3 font-semibold">Timestamp</th>
                  <th className="px-4 py-3 font-semibold">Event Type</th>
                  <th className="px-4 py-3 font-semibold">Severity</th>
                  <th className="px-4 py-3 font-semibold">User / Org</th>
                  <th className="px-4 py-3 font-semibold">Target ARN</th>
                  <th className="px-4 py-3 font-semibold text-right">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {securityEvents.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                      No security anomalies or violations recorded.
                    </td>
                  </tr>
                ) : (
                  securityEvents.map((evt) => (
                    <tr key={evt.id} className="hover:bg-slate-800/40 transition">
                      <td className="px-4 py-3 whitespace-nowrap text-xs text-slate-400 font-mono">
                        {new Date(evt.timestamp).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className="px-2 py-0.5 rounded text-xs font-mono font-medium bg-rose-950/70 text-rose-300 border border-rose-800/50">
                          {evt.event_type}
                        </span>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span
                          className={`px-2 py-0.5 rounded text-xs font-bold ${
                            evt.severity === 'CRITICAL'
                              ? 'bg-rose-900 text-rose-100'
                              : 'bg-amber-950 text-amber-400'
                          }`}
                        >
                          {evt.severity}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-300 font-mono">
                        {evt.user_id} ({evt.org_id})
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-400 font-mono max-w-xs truncate">
                        {evt.target_arn || '—'}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-right">
                        {evt.details && (
                          <button
                            onClick={() => setSelectedDetails(evt.details)}
                            className="text-xs text-rose-400 hover:text-rose-300 underline"
                          >
                            View
                          </button>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 4: Org Roles & Members */}
      {activeTab === 'team' && (
        <div className="space-y-4">
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
            <table className="w-full text-left text-sm text-slate-300">
              <thead className="bg-slate-800/80 text-xs uppercase text-slate-400 border-b border-slate-700/50">
                <tr>
                  <th className="px-4 py-3 font-semibold">User Email</th>
                  <th className="px-4 py-3 font-semibold">Role Tier</th>
                  <th className="px-4 py-3 font-semibold">Domain Verified</th>
                  <th className="px-4 py-3 font-semibold">Joined At</th>
                  <th className="px-4 py-3 font-semibold text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {users.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                      No members registered in this organization.
                    </td>
                  </tr>
                ) : (
                  users.map((u) => (
                    <tr key={u.user_id} className="hover:bg-slate-800/40 transition">
                      <td className="px-4 py-3 text-xs font-medium text-slate-200">{u.email}</td>
                      <td className="px-4 py-3">
                        <span
                          className={`px-2 py-0.5 rounded text-xs font-semibold capitalize ${
                            u.role === 'admin'
                              ? 'bg-purple-950/80 text-purple-300 border border-purple-800'
                              : u.role === 'devops'
                              ? 'bg-indigo-950/80 text-indigo-300 border border-indigo-800'
                              : 'bg-slate-800 text-slate-300 border border-slate-700'
                          }`}
                        >
                          {u.role === 'admin'
                            ? '👑 Admin (Tier 3)'
                            : u.role === 'devops'
                            ? '🚀 DevOps (Tier 2)'
                            : '🔍 FinOps (Tier 1)'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs">
                        {u.domain_verified ? (
                          <span className="text-emerald-400 flex items-center gap-1 font-mono">
                            <CheckCircle2 className="h-3 w-3" /> Yes
                          </span>
                        ) : (
                          <span className="text-slate-500 font-mono">No</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-400 font-mono">
                        {new Date(u.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => {
                            setPromoteModalUser(u);
                            setNewRole(u.role);
                          }}
                          className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded text-xs border border-slate-700 transition"
                        >
                          Change Role
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* JSON Details Modal */}
      {selectedDetails && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-lg w-full p-5 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-slate-200 text-sm">Audit Payload Details</h3>
              <button
                onClick={() => setSelectedDetails(null)}
                className="text-slate-400 hover:text-slate-200 text-sm"
              >
                ✕
              </button>
            </div>
            <pre className="bg-slate-950 p-4 rounded-lg text-xs font-mono text-indigo-300 overflow-auto max-h-80 border border-slate-800">
              {JSON.stringify(selectedDetails, null, 2)}
            </pre>
            <div className="flex justify-end">
              <button
                onClick={() => setSelectedDetails(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Role Promotion Modal */}
      {promoteModalUser && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <form
            onSubmit={handlePromoteSubmit}
            className="bg-slate-900 border border-slate-700 rounded-xl max-w-md w-full p-5 space-y-4 shadow-2xl"
          >
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-slate-100 text-sm">Promote User Role</h3>
              <button
                type="button"
                onClick={() => setPromoteModalUser(null)}
                className="text-slate-400 hover:text-slate-200 text-sm"
              >
                ✕
              </button>
            </div>

            <div className="text-xs text-slate-400">
              Target User: <span className="text-slate-200 font-mono">{promoteModalUser.email}</span>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-medium text-slate-300">Assign Role</label>
              <select
                value={newRole}
                onChange={(e) => setNewRole(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200"
              >
                <option value="finops">FinOps Analyst (Tier 1 - Read Only)</option>
                <option value="devops">DevOps Engineer (Tier 2 - Active Remediation)</option>
                <option value="admin">Organization Admin (Tier 3 - Full Account Binding)</option>
              </select>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-medium text-slate-300">Audit Justification</label>
              <input
                type="text"
                required
                placeholder="Reason for role change (e.g. Lead DevOps Engineer)"
                value={promoteReason}
                onChange={(e) => setPromoteReason(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setPromoteModalUser(null)}
                className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={actionLoading}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-medium transition"
              >
                {actionLoading ? 'Updating...' : 'Confirm & Log Audit'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};
