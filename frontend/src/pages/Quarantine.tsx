import React, { useState, useEffect } from 'react';
import { getQuarantineItems, dismissQuarantine, safeDeleteQuarantine, type QuarantineItem } from '../lib/api';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { EmptyState } from '../components/ui/EmptyState';

export const Quarantine: React.FC = () => {
  const [items, setItems] = useState<QuarantineItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  const fetchItems = async () => {
    try {
      setLoading(true);
      const res = await getQuarantineItems();
      setItems(res.items || []);
    } catch (err: any) {
      setFeedback({ message: err.message || 'Failed to fetch quarantine list', type: 'error' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchItems();
  }, []);

  const handleDismiss = async (item: QuarantineItem) => {
    setActionLoading(item.id);
    setFeedback(null);
    try {
      const res = await dismissQuarantine({
        item_id: item.id,
        resource_id: item.resource_id,
        region: item.region,
        account_id: item.account_id,
      });
      setFeedback({ message: res.message, type: 'success' });
      await fetchItems();
    } catch (err: any) {
      setFeedback({ message: err.message || 'Failed to whitelist resource', type: 'error' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleSafeDelete = async (item: QuarantineItem) => {
    if (!window.confirm(`Are you sure you want to trigger safe deletion for ${item.resource_id}? An automated backup snapshot will be created before deletion.`)) {
      return;
    }
    setActionLoading(item.id);
    setFeedback(null);
    try {
      const res = await safeDeleteQuarantine({
        item_id: item.id,
        resource_id: item.resource_id,
        region: item.region,
        account_id: item.account_id,
      });
      setFeedback({ message: res.message, type: 'success' });
      await fetchItems();
    } catch (err: any) {
      setFeedback({ message: err.message || 'Safe deletion failed', type: 'error' });
    } finally {
      setActionLoading(null);
    }
  };

  const calculateDaysRemaining = (expiryDateStr: string) => {
    const expiry = new Date(expiryDateStr).getTime();
    const now = new Date().getTime();
    const diffDays = Math.ceil((expiry - now) / (1000 * 60 * 60 * 24));
    return diffDays > 0 ? diffDays : 0;
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <span>🛡️</span> Quarantine & Safe Actions
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Enterprise guardrail: Resources flagged for termination with 7-day grace periods and snapshot rollbacks.
          </p>
        </div>
        <button
          onClick={fetchItems}
          className="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-lg border border-slate-700 transition"
        >
          🔄 Refresh
        </button>
      </div>

      {feedback && (
        <div
          className={`p-3.5 rounded-xl text-xs font-medium border ${
            feedback.type === 'success'
              ? 'bg-emerald-950/60 border-emerald-500/40 text-emerald-300'
              : 'bg-rose-950/60 border-rose-500/40 text-rose-300'
          }`}
        >
          {feedback.message}
        </div>
      )}

      {/* Info Card */}
      <Card className="bg-slate-900/60 border-slate-800 p-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          <div className="flex items-start space-x-3">
            <span className="text-xl">⏳</span>
            <div>
              <strong className="text-white">7-Day "Tag-and-Wait"</strong>
              <p className="text-slate-400 mt-0.5">Resources are tagged in AWS with a 7-day deletion countdown before any action is executed.</p>
            </div>
          </div>
          <div className="flex items-start space-x-3">
            <span className="text-xl">📸</span>
            <div>
              <strong className="text-white">Snapshot-Before-Delete</strong>
              <p className="text-slate-400 mt-0.5">Every volume deletion automatically captures an encrypted snapshot for 1-click rollback.</p>
            </div>
          </div>
          <div className="flex items-start space-x-3">
            <span className="text-xl">✅</span>
            <div>
              <strong className="text-white">Instant Whitelisting</strong>
              <p className="text-slate-400 mt-0.5">Engineers can click "Keep Resource" to immediately unflag and preserve critical assets.</p>
            </div>
          </div>
        </div>
      </Card>

      {/* Table */}
      {loading ? (
        <div className="py-16 text-center text-slate-400">
          <div className="animate-spin w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full mx-auto mb-3"></div>
          Loading quarantine inventory...
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          title="No Quarantined Resources"
          description="Your cloud environment has zero resources currently scheduled for quarantine or deletion."
          action={
            <a
              href="/"
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg transition"
            >
              Run Cost Scan
            </a>
          }
        />
      ) : (
        <Card className="overflow-hidden border-slate-800">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/80 text-slate-400 font-semibold border-b border-slate-800">
                <tr>
                  <th className="p-3.5">Resource ID</th>
                  <th className="p-3.5">Type & Region</th>
                  <th className="p-3.5">Quarantine Reason</th>
                  <th className="p-3.5">Grace Period</th>
                  <th className="p-3.5">Status</th>
                  <th className="p-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
                {items.map((item) => {
                  const daysLeft = calculateDaysRemaining(item.quarantine_until);
                  const isPending = item.status === 'quarantined';

                  return (
                    <tr key={item.id} className="hover:bg-slate-800/30 transition">
                      <td className="p-3.5 font-bold text-white">
                        {item.resource_id}
                        {item.snapshot_id && (
                          <div className="text-[10px] text-purple-400 font-normal mt-0.5">
                            Snapshot: {item.snapshot_id}
                          </div>
                        )}
                      </td>
                      <td className="p-3.5">
                        <span className="text-slate-200 font-sans">{item.resource_type}</span>
                        <span className="text-slate-500 block text-[11px]">{item.region}</span>
                      </td>
                      <td className="p-3.5 font-sans text-slate-400 max-w-xs truncate">
                        {item.reason}
                      </td>
                      <td className="p-3.5 font-sans">
                        {isPending ? (
                          <Badge variant={daysLeft <= 2 ? 'danger' : 'warning'}>
                            {daysLeft > 0 ? `${daysLeft} days remaining` : 'Expired'}
                          </Badge>
                        ) : (
                          <span className="text-slate-500">—</span>
                        )}
                      </td>
                      <td className="p-3.5 font-sans">
                        <Badge
                          variant={
                            item.status === 'quarantined'
                              ? 'warning'
                              : item.status === 'restored'
                              ? 'success'
                              : 'muted'
                          }
                        >
                          {item.status.toUpperCase()}
                        </Badge>
                      </td>
                      <td className="p-3.5 text-right font-sans space-x-2">
                        {isPending && (
                          <>
                            <button
                              disabled={actionLoading === item.id}
                              onClick={() => handleDismiss(item)}
                              className="px-2.5 py-1 bg-emerald-950/60 hover:bg-emerald-900 border border-emerald-500/40 text-emerald-300 text-xs rounded transition"
                            >
                              Keep Resource
                            </button>
                            <button
                              disabled={actionLoading === item.id}
                              onClick={() => handleSafeDelete(item)}
                              className="px-2.5 py-1 bg-rose-950/60 hover:bg-rose-900 border border-rose-500/40 text-rose-300 text-xs rounded transition"
                            >
                              Safe Delete Now
                            </button>
                          </>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
};
