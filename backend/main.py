import os
import logging
import uuid
import asyncio
import json
from datetime import datetime
from typing import Dict, List, Literal
import httpx
from fastapi import FastAPI, HTTPException, status, WebSocket, WebSocketDisconnect, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from aws_scanner import (
    list_aws_regions,
    scan_all_resources,
    execute_remediation,
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

db_client = InsForgeClient()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

# Initialize FastAPI application
app = FastAPI(
    title="AI Cloud Cost Detective Backend",
    description="FastAPI Backend for querying AWS infrastructure cost data",
    version="1.0.0"
)

# Configure CORS
origins = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define request/response models
class AnalyzeRequest(BaseModel):
    region: str = Field(..., description="The AWS region to scan, e.g., 'us-east-1'")
    analysis_id: str | None = Field(None, description="Optional UUID to track progress via WebSockets")

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
            self.active_connections[analysis_id].remove(websocket)
            if not self.active_connections[analysis_id]:
                del self.active_connections[analysis_id]
        logger.info(f"WebSocket client disconnected from progress stream for analysis_id: {analysis_id}")

    async def broadcast(self, analysis_id: str, message: str):
        if analysis_id in self.active_connections:
            logger.info(f"Broadcasting to {analysis_id}: {message}")
            for connection in self.active_connections[analysis_id]:
                try:
                    await connection.send_text(message)
                except Exception as e:
                    logger.error(f"Error sending message down socket: {e}")

manager = ConnectionManager()

async def get_current_user(authorization: str = Header(..., description="InsForge JWT Authorization Header")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "INVALID_TOKEN_FORMAT", "message": "Authorization header must be Bearer <token>"}
        )
    token = authorization.split(" ")[1]
    
    project_url = os.environ.get("INSFORGE_PROJECT_URL")
    anon_key = os.environ.get("INSFORGE_ANON_KEY")
    if not project_url or not anon_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "AUTH_CONFIG_ERROR", "message": "InsForge URL or Anon Key is not set on the server"}
        )
        
    url = f"{project_url.rstrip('/')}/api/auth/sessions/current"
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {token}"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=10.0)
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"error": "UNAUTHORIZED", "message": "Invalid or expired session token"}
                )
            return {
                "user": response.json().get("user"),
                "token": token
            }
        except httpx.RequestError as e:
            logger.exception("Error calling InsForge Auth")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"error": "AUTH_SERVICE_UNAVAILABLE", "message": f"Could not connect to authentication service: {str(e)}"}
            )
    

@app.get("/api/regions", status_code=status.HTTP_200_OK)
async def get_regions():
    """
    Retrieve a list of active AWS regions.
    Raises 401/400/429/500 if the AWS API calls fail.
    """
    logger.info("Fetching active AWS regions")
    try:
        regions = list_aws_regions()
        return {"regions": regions}
    except AWSCredentialException as e:
        await credential_exception_handler(None, e)
    except AWSRegionException as e:
        await region_exception_handler(None, e)
    except AWSRateLimitException as e:
        await rate_limit_exception_handler(None, e)
    except AWSScanException as e:
        await scan_exception_handler(None, e)


@app.websocket("/ws/progress/{analysis_id}")
async def websocket_endpoint(websocket: WebSocket, analysis_id: str):
    await manager.connect(websocket, analysis_id)
    try:
        # Keep connection open. WebSockets expect us to read from them or wait
        while True:
            # Just receive text to keep the socket alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, analysis_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
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
async def analyze_region(payload: AnalyzeRequest, user: dict = Depends(get_current_user)):
    """
    Scan active cost-driving AWS resources in the specified region, perform AI-powered cost analysis,
    and persist results to InsForge Database. Progress is streamed via WebSockets.
    Accepts: { "region": "<region_name>", "analysis_id": "<uuid>" }
    """
    region = payload.region.strip()
    if not region:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Region parameter cannot be empty."
        )
        
    analysis_id = payload.analysis_id or str(uuid.uuid4())
    logger.info(f"Initiating resource scan for region: {region} with analysis_id: {analysis_id}")
    
    try:
        # Step 1: Initializing clients
        await manager.broadcast(analysis_id, "Initializing AWS clients...")
        await db_client.create_analysis(analysis_id, region, token=user["token"])
        
        # Step 2: Scanning resources
        await manager.broadcast(analysis_id, f"Scanning EC2, EBS, and RDS resources in {region}...")
        resources = scan_all_resources(region)
        
        # Step 3: AI analysis
        await manager.broadcast(analysis_id, "Generating structured cost analysis via Gemini AI...")
        analysis = analyze_costs(resources)
        
        # Step 4: Persisting results
        await manager.broadcast(analysis_id, "Persisting audit metrics to InsForge Cloud...")
        
        issues_found = len(analysis.get('recommendations', []))
        total_savings = sum(item.get('estimated_savings', 0.0) for item in analysis.get('recommendations', []))
        estimated_savings = f"${total_savings:.2f}"
        
        await db_client.update_analysis_success(
            analysis_id=analysis_id,
            resources_scanned=len(resources),
            issues_found=issues_found,
            estimated_savings=estimated_savings,
            analysis_result=analysis,
            token=user["token"]
        )
        
        # Step 5: Complete
        await manager.broadcast(analysis_id, "Analysis complete")
        
        return {
            "analysis_id": analysis_id,
            "region": region,
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


class RemediateRequest(BaseModel):
    analysis_id: str = Field(..., description="The ID of the cost analysis record")
    resource_id: str = Field(..., description="The ID of the target resource to remediate")
    issue_type: str = Field(..., description="The cost optimization issue type")
    region: str = Field(..., description="The AWS region of the target resource")


@app.post("/api/remediate", status_code=status.HTTP_200_OK)
async def remediate_resource(payload: RemediateRequest, user: dict = Depends(get_current_user)):
    """
    Executes cost-saving remediation for a specific resource, updates the database log,
    and returns the execution status.
    """
    logger.info(f"Remediation request received for resource {payload.resource_id} under analysis {payload.analysis_id}")
    
    # 1. Execute the remediation via boto3 (run in threadpool to avoid blocking event loop)
    try:
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
    
    # 2. Retrieve analysis record
    record = await db_client.get_analysis(payload.analysis_id, token=user["token"])
    analysis_result = record.get("analysis_result")
    if not analysis_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "ANALYSIS_RESULT_NOT_FOUND",
                "message": "No analysis result found for this audit log."
            }
        )
        
    recommendations = analysis_result.get("recommendations", [])
    found = False
    for rec in recommendations:
        if rec.get("resource_id") == payload.resource_id:
            rec["remediated"] = True
            rec["remediated_at"] = datetime.utcnow().isoformat() + "Z"
            found = True
            break
            
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "RESOURCE_NOT_FOUND_IN_ANALYSIS",
                "message": f"Resource {payload.resource_id} not found in the recommendations list."
            }
        )
        
    # 3. Patch the updated analysis_result back to the database
    await db_client.update_analysis_result(payload.analysis_id, analysis_result, token=user["token"])
    
    return {
        "success": True,
        "message": result.get("message", "Remediation executed successfully."),
        "resource_id": payload.resource_id,
        "remediated_at": datetime.utcnow().isoformat() + "Z"
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
async def chat_with_finops_assistant(payload: ChatRequest, user: dict = Depends(get_current_user)):
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


@app.on_event("startup")
async def startup_event():
    database.init_db()
    asyncio.create_task(daily_anomaly_scanner_loop())


async def run_scheduled_anomaly_scan():
    """Daily scheduled background scan task."""
    logger.info("Running daily scheduled cost anomaly scan...")
    import sqlite3
    try:
        conn = sqlite3.connect(database.DB_PATH)
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
            conn_alert = sqlite3.connect(database.DB_PATH)
            cur_alert = conn_alert.cursor()
            cur_alert.execute("SELECT id FROM alert_logs WHERE user_id = ? AND date = ?", (user_id, anomaly_date))
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


async def daily_anomaly_scanner_loop():
    logger.info("Starting daily anomaly scanner background scheduler loop")
    while True:
        try:
            await asyncio.sleep(24 * 60 * 60)
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
async def get_budgets_spend(region: str = "us-east-1", user: dict = Depends(get_current_user)):
    try:
        user_id = user["user"].get("id")
        config = await db_client.get_budget(user_id, token=user["token"])
        threshold = config.get("threshold", 1000.0)
        
        spend_res = anomaly_detector.fetch_daily_spend(region, threshold=threshold)
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
    except Exception as e:
        logger.error(f"Error in budgets spend endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "SPEND_DATA_FETCH_FAILED", "message": str(e)}
        )


@app.post("/api/budgets/trigger-scan", status_code=status.HTTP_200_OK)
async def trigger_budgets_scan(user: dict = Depends(get_current_user)):
    user_id = user["user"].get("id")
    region = "us-east-1"
    
    try:
        config = await db_client.get_budget(user_id, token=user["token"])
        threshold = config.get("threshold", 1000.0)
        emails = config.get("emails", [])
        channels = emails
        
        spend_res = anomaly_detector.fetch_daily_spend(region, threshold=threshold)
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
                "date": datetime.utcnow().date().strftime('%Y-%m-%d'),
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
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)  # nosec B104
