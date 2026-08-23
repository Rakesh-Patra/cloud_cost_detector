import os
import logging
import uuid
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Literal
import boto3
import httpx
from fastapi import FastAPI, HTTPException, status, WebSocket, WebSocketDisconnect, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
try:
    from pythonjsonlogger.json import JsonFormatter
except ImportError:
    from pythonjsonlogger.jsonlogger import JsonFormatter

from aws_scanner import (
    list_aws_regions,
    scan_all_resources,
    execute_remediation,
    get_assumed_role_session,
    generate_cloudformation_template,
    generate_session_policy,
    safe_delete_ebs_volume,
    quarantine_resource,
    restore_quarantined_resource,
    validate_saas_credentials,
    AWSCredentialException,
    AWSRegionException,
    AWSRateLimitException,
    AWSScanException
)
from ai_analyzer import analyze_costs, generate_chat_response, GeminiAPIException
from insforge_client import InsForgeClient, InsForgeException
import database
import anomaly_detector

# Load environment variables at application startup
load_dotenv()

# Configure Structured Logging (JSON in production / CloudWatch, formatted console in local dev)
log_handler = logging.StreamHandler()
if os.environ.get("ENVIRONMENT", "").lower() in ("production", "prod", "staging") or os.environ.get("LOG_FORMAT", "").lower() == "json":
    formatter = JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    log_handler.setFormatter(formatter)
else:
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    log_handler.setFormatter(formatter)

root_logger = logging.getLogger()
root_logger.handlers = [log_handler]
root_logger.setLevel(logging.INFO)

logger = logging.getLogger("main")

# Initialize Rate Limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])

db_client = InsForgeClient()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern FastAPI lifespan context manager for startup and graceful shutdown."""
    database.init_db()

    # --- Credential Health Check ---
    # Validate the SaaS-side AWS credentials on every startup.
    # If they are temporary (e.g., assumed-role from a CloudFormation session) they
    # will expire in ~1 hour and cause InvalidClientTokenId errors on all scans.
    # Set AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY to a permanent IAM User key to fix this.
    cred_status = validate_saas_credentials()
    if cred_status["ok"]:
        logger.info(
            "✅ SaaS AWS credentials are permanent. Account: %s | ARN: %s",
            cred_status["account_id"],
            cred_status["arn"],
        )
    else:
        logger.warning(
            "⚠️  SaaS AWS credential issue detected at startup: %s",
            cred_status["message"],
        )

    scanner_task = asyncio.create_task(daily_anomaly_scanner_loop())
    logger.info("Application startup completed successfully with DB initialized and scheduler running.")
    yield
    logger.info("Application shutting down; cancelling background tasks.")
    scanner_task.cancel()
    try:
        await scanner_task
    except asyncio.CancelledError:
        pass


# Initialize FastAPI application
app = FastAPI(
    title="AI Cloud Cost Detective Backend",
    description="FastAPI Multi-Tenant Backend for AWS FinOps & Cost Optimization",
    version="2.0.0",
    lifespan=lifespan
)

# Wire SlowAPI limiter state and error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS
allowed_origins_str = os.environ.get("ALLOWED_ORIGINS", "")
if allowed_origins_str:
    origins = [orig.strip() for orig in allowed_origins_str.split(",") if orig.strip()]
else:
    # Default fallback for development
    origins = ["http://localhost:5173", "http://127.0.0.1:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True if "*" not in origins else False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instrument Prometheus metrics if available
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app)
except Exception:
    pass

@app.get("/healthz", status_code=status.HTTP_200_OK, tags=["Health"])
@app.get("/livez", status_code=status.HTTP_200_OK, tags=["Health"])
async def liveness_probe():
    """Liveness probe to confirm the container process is running."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/readyz", tags=["Health"])
async def readiness_probe():
    """Readiness probe to confirm database connectivity and application readiness."""
    db_ok = database.check_db_health()
    if not db_ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "database": "disconnected"}
        )
    return {"status": "ready", "database": "connected"}

# Define request/response models

class AnalyzeRequest(BaseModel):
    region: str = Field(..., description="The AWS region to scan, e.g., 'us-east-1'")
    analysis_id: str | None = Field(None, description="Optional UUID to track progress via WebSockets")
    account_id: str | None = Field(None, description="Optional connected Cloud Account ID for STS AssumeRole")

class AnalyzeMultiRegionRequest(BaseModel):
    regions: list[str] = Field(default=["us-east-1", "us-east-2", "us-west-2", "eu-west-1"], description="List of AWS regions to scan concurrently")
    analysis_id: str | None = Field(None, description="Optional UUID to track progress via WebSockets")
    account_id: str | None = Field(None, description="Optional connected Cloud Account ID for STS AssumeRole")

class ConnectAccountRequest(BaseModel):
    account_alias: str = Field(..., description="Friendly name for the account, e.g., 'Production-AWS'")
    aws_account_id: str = Field(..., description="12-digit AWS Account ID")
    role_arn: str = Field(..., description="The IAM Role ARN created in customer account")
    external_id: str = Field(..., description="The unique external ID for security handshake")
    regions: list[str] = Field(default=["us-east-1", "us-east-2", "us-west-2", "eu-west-1"])
    duration_days: int | None = Field(None, description="Optional access grant duration in days (e.g. 7, 30, 90)")
    tier: str = Field(default="readonly", description="IAM Role access tier ('readonly', 'remediation', 'admin')")

class QuarantineApplyRequest(BaseModel):
    resource_id: str = Field(..., description="AWS Resource ID (e.g. vol-1234, i-5678)")
    resource_type: str = Field(..., description="Resource Type (EBS Volume, EC2 Instance)")
    region: str = Field(..., description="AWS region")
    reason: str = Field(..., description="Why the resource was quarantined")
    account_id: str | None = Field(None, description="Optional connected account ID")
    quarantine_days: int = Field(default=7, description="Number of grace period days")

class QuarantineActionRequest(BaseModel):
    item_id: str = Field(..., description="Quarantine record ID")
    resource_id: str = Field(..., description="AWS Resource ID")
    region: str = Field(..., description="AWS region")
    account_id: str | None = Field(None, description="Optional connected account ID")

class DomainChallengeRequest(BaseModel):
    domain: str = Field(..., description="Company domain to verify ownership, e.g., 'acme.com'")

class DomainVerifyRequest(BaseModel):
    domain: str = Field(..., description="Company domain")
    token: str = Field(..., description="Challenge token issued for domain ownership verification")

class RolePromoteRequest(BaseModel):
    user_id: str = Field(..., description="Target user ID to promote")
    new_role: Literal["admin", "devops", "finops", "viewer"] = Field(..., description="New RBAC role to assign")
    reason: str = Field(default="", description="Business justification for role promotion")

class ApprovalCreateRequest(BaseModel):
    action: str = Field(..., description="Action to perform, e.g., 'ec2:StopInstances'")
    resource_id: str = Field(..., description="Target AWS Resource ID")
    resource_arn: str | None = Field(None, description="Full target AWS Resource ARN")
    region: str = Field(default="us-east-1", description="AWS Region")
    account_id: str | None = Field(None, description="Connected account ID")
    environment: str = Field(default="Production", description="Deployment environment tier")
    reason: str = Field(default="", description="Remediation rationale")

class ApprovalReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"] = Field(..., description="Approval decision")

@app.exception_handler(AWSCredentialException)
async def credential_exception_handler(request, exc):
    logger.error(f"Credentials failure: {exc}")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error": "AWS_CREDENTIALS_MISSING_OR_INVALID",
            "message": str(exc)
        }
    )

@app.exception_handler(AWSRegionException)
async def region_exception_handler(request, exc):
    logger.error(f"Region failure: {exc}")
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "error": "AWS_REGION_ERROR",
            "message": str(exc)
        }
    )

@app.exception_handler(AWSRateLimitException)
async def rate_limit_exception_handler(request, exc):
    logger.error(f"Rate limit failure: {exc}")
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "error": "AWS_RATE_LIMIT_EXCEEDED",
            "message": str(exc)
        }
    )

@app.exception_handler(AWSScanException)
async def scan_exception_handler(request, exc):
    logger.error(f"General scan failure: {exc}")
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={
            "error": "AWS_SCAN_FAILED",
            "message": str(exc)
        }
    )

@app.exception_handler(GeminiAPIException)
async def gemini_api_exception_handler(request, exc):
    logger.error(f"Gemini API failure: {exc}")
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={
            "error": "GEMINI_API_ERROR",
            "message": str(exc)
        }
    )

@app.exception_handler(InsForgeException)
async def insforge_exception_handler(request, exc):
    logger.error(f"InsForge DB failure: {exc}")
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={
            "error": "DATABASE_ERROR",
            "message": str(exc)
        }
    )

class ConnectionManager:
    """
    Manages active WebSocket progress connections for scan tracking.
    Supports in-memory client pooling and safe concurrent broadcast.
    """
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, analysis_id: str):
        await websocket.accept()
        if analysis_id not in self.active_connections:
            self.active_connections[analysis_id] = []
        self.active_connections[analysis_id].append(websocket)
        logger.info(f"WebSocket client connected to progress stream for analysis_id: {analysis_id}")

    def disconnect(self, websocket: WebSocket, analysis_id: str):
        if analysis_id in self.active_connections:
            if websocket in self.active_connections[analysis_id]:
                self.active_connections[analysis_id].remove(websocket)
            if not self.active_connections[analysis_id]:
                del self.active_connections[analysis_id]
        logger.info(f"WebSocket client disconnected from progress stream for analysis_id: {analysis_id}")

    async def broadcast(self, analysis_id: str, message: str):
        if analysis_id in self.active_connections:
            logger.info(f"Broadcasting to {analysis_id}: {message}")
            for connection in list(self.active_connections[analysis_id]):
                try:
                    await connection.send_text(message)
                except Exception as e:
                    logger.error(f"Error sending message down socket: {e}")

manager = ConnectionManager()

def is_production_env() -> bool:
    env = os.environ.get("ENVIRONMENT", os.environ.get("APP_ENV", os.environ.get("ENV", "development"))).strip().lower()
    return env in ("production", "prod", "staging") or os.environ.get("FAIL_CLOSED_AUTH", "").strip().lower() in ("true", "1")

async def get_current_user(
    authorization: str | None = Header(None, description="InsForge JWT Authorization Header"),
    x_api_key: str | None = Header(None, alias="X-API-Key", description="API Key for CI/CD or automation")
):
    is_prod = is_production_env()

    # 1. Allow authenticated API Key access (useful for microservices, CI/CD, or automated cron)
    api_secret = os.environ.get("API_SECRET_KEY")
    if x_api_key and api_secret and x_api_key.strip() == api_secret.strip():
        return {
            "user": {
                "id": "system-api-key",
                "email": "admin@api.internal",
                "role": "admin"
            },
            "token": "api-key-authorized"
        }

    if not authorization or not authorization.startswith("Bearer "):
        if is_prod:
            logger.warning("Unauthenticated request blocked in production environment (fail-closed)")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "AUTHENTICATION_REQUIRED", "message": "Authorization header with Bearer token or valid X-API-Key is required."}
            )
        return {"user": {"id": "dev-user-id", "email": "guest@local.user", "role": "devops"}, "token": "guest-token"}
    
    token = authorization.split(" ")[1].strip()
    if not token:
        if is_prod:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "AUTHENTICATION_REQUIRED", "message": "Bearer token must not be empty."}
            )
        return {"user": {"id": "dev-user-id", "email": "guest@local.user", "role": "devops"}, "token": "guest-token"}
    
    project_url = os.environ.get("INSFORGE_PROJECT_URL")
    anon_key = os.environ.get("INSFORGE_ANON_KEY")
    if not project_url or not anon_key:
        if is_prod:
            logger.error("Authentication configuration missing in production environment")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "AUTH_CONFIGURATION_ERROR", "message": "Authentication service is not properly configured."}
            )

    # Decode user information directly from JWT token payload (for claim inspection / dev fallback)
    decoded_user = {"id": "local-user-id", "email": "guest@local.user", "role": "viewer"}
    try:
        parts = token.split(".")
        if len(parts) >= 2:
            import base64
            p = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
            data = json.loads(base64.urlsafe_b64decode(p).decode("utf-8", "ignore"))
            if data.get("sub") or data.get("email"):
                decoded_user = {
                    "id": data.get("sub") or "local-user-id",
                    "email": data.get("email") or "guest@local.user",
                    "role": data.get("role") or data.get("user_metadata", {}).get("role") or ("viewer" if is_prod else "devops")
                }
    except Exception as decode_err:
        logger.debug(f"Could not parse JWT payload: {decode_err}")

    url = f"{project_url.rstrip('/')}/api/auth/sessions/current" if project_url else ""
    headers = {
        "apikey": anon_key or "",
        "Authorization": f"Bearer {token}"
    }
    
    if url:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers, timeout=10.0)
                if response.status_code != 200:
                    if is_prod:
                        logger.warning(f"InsForge session verification failed with status {response.status_code}")
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail={"error": "INVALID_SESSION", "message": "The provided authentication token is invalid or expired."}
                        )
                    logger.info(f"InsForge session check returned {response.status_code}, using decoded token identity in dev: {decoded_user.get('email')}")
                    return {"user": decoded_user, "token": token}
                
                resp_user = response.json().get("user") or decoded_user
                return {
                    "user": resp_user,
                    "token": token
                }
            except HTTPException:
                raise
            except httpx.RequestError as e:
                if is_prod:
                    logger.error(f"Auth service connection error in production: {e}")
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail={"error": "AUTH_SERVICE_UNAVAILABLE", "message": f"Authentication service unavailable: {str(e)}"}
                    )
                logger.warning(f"Error checking InsForge session in dev ({e}), using decoded token identity: {decoded_user.get('email')}")
                return {"user": decoded_user, "token": token}
            except Exception as e:
                if is_prod:
                    logger.error(f"Unexpected auth error in production: {e}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail={"error": "AUTH_INTERNAL_ERROR", "message": "Failed to verify session."}
                    )
                return {"user": decoded_user, "token": token}

    return {"user": decoded_user, "token": token}

    

def get_user_org_id(user: dict) -> str:
    user_info = user.get("user") or {}
    return str(user_info.get("org_id") or user_info.get("id") or user_info.get("email") or "default_org")

def get_user_role(user: dict) -> str:
    """
    Extracts the user's role securely with defense-in-depth:
    1. Re-fetches role directly from the DB profile (user_profiles),
       never relying on client JWT token payload alone.
    2. Fail-closed default: 'viewer' (Lowest privilege read-only).
    """
    user_info = user.get("user") or {}
    user_id = user_info.get("id")
    email = str(user_info.get("email") or "guest@local.user").lower()
    
    # 1. Check verified DB profile first (defense-in-depth)
    if user_id:
        profile = database.get_user_profile_db(user_id)
        if profile and profile.get("role"):
            return str(profile["role"]).lower()

    # 2. Check explicit role claim in JWT/session
    if user_info.get("role"):
        clean = str(user_info["role"]).lower()
        if clean in ["admin", "devops", "finops", "viewer"]:
            if user_id:
                database.get_or_create_user_profile(user_id, email, default_role=clean)
            return clean

    metadata = user_info.get("user_metadata") or user_info.get("metadata") or {}
    if metadata.get("role"):
        clean = str(metadata["role"]).lower()
        if clean in ["admin", "devops", "finops", "viewer"]:
            if user_id:
                database.get_or_create_user_profile(user_id, email, default_role=clean)
            return clean

    # 3. Local/Dev convenience fallback based on email
    if not is_production_env():
        if "admin" in email:
            assigned = "admin"
        elif "devops" in email:
            assigned = "devops"
        elif "viewer" in email or "analyst" in email or "finops" in email:
            assigned = "viewer"
        else:
            assigned = "finops"
        if user_id:
            database.get_or_create_user_profile(user_id, email, default_role=assigned)
        return assigned

    return "viewer"

def get_role_tier(role: str) -> int:
    """Maps RBAC role names to security tiers (1: Audit, 2: Remediation, 3: Admin)."""
    r = role.lower()
    if r == "admin":
        return 3
    if r == "devops":
        return 2
    return 1  # finops, viewer

def require_role(min_tier: int = 2):
    """
    FastAPI dependency / decorator to enforce minimum RBAC tier:
    - Tier 1: FinOps / Viewer (Read-only Audit)
    - Tier 2: DevOps (Active Remediation & Quarantine)
    - Tier 3: Admin (Full Account Binding, Promotion & Settings)
    """
    async def tier_checker(user: dict = Depends(get_current_user)):
        role = get_user_role(user)
        user_tier = get_role_tier(role)
        if user_tier < min_tier:
            tier_names = {1: "Tier 1 (FinOps Audit)", 2: "Tier 2 (DevOps Remediation)", 3: "Tier 3 (Admin)"}
            logger.warning(f"RBAC Denied: User {user.get('user', {}).get('email')} with role '{role}' (Tier {user_tier}) attempted action requiring {tier_names.get(min_tier)}.")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "INSUFFICIENT_PERMISSIONS",
                    "message": f"Role '{role}' (Tier {user_tier}) is not authorized. Minimum required tier: {tier_names.get(min_tier)}."
                }
            )
        return user
    return tier_checker

def require_roles(allowed_roles: list[str]):
    """FastAPI dependency to enforce Role-Based Access Control (RBAC)."""
    async def role_checker(user: dict = Depends(get_current_user)):
        role = get_user_role(user)
        if role not in allowed_roles:
            logger.warning(f"Access denied for user {user.get('user', {}).get('email')} with role '{role}'. Required: {allowed_roles}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "INSUFFICIENT_PERMISSIONS",
                    "message": f"Role '{role}' is not authorized to perform this action. Required role(s): {', '.join(allowed_roles)}."
                }
            )
        return user
    return role_checker

@app.get("/api/me", status_code=status.HTTP_200_OK, tags=["Auth"])
async def get_me(user: dict = Depends(get_current_user)):
    """Returns the current user profile and RBAC role."""
    user_info = user.get("user") or {}
    role = get_user_role(user)
    org_id = get_user_org_id(user)
    return {
        "email": user_info.get("email", "guest@local.user"),
        "id": user_info.get("id"),
        "role": role,
        "org_id": org_id,
        "tier": get_role_tier(role)
    }


@app.get("/api/regions", status_code=status.HTTP_200_OK)
async def get_regions(user: dict = Depends(get_current_user)):
    """
    Retrieve a list of active AWS regions. Fallback to standard AWS regions if listing fails.
    """
    logger.info("Fetching active AWS regions")
    try:
        regions = list_aws_regions()
        return {"regions": regions}
    except Exception as e:
        logger.warning(f"Could not dynamically list AWS regions ({e}), returning default AWS region list")
        default_regions = [
            "us-east-1", "us-east-2", "us-west-1", "us-west-2",
            "ap-south-1", "ap-northeast-1", "ap-southeast-1", "ap-southeast-2",
            "eu-west-1", "eu-central-1", "sa-east-1"
        ]
        return {"regions": default_regions}


@app.websocket("/ws/progress/{analysis_id}")
async def websocket_endpoint(websocket: WebSocket, analysis_id: str, token: str | None = None):
    # Accept WebSocket connection immediately for progress streaming
    await websocket.accept()
    await manager.connect(websocket, analysis_id)
    try:
        # Keep connection open with active heartbeat ping/pong
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=35.0)
                if msg.strip().lower() == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send keepalive ping to maintain connection through ELB / NAT Gateways
                await websocket.send_text(json.dumps({"type": "ping", "timestamp": datetime.now(timezone.utc).isoformat()}))
    except WebSocketDisconnect:
        manager.disconnect(websocket, analysis_id)
    except Exception as e:
        logger.debug(f"WebSocket closed for {analysis_id}: {e}")
        manager.disconnect(websocket, analysis_id)


@app.get("/api/history", status_code=status.HTTP_200_OK)
async def get_history(user: dict = Depends(get_current_user)):
    """
    Retrieve the analysis audit logs from InsForge Database.
    """
    logger.info("Fetching cost analysis history")
    try:
        history = await db_client.get_analysis_history(token=user["token"])
        return history
    except InsForgeException as e:
        await insforge_exception_handler(None, e)


@app.post("/api/analyze", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def analyze_region(request: Request, payload: AnalyzeRequest, user: dict = Depends(get_current_user)):
    """
    Scan active cost-driving AWS resources in the specified region, perform AI-powered cost analysis,
    and persist results to InsForge Database. Supports STS AssumeRole for multi-tenant accounts.
    """
    region = payload.region.strip()
    if not region:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Region parameter cannot be empty."
        )
        
    analysis_id = payload.analysis_id or str(uuid.uuid4())
    logger.info(f"Initiating resource scan for region: {region} with analysis_id: {analysis_id} (account: {payload.account_id})")
    
    # 1. Establish AWS Session (dynamic STS AssumeRole if account_id is supplied)
    session = None
    user_org = get_user_org_id(user)
    if payload.account_id:
        acc = database.get_cloud_account(payload.account_id, org_id=user_org)
        if not acc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cloud Account '{payload.account_id}' not found or access denied."
            )
        if acc.get("status") == "expired":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cloud Account access has expired on {acc.get('expires_at')}. Please refresh or renew permissions."
            )
        try:
            await manager.broadcast(analysis_id, f"Connecting to AWS Account ({acc.get('account_alias')}) via STS AssumeRole...")
            user_email = user.get("user", {}).get("email") or "finops-user"
            import re
            safe_session_name = re.sub(r'[^a-zA-Z0-9+=,.@-]', '-', user_email)[:64]
            try:
                session = get_assumed_role_session(acc["role_arn"], acc["external_id"], session_name=safe_session_name)
            except Exception as e:
                # If scanning the same local SaaS account and STS AssumeRole lacks permissions, fallback to direct credentials
                saas_acc = os.environ.get("AWS_SAAS_ACCOUNT_ID", "717056864326")
                if acc.get("aws_account_id") == saas_acc or "717056864326" in acc.get("role_arn", ""):
                    logger.warning(f"STS AssumeRole failed ({e}). Falling back to direct AWS session for primary account.")
                    session = boto3.Session(region_name=region)
                else:
                    raise e
            database.update_cloud_account_last_scanned(payload.account_id)
        except HTTPException:
            raise
        except Exception as sts_err:
            logger.error(f"Failed to assume role for account {payload.account_id}: {sts_err}")
            await manager.broadcast(analysis_id, f"STS Authentication failed: {str(sts_err)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Failed to authenticate with AWS Account via STS: {str(sts_err)}"
            )

    try:
        # Step 1: Initializing clients
        await manager.broadcast(analysis_id, "Initializing AWS clients...")
        try:
            await db_client.create_analysis(analysis_id, region, token=user["token"])
        except Exception as db_err:
            logger.warning(f"InsForge create_analysis notice: {db_err}")
        
        # Step 2: Scanning resources with 14-day CloudWatch telemetry
        await manager.broadcast(analysis_id, f"Scanning EC2, EBS, RDS & 14-day telemetry in {region}...")
        if session is not None:
            resources = await asyncio.to_thread(scan_all_resources, region, session)
        else:
            resources = await asyncio.to_thread(scan_all_resources, region)
        
        # Step 3: AI analysis with Tier 1 deterministic pricing filter
        await manager.broadcast(analysis_id, "Running precision pricing engine & Gemini AI synthesis...")
        analysis = await asyncio.to_thread(analyze_costs, resources, region)
        
        # Step 4: Persisting results
        await manager.broadcast(analysis_id, "Persisting audit metrics...")
        
        issues_found = len(analysis.get('recommendations', []))
        total_savings = sum(item.get('estimated_savings', 0.0) for item in analysis.get('recommendations', []))
        estimated_savings = f"${total_savings:.2f}"
        
        try:
            await db_client.update_analysis_success(
                analysis_id=analysis_id,
                resources_scanned=len(resources),
                issues_found=issues_found,
                estimated_savings=estimated_savings,
                analysis_result=analysis,
                token=user["token"]
            )
        except Exception as db_err:
            logger.warning(f"InsForge update_analysis_success notice: {db_err}")
        
        # Step 5: Complete
        await manager.broadcast(analysis_id, "Analysis complete")
        
        return {
            "analysis_id": analysis_id,
            "region": region,
            "account_id": payload.account_id,
            "resources": resources,
            "count": len(resources),
            "analysis": analysis
        }
    except Exception as e:
        # Mark db record as failed
        await db_client.update_analysis_failure(analysis_id, token=user["token"])
        
        # Broadcast error
        await manager.broadcast(analysis_id, f"Analysis failed: {str(e)}")
        
        # Re-route exceptions to their handlers
        if isinstance(e, AWSCredentialException):
            await credential_exception_handler(None, e)
        elif isinstance(e, AWSRegionException):
            await region_exception_handler(None, e)
        elif isinstance(e, AWSRateLimitException):
            await rate_limit_exception_handler(None, e)
        elif isinstance(e, AWSScanException):
            await scan_exception_handler(None, e)
        elif isinstance(e, GeminiAPIException):
            await gemini_api_exception_handler(None, e)
        elif isinstance(e, InsForgeException):
            await insforge_exception_handler(None, e)
        else:
            logger.error(f"Unhandled error in analyze: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An unexpected error occurred: {str(e)}"
            )


@app.post("/api/analyze/all", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def analyze_all_regions(request: Request, payload: AnalyzeMultiRegionRequest, user: dict = Depends(get_current_user)):
    """
    Concurrent multi-region AWS cost audit.
    Scans EC2, EBS, RDS, S3 across all selected regions in parallel using asyncio.gather.
    Persists combined findings and AI synthesis to the database.
    """
    regions = [r.strip() for r in payload.regions if r.strip()]
    if not regions:
        regions = ["us-east-1", "us-east-2", "us-west-2", "eu-west-1"]

    analysis_id = payload.analysis_id or str(uuid.uuid4())
    user_org = get_user_org_id(user)
    
    session = None
    if payload.account_id:
        acc = database.get_cloud_account(payload.account_id, org_id=user_org)
        if not acc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cloud Account '{payload.account_id}' not found or access denied."
            )
        if acc.get("status") == "expired":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cloud Account access has expired on {acc.get('expires_at')}. Please refresh or renew permissions."
            )
        user_email = user.get("user", {}).get("email") or "finops-user"
        import re
        safe_session_name = re.sub(r'[^a-zA-Z0-9+=,.@-]', '-', user_email)[:64]
        session = get_assumed_role_session(acc["role_arn"], acc["external_id"], session_name=safe_session_name)
        database.update_cloud_account_last_scanned(payload.account_id)

    await manager.broadcast(analysis_id, f"Initiating parallel multi-region scan across {len(regions)} regions ({', '.join(regions)})...")
    
    async def scan_single_region(reg: str):
        try:
            return await asyncio.to_thread(scan_all_resources, reg, session)
        except Exception as scan_err:
            logger.warning(f"Error scanning region {reg}: {scan_err}")
            return []

    # Run region scans concurrently
    results = await asyncio.gather(*(scan_single_region(r) for r in regions))
    all_resources = []
    for res_list in results:
        all_resources.extend(res_list)

    await manager.broadcast(analysis_id, f"Scanned total {len(all_resources)} resources across {len(regions)} regions. Synthesizing AI findings...")
    primary_region = regions[0]
    analysis = await asyncio.to_thread(analyze_costs, all_resources, primary_region)

    issues_found = len(analysis.get('recommendations', []))
    total_savings = sum(item.get('estimated_savings', 0.0) for item in analysis.get('recommendations', []))
    estimated_savings = f"${total_savings:.2f}"

    try:
        await db_client.create_analysis(analysis_id, f"Multi-Region ({len(regions)})", token=user["token"])
        await db_client.update_analysis_success(
            analysis_id=analysis_id,
            resources_scanned=len(all_resources),
            issues_found=issues_found,
            estimated_savings=estimated_savings,
            analysis_result=analysis,
            token=user["token"]
        )
    except Exception as db_err:
        logger.warning(f"InsForge multi-region update notice: {db_err}")

    await manager.broadcast(analysis_id, "Multi-region analysis complete")
    return {
        "analysis_id": analysis_id,
        "regions_scanned": regions,
        "resources_scanned": len(all_resources),
        "issues_found": issues_found,
        "estimated_savings": estimated_savings,
        "analysis": analysis
    }


class RemediateRequest(BaseModel):
    analysis_id: str = Field(..., description="The ID of the cost analysis record")
    resource_id: str = Field(..., description="The ID of the target resource to remediate")
    issue_type: str = Field(..., description="The cost optimization issue type")
    region: str = Field(..., description="The AWS region of the target resource")
    account_id: str | None = Field(None, description="Optional connected cloud account ID")


@app.post("/api/remediate", status_code=status.HTTP_200_OK)
async def remediate_resource(payload: RemediateRequest, user: dict = Depends(require_role(min_tier=2))):
    """
    Executes cost-saving remediation for a specific resource, updates the database log,
    and returns the execution status. Uses session-scoped least privilege and audit logging.
    """
    logger.info(f"Remediation request received for resource {payload.resource_id} under analysis {payload.analysis_id}")
    
    user_org = get_user_org_id(user)
    user_info = user.get("user") or {}
    user_id = user_info.get("id") or "devops"
    user_email = user_info.get("email") or "devops@domain.com"
    session = None

    if payload.account_id:
        acc = database.get_cloud_account(payload.account_id, org_id=user_org)
        if not acc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cloud Account '{payload.account_id}' not found or access denied."
            )
        if acc.get("status") == "expired":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cloud Account access has expired on {acc.get('expires_at')}. Please refresh or renew permissions."
            )
        import re
        safe_session_name = re.sub(r'[^a-zA-Z0-9+=,.@-]', '-', user_email)[:64]
        session_policy = generate_session_policy("remediation", [f"arn:aws:ec2:{payload.region}:*:*"])
        session = get_assumed_role_session(acc["role_arn"], acc["external_id"], session_name=safe_session_name, session_policy=session_policy)

    # 1. Execute the remediation via boto3
    try:
        if session is not None:
            result = await asyncio.to_thread(
                execute_remediation,
                payload.region,
                payload.resource_id,
                payload.issue_type,
                session
            )
        else:
            result = await asyncio.to_thread(
                execute_remediation,
                payload.region,
                payload.resource_id,
                payload.issue_type
            )
    except ValueError as e:
        logger.error(f"Invalid remediation parameter: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "INVALID_REMEDIATION_PARAMETER",
                "message": str(e)
            }
        )
    
    # 2. Retrieve analysis record and update remediation status
    remediated_at = datetime.now(timezone.utc).isoformat()
    token = user.get("token") if isinstance(user, dict) else None
    
    try:
        record = await db_client.get_analysis(payload.analysis_id, token=token)
        analysis_result = record.get("analysis_result") if record else None
        if analysis_result:
            recommendations = analysis_result.get("recommendations", [])
            for rec in recommendations:
                if rec.get("resource_id") == payload.resource_id:
                    rec["remediated"] = True
                    rec["remediated_at"] = remediated_at
                    if isinstance(result, dict) and result.get("snapshot_id"):
                        rec["snapshot_id"] = result.get("snapshot_id")
                    break

            # 3. Patch the updated analysis_result back to the database
            await db_client.update_analysis_result(payload.analysis_id, analysis_result, token=token)
    except Exception as db_err:
        logger.warning(f"InsForge analysis update notice during remediation of {payload.resource_id}: {db_err}")

    database.log_activity_event(
        user_id=user_id,
        user_email=user_email,
        org_id=user_org,
        action="EXECUTE_REMEDIATION",
        target_arn=payload.resource_id,
        tier="remediation",
        result="success",
        details={"issue_type": payload.issue_type, "region": payload.region, "result": result}
    )

    return {
        "success": True,
        "resource_id": payload.resource_id,
        "action": payload.issue_type,
        "remediated_at": remediated_at,
        "details": result
    }


# =====================================================================
# --- Phase 1: Multi-Tenant Cloud Accounts (STS AssumeRole) API ---
# =====================================================================

@app.get("/api/v1/credentials/status", status_code=status.HTTP_200_OK, tags=["Cloud Accounts"])
async def get_saas_credential_status(user: dict = Depends(require_roles(["admin", "devops"]))):
    """
    Returns the health status of the SaaS-side AWS credentials used to call STS AssumeRole.

    If credentials are temporary they will expire and cause InvalidClientTokenId errors.
    Set AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY to a permanent IAM User key to fix this.
    """
    result = validate_saas_credentials()
    http_status = status.HTTP_200_OK if result["ok"] else status.HTTP_503_SERVICE_UNAVAILABLE
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=http_status, content=result)


@app.get("/api/v1/accounts/cfn-template", status_code=status.HTTP_200_OK, tags=["Cloud Accounts"])
async def get_cfn_template(
    mode: Literal["readonly", "remediation", "admin"] = "readonly",
    duration_days: int | None = None,
    user: dict = Depends(get_current_user)
):
    """
    Generates a secure 1-Click AWS CloudFormation template and direct AWS Console link.
    External ID is persisted per organization so reopening the modal retains the same token.
    Supports mode='readonly' (Tier 1 Audit), mode='remediation' (Tier 2 Active Cleanup),
    mode='admin' (Tier 3 Full Admin — AdministratorAccess + Billing),
    and duration_days for cryptographic AWS IAM DateLessThan time-limited access.
    """
    user_org = get_user_org_id(user)
    external_id = database.get_or_create_org_external_id(user_org)
    
    saas_account_id = os.environ.get("AWS_SAAS_ACCOUNT_ID")
    if not saas_account_id or saas_account_id == "123456789012":
        try:
            from aws_scanner import validate_saas_credentials
            cred = validate_saas_credentials()
            saas_account_id = cred.get("account_id") or "717056864326"
        except Exception:
            saas_account_id = "717056864326"
    
    cfn_yaml = generate_cloudformation_template(saas_account_id, external_id, mode=mode, duration_days=duration_days)
    
    # 1-Click AWS Console Quick Create URL (template upload flow — more reliable than review)
    aws_quick_create_url = (
        f"https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/create/template"
        f"?stackName=CloudCostDetective-AuditIntegration"
        f"&param_SaaSAccountId={saas_account_id}"
        f"&param_ExternalId={external_id}"
    )

    return {
        "external_id": external_id,
        "saas_account_id": saas_account_id,
        "cfn_yaml": cfn_yaml,
        "quick_create_url": aws_quick_create_url,
        "mode": mode,
        "duration_days": duration_days
    }

@app.post("/api/v1/accounts/connect", status_code=status.HTTP_201_CREATED, tags=["Cloud Accounts"])
async def connect_cloud_account(payload: ConnectAccountRequest, request: Request, user: dict = Depends(get_current_user)):
    """
    Validates STS AssumeRole handshake and saves the connected AWS account with defense-in-depth:
    1. Rejects immediately without calling STS if target role ARN is bound to another tenant.
    2. Enforces that only an Org Admin can bind a new role ARN for the first time.
    3. Uses Session Policies on STS AssumeRole to enforce least privilege.
    """
    user_org = get_user_org_id(user)
    user_role = get_user_role(user)
    user_info = user.get("user") or {}
    user_id = user_info.get("id") or "user"
    user_email = user_info.get("email") or "user@domain.com"
    client_ip = request.client.host if request.client else "unknown"

    # Step 1-3: Confused-Deputy & Org Binding Check
    passed, msg, saved_acc = database.check_and_bind_account(
        org_id=user_org,
        user_id=user_id,
        user_role=user_role,
        account_alias=payload.account_alias,
        aws_account_id=payload.aws_account_id,
        role_arn=payload.role_arn,
        external_id=payload.external_id,
        tier=payload.tier,
        duration_days=payload.duration_days,
        regions=payload.regions,
        ip_address=client_ip
    )

    if not passed:
        # Don't leak details; log security event and reject
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST if "Admin" not in msg else status.HTTP_403_FORBIDDEN,
            detail={"error": "BINDING_REJECTED", "message": msg}
        )

    # Step 4: Validate STS Handshake with Session Policy
    try:
        session_policy = generate_session_policy(payload.tier)
        session = get_assumed_role_session(payload.role_arn, payload.external_id, session_policy=session_policy)
        sts = session.client('sts')
        identity = sts.get_caller_identity()
        logger.info(f"Verified STS AssumeRole connection for {payload.aws_account_id}: {identity.get('Arn')}")
        
        database.log_activity_event(
            user_id=user_id,
            user_email=user_email,
            org_id=user_org,
            action="CONNECT_CLOUD_ACCOUNT",
            target_arn=payload.role_arn,
            tier=payload.tier,
            result="success",
            details={"aws_account_id": payload.aws_account_id, "alias": payload.account_alias}
        )
    except Exception as e:
        logger.warning(f"Could not verify live STS connection ({e}). Proceeding in registered mode.")
        database.log_activity_event(
            user_id=user_id,
            user_email=user_email,
            org_id=user_org,
            action="CONNECT_CLOUD_ACCOUNT_OFFLINE",
            target_arn=payload.role_arn,
            tier=payload.tier,
            result="registered_offline",
            details={"warning": str(e)}
        )

    return saved_acc

@app.get("/api/v1/accounts", status_code=status.HTTP_200_OK, tags=["Cloud Accounts"])
async def list_accounts(user: dict = Depends(get_current_user)):
    """List all connected AWS accounts for the user organization."""
    user_org = get_user_org_id(user)
    accounts = database.list_cloud_accounts(user_org)
    return {"accounts": accounts}

@app.delete("/api/v1/accounts/{account_id}", status_code=status.HTTP_200_OK, tags=["Cloud Accounts"])
async def delete_account(account_id: str, user: dict = Depends(require_roles(["admin"]))):
    """Disconnect an AWS cloud account (Admin only)."""
    user_org = get_user_org_id(user)
    user_info = user.get("user") or {}
    success = database.delete_cloud_account(account_id, user_org)
    if not success:
        raise HTTPException(status_code=404, detail="Cloud account not found.")

    database.log_activity_event(
        user_id=user_info.get("id") or "admin",
        user_email=user_info.get("email") or "admin@domain.com",
        org_id=user_org,
        action="DISCONNECT_CLOUD_ACCOUNT",
        target_arn=account_id,
        result="success",
        details={"account_id": account_id}
    )
    return {"success": True, "message": "Account disconnected."}


# =====================================================================
# --- Section 4: Domain Challenge, Org Verification & Role Promotion ---
# =====================================================================

@app.post("/api/v1/org/domain-challenge", status_code=status.HTTP_200_OK, tags=["Identity & Verification"])
async def create_domain_challenge(payload: DomainChallengeRequest, user: dict = Depends(get_current_user)):
    """Issues a DNS TXT / Domain challenge token to verify company ownership before granting Admin rights."""
    user_org = get_user_org_id(user)
    token = database.create_org_domain_challenge(user_org, payload.domain)
    return {
        "domain": payload.domain,
        "challenge_type": "DNS_TXT",
        "txt_record_name": f"_cloudcost-challenge.{payload.domain}",
        "txt_record_value": token,
        "instructions": f"Add a DNS TXT record for '_cloudcost-challenge.{payload.domain}' with value '{token}', then click Verify."
    }

@app.post("/api/v1/org/verify-domain", status_code=status.HTTP_200_OK, tags=["Identity & Verification"])
async def verify_domain(payload: DomainVerifyRequest, user: dict = Depends(get_current_user)):
    """Verifies domain challenge token and promotes the initial user to verified Organization Admin."""
    user_org = get_user_org_id(user)
    user_info = user.get("user") or {}
    user_id = user_info.get("id") or "user"
    user_email = user_info.get("email") or ""

    success = database.verify_org_domain(user_org, payload.domain, payload.token, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "DOMAIN_VERIFICATION_FAILED", "message": "The provided domain verification token is invalid."}
        )

    database.log_activity_event(
        user_id=user_id,
        user_email=user_email,
        org_id=user_org,
        action="VERIFY_ORG_DOMAIN",
        result="success",
        details={"domain": payload.domain}
    )
    return {"success": True, "message": f"Domain {payload.domain} verified. You are now verified Organization Admin."}

@app.get("/api/v1/org/users", status_code=status.HTTP_200_OK, tags=["Identity & Verification"])
async def list_org_users(user: dict = Depends(require_role(min_tier=2))):
    """List members of the organization with their RBAC roles (DevOps & Admin)."""
    user_org = get_user_org_id(user)
    users = database.list_org_users_db(user_org)
    return {"users": users}

@app.post("/api/v1/org/promote", status_code=status.HTTP_200_OK, tags=["Identity & Verification"])
async def promote_user(payload: RolePromoteRequest, user: dict = Depends(require_roles(["admin"]))):
    """Promotes or demotes an organization user's role (Admin only). Logged to immutable audit trail."""
    user_org = get_user_org_id(user)
    admin_info = user.get("user") or {}
    admin_id = admin_info.get("id") or "admin"
    admin_email = admin_info.get("email") or "admin@domain.com"

    success = database.update_user_role_db(
        user_id=payload.user_id,
        new_role=payload.new_role,
        promoted_by_user_id=admin_id,
        org_id=user_org,
        reason=payload.reason
    )
    if not success:
        raise HTTPException(status_code=404, detail="User not found in organization.")

    database.log_activity_event(
        user_id=admin_id,
        user_email=admin_email,
        org_id=user_org,
        action="PROMOTE_USER_ROLE",
        target_arn=payload.user_id,
        result="success",
        details={"target_user_id": payload.user_id, "new_role": payload.new_role, "reason": payload.reason}
    )
    return {"success": True, "message": f"User {payload.user_id} updated to role '{payload.new_role}'."}


# =====================================================================
# --- Section 5: Dual-Control Approvals for Production Remediation ---
# =====================================================================

@app.get("/api/v1/approvals", status_code=status.HTTP_200_OK, tags=["Dual-Control Approvals"])
async def list_approvals(status_filter: str | None = None, user: dict = Depends(get_current_user)):
    """List dual-control remediation approvals for the organization."""
    user_org = get_user_org_id(user)
    approvals = database.list_remediation_approvals(user_org, status_filter)
    return {"approvals": approvals}

@app.post("/api/v1/approvals/request", status_code=status.HTTP_201_CREATED, tags=["Dual-Control Approvals"])
async def request_approval(payload: ApprovalCreateRequest, user: dict = Depends(require_role(min_tier=2))):
    """Explicitly submits a remediation request to the dual-control approval queue."""
    user_org = get_user_org_id(user)
    user_info = user.get("user") or {}
    user_id = user_info.get("id") or "devops"
    user_email = user_info.get("email") or "devops@domain.com"

    req = database.create_remediation_approval(
        org_id=user_org,
        requester_id=user_id,
        requester_email=user_email,
        action=payload.action,
        resource_id=payload.resource_id,
        resource_arn=payload.resource_arn,
        region=payload.region,
        account_id=payload.account_id,
        environment=payload.environment,
        reason=payload.reason
    )
    database.log_activity_event(
        user_id=user_id,
        user_email=user_email,
        org_id=user_org,
        action="REQUEST_REMEDIATION_APPROVAL",
        target_arn=payload.resource_id,
        result="pending_approval",
        details={"approval_id": req["id"], "environment": payload.environment, "action": payload.action}
    )
    return req

@app.post("/api/v1/approvals/{approval_id}/review", status_code=status.HTTP_200_OK, tags=["Dual-Control Approvals"])
async def review_approval(approval_id: str, payload: ApprovalReviewRequest, user: dict = Depends(require_role(min_tier=2))):
    """
    Reviews a pending remediation approval.
    Enforces dual-control: Requester cannot approve their own request!
    """
    user_org = get_user_org_id(user)
    user_info = user.get("user") or {}
    user_id = user_info.get("id") or "reviewer"
    user_email = user_info.get("email") or "reviewer@domain.com"

    try:
        updated = database.review_remediation_approval(
            approval_id=approval_id,
            approver_id=user_id,
            approver_email=user_email,
            decision=payload.decision,
            org_id=user_org
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Approval request not found.")

        database.log_activity_event(
            user_id=user_id,
            user_email=user_email,
            org_id=user_org,
            action=f"REVIEW_APPROVAL_{payload.decision.upper()}",
            target_arn=approval_id,
            approval_chain=f"reviewed_by:{user_email}",
            result=payload.decision,
            details={"approval_id": approval_id, "decision": payload.decision}
        )
        return updated
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail={"error": "DUAL_CONTROL_VIOLATION", "message": str(val_err)})

@app.post("/api/v1/approvals/{approval_id}/execute", status_code=status.HTTP_200_OK, tags=["Dual-Control Approvals"])
async def execute_approved_remediation(approval_id: str, user: dict = Depends(require_role(min_tier=2))):
    """Executes a previously approved production remediation using session-scoped least privilege."""
    user_org = get_user_org_id(user)
    user_info = user.get("user") or {}
    user_id = user_info.get("id") or "executor"
    user_email = user_info.get("email") or "executor@domain.com"

    appr = database.get_remediation_approval(approval_id, user_org)
    if not appr:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    if appr.get("status") != "approved":
        raise HTTPException(status_code=400, detail=f"Cannot execute remediation in status '{appr.get('status')}'. Must be 'approved'.")

    # Execute with session-scoped policy
    session = None
    if appr.get("account_id"):
        acc = database.get_cloud_account(appr["account_id"], org_id=user_org)
        if acc:
            session_policy = generate_session_policy("remediation", [appr.get("resource_arn") or "*"])
            session = get_assumed_role_session(acc["role_arn"], acc["external_id"], session_policy=session_policy)

    exec_result = await asyncio.to_thread(
        execute_remediation,
        appr.get("region", "us-east-1"),
        appr["resource_id"],
        appr.get("action", "ec2:StopInstances"),
        session
    )

    database.log_activity_event(
        user_id=user_id,
        user_email=user_email,
        org_id=user_org,
        action="EXECUTE_APPROVED_REMEDIATION",
        target_arn=appr["resource_id"],
        approval_chain=f"requested:{appr.get('requester_email')}|approved:{appr.get('approver_email')}",
        result="success",
        details={"approval_id": approval_id, "execution_result": str(exec_result)}
    )

    return {"success": True, "approval_id": approval_id, "result": exec_result}


# =====================================================================
# --- Section 6: Immutable Activity Audit Trail API ---
# =====================================================================

@app.get("/api/v1/audit/logs", status_code=status.HTTP_200_OK, tags=["Audit Trail"])
async def list_audit_logs(limit: int = 100, user: dict = Depends(get_current_user)):
    """
    Returns the immutable activity audit log.
    Admins see full organizational activity. DevOps/FinOps see actions filtered to their user ID.
    """
    user_org = get_user_org_id(user)
    user_role = get_user_role(user)
    user_info = user.get("user") or {}
    user_id = user_info.get("id")

    # Non-admins get their own actions filtered
    filter_user = None if user_role == "admin" else user_id
    logs = database.get_activity_logs(user_org, user_id=filter_user, limit=limit)
    return {"logs": logs, "viewer_role": user_role}

@app.get("/api/v1/audit/security-events", status_code=status.HTTP_200_OK, tags=["Audit Trail"])
async def list_security_events(limit: int = 50, user: dict = Depends(require_roles(["admin"]))):
    """Returns critical security events (confused deputy, cross-org takeover attempts) - Admin only."""
    user_org = get_user_org_id(user)
    events = database.get_security_events(user_org, limit=limit)
    return {"events": events}


# =====================================================================
# --- Phase 1: Tag-and-Wait Quarantine & Safe Deletion API ---
# =====================================================================

@app.post("/api/v1/quarantine/apply", status_code=status.HTTP_201_CREATED, tags=["Quarantine"])
async def apply_quarantine(payload: QuarantineApplyRequest, user: dict = Depends(require_role(min_tier=2))):
    """
    Tags an AWS resource with 7-day quarantine metadata and registers it in the quarantine ledger (Tier 2 DevOps / Admin).
    """
    user_org = get_user_org_id(user)
    user_info = user.get("user") or {}
    user_id = user_info.get("id") or "user"
    user_email = user_info.get("email") or "user@domain.com"
    session = None
    if payload.account_id:
        acc = database.get_cloud_account(payload.account_id, org_id=user_org)
        if not acc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cloud Account '{payload.account_id}' not found or access denied."
            )
        if acc.get("status") == "expired":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cloud Account access has expired on {acc.get('expires_at')}. Please refresh permissions."
            )
        session_policy = generate_session_policy("remediation", [f"arn:aws:ec2:{payload.region}:*:*"])
        session = get_assumed_role_session(acc["role_arn"], acc["external_id"], session_policy=session_policy)

    # Apply AWS tags
    try:
        if session:
            await asyncio.to_thread(
                quarantine_resource,
                session,
                payload.region,
                payload.resource_id,
                payload.resource_type,
                payload.quarantine_days
            )
    except Exception as e:
        logger.warning(f"Could not apply AWS tags ({e}). Saving record to local ledger.")

    item_id = f"quar_{uuid.uuid4().hex[:12]}"
    record = database.save_quarantine_item(
        item_id=item_id,
        org_id=user_org,
        account_id=payload.account_id or "default",
        resource_id=payload.resource_id,
        resource_type=payload.resource_type,
        region=payload.region,
        reason=payload.reason,
        quarantine_days=payload.quarantine_days
    )

    database.log_activity_event(
        user_id=user_id,
        user_email=user_email,
        org_id=user_org,
        action="QUARANTINE_RESOURCE",
        target_arn=payload.resource_id,
        tier="remediation",
        result="success",
        details={"item_id": item_id, "reason": payload.reason}
    )
    return record

@app.get("/api/v1/quarantine/items", status_code=status.HTTP_200_OK, tags=["Quarantine"])
async def list_quarantine(status_filter: str | None = None, user: dict = Depends(get_current_user)):
    """Retrieve quarantine inventory items."""
    user_org = get_user_org_id(user)
    items = database.list_quarantine_items(user_org, status_filter)
    return {"items": items}

@app.post("/api/v1/quarantine/dismiss", status_code=status.HTTP_200_OK, tags=["Quarantine"])
async def dismiss_quarantine(payload: QuarantineActionRequest, user: dict = Depends(require_role(min_tier=2))):
    """
    Removes quarantine tag and whitelists resource (Tier 2 DevOps / Admin).
    """
    user_org = get_user_org_id(user)
    user_info = user.get("user") or {}
    user_id = user_info.get("id") or "user"
    user_email = user_info.get("email") or "user@domain.com"
    session = None
    if payload.account_id:
        acc = database.get_cloud_account(payload.account_id, org_id=user_org)
        if not acc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cloud Account '{payload.account_id}' not found or access denied."
            )
        if acc.get("status") == "expired":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cloud Account access has expired on {acc.get('expires_at')}. Please refresh permissions."
            )
        session_policy = generate_session_policy("remediation", [f"arn:aws:ec2:{payload.region}:*:*"])
        session = get_assumed_role_session(acc["role_arn"], acc["external_id"], session_policy=session_policy)

    if session:
        try:
            await asyncio.to_thread(restore_quarantined_resource, session, payload.region, payload.resource_id)
        except Exception as e:
            logger.warning(f"AWS tag removal warning: {e}")

    database.update_quarantine_status(payload.item_id, "restored", org_id=user_org)
    database.log_activity_event(
        user_id=user_id,
        user_email=user_email,
        org_id=user_org,
        action="DISMISS_QUARANTINE",
        target_arn=payload.resource_id,
        tier="remediation",
        result="restored",
        details={"item_id": payload.item_id}
    )
    return {"success": True, "message": f"Resource {payload.resource_id} restored and whitelisted."}

@app.post("/api/v1/quarantine/safe-delete", status_code=status.HTTP_200_OK, tags=["Quarantine"])
async def safe_delete_quarantined(payload: QuarantineActionRequest, user: dict = Depends(require_roles(["admin"]))):
    """
    Enterprise Safeguard: Creates a backup snapshot before permanently deleting volume (Admin only).
    """
    user_org = get_user_org_id(user)
    user_info = user.get("user") or {}
    user_id = user_info.get("id") or "admin"
    user_email = user_info.get("email") or "admin@domain.com"
    session = None
    if payload.account_id:
        acc = database.get_cloud_account(payload.account_id, org_id=user_org)
        if not acc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cloud Account '{payload.account_id}' not found or access denied."
            )
        if acc.get("status") == "expired":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cloud Account access has expired on {acc.get('expires_at')}. Please refresh permissions."
            )
        session_policy = generate_session_policy("remediation", [f"arn:aws:ec2:{payload.region}:*:*"])
        session = get_assumed_role_session(acc["role_arn"], acc["external_id"], session_policy=session_policy)

    snapshot_id = None
    try:
        active_session = session if session is not None else boto3.Session()
        res = await asyncio.to_thread(safe_delete_ebs_volume, active_session, payload.region, payload.resource_id)
        snapshot_id = res.get("snapshot_id")
    except Exception as e:
        logger.error(f"Safe delete failed: {e}")
        raise HTTPException(status_code=500, detail=f"Safe deletion failed: {str(e)}")

    database.update_quarantine_status(payload.item_id, "deleted", snapshot_id=snapshot_id, org_id=user_org)
    database.log_activity_event(
        user_id=user_id,
        user_email=user_email,
        org_id=user_org,
        action="SAFE_DELETE_RESOURCE",
        target_arn=payload.resource_id,
        tier="admin",
        result="success",
        details={"item_id": payload.item_id, "snapshot_id": snapshot_id}
    )
    return {
        "success": True,
        "snapshot_id": snapshot_id,
        "message": f"Safely deleted {payload.resource_id}. Snapshot {snapshot_id} created for rollback."
    }


class ChatMessage(BaseModel):
    role: Literal["user", "model"]
    text: str


class ChatRequest(BaseModel):
    message: str = Field(..., description="The user's latest query")
    history: List[ChatMessage] = Field(default_factory=list, description="Previous chat messages for context")
    resources: List[dict] = Field(default_factory=list, description="Array of scanned resources")
    recommendations: List[dict] = Field(default_factory=list, description="Array of optimization recommendations")


@app.post("/api/chat", status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def chat_with_finops_assistant(request: Request, payload: ChatRequest, user: dict = Depends(get_current_user)):
    """
    Endpoint to converse with the Cloud FinOps AI Assistant about resource cost and optimization.
    """
    logger.info(f"Chat request received from user {user['user'].get('id')} with message length {len(payload.message)}")
    
    # Query database for all audited region records to provide multi-region summary context
    try:
        audit_history = await db_client.get_analysis_history(token=user["token"])
    except Exception as e:
        logger.warning(f"Failed to retrieve audit history for chat context: {str(e)}")
        audit_history = []

    try:
        response_text = await asyncio.to_thread(
            generate_chat_response,
            payload.message,
            [msg.model_dump() for msg in payload.history],
            payload.resources,
            payload.recommendations,
            audit_history
        )
        return {"response": response_text}
    except GeminiAPIException as e:
        await gemini_api_exception_handler(None, e)


class BudgetConfigRequest(BaseModel):
    threshold: float = Field(..., description="Monthly budget limit in USD")
    emails: List[str] = Field(default_factory=list, description="Notification email list")


async def run_scheduled_anomaly_scan():
    """Daily scheduled background scan task with distributed leader locking for multi-pod deployments."""
    logger.info("Checking distributed lock for daily scheduled cost anomaly scan...")
    acquired, lock_conn, db_type = database.acquire_advisory_lock(71705686)
    if not acquired:
        logger.info("Another replica pod is currently running the anomaly scan (lock active). Skipping.")
        return

    try:
        logger.info("Acquired scheduler lock. Running daily scheduled cost anomaly scan...")
        conn, db_type = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, threshold, slack_webhooks, emails FROM budget_configs")
        rows = cursor.fetchall()
        conn.close()
        
        for row in rows:
            user_id = row[0]
            threshold = row[1] if row[1] is not None else 1000.0
            emails = json.loads(row[3]) if row[3] else []
            
            if not emails:
                continue
                
            region = "us-east-1"
            spend_res = anomaly_detector.fetch_daily_spend(region, threshold=threshold)
            daily_costs = spend_res["daily_costs"]
            is_simulated = spend_res["is_simulated"]
            anomalies = anomaly_detector.detect_cost_anomalies(daily_costs)
            
            if not anomalies:
                continue
                
            latest_anomaly = anomalies[-1]
            anomaly_date = latest_anomaly['date']
            
            # Deduplicate
            conn_alert, alert_db_type = database.get_connection()
            cur_alert = conn_alert.cursor()
            param_placeholder = "%s" if alert_db_type == "postgres" else "?"
            cur_alert.execute(f"SELECT id FROM alert_logs WHERE user_id = {param_placeholder} AND date = {param_placeholder}", (user_id, anomaly_date))
            existing = cur_alert.fetchone()
            conn_alert.close()
            
            if existing:
                continue
                
            channels = emails
            notified_channels = await anomaly_detector.send_alert(latest_anomaly, channels, is_simulated=is_simulated)
            
            has_simulated = any("Simulated" in chan for chan in notified_channels)
            status_str = "success" if len(notified_channels) == len(channels) else "partial_failure"
            if has_simulated or is_simulated:
                status_str = "simulated"
            if not notified_channels:
                status_str = "failure"
                
            alert_id = str(uuid.uuid4())
            await db_client.save_alert_log(
                user_id=user_id,
                alert_id=alert_id,
                date=anomaly_date,
                details=latest_anomaly,
                status=status_str,
                channels=notified_channels
            )
            logger.info(f"Scheduled alert successfully processed for user {user_id} on date {anomaly_date}")
    except Exception as e:
        logger.error(f"Error in run_scheduled_anomaly_scan: {str(e)}")
    finally:
        database.release_advisory_lock(lock_conn, db_type, 71705686)


async def daily_anomaly_scanner_loop():
    logger.info("Starting daily anomaly scanner background scheduler loop")
    
    # Check if we should run an initial scan on startup
    try:
        conn, db_type = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT created_at FROM alert_logs ORDER BY created_at DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        
        should_run_now = True
        if row:
            last_run_str = row[0].rstrip('Z').split('.')[0]
            last_run = datetime.strptime(last_run_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - last_run < timedelta(hours=24):
                should_run_now = False
                logger.info(f"Last anomaly scan was run at {row[0]}, which is less than 24 hours ago. Skipping initial startup scan.")
        
        if should_run_now:
            logger.info("No recent scans found or last scan is older than 24 hours. Running startup anomaly scan.")
            await run_scheduled_anomaly_scan()
    except Exception as e:
        logger.error(f"Error checking last scan run on startup: {str(e)}")
        # Run anyway on error to be safe
        await run_scheduled_anomaly_scan()

    while True:
        try:
            # Calculate sleep seconds to align with UTC midnight
            now = datetime.now(timezone.utc)
            tomorrow = now + timedelta(days=1)
            next_midnight = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0, tzinfo=timezone.utc)
            sleep_seconds = (next_midnight - now).total_seconds()
            
            logger.info(f"Next scheduled anomaly scan in {sleep_seconds:.1f} seconds (at UTC midnight {next_midnight.strftime('%Y-%m-%d %H:%M:%S')})")
            await asyncio.sleep(sleep_seconds)
            await run_scheduled_anomaly_scan()
        except asyncio.CancelledError:
            logger.info("Daily anomaly scanner scheduler loop cancelled")
            break
        except Exception as e:
            logger.error(f"Error in anomaly scanner scheduler loop: {str(e)}")
            await asyncio.sleep(300)



@app.get("/api/budgets", status_code=status.HTTP_200_OK)
async def get_budgets(user: dict = Depends(get_current_user)):
    user_id = user["user"].get("id")
    config = await db_client.get_budget(user_id, token=user["token"])
    logs = await db_client.get_alert_history(user_id, token=user["token"])
    return {
        "config": config,
        "logs": logs
    }


@app.post("/api/budgets", status_code=status.HTTP_200_OK)
async def update_budgets(payload: BudgetConfigRequest, user: dict = Depends(get_current_user)):
    user_id = user["user"].get("id")
    await db_client.save_budget(
        user_id=user_id,
        threshold=payload.threshold,
        slack_webhooks=[],
        emails=payload.emails,
        token=user["token"]
    )
    return {"success": True, "message": "Budget configuration updated successfully."}


@app.get("/api/budgets/spend", status_code=status.HTTP_200_OK)
async def get_budgets_spend(region: str = "us-east-1", account_id: str | None = None, user: dict = Depends(get_current_user)):
    try:
        user_id = user["user"].get("id")
        user_org = get_user_org_id(user)
        config = await db_client.get_budget(user_id, token=user["token"])
        threshold = config.get("threshold", 1000.0)
        
        session = None
        if account_id:
            acc = database.get_cloud_account(account_id, org_id=user_org)
            if not acc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Cloud Account '{account_id}' not found or access denied."
                )
            if acc.get("status") == "expired":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Cloud Account access has expired on {acc.get('expires_at')}. Please refresh permissions."
                )
            session = get_assumed_role_session(acc["role_arn"], acc["external_id"])
        
        spend_res = anomaly_detector.fetch_daily_spend(region, threshold=threshold, session=session)
        daily_costs = spend_res["daily_costs"]
        is_simulated = spend_res["is_simulated"]
        anomalies = anomaly_detector.detect_cost_anomalies(daily_costs)
        
        spend_14 = daily_costs[-14:] if len(daily_costs) >= 14 else daily_costs
        spend_dates = {d['date'] for d in spend_14}
        anomalies_14 = [a for a in anomalies if a['date'] in spend_dates]
        
        return {
            "spend_data": spend_14,
            "anomalies": anomalies_14,
            "is_simulated": is_simulated
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in budgets spend endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "SPEND_DATA_FETCH_FAILED", "message": str(e)}
        )


@app.post("/api/budgets/trigger-scan", status_code=status.HTTP_200_OK)
async def trigger_budgets_scan(account_id: str | None = None, user: dict = Depends(get_current_user)):
    user_id = user["user"].get("id")
    user_org = get_user_org_id(user)
    region = "us-east-1"
    
    try:
        config = await db_client.get_budget(user_id, token=user["token"])
        threshold = config.get("threshold", 1000.0)
        emails = config.get("emails", [])
        channels = emails
        
        session = None
        if account_id:
            acc = database.get_cloud_account(account_id, org_id=user_org)
            if not acc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Cloud Account '{account_id}' not found or access denied."
                )
            if acc.get("status") == "expired":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Cloud Account access has expired on {acc.get('expires_at')}. Please refresh permissions."
                )
            session = get_assumed_role_session(acc["role_arn"], acc["external_id"])
        
        spend_res = anomaly_detector.fetch_daily_spend(region, threshold=threshold, session=session)
        daily_costs = spend_res["daily_costs"]
        is_simulated = spend_res["is_simulated"]
        anomalies = anomaly_detector.detect_cost_anomalies(daily_costs)
        
        if anomalies:
            latest_anomaly = anomalies[-1]
            notified_channels = await anomaly_detector.send_alert(latest_anomaly, channels, is_simulated=is_simulated)
            has_simulated = any("Simulated" in chan for chan in notified_channels)
            status_str = "success" if len(notified_channels) == len(channels) else "partial_failure"
            if has_simulated or is_simulated:
                status_str = "simulated"
            if not notified_channels:
                status_str = "failure"
                
            alert_id = str(uuid.uuid4())
            await db_client.save_alert_log(
                user_id=user_id,
                alert_id=alert_id,
                date=latest_anomaly['date'],
                details=latest_anomaly,
                status=status_str,
                channels=notified_channels,
                token=user["token"]
            )
            
            return {
                "success": True,
                "anomaly_found": True,
                "anomaly": latest_anomaly,
                "notified": notified_channels,
                "status": status_str,
                "message": f"Scan completed. Cost spike of ${latest_anomaly['amount']:.2f} detected on {latest_anomaly['date']}."
            }
        else:
            daily_base = max(5.0, threshold / 30.0)
            test_anomaly = {
                "date": datetime.now(timezone.utc).date().strftime('%Y-%m-%d'),
                "amount": round(daily_base * 2.2, 2),
                "average": round(daily_base, 2),
                "percent_increase": 120.0
            }
            
            notified_channels = await anomaly_detector.send_alert(test_anomaly, channels, is_test=True, is_simulated=is_simulated)
            has_simulated = any("Simulated" in chan for chan in notified_channels)
            status_str = "success" if len(notified_channels) == len(channels) else "partial_failure"
            if has_simulated or is_simulated:
                status_str = "simulated"
            if not notified_channels:
                status_str = "no_channels" if not channels else "failure"
                
            alert_id = str(uuid.uuid4())
            await db_client.save_alert_log(
                user_id=user_id,
                alert_id=alert_id,
                date=test_anomaly['date'],
                details=test_anomaly,
                status=status_str,
                channels=notified_channels,
                token=user["token"]
            )
            
            return {
                "success": True,
                "anomaly_found": False,
                "anomaly": test_anomaly,
                "notified": notified_channels,
                "status": status_str,
                "message": "No cost anomalies found in the past 14 days. Dispatched test alert to verify channels."
            }
            
    except Exception as e:
        logger.error(f"Error manually triggering budgets scan: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "TRIGGER_SCAN_FAILED", "message": str(e)}
        )


if __name__ == "__main__":
    import uvicorn
    env_mode = os.getenv("ENV", "prod").lower()
    should_reload = env_mode in ("dev", "development")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=should_reload)  # nosec B104
