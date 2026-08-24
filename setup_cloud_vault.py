import urllib.request
import urllib.error
import json
import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

if len(sys.argv) < 3:
    print("Usage: python setup_cloud_vault.py <VAULT_ADDR> <ROOT_TOKEN> [NAMESPACE]")
    print("Example: python setup_cloud_vault.py https://vault-cluster...:8200 hvs.abcdef12345... admin")
    sys.exit(1)

VAULT_ADDR = sys.argv[1].rstrip("/")
VAULT_TOKEN = sys.argv[2]
VAULT_NAMESPACE = sys.argv[3] if len(sys.argv) > 3 else ("admin" if "hashicorp.cloud" in VAULT_ADDR else os.getenv("VAULT_NAMESPACE", "admin"))

print(f"Connecting to Vault at {VAULT_ADDR} (Namespace: '{VAULT_NAMESPACE}')...")

def vault_api_call(endpoint, data=None, method="POST"):
    url = f"{VAULT_ADDR}{endpoint}"
    payload = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=payload, method=method)
    req.add_header("X-Vault-Token", VAULT_TOKEN)
    req.add_header("Content-Type", "application/json")
    if VAULT_NAMESPACE:
        req.add_header("X-Vault-Namespace", VAULT_NAMESPACE)
    
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            return True, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        return False, f"HTTP {e.code}: {e.reason} - {error_body}"
    except Exception as e:
        return False, str(e)

# 1. Enable KV v2 secret engine if not enabled
print("\n1. Ensuring 'secret/' KV v2 engine is enabled...")
ok, resp = vault_api_call("/v1/sys/mounts/secret", {"type": "kv", "options": {"version": "2"}})
if ok:
    print("✅ Secret engine 'secret/' mounted as KV-v2.")
else:
    print(f"ℹ️ Note on secret engine (might already exist): {resp}")

# 2. Enable JWT Auth method
print("\n2. Enabling JWT Auth method...")
ok, resp = vault_api_call("/v1/sys/auth/jwt", {"type": "jwt"})
if ok:
    print("✅ JWT Auth method enabled successfully.")
else:
    print(f"ℹ️ Note on enabling JWT auth (might already be enabled): {resp}")

# 3. Write JWT config to trust GitHub Actions
print("\n3. Configuring JWT Auth OIDC discovery...")
jwt_config = {
    "oidc_discovery_url": "https://token.actions.githubusercontent.com",
    "bound_issuer": "https://token.actions.githubusercontent.com"
}
ok, resp = vault_api_call("/v1/auth/jwt/config", jwt_config)
if ok:
    print("✅ JWT OIDC config updated to trust token.actions.githubusercontent.com.")
else:
    print(f"❌ Failed to update JWT config: {resp}")

# 4. Create Cloud Cost Policy
print("\n4. Creating Vault ACL policy 'cloud-cost-policy'...")
policy_rules = """
path "secret/data/cloud_cost" {
  capabilities = ["read", "list"]
}
path "secret/data/cloud_cost/*" {
  capabilities = ["read", "list"]
}
path "secret/metadata/cloud_cost/*" {
  capabilities = ["read", "list"]
}
"""
ok, resp = vault_api_call("/v1/sys/policies/acl/cloud-cost-policy", {"policy": policy_rules})
if ok:
    print("✅ Vault ACL policy 'cloud-cost-policy' created successfully.")
else:
    print(f"❌ Failed to create Vault policy: {resp}")

# 5. Create Github Actions Role
print("\n5. Creating Vault Role 'github-actions-role'...")
role_data = {
    "role_type": "jwt",
    "bound_audiences": [
        "https://github.com/Rakesh-Patra",
        "https://github.com/rakesh-patra",
        VAULT_ADDR
    ],
    "bound_claims_type": "glob",
    "bound_claims": {
        "sub": "repo:Rakesh-Patra/cloud_cost_detector:*"
    },
    "user_claim": "actor",
    "token_policies": ["default", "cloud-cost-policy"],
    "token_ttl": 3600
}
ok, resp = vault_api_call("/v1/auth/jwt/role/github-actions-role", role_data)
if ok:
    print("✅ Vault role 'github-actions-role' created successfully.")
else:
    print(f"❌ Failed to create Vault role: {resp}")

print("\n🎉 Vault server configuration completed successfully! It is now fully ready to authorize GitHub Actions.")
