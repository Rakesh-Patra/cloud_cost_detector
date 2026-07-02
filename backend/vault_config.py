import os
import logging
import hvac

logger = logging.getLogger("vault_config")

# Set up logging for this module
logging.basicConfig(level=logging.INFO)

def load_vault_secrets():
    vault_addr = os.getenv("VAULT_ADDR")
    if not vault_addr:
        logger.info("VAULT_ADDR not set in environment. Falling back to local .env configuration.")
        return

    logger.info(f"Connecting to HashiCorp Vault at {vault_addr}...")
    client = hvac.Client(url=vault_addr)

    # 1. Authenticate with Vault
    token = os.getenv("VAULT_TOKEN")
    if token:
        client.token = token
        logger.info("Authenticated successfully using VAULT_TOKEN.")
    else:
        # JWT/OIDC authentication flow (e.g. inside cloud/GitHub Action runner)
        jwt_token = os.getenv("VAULT_JWT_TOKEN")
        jwt_path = os.getenv("JWT_TOKEN_PATH") or os.getenv("AWS_WEB_IDENTITY_TOKEN_FILE")
        role = os.getenv("VAULT_ROLE")

        # Load JWT token if stored in file
        if not jwt_token and jwt_path and os.path.exists(jwt_path):
            try:
                with open(jwt_path, "r") as f:
                    jwt_token = f.read().strip()
                logger.info(f"Loaded JWT token from file: {jwt_path}")
            except Exception as e:
                logger.warning(f"Could not read JWT token from file path {jwt_path}: {e}")

        if jwt_token and role:
            try:
                client.auth.jwt.jwt_login(
                    role=role,
                    jwt=jwt_token,
                    use_token_as_default=True
                )
                logger.info(f"Authenticated successfully via JWT/OIDC with role: {role}")
            except Exception as e:
                logger.error(f"Failed to authenticate with Vault via OIDC JWT: {e}")
                return
        else:
            logger.warning("No Vault auth credentials found. Skipping Vault secrets resolution.")
            return

    if not client.is_authenticated():
        logger.error("Vault client authentication check failed.")
        return

    # 2. Fetch secrets from Vault paths
    paths = [
        "secret/data/cloud_cost/aws",
        "secret/data/cloud_cost/ci"
    ]
    
    # Mapping of Vault fields to expected Application Env Variables
    mapping = {
        "access_key": "AWS_ACCESS_KEY_ID",
        "secret_key": "AWS_SECRET_ACCESS_KEY",
        "gemini_api_key": "GEMINI_API_KEY",
        "insforge_anon_key": "INSFORGE_ANON_KEY",
        "insforge_project_url": "INSFORGE_PROJECT_URL",
        "slack_webhook": "SLACK_WEBHOOK_URL",
        "infracost_key": "INFRACOST_API_KEY",
    }

    for path in paths:
        try:
            logger.info(f"Reading secrets from Vault path: {path}")
            response = client.read(path)
            
            if not response or "data" not in response:
                logger.warning(f"No secret data found at path: {path}")
                continue
                
            # Vault KV-v2 wraps data inside a "data" object inside "data"
            data = response["data"]
            if "data" in data:
                secrets = data["data"]
            else:
                secrets = data
                
            # Inject variables into environment
            for vault_key, value in secrets.items():
                if value:
                    env_key = mapping.get(vault_key.lower(), vault_key.upper())
                    os.environ[env_key] = str(value)
                    # Mask token prints in logs
                    masked_val = str(value)[:5] + "..." if len(str(value)) > 5 else "***"
                    logger.info(f"Loaded '{env_key}' from Vault ({masked_val})")
        except Exception as e:
            logger.warning(f"Error reading secrets from Vault path '{path}': {e}")
