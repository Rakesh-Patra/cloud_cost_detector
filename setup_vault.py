import os
import zipfile
import urllib.request
import subprocess
import time
import json
import socket

# Configuration for local Vault installation
VAULT_ZIP_URL = "https://releases.hashicorp.com/vault/1.15.2/vault_1.15.2_windows_amd64.zip"
BIN_DIR = os.path.join(os.getcwd(), "bin")
VAULT_EXE = os.path.join(BIN_DIR, "vault.exe")
VAULT_ZIP = os.path.join(BIN_DIR, "vault.zip")
VAULT_ADDR = "http://127.0.0.1:8200"
VAULT_TOKEN = "root"

def setup():
    if not os.path.exists(BIN_DIR):
        os.makedirs(BIN_DIR)
        
    # 1. Download Vault
    if not os.path.exists(VAULT_EXE):
        print(f"Downloading Vault from {VAULT_ZIP_URL}...")
        urllib.request.urlretrieve(VAULT_ZIP_URL, VAULT_ZIP)
        print("Extracting Vault binary...")
        with zipfile.ZipFile(VAULT_ZIP, 'r') as zip_ref:
            zip_ref.extractall(BIN_DIR)
        os.remove(VAULT_ZIP)
        print("Vault installed in bin/ directory.")
    else:
        print("Vault binary already exists.")

    # 2. Check if Vault is already running on port 8200
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(("127.0.0.1", 8200))
        print("Vault is already running on port 8200.")
        s.close()
    except socket.error:
        # Start Vault server in dev mode
        print("Starting Vault server in dev mode...")
        log_file = open(os.path.join(BIN_DIR, "vault.log"), "w")
        
        # 0x00000008 is the flag for DETACHED_PROCESS on Windows
        # This keeps Vault running independently after the Python script exits
        DETACHED_PROCESS = 0x00000008
        subprocess.Popen(
            [VAULT_EXE, "server", "-dev", "-dev-root-token-id=root", "-dev-listen-address=127.0.0.1:8200"],
            stdout=log_file,
            stderr=log_file,
            creationflags=DETACHED_PROCESS
        )
        print("Vault server started in background. Log saved in bin/vault.log.")
        time.sleep(3) # Wait for it to boot

    # 3. Configure Vault via REST API
    print("Configuring Vault local settings...")
    
    # Check status
    req = urllib.request.Request(f"{VAULT_ADDR}/v1/sys/health", method="GET")
    try:
        with urllib.request.urlopen(req) as response:
            status = json.loads(response.read().decode())
            print(f"Vault status: initialized={status['initialized']}, sealed={status['sealed']}")
    except Exception as e:
        print(f"Could not connect to Vault sys/health: {e}")
        return

    # Enable JWT Auth method
    enable_jwt_url = f"{VAULT_ADDR}/v1/sys/auth/jwt"
    enable_jwt_data = json.dumps({"type": "jwt"}).encode('utf-8')
    req = urllib.request.Request(enable_jwt_url, data=enable_jwt_data, method="POST")
    req.add_header("X-Vault-Token", VAULT_TOKEN)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as response:
            print("JWT Auth method enabled successfully.")
    except Exception as e:
        # Might already be enabled
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
            print("JWT OIDC config updated to trust token.actions.githubusercontent.com.")
    except Exception as e:
        print(f"Failed to update JWT config: {e}")

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
            print("Vault role 'github-actions-role' created successfully.")
    except Exception as e:
        print(f"Failed to create Vault role: {e}")

    # Create Cloud Cost Policy
    policy_url = f"{VAULT_ADDR}/v1/sys/policies/acl/cloud-cost-policy"
    policy_rules = """
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
            print("Vault ACL policy 'cloud-cost-policy' created successfully.")
    except Exception as e:
        print(f"Failed to create Vault policy: {e}")

    print("\nVault setup complete! Vault is running locally at http://127.0.0.1:8200 with token 'root'.")
    print("OIDC authentication role 'github-actions-role' has been configured.")
    print("Vault UI is accessible at http://127.0.0.1:8200/ui using Token method (token: 'root').")

if __name__ == "__main__":
    setup()
