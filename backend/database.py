import sqlite3
import json
import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger("database")

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "data", "db.sqlite3"))
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
_in_memory_holder = None

def get_connection():
    """Returns a database connection (PostgreSQL if DATABASE_URL set, else SQLite)."""
    global _in_memory_holder
    if DATABASE_URL:
        try:
            import psycopg2
            return psycopg2.connect(DATABASE_URL), "postgres"
        except Exception as e:
            logger.warning(f"Failed to connect to PostgreSQL via DATABASE_URL: {e}. Falling back to SQLite.")
    
    current_db_path = os.getenv("DB_PATH", DB_PATH)
    if current_db_path == ":memory:":
        if _in_memory_holder is None:
            _in_memory_holder = sqlite3.connect("file:cost_test_mem?mode=memory&cache=shared", uri=True)
        return sqlite3.connect("file:cost_test_mem?mode=memory&cache=shared", uri=True), "sqlite"

    db_dir = os.path.dirname(current_db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(current_db_path)
    return conn, "sqlite"

def check_db_health() -> bool:
    """Verifies database connectivity for readiness probe."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False

def init_db():
    """Initialize tables for budget configurations and alert logs."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        
        if db_type == "postgres":
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS organizations (
                id VARCHAR(255) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                created_at VARCHAR(255)
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS cloud_accounts (
                id VARCHAR(255) PRIMARY KEY,
                org_id VARCHAR(255) NOT NULL,
                account_alias VARCHAR(255),
                aws_account_id VARCHAR(255),
                role_arn VARCHAR(500) NOT NULL,
                external_id VARCHAR(255) NOT NULL,
                status VARCHAR(50) DEFAULT 'active',
                regions TEXT,
                created_at VARCHAR(255),
                last_scanned_at VARCHAR(255)
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS quarantine_items (
                id VARCHAR(255) PRIMARY KEY,
                org_id VARCHAR(255) NOT NULL,
                account_id VARCHAR(255),
                resource_id VARCHAR(255) NOT NULL,
                resource_type VARCHAR(100),
                region VARCHAR(100),
                reason TEXT,
                snapshot_id VARCHAR(255),
                quarantine_until VARCHAR(255),
                status VARCHAR(50) DEFAULT 'quarantined',
                created_at VARCHAR(255)
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS budget_configs (
                user_id VARCHAR(255) PRIMARY KEY,
                threshold DOUBLE PRECISION,
                slack_webhooks TEXT,
                emails TEXT,
                updated_at VARCHAR(255)
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS alert_logs (
                id VARCHAR(255) PRIMARY KEY,
                user_id VARCHAR(255),
                date VARCHAR(255),
                details TEXT,
                status VARCHAR(100),
                channels TEXT,
                created_at VARCHAR(255)
            );
            """)
        else:
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS organizations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS cloud_accounts (
                id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL,
                account_alias TEXT,
                aws_account_id TEXT,
                role_arn TEXT NOT NULL,
                external_id TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                regions TEXT,
                created_at TEXT,
                last_scanned_at TEXT
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS quarantine_items (
                id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL,
                account_id TEXT,
                resource_id TEXT NOT NULL,
                resource_type TEXT,
                region TEXT,
                reason TEXT,
                snapshot_id TEXT,
                quarantine_until TEXT,
                status TEXT DEFAULT 'quarantined',
                created_at TEXT
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS budget_configs (
                user_id TEXT PRIMARY KEY,
                threshold REAL,
                slack_webhooks TEXT,
                emails TEXT,
                updated_at TEXT
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS alert_logs (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                date TEXT,
                details TEXT,
                status TEXT,
                channels TEXT,
                created_at TEXT
            )
            """)
        
        conn.commit()
        conn.close()
        logger.info(f"Database initialized using engine: {db_type}")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")

def get_budget_config(user_id: str) -> dict:
    """Retrieve budget and alert configurations for a user."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        param_placeholder = "%s" if db_type == "postgres" else "?"
        cursor.execute(
            f"SELECT threshold, slack_webhooks, emails FROM budget_configs WHERE user_id = {param_placeholder}",
            (user_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "threshold": row[0],
                "slack_webhooks": json.loads(row[1]) if row[1] else [],
                "emails": json.loads(row[2]) if row[2] else []
            }
    except Exception as e:
        logger.error(f"Error fetching budget config for user {user_id}: {str(e)}")
        
    return {
        "threshold": 1000.0,
        "slack_webhooks": [],
        "emails": []
    }

def save_budget_config(user_id: str, threshold: float, slack_webhooks: list, emails: list):
    """Save or update budget and alert configurations for a user."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        now_str = datetime.now(timezone.utc).isoformat()
        
        if db_type == "postgres":
            query = """
            INSERT INTO budget_configs (user_id, threshold, slack_webhooks, emails, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT(user_id) DO UPDATE SET
                threshold = EXCLUDED.threshold,
                slack_webhooks = EXCLUDED.slack_webhooks,
                emails = EXCLUDED.emails,
                updated_at = EXCLUDED.updated_at
            """
            cursor.execute(query, (user_id, threshold, json.dumps(slack_webhooks), json.dumps(emails), now_str))
        else:
            query = """
            INSERT INTO budget_configs (user_id, threshold, slack_webhooks, emails, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                threshold = excluded.threshold,
                slack_webhooks = excluded.slack_webhooks,
                emails = excluded.emails,
                updated_at = excluded.updated_at
            """
            cursor.execute(query, (user_id, threshold, json.dumps(slack_webhooks), json.dumps(emails), now_str))
            
        conn.commit()
        conn.close()
        logger.info(f"Saved budget config for user {user_id}")
    except Exception as e:
        logger.error(f"Error saving budget config for user {user_id}: {str(e)}")
        raise e

def get_alert_logs(user_id: str) -> list:
    """Retrieve historical alert log records for a user."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        param_placeholder = "%s" if db_type == "postgres" else "?"
        cursor.execute(
            f"SELECT id, date, details, status, channels, created_at FROM alert_logs WHERE user_id = {param_placeholder} ORDER BY created_at DESC",
            (user_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        logs = []
        for row in rows:
            logs.append({
                "id": row[0],
                "date": row[1],
                "details": json.loads(row[2]) if row[2] else {},
                "status": row[3],
                "channels": json.loads(row[4]) if row[4] else [],
                "created_at": row[5]
            })
        return logs
    except Exception as e:
        logger.error(f"Error fetching alert logs for user {user_id}: {str(e)}")
        return []

def save_alert_log(user_id: str, alert_id: str, date: str, details: dict, status: str, channels: list):
    """Log an alert execution to database history."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        now_str = datetime.now(timezone.utc).isoformat()
        param_placeholder = "%s" if db_type == "postgres" else "?"
        
        query = f"""
        INSERT INTO alert_logs (id, user_id, date, details, status, channels, created_at)
        VALUES ({param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder})
        """
        cursor.execute(query, (alert_id, user_id, date, json.dumps(details), status, json.dumps(channels), now_str))
        conn.commit()
        conn.close()
        logger.info(f"Saved alert log {alert_id} for user {user_id}")
    except Exception as e:
        logger.error(f"Error saving alert log for user {user_id}: {str(e)}")
        raise e

# --- Multi-Tenant Cloud Accounts Management ---

def save_cloud_account(account_id: str, org_id: str, account_alias: str, aws_account_id: str, role_arn: str, external_id: str, regions: list = None, status: str = "active") -> dict:
    """Save or update a connected AWS Cloud Account with its STS AssumeRole ARN and External ID."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        now_str = datetime.now(timezone.utc).isoformat()
        regions_json = json.dumps(regions or ["us-east-1", "us-east-2", "us-west-2", "eu-west-1"])

        if db_type == "postgres":
            query = """
            INSERT INTO cloud_accounts (id, org_id, account_alias, aws_account_id, role_arn, external_id, status, regions, created_at, last_scanned_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
            ON CONFLICT(id) DO UPDATE SET
                account_alias = EXCLUDED.account_alias,
                aws_account_id = EXCLUDED.aws_account_id,
                role_arn = EXCLUDED.role_arn,
                external_id = EXCLUDED.external_id,
                status = EXCLUDED.status,
                regions = EXCLUDED.regions
            """
            cursor.execute(query, (account_id, org_id, account_alias, aws_account_id, role_arn, external_id, status, regions_json, now_str))
        else:
            query = """
            INSERT INTO cloud_accounts (id, org_id, account_alias, aws_account_id, role_arn, external_id, status, regions, created_at, last_scanned_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(id) DO UPDATE SET
                account_alias = excluded.account_alias,
                aws_account_id = excluded.aws_account_id,
                role_arn = excluded.role_arn,
                external_id = excluded.external_id,
                status = excluded.status,
                regions = excluded.regions
            """
            cursor.execute(query, (account_id, org_id, account_alias, aws_account_id, role_arn, external_id, status, regions_json, now_str))

        conn.commit()
        conn.close()
        return {
            "id": account_id,
            "org_id": org_id,
            "account_alias": account_alias,
            "aws_account_id": aws_account_id,
            "role_arn": role_arn,
            "external_id": external_id,
            "status": status,
            "regions": json.loads(regions_json),
            "created_at": now_str
        }
    except Exception as e:
        logger.error(f"Error saving cloud account {account_id}: {e}")
        raise e

def list_cloud_accounts(org_id: str = "default_org") -> list:
    """Retrieve all connected cloud accounts for an organization."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        param_placeholder = "%s" if db_type == "postgres" else "?"
        cursor.execute(
            f"SELECT id, org_id, account_alias, aws_account_id, role_arn, external_id, status, regions, created_at, last_scanned_at FROM cloud_accounts WHERE org_id = {param_placeholder} ORDER BY created_at DESC",
            (org_id,)
        )
        rows = cursor.fetchall()
        conn.close()

        accounts = []
        for r in rows:
            accounts.append({
                "id": r[0],
                "org_id": r[1],
                "account_alias": r[2],
                "aws_account_id": r[3],
                "role_arn": r[4],
                "external_id": r[5],
                "status": r[6],
                "regions": json.loads(r[7]) if r[7] else [],
                "created_at": r[8],
                "last_scanned_at": r[9]
            })
        return accounts
    except Exception as e:
        logger.error(f"Error listing cloud accounts for org {org_id}: {e}")
        return []

def get_cloud_account(account_id: str, org_id: str = None) -> dict | None:
    """Retrieve single cloud account by ID. If org_id is provided, checks org ownership."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        param_placeholder = "%s" if db_type == "postgres" else "?"
        if org_id:
            cursor.execute(
                f"SELECT id, org_id, account_alias, aws_account_id, role_arn, external_id, status, regions, created_at, last_scanned_at FROM cloud_accounts WHERE id = {param_placeholder} AND org_id = {param_placeholder}",
                (account_id, org_id)
            )
        else:
            cursor.execute(
                f"SELECT id, org_id, account_alias, aws_account_id, role_arn, external_id, status, regions, created_at, last_scanned_at FROM cloud_accounts WHERE id = {param_placeholder}",
                (account_id,)
            )
        r = cursor.fetchone()
        conn.close()
        if r:
            return {
                "id": r[0],
                "org_id": r[1],
                "account_alias": r[2],
                "aws_account_id": r[3],
                "role_arn": r[4],
                "external_id": r[5],
                "status": r[6],
                "regions": json.loads(r[7]) if r[7] else [],
                "created_at": r[8],
                "last_scanned_at": r[9]
            }
        return None
    except Exception as e:
        logger.error(f"Error fetching cloud account {account_id}: {e}")
        return None

def update_cloud_account_last_scanned(account_id: str):
    """Updates the last_scanned_at timestamp for a cloud account."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        now_str = datetime.now(timezone.utc).isoformat()
        param_placeholder = "%s" if db_type == "postgres" else "?"
        cursor.execute(
            f"UPDATE cloud_accounts SET last_scanned_at = {param_placeholder} WHERE id = {param_placeholder}",
            (now_str, account_id)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error updating last_scanned for account {account_id}: {e}")

def delete_cloud_account(account_id: str, org_id: str = None) -> bool:
    """Delete a connected cloud account."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        param_placeholder = "%s" if db_type == "postgres" else "?"
        if org_id:
            cursor.execute(
                f"DELETE FROM cloud_accounts WHERE id = {param_placeholder} AND org_id = {param_placeholder}",
                (account_id, org_id)
            )
        else:
            cursor.execute(
                f"DELETE FROM cloud_accounts WHERE id = {param_placeholder}",
                (account_id,)
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error deleting cloud account {account_id}: {e}")
        return False

# --- Tag-and-Wait Quarantine & Safe Deletion Management ---

def save_quarantine_item(item_id: str, org_id: str, account_id: str, resource_id: str, resource_type: str, region: str, reason: str, quarantine_days: int = 7, snapshot_id: str = None) -> dict:
    """Register an orphaned/idle resource into quarantine with an expiry date."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        expiry = (now + timedelta(days=quarantine_days)).isoformat()
        now_str = now.isoformat()
        param_placeholder = "%s" if db_type == "postgres" else "?"

        query = f"""
        INSERT INTO quarantine_items (id, org_id, account_id, resource_id, resource_type, region, reason, snapshot_id, quarantine_until, status, created_at)
        VALUES ({param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder})
        """
        cursor.execute(query, (item_id, org_id, account_id, resource_id, resource_type, region, reason, snapshot_id, expiry, "quarantined", now_str))
        conn.commit()
        conn.close()
        return {
            "id": item_id,
            "org_id": org_id,
            "account_id": account_id,
            "resource_id": resource_id,
            "resource_type": resource_type,
            "region": region,
            "reason": reason,
            "snapshot_id": snapshot_id,
            "quarantine_until": expiry,
            "status": "quarantined",
            "created_at": now_str
        }
    except Exception as e:
        logger.error(f"Error saving quarantine item {resource_id}: {e}")
        raise e

def list_quarantine_items(org_id: str = "default_org", status_filter: str = None) -> list:
    """List quarantine items for an organization, optionally filtering by status."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        param_placeholder = "%s" if db_type == "postgres" else "?"
        
        if status_filter:
            cursor.execute(
                f"SELECT id, org_id, account_id, resource_id, resource_type, region, reason, snapshot_id, quarantine_until, status, created_at FROM quarantine_items WHERE org_id = {param_placeholder} AND status = {param_placeholder} ORDER BY created_at DESC",
                (org_id, status_filter)
            )
        else:
            cursor.execute(
                f"SELECT id, org_id, account_id, resource_id, resource_type, region, reason, snapshot_id, quarantine_until, status, created_at FROM quarantine_items WHERE org_id = {param_placeholder} ORDER BY created_at DESC",
                (org_id,)
            )
        rows = cursor.fetchall()
        conn.close()

        items = []
        for r in rows:
            items.append({
                "id": r[0],
                "org_id": r[1],
                "account_id": r[2],
                "resource_id": r[3],
                "resource_type": r[4],
                "region": r[5],
                "reason": r[6],
                "snapshot_id": r[7],
                "quarantine_until": r[8],
                "status": r[9],
                "created_at": r[10]
            })
        return items
    except Exception as e:
        logger.error(f"Error listing quarantine items: {e}")
        return []

def update_quarantine_status(item_id: str, status: str, snapshot_id: str = None, org_id: str = "default_org") -> bool:
    """Update status of a quarantine item ('dismissed', 'deleted', 'restored')."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        param_placeholder = "%s" if db_type == "postgres" else "?"

        if snapshot_id:
            cursor.execute(
                f"UPDATE quarantine_items SET status = {param_placeholder}, snapshot_id = {param_placeholder} WHERE id = {param_placeholder} AND org_id = {param_placeholder}",
                (status, snapshot_id, item_id, org_id)
            )
        else:
            cursor.execute(
                f"UPDATE quarantine_items SET status = {param_placeholder} WHERE id = {param_placeholder} AND org_id = {param_placeholder}",
                (status, item_id, org_id)
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error updating quarantine status for {item_id}: {e}")
        return False

