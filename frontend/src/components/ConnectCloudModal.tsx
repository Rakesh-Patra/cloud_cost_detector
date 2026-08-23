import React, { useState, useEffect } from 'react';
import { Download, Copy, Check, ExternalLink, FileCode } from 'lucide-react';
import { getCfnTemplate, connectCloudAccount, type CfnTemplateResponse, type CloudAccount } from '../lib/api';

interface ConnectCloudModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAccountConnected: (account: CloudAccount) => void;
}

export const ConnectCloudModal: React.FC<ConnectCloudModalProps> = ({
  isOpen,
  onClose,
  onAccountConnected,
}) => {
  const [cfnData, setCfnData] = useState<CfnTemplateResponse | null>(null);
  const [loadingTemplate, setLoadingTemplate] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [alias, setAlias] = useState('');
  const [awsAccountId, setAwsAccountId] = useState('');
  const [roleArn, setRoleArn] = useState('');
  const [copiedYaml, setCopiedYaml] = useState(false);

  const handleDownloadTemplate = () => {
    if (!cfnData?.cfn_yaml) return;
    const blob = new Blob([cfnData.cfn_yaml], { type: 'text/yaml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `cloudcost-role-${cfnData.external_id || 'template'}.yaml`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleCopyTemplate = async () => {
    if (!cfnData?.cfn_yaml) return;
    try {
      await navigator.clipboard.writeText(cfnData.cfn_yaml);
      setCopiedYaml(true);
      setTimeout(() => setCopiedYaml(false), 2500);
    } catch {
      // fallback
    }
  };

  const [mode, setMode] = useState<'readonly' | 'remediation'>('readonly');
  const [durationDays, setDurationDays] = useState<number | null>(null);

  const loadTemplate = (selectedMode: 'readonly' | 'remediation', selectedDuration: number | null) => {
    setLoadingTemplate(true);
    setError(null);
    getCfnTemplate(selectedMode, selectedDuration)
      .then((data) => {
        setCfnData(data);
        setLoadingTemplate(false);
      })
      .catch((err) => {
        setError(err.message || 'Failed to generate onboarding CloudFormation template');
        setLoadingTemplate(false);
      });
  };

  useEffect(() => {
    if (isOpen) {
      loadTemplate(mode, durationDays);
    }
  }, [isOpen, mode, durationDays]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!cfnData) return;
    if (!alias.trim() || !awsAccountId.trim() || !roleArn.trim()) {
      setError('Please fill in all required fields.');
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const newAccount = await connectCloudAccount({
        account_alias: alias.trim(),
        aws_account_id: awsAccountId.trim(),
        role_arn: roleArn.trim(),
        external_id: cfnData.external_id,
        regions: ['us-east-1', 'us-east-2', 'us-west-2', 'eu-west-1'],
        duration_days: durationDays,
      });
      window.dispatchEvent(new Event('cloud-accounts-updated'));
      onAccountConnected(newAccount);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to connect AWS Account. Please check the Role ARN.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-fade-in">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-2xl w-full p-6 shadow-2xl relative max-h-[90vh] overflow-y-auto">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-white p-2 rounded-lg hover:bg-slate-800 transition"
        >
          ✕
        </button>

        <div className="flex items-center space-x-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-purple-500/20 border border-purple-500/40 flex items-center justify-center text-purple-400 font-bold text-lg">
            ⚡
          </div>
          <div>
            <h2 className="text-xl font-bold text-white">Connect AWS Cloud Account</h2>
            <p className="text-sm text-slate-400">Zero permanent keys. Connected securely via AWS STS AssumeRole.</p>
          </div>
        </div>

        {/* Security Trust Callout */}
        <div className="bg-emerald-950/40 border border-emerald-500/30 rounded-xl p-3.5 mb-6 flex items-start space-x-3 text-xs text-emerald-200">
          <span className="text-base">🛡️</span>
          <div>
            <span className="font-semibold text-emerald-300">Security Guarantee:</span>{' '}
            Our SaaS uses AWS STS with your dedicated External ID. We never store root AWS secret keys
            and have zero access to your application data.{' '}
            <span className="text-emerald-400 font-medium">
              {durationDays
                ? `Cryptographically expires after ${durationDays} days via AWS DateLessThan condition.`
                : 'Role connection remains active permanently until deleted in your AWS Console.'}
            </span>
          </div>
        </div>

        {/* Permission Mode & Duration Selectors */}
        <div className="space-y-2.5 mb-4">
          <div className="bg-slate-950 p-1.5 rounded-xl border border-slate-800 flex items-center gap-1.5 text-xs">
            <button
              type="button"
              onClick={() => setMode('readonly')}
              className={`flex-1 py-2 px-3 rounded-lg font-medium transition flex items-center justify-center gap-1.5 ${
                mode === 'readonly'
                  ? 'bg-purple-600 text-white shadow-md shadow-purple-600/30'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <span>🔍 Tier 1: Read-Only Audit</span>
            </button>
            <button
              type="button"
              onClick={() => setMode('remediation')}
              className={`flex-1 py-2 px-3 rounded-lg font-medium transition flex items-center justify-center gap-1.5 ${
                mode === 'remediation'
                  ? 'bg-purple-600 text-white shadow-md shadow-purple-600/30'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <span>⚡ Tier 2: Active Auto-Remediation</span>
            </button>
          </div>

          {/* Time-Limited Access Grant Selector */}
          <div className="bg-slate-950/80 p-2 rounded-xl border border-slate-800 flex items-center justify-between gap-2 text-xs">
            <span className="text-slate-400 font-medium flex items-center gap-1.5 pl-1">
              ⏳ Access Grant Window:
            </span>
            <div className="flex items-center gap-1">
              {[
                { label: '♾️ Permanent', value: null },
                { label: '7 Days (POC)', value: 7 },
                { label: '30 Days (Audit)', value: 30 },
                { label: '90 Days (Quarterly)', value: 90 },
              ].map((opt) => (
                <button
                  key={opt.label}
                  type="button"
                  onClick={() => setDurationDays(opt.value)}
                  className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition ${
                    durationDays === opt.value
                      ? 'bg-slate-700 text-purple-300 border border-purple-500/50 shadow-sm'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {loadingTemplate ? (
          <div className="py-12 text-center text-slate-400">
            <div className="animate-spin w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full mx-auto mb-3"></div>
            Generating unique CloudFormation setup bundle...
          </div>
        ) : (
          <div>
            {/* Step 1: Deploy IAM Role */}
            <div className="bg-slate-800/60 border border-slate-700/80 rounded-xl p-4 mb-5 space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-white flex items-center gap-1.5">
                    <FileCode className="w-4 h-4 text-purple-400" />
                    Step 1: Deploy {mode === 'remediation' ? 'Active Remediation' : 'Read-Only'} IAM Role in AWS
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {mode === 'remediation'
                      ? 'Grants SecurityAudit + scoped actions to quarantine/stop/snapshot idle resources.'
                      : 'Grants zero write access. Read-only SecurityAudit + CloudWatch and Cost Explorer metrics.'}
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap">
                  <button
                    type="button"
                    onClick={handleDownloadTemplate}
                    className="px-3 py-2 bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold rounded-lg shadow-md shadow-purple-600/30 flex items-center space-x-1.5 transition"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download .yaml</span>
                  </button>
                  <button
                    type="button"
                    onClick={handleCopyTemplate}
                    className="px-3 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs font-medium rounded-lg border border-slate-600 flex items-center space-x-1.5 transition"
                  >
                    {copiedYaml ? (
                      <>
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                        <span className="text-emerald-400">Copied!</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5" />
                        <span>Copy YAML</span>
                      </>
                    )}
                  </button>
                  <a
                    href="https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/create/template"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg border border-slate-700 flex items-center space-x-1.5 transition"
                  >
                    <span>AWS Console</span>
                    <ExternalLink className="w-3.5 h-3.5 text-slate-400" />
                  </a>
                </div>
              </div>

              {cfnData && (
                <div className="bg-slate-950/70 p-2.5 rounded-lg border border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between text-xs gap-1 font-mono">
                  <span className="text-slate-400">
                    Handshake Token (External ID): <strong className="text-purple-300 select-all">{cfnData.external_id}</strong>
                  </span>
                  <span className="text-[11px] text-slate-500 font-sans">Embedded inside downloaded template</span>
                </div>
              )}
            </div>

            {/* Step 2: Form */}
            <form onSubmit={handleSubmit} className="space-y-4">
              <h3 className="text-sm font-semibold text-white">Step 2: Enter Role ARN & Account Details</h3>

              {error && (
                <div className="bg-rose-950/50 border border-rose-500/40 text-rose-300 text-xs p-3 rounded-lg space-y-1">
                  <p>{error}</p>
                  {(error.toLowerCase().includes('invalidclienttokenid') ||
                    error.toLowerCase().includes('security token') ||
                    error.toLowerCase().includes('sts') ||
                    error.toLowerCase().includes('expired')) && (
                    <p className="text-amber-300 font-medium mt-1">
                      💡 This is a <strong>server-side</strong> credential issue, not a problem with your Role ARN.
                      Ask your admin to set permanent <code>AWS_ACCESS_KEY_ID</code> +{' '}
                      <code>AWS_SECRET_ACCESS_KEY</code> (IAM User keys) in the backend{' '}
                      <code>.env</code> file and restart the server.
                    </p>
                  )}
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Account Alias / Name <span className="text-rose-400">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Production-Main"
                    value={alias}
                    onChange={(e) => setAlias(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-purple-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    AWS Account ID <span className="text-rose-400">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="12-digit Account ID"
                    value={awsAccountId}
                    onChange={(e) => setAwsAccountId(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-purple-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Generated Role ARN <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="arn:aws:iam::123456789012:role/CloudCostDetective-AuditRole"
                  value={roleArn}
                  onChange={(e) => setRoleArn(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm font-mono text-purple-200 focus:outline-none focus:border-purple-500"
                />
                <p className="text-[11px] text-slate-500 mt-1">
                  Found in the <strong>Outputs</strong> tab of your completed CloudFormation Stack.
                </p>
              </div>

              <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-medium rounded-lg transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-5 py-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-semibold rounded-lg shadow-lg shadow-purple-600/30 flex items-center space-x-2 transition"
                >
                  {submitting ? (
                    <>
                      <div className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full"></div>
                      <span>Verifying STS Handshake...</span>
                    </>
                  ) : (
                    <span>Test & Connect Account</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        )}
      </div>
    </div>
  );
};
