# -*- coding: utf-8 -*-
import os
import sys
import json
import urllib.request
import urllib.error

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

VAULT_ADDR = os.getenv("VAULT_ADDR", "").rstrip("/")
VAULT_TOKEN = os.getenv("VAULT_TOKEN", "")
VAULT_NAMESPACE = os.getenv("VAULT_NAMESPACE", "admin")

if len(sys.argv) > 1:
    VAULT_ADDR = sys.argv[1].rstrip("/")
if len(sys.argv) > 2:
    VAULT_TOKEN = sys.argv[2]
if len(sys.argv) > 3:
    VAULT_NAMESPACE = sys.argv[3]

ENV_FILE = os.path.join(os.getcwd(), ".env.vault")
if not os.path.exists(ENV_FILE):
    ENV_FILE = os.path.join(os.getcwd(), ".env")

def load_env_file(path):
    env_vars = {}
    if not os.path.exists(path):
        return env_vars
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip().strip('"').strip("'")
    return env_vars

def write_vault_kv(path, data):
    url = f"{VAULT_ADDR}/v1/secret/data/{path}"
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("Invalid URL scheme: only http and https are allowed")
    payload = json.dumps({"data": data}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("X-Vault-Token", VAULT_TOKEN)
    req.add_header("X-Vault-Namespace", VAULT_NAMESPACE)
    req.add_header("Content-Type", "application/json")
    try:
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        with urllib.request.urlopen(req) as resp:
            return True, "Success"
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return False, f"HTTP {e.code}: {body}"
    except Exception as e:
        return False, str(e)

def main():
    print(f"Connecting to HCP Vault at {VAULT_ADDR} (Namespace: {VAULT_NAMESPACE})...")
    env_data = load_env_file(ENV_FILE)
    print(f"Loaded {len(env_data)} variables from {os.path.basename(ENV_FILE)}.")
    
    # 1. App Secrets
    app_secrets = {
        "gemini_api_key": env_data.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY", ""),
        "insforge_project_url": env_data.get("INSFORGE_PROJECT_URL") or os.getenv("INSFORGE_PROJECT_URL", ""),
        "insforge_anon_key": env_data.get("INSFORGE_ANON_KEY") or os.getenv("INSFORGE_ANON_KEY", ""),
        "aws_access_key_id": env_data.get("AWS_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID", ""),
        "aws_secret_access_key": env_data.get("AWS_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY", ""),
        "aws_default_region": env_data.get("AWS_DEFAULT_REGION") or os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
    }
    app_secrets = {k: v for k, v in app_secrets.items() if v and "placeholder" not in v and not v.endswith("_here")}
    if app_secrets:
        ok, msg = write_vault_kv("cloud_cost/app", app_secrets)
        if ok:
            print(f"[OK] Stored app secrets: {list(app_secrets.keys())}")
        else:
            print(f"[ERROR] Failed to store app secrets: {msg}")
    else:
        print("[INFO] No app secrets found in .env.vault / .env (all empty or placeholders)")
    
    # 2. SSH Secrets
    ssh_key = env_data.get("SSH_PRIVATE_KEY") or os.getenv("SSH_PRIVATE_KEY", "")
    if ssh_key and os.path.exists(ssh_key):
        with open(ssh_key, "r", encoding="utf-8") as f:
            ssh_key = f.read()
    elif not ssh_key:
        for possible_key in [
            "terraform/environment/dev/cloud_cost.pem",
            "cloud_cost.pem",
            "id_rsa",
            "terrakey",
            "terraform/terrakey"
        ]:
            if os.path.exists(possible_key):
                with open(possible_key, "r", encoding="utf-8") as f:
                    ssh_key = f.read()
                print(f"[INFO] Auto-detected SSH key from local file: {possible_key}")
                break
    if ssh_key and "placeholder" not in ssh_key:
        ok, msg = write_vault_kv("cloud_cost/ssh", {"private_key": ssh_key})
        if ok:
            print("[OK] Stored SSH private key at secret/data/cloud_cost/ssh")
        else:
            print(f"[ERROR] Failed to store SSH private key: {msg}")
    else:
        print("[INFO] No SSH private key provided.")
    
    # 3. Docker Secrets
    docker_user = env_data.get("REGISTRY_USERNAME") or env_data.get("DOCKER_USERNAME") or os.getenv("REGISTRY_USERNAME", "")
    docker_pass = env_data.get("REGISTRY_PASSWORD") or env_data.get("DOCKER_PASSWORD") or os.getenv("REGISTRY_PASSWORD", "")
    if docker_user and docker_pass:
        ok, msg = write_vault_kv("cloud_cost/docker", {"username": docker_user, "password": docker_pass})
        if ok:
            print("[OK] Stored Docker registry credentials at secret/data/cloud_cost/docker")
        else:
            print(f"[ERROR] Failed to store Docker credentials: {msg}")
    else:
        print("[INFO] No Docker registry credentials provided.")
    
    # 4. CI Secrets
    ci_secrets = {}
    infracost_key = env_data.get("INFRACOST_API_KEY") or os.getenv("INFRACOST_API_KEY", "")
    slack_webhook = env_data.get("SLACK_WEBHOOK_URL") or os.getenv("SLACK_WEBHOOK_URL", "")
    if infracost_key:
        ci_secrets["infracost_key"] = infracost_key
    if slack_webhook:
        ci_secrets["slack_webhook"] = slack_webhook
    if ci_secrets:
        ok, msg = write_vault_kv("cloud_cost/ci", ci_secrets)
        if ok:
            print(f"[OK] Stored CI secrets: {list(ci_secrets.keys())}")
        else:
            print(f"[ERROR] Failed to store CI secrets: {msg}")
    else:
        print("[INFO] No CI secrets (Infracost / Slack) provided.")
    print("\nVault secret seeding completed!")

if __name__ == "__main__":
    main()