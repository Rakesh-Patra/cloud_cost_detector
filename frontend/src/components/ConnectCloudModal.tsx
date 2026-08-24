import React, { useState, useEffect } from 'react';
import { Download, Copy, Check, ExternalLink, FileCode, Shield, Key, Clock, UserCheck, AlertTriangle } from 'lucide-react';
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
  const [activePersona, setActivePersona] = useState<'admin' | 'engineer'>('admin');
  const [mode, setMode] = useState<'readonly' | 'remediation' | 'admin'>('readonly');
  const [durationDays, setDurationDays] = useState<number | null>(null);

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
    link.download = `cloudcost-role-${mode}-${cfnData.external_id || 'template'}.yaml`;
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

  const loadTemplate = (selectedMode: 'readonly' | 'remediation' | 'admin', selectedDuration: number | null) => {
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
    if (!alias.trim() || !awsAccountId.trim() || !roleArn.trim()) {
      setError('Please fill in all required fields.');
      return;
    }

    setSubmitting(true);
    setError(null);

    const extId = cfnData?.external_id || 'default-ext-id';

    try {
      const newAccount = await connectCloudAccount({
        account_alias: alias.trim(),
        aws_account_id: awsAccountId.trim(),
        role_arn: roleArn.trim(),
        external_id: extId,
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md p-4 animate-fade-in">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-2xl w-full p-6 shadow-2xl relative max-h-[92vh] overflow-y-auto">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-white p-2 rounded-lg hover:bg-slate-800 transition"
        >
          ✕
        </button>

        {/* Modal Header */}
        <div className="flex items-center space-x-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-purple-500/20 border border-purple-500/40 flex items-center justify-center text-purple-400 font-bold text-lg">
            ⚡
          </div>
          <div>
            <h2 className="text-xl font-bold text-white">Connect AWS Cloud Account</h2>
            <p className="text-sm text-slate-400">Zero permanent keys. Connected securely via AWS STS AssumeRole.</p>
          </div>
        </div>

        {/* Role Persona View Selector */}
        <div className="flex rounded-xl bg-slate-950 p-1.5 border border-slate-800 mb-4 gap-1.5 text-xs font-semibold">
          <button
            type="button"
            onClick={() => setActivePersona('admin')}
            className={`flex-1 py-2 px-3 rounded-lg transition flex items-center justify-center gap-2 ${
              activePersona === 'admin'
                ? 'bg-purple-600 text-white shadow-lg shadow-purple-600/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Key className="w-3.5 h-3.5" />
            <span>👑 Cloud Admin (Setup & IAM Generation)</span>
          </button>
          <button
            type="button"
            onClick={() => setActivePersona('engineer')}
            className={`flex-1 py-2 px-3 rounded-lg transition flex items-center justify-center gap-2 ${
              activePersona === 'engineer'
                ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <UserCheck className="w-3.5 h-3.5" />
            <span>🚀 DevOps / FinOps Engineer (Verify & Connect)</span>
          </button>
        </div>

        {/* Security Guarantee Banner */}
        <div className="bg-emerald-950/40 border border-emerald-500/30 rounded-xl p-3.5 mb-5 flex items-start space-x-3 text-xs text-emerald-200">
          <Shield className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold text-emerald-300">Security Guarantee:</span>{' '}
            Uses AWS STS with dedicated External ID handshake. Never stores root secret keys.{' '}
            <span className="text-emerald-400 font-medium">
              {durationDays
                ? `Cryptographically expires after ${durationDays} days via AWS DateLessThan condition.`
                : 'Role connection remains active permanently until deleted in your AWS Console.'}
            </span>
          </div>
        </div>

        {/* ADMIN PERSONA CONTENT: Tier Selection, Duration, and CloudFormation generation */}
        {activePersona === 'admin' && (
          <div className="space-y-4 mb-5">
            {/* Enterprise Admin vs Personal AWS Guidance Alert */}
            <div className="bg-indigo-950/30 border border-indigo-500/30 rounded-xl p-3.5 flex items-start space-x-3 text-xs text-indigo-200">
              <AlertTriangle className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-indigo-300">Organization IAM Guidance:</span>{' '}
                Only Organization Admins with IAM creation permissions can deploy this CloudFormation stack into your company's AWS Account.
                <div className="mt-1 text-slate-300">
                  • <strong>FinOps / DevOps Engineers:</strong> Ask your Cloud Admin to deploy this stack once and share the resulting Role ARN with you.<br />
                  • <strong>Personal AWS Sandbox:</strong> If you are testing with your personal AWS account, log in to your AWS Console and deploy the template directly.
                </div>
              </div>
            </div>

            {/* Tier Selectors (Tier 1, Tier 2, Tier 3) */}
            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                Select IAM Access Tier:
              </label>
              <div className="grid grid-cols-3 gap-2 bg-slate-950 p-1.5 rounded-xl border border-slate-800 text-xs">
                <button
                  type="button"
                  onClick={() => setMode('readonly')}
                  className={`py-2 px-2.5 rounded-lg font-medium transition text-center ${
                    mode === 'readonly'
                      ? 'bg-purple-600 text-white shadow-md shadow-purple-600/30'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <div className="font-semibold">🔍 Tier 1</div>
                  <div className="text-[10px] opacity-80">Read-Only Audit</div>
                </button>
                <button
                  type="button"
                  onClick={() => setMode('remediation')}
                  className={`py-2 px-2.5 rounded-lg font-medium transition text-center ${
                    mode === 'remediation'
                      ? 'bg-purple-600 text-white shadow-md shadow-purple-600/30'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <div className="font-semibold">⚡ Tier 2</div>
                  <div className="text-[10px] opacity-80">Auto-Remediate</div>
                </button>
                <button
                  type="button"
                  onClick={() => setMode('admin')}
                  className={`py-2 px-2.5 rounded-lg font-medium transition text-center ${
                    mode === 'admin'
                      ? 'bg-amber-600 text-white shadow-md shadow-amber-600/30'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <div className="font-semibold">👑 Tier 3</div>
                  <div className="text-[10px] opacity-80">Full Admin Access</div>
                </button>
              </div>
            </div>

            {/* Time-Limited Access Grant Selector */}
            <div className="bg-slate-950/80 p-2.5 rounded-xl border border-slate-800 flex items-center justify-between gap-2 text-xs">
              <span className="text-slate-400 font-medium flex items-center gap-1.5 pl-1">
                <Clock className="w-3.5 h-3.5 text-purple-400" />
                Access Grant Window (Time Limit):
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

            {mode === 'admin' && (
              <div className="p-3 bg-amber-950/40 border border-amber-500/40 rounded-xl flex items-start gap-2.5 text-xs text-amber-200">
                <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                <div>
                  <span className="font-bold text-amber-300">Tier 3 (Admin) Warning:</span> Generates an IAM role with AdministratorAccess and Billing policies. Best for root tenant setup. For day-to-day scanning, Tier 1 or Tier 2 is recommended.
                </div>
              </div>
            )}

            {/* Step 1: Deploy IAM Role via CloudFormation */}
            {loadingTemplate ? (
              <div className="py-8 text-center text-slate-400">
                <div className="animate-spin w-7 h-7 border-2 border-purple-500 border-t-transparent rounded-full mx-auto mb-2"></div>
                Generating CloudFormation setup bundle...
              </div>
            ) : (
              <div className="bg-slate-800/60 border border-slate-700/80 rounded-xl p-4 space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-semibold text-white flex items-center gap-1.5">
                      <FileCode className="w-4 h-4 text-purple-400" />
                      Step 1: Deploy {mode === 'admin' ? 'Admin' : mode === 'remediation' ? 'Active Remediation' : 'Read-Only'} IAM Role in AWS
                    </h3>
                    <p className="text-xs text-slate-400 mt-0.5">
                      {mode === 'admin'
                        ? 'Grants AdministratorAccess + Billing policies to the STS AssumeRole.'
                        : mode === 'remediation'
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
                    <span className="text-[11px] text-slate-500 font-sans">Pass to engineer or stack parameters</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* DEVOPS / FINOPS ENGINEER PERSONA CONTENT: Streamlined ARN verification */}
        {activePersona === 'engineer' && (
          <div className="bg-indigo-950/30 border border-indigo-500/20 rounded-xl p-4 mb-5 space-y-2 text-xs text-indigo-200">
            <div className="font-semibold text-indigo-300 flex items-center gap-1.5">
              <UserCheck className="w-4 h-4 text-indigo-400" />
              DevOps & FinOps Verification Mode
            </div>
            <p className="text-slate-300">
              Your Cloud Admin has already generated and deployed the CloudFormation Stack. Simply paste the <strong>Role ARN</strong> from the completed stack's Outputs tab below to test the connection.
            </p>
          </div>
        )}

        {/* Step 2 Form (Both Admin & Engineer can verify & connect) */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <h3 className="text-sm font-semibold text-white flex items-center gap-1.5">
            <span>{activePersona === 'admin' ? 'Step 2: Enter Role ARN & Account Details' : 'Verify & Connect AWS Account'}</span>
          </h3>

          {error && (
            <div className="bg-rose-950/50 border border-rose-500/40 text-rose-300 text-xs p-3 rounded-lg space-y-1">
              <p>{error}</p>
              {(error.toLowerCase().includes('invalidclienttokenid') ||
                error.toLowerCase().includes('security token') ||
                error.toLowerCase().includes('sts') ||
                error.toLowerCase().includes('expired')) && (
                <p className="text-amber-300 font-medium mt-1">
                  💡 This is a <strong>server-side</strong> credential issue. Ensure permanent <code>AWS_ACCESS_KEY_ID</code> + <code>AWS_SECRET_ACCESS_KEY</code> are configured in backend <code>.env</code>.
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
                placeholder="e.g. Production-Main or Staging-Cluster"
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
                placeholder="12-digit AWS Account ID"
                value={awsAccountId}
                onChange={(e) => setAwsAccountId(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-purple-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              IAM Role ARN <span className="text-rose-400">*</span>
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
              Found in the <strong>Outputs</strong> tab of your completed CloudFormation Stack or provided by your Cloud Admin.
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
    </div>
  );
};

