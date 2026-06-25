import os
import logging
from datetime import datetime
import httpx
import database

logger = logging.getLogger("insforge_client")

class InsForgeException(Exception):
    """Custom exception for InsForge integration errors."""
    pass

class InsForgeClient:
    def __init__(self):
        self.project_url = os.environ.get("INSFORGE_PROJECT_URL")
        self.anon_key = os.environ.get("INSFORGE_ANON_KEY")
        
        # Normalize trailing slash in URL
        if self.project_url:
            self.project_url = self.project_url.rstrip('/')
            
        self.enabled = bool(self.project_url and self.anon_key)
        if not self.enabled:
            logger.warning(
                "InsForge connection variables (INSFORGE_PROJECT_URL, INSFORGE_ANON_KEY) "
                "are missing. DB logging is disabled."
            )

    def _get_headers(self, token: str = None, with_prefer: str = None) -> dict:
        if not self.enabled:
            raise InsForgeException("InsForge client is not configured. Check your environment variables.")
        auth_token = token if token else self.anon_key
        headers = {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
        if with_prefer:
            headers["Prefer"] = with_prefer
        return headers

    async def create_analysis(self, analysis_id: str, region: str, token: str = None) -> None:
        """Create a new cost analysis log record with status='running'."""
        if not self.enabled:
            logger.info(f"Skipping InsForge logging (disabled) for analysis: {analysis_id}")
            return

        url = f"{self.project_url}/api/database/records/analyses"
        payload = {
            "id": analysis_id,
            "region": region,
            "resources_scanned": 0,
            "issues_found": 0,
            "estimated_savings": "$0.00",
            "status": "running",
            "created_at": datetime.utcnow().isoformat() + "Z"
        }

        async with httpx.AsyncClient() as client:
            try:
                logger.info(f"Writing initial analysis log {analysis_id} to InsForge")
                # Using Prefer: resolution=merge-duplicates to upsert/insert cleanly
                headers = self._get_headers(token=token, with_prefer="resolution=merge-duplicates")
                response = await client.post(url, json=payload, headers=headers, timeout=10.0)
                
                # Check response. PostgREST returns 201 Created on successful insert
                if response.status_code not in (200, 201):
                    logger.error(f"Failed to create analysis in InsForge: {response.status_code} - {response.text}")
                    raise InsForgeException(f"InsForge DB error (status {response.status_code}): {response.text}")
            except Exception as e:
                logger.error(f"Error connecting to InsForge: {str(e)}")
                if isinstance(e, InsForgeException):
                    raise e
                raise InsForgeException(f"Failed to communicate with InsForge: {str(e)}") from e

    async def update_analysis_success(
        self,
        analysis_id: str,
        resources_scanned: int,
        issues_found: int,
        estimated_savings: str,
        analysis_result: dict,
        token: str = None
    ) -> None:
        """Update analysis log to 'completed' with resource counts, savings, and JSON results."""
        if not self.enabled:
            return

        url = f"{self.project_url}/api/database/records/analyses?id=eq.{analysis_id}"
        payload = {
            "resources_scanned": resources_scanned,
            "issues_found": issues_found,
            "estimated_savings": estimated_savings,
            "analysis_result": analysis_result,
            "status": "completed"
        }

        async with httpx.AsyncClient() as client:
            try:
                logger.info(f"Updating analysis log {analysis_id} status to COMPLETED")
                headers = self._get_headers(token=token, with_prefer="return=minimal")
                response = await client.patch(url, json=payload, headers=headers, timeout=10.0)
                
                if response.status_code not in (200, 204):
                    logger.error(f"Failed to update analysis in InsForge: {response.status_code} - {response.text}")
                    raise InsForgeException(f"InsForge DB update failed (status {response.status_code}): {response.text}")
            except Exception as e:
                logger.error(f"Error updating InsForge record: {str(e)}")
                if isinstance(e, InsForgeException):
                    raise e
                raise InsForgeException(f"Failed to update database record in InsForge: {str(e)}") from e

    async def update_analysis_failure(self, analysis_id: str, token: str = None) -> None:
        """Update analysis status to 'failed' on error."""
        if not self.enabled:
            return

        url = f"{self.project_url}/api/database/records/analyses?id=eq.{analysis_id}"
        payload = {
            "status": "failed"
        }

        async with httpx.AsyncClient() as client:
            try:
                logger.info(f"Updating analysis log {analysis_id} status to FAILED")
                headers = self._get_headers(token=token, with_prefer="return=minimal")
                response = await client.patch(url, json=payload, headers=headers, timeout=10.0)
                
                if response.status_code not in (200, 204):
                    logger.error(f"Failed to fail analysis in InsForge: {response.status_code} - {response.text}")
            except Exception as e:
                logger.error(f"Error reporting failure to InsForge: {str(e)}")

    async def get_analysis_history(self, token: str = None) -> list:
        """Retrieve audit history from the database, sorted by date descending."""
        if not self.enabled:
            raise InsForgeException("InsForge is not configured. Check your environment variables.")

        url = f"{self.project_url}/api/database/records/analyses"
        params = {
            "select": "*",
            "order": "created_at.desc"
        }

        async with httpx.AsyncClient() as client:
            try:
                logger.info("Fetching analysis history from InsForge DB")
                headers = self._get_headers(token=token)
                response = await client.get(url, params=params, headers=headers, timeout=10.0)
                
                if response.status_code != 200:
                    logger.error(f"Failed to fetch history from InsForge: {response.status_code} - {response.text}")
                    raise InsForgeException(f"InsForge history query failed (status {response.status_code}): {response.text}")
                
                return response.json()
            except Exception as e:
                logger.error(f"Error querying history from InsForge: {str(e)}")
                if isinstance(e, InsForgeException):
                    raise e
                raise InsForgeException(f"Failed to query history from InsForge: {str(e)}") from e

    async def get_analysis(self, analysis_id: str, token: str = None) -> dict:
        """Retrieve a specific analysis log record by ID."""
        if not self.enabled:
            raise InsForgeException("InsForge client is not configured. Check your environment variables.")

        url = f"{self.project_url}/api/database/records/analyses"
        params = {
            "id": f"eq.{analysis_id}"
        }

        async with httpx.AsyncClient() as client:
            try:
                logger.info(f"Fetching analysis record {analysis_id} from InsForge")
                headers = self._get_headers(token=token)
                response = await client.get(url, params=params, headers=headers, timeout=10.0)
                
                if response.status_code != 200:
                    logger.error(f"Failed to fetch analysis from InsForge: {response.status_code} - {response.text}")
                    raise InsForgeException(f"InsForge query failed (status {response.status_code}): {response.text}")
                
                records = response.json()
                if not records:
                    raise InsForgeException(f"Analysis record with ID {analysis_id} not found.")
                return records[0]
            except Exception as e:
                logger.error(f"Error querying analysis {analysis_id} from InsForge: {str(e)}")
                if isinstance(e, InsForgeException):
                    raise e
                raise InsForgeException(f"Failed to query analysis from InsForge: {str(e)}") from e

    async def update_analysis_result(self, analysis_id: str, analysis_result: dict, token: str = None) -> None:
        """Update only the analysis_result JSON field of a specific analysis record."""
        if not self.enabled:
            return

        url = f"{self.project_url}/api/database/records/analyses?id=eq.{analysis_id}"
        payload = {
            "analysis_result": analysis_result
        }

        async with httpx.AsyncClient() as client:
            try:
                logger.info(f"Updating analysis_result for record {analysis_id}")
                headers = self._get_headers(token=token, with_prefer="return=minimal")
                response = await client.patch(url, json=payload, headers=headers, timeout=10.0)
                
                if response.status_code not in (200, 204):
                    logger.error(f"Failed to update analysis_result in InsForge: {response.status_code} - {response.text}")
                    raise InsForgeException(f"InsForge DB update failed (status {response.status_code}): {response.text}")
            except Exception as e:
                logger.error(f"Error updating analysis_result: {str(e)}")
                if isinstance(e, InsForgeException):
                    raise e
                raise InsForgeException(f"Failed to update database record in InsForge: {str(e)}") from e

    async def get_budget(self, user_id: str, token: str = None) -> dict:
        """Fetch budget and alert channels config. Fall back to local SQLite if relation doesn't exist."""
        if not self.enabled:
            return database.get_budget_config(user_id)

        url = f"{self.project_url}/api/database/records/budgets"
        params = {"user_id": f"eq.{user_id}"}
        
        async with httpx.AsyncClient() as client:
            try:
                logger.info(f"Fetching budget config for user {user_id} from InsForge")
                headers = self._get_headers(token=token)
                response = await client.get(url, params=params, headers=headers, timeout=10.0)
                
                if response.status_code == 200:
                    records = response.json()
                    if records:
                        rec = records[0]
                        # Parse potentially JSON-stringified arrays from database
                        slack = rec.get("slack_webhooks", [])
                        emails = rec.get("emails", [])
                        if isinstance(slack, str):
                            import json
                            slack = json.loads(slack)
                        if isinstance(emails, str):
                            import json
                            emails = json.loads(emails)
                        return {
                            "threshold": float(rec.get("threshold", 1000.0)),
                            "slack_webhooks": slack,
                            "emails": emails
                        }
                    else:
                        # Return defaults if user has no saved record yet
                        return {"threshold": 1000.0, "slack_webhooks": [], "emails": []}
                elif response.status_code == 404 and "public.budgets" in response.text:
                    logger.warning("InsForge 'budgets' table not found (404 relation). Falling back to local SQLite.")
                    return database.get_budget_config(user_id)
                else:
                    logger.warning(f"InsForge budgets query returned status {response.status_code}. Falling back to local SQLite.")
                    return database.get_budget_config(user_id)
            except Exception as e:
                logger.warning(f"Error querying InsForge budgets: {str(e)}. Falling back to local SQLite.")
                return database.get_budget_config(user_id)

    async def save_budget(self, user_id: str, threshold: float, slack_webhooks: list, emails: list, token: str = None) -> None:
        """Save budget configuration. Fall back to local SQLite on database error."""
        # Always update local SQLite as a local backup
        database.save_budget_config(user_id, threshold, slack_webhooks, emails)

        if not self.enabled:
            return

        url = f"{self.project_url}/api/database/records/budgets"
        payload = {
            "user_id": user_id,
            "threshold": threshold,
            "slack_webhooks": slack_webhooks,
            "emails": emails,
            "updated_at": datetime.utcnow().isoformat() + "Z"
        }

        async with httpx.AsyncClient() as client:
            try:
                logger.info(f"Upserting budget config for user {user_id} to InsForge")
                headers = self._get_headers(token=token, with_prefer="resolution=merge-duplicates")
                response = await client.post(url, json=payload, headers=headers, timeout=10.0)
                
                if response.status_code not in (200, 201):
                    logger.warning(f"InsForge budget save returned status {response.status_code}. Fallback active.")
            except Exception as e:
                logger.warning(f"Error saving budget to InsForge: {str(e)}. Fallback active.")

    async def get_alert_history(self, user_id: str, token: str = None) -> list:
        """Fetch alert logs history. Fall back to local SQLite if relation doesn't exist."""
        if not self.enabled:
            return database.get_alert_logs(user_id)

        url = f"{self.project_url}/api/database/records/alert_logs"
        params = {
            "user_id": f"eq.{user_id}",
            "order": "created_at.desc"
        }
        
        async with httpx.AsyncClient() as client:
            try:
                logger.info(f"Fetching alert history for user {user_id} from InsForge")
                headers = self._get_headers(token=token)
                response = await client.get(url, params=params, headers=headers, timeout=10.0)
                
                if response.status_code == 200:
                    records = response.json()
                    parsed_records = []
                    for rec in records:
                        details = rec.get("details", {})
                        channels = rec.get("channels", [])
                        if isinstance(details, str):
                            import json
                            details = json.loads(details)
                        if isinstance(channels, str):
                            import json
                            channels = json.loads(channels)
                        parsed_records.append({
                            "id": rec.get("id"),
                            "date": rec.get("date"),
                            "details": details,
                            "status": rec.get("status"),
                            "channels": channels,
                            "created_at": rec.get("created_at")
                        })
                    return parsed_records
                elif response.status_code == 404 and "public.alert_logs" in response.text:
                    logger.warning("InsForge 'alert_logs' table not found (404 relation). Falling back to local SQLite.")
                    return database.get_alert_logs(user_id)
                else:
                    logger.warning(f"InsForge alert logs query returned status {response.status_code}. Falling back to local SQLite.")
                    return database.get_alert_logs(user_id)
            except Exception as e:
                logger.warning(f"Error querying InsForge alert logs: {str(e)}. Falling back to local SQLite.")
                return database.get_alert_logs(user_id)

    async def save_alert_log(self, user_id: str, alert_id: str, date: str, details: dict, status: str, channels: list, token: str = None) -> None:
        """Log an alert execution to database history. Fall back to local SQLite on error."""
        # Always log to local SQLite as a local backup
        database.save_alert_log(user_id, alert_id, date, details, status, channels)

        if not self.enabled:
            return

        url = f"{self.project_url}/api/database/records/alert_logs"
        payload = {
            "id": alert_id,
            "user_id": user_id,
            "date": date,
            "details": details,
            "status": status,
            "channels": channels,
            "created_at": datetime.utcnow().isoformat() + "Z"
        }

        async with httpx.AsyncClient() as client:
            try:
                logger.info(f"Writing alert log {alert_id} to InsForge")
                headers = self._get_headers(token=token, with_prefer="resolution=merge-duplicates")
                response = await client.post(url, json=payload, headers=headers, timeout=10.0)
                
                if response.status_code not in (200, 201):
                    logger.warning(f"InsForge alert log save returned status {response.status_code}. Fallback active.")
            except Exception as e:
                logger.warning(f"Error writing alert log to InsForge: {str(e)}. Fallback active.")
