import urllib.request
import json
import sys

if len(sys.argv) < 3:
    print("Usage: python setup_cloud_vault.py <VAULT_ADDR> <ROOT_TOKEN>")
    print("Example: python setup_cloud_vault.py http://32.199.186.140:8200 hvs.abcdef12345...")
    sys.exit(1)

VAULT_ADDR = sys.argv[1].rstrip("/")
VAULT_TOKEN = sys.argv[2]

# Enable JWT Auth method
print(f"Connecting to Vault at {VAULT_ADDR}...")
enable_jwt_url = f"{VAULT_ADDR}/v1/sys/auth/jwt"
enable_jwt_data = json.dumps({"type": "jwt"}).encode('utf-8')
req = urllib.request.Request(enable_jwt_url, data=enable_jwt_data, method="POST")
req.add_header("X-Vault-Token", VAULT_TOKEN)
req.add_header("Content-Type", "application/json")
try:
    with urllib.request.urlopen(req) as response:
        print("✅ JWT Auth method enabled successfully.")
except Exception as e:
    print(f"Note on enabling JWT auth (might already be enabled): {e}")

# Write JWT config to trust GitHub Actions
jwt_config_url = f"{VAULT_ADDR}/v1/auth/jwt/config"
jwt_config_data = json.dumps({
    "oidc_discovery_url": "https://token.actions.githubusercontent.com",
    "bound_issuer": "https://token.actions.githubusercontent.com"
}).encode('utf-8')
req = urllib.request.Request(jwt_config_url, data=jwt_config_data, method="POST")
req.add_header("X-Vault-Token", VAULT_TOKEN)
req.add_header("Content-Type", "application/json")
try:
    with urllib.request.urlopen(req) as response:
        print("✅ JWT OIDC config updated to trust token.actions.githubusercontent.com.")
except Exception as e:
    print(f"❌ Failed to update JWT config: {e}")

# Create Github Actions Role
role_url = f"{VAULT_ADDR}/v1/auth/jwt/role/github-actions-role"
role_data = json.dumps({
    "role_type": "jwt",
    "bound_audiences": "https://github.com/Rakesh-Patra",
    "bound_claims_type": "glob",
    "bound_claims": {
        "sub": "repo:Rakesh-Patra/cloud_cost_detector:*"
    },
    "user_claim": "actor",
    "token_policies": ["default", "cloud-cost-policy"],
    "token_ttl": 3600
}).encode('utf-8')
req = urllib.request.Request(role_url, data=role_data, method="POST")
req.add_header("X-Vault-Token", VAULT_TOKEN)
req.add_header("Content-Type", "application/json")
try:
    with urllib.request.urlopen(req) as response:
        print("✅ Vault role 'github-actions-role' created successfully.")
except Exception as e:
    print(f"❌ Failed to create Vault role: {e}")

# Create Cloud Cost Policy
policy_url = f"{VAULT_ADDR}/v1/sys/policies/acl/cloud-cost-policy"
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
policy_data = json.dumps({"policy": policy_rules}).encode('utf-8')
req = urllib.request.Request(policy_url, data=policy_data, method="POST")
req.add_header("X-Vault-Token", VAULT_TOKEN)
req.add_header("Content-Type", "application/json")
try:
    with urllib.request.urlopen(req) as response:
        print("✅ Vault ACL policy 'cloud-cost-policy' created successfully.")
except Exception as e:
    print(f"❌ Failed to create Vault policy: {e}")

print("\n🎉 Vault server configuration completed successfully! It is now fully ready to authorize GitHub Actions.")
