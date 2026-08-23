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
    conn = sqlite3.connect(current_db_path, timeout=30.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
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

def acquire_advisory_lock(lock_id: int = 71705686):
    """
    Acquires a cluster-wide distributed advisory lock in PostgreSQL.
    In multi-pod Kubernetes deployments, prevents duplicate background scheduler execution.
    Returns: (acquired: bool, conn: Any, db_type: str)
    """
    try:
        conn, db_type = get_connection()
        if db_type == "postgres":
            cursor = conn.cursor()
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (lock_id,))
            row = cursor.fetchone()
            acquired = bool(row and row[0])
            if not acquired:
                conn.close()
                return False, None, db_type
            return True, conn, db_type
        # In SQLite / single-node dev, proceed normally
        return True, conn, db_type
    except Exception as e:
        logger.error(f"Error acquiring advisory lock {lock_id}: {e}")
        return True, None, "error_fallback"

def release_advisory_lock(conn, db_type: str, lock_id: int = 71705686):
    """Releases a cluster-wide distributed advisory lock in PostgreSQL."""
    if not conn:
        return
    try:
        if db_type == "postgres":
            cursor = conn.cursor()
            cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
            conn.close()
        elif db_type == "sqlite":
            conn.close()
    except Exception as e:
        logger.error(f"Error releasing advisory lock {lock_id}: {e}")

def init_db():
    """Initialize tables for budget configurations, org settings, cloud accounts, and alert logs."""
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
            CREATE TABLE IF NOT EXISTS org_settings (
                org_id VARCHAR(255) PRIMARY KEY,
                external_id VARCHAR(255) NOT NULL,
                created_at VARCHAR(255),
                updated_at VARCHAR(255)
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
                last_scanned_at VARCHAR(255),
                expires_at VARCHAR(255)
            );
            """)
            try:
                cursor.execute("ALTER TABLE cloud_accounts ADD COLUMN IF NOT EXISTS expires_at VARCHAR(255);")
            except Exception:
                pass
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
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id VARCHAR(255) PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                org_id VARCHAR(255) NOT NULL,
                role VARCHAR(50) DEFAULT 'finops',
                status VARCHAR(50) DEFAULT 'active',
                domain_verified INTEGER DEFAULT 0,
                created_at VARCHAR(255),
                updated_at VARCHAR(255)
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS org_domains (
                domain VARCHAR(255) PRIMARY KEY,
                org_id VARCHAR(255) NOT NULL,
                verified INTEGER DEFAULT 0,
                verification_token VARCHAR(255) NOT NULL,
                created_at VARCHAR(255)
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS role_promotion_audit (
                id VARCHAR(255) PRIMARY KEY,
                promoted_user_id VARCHAR(255) NOT NULL,
                promoted_by_user_id VARCHAR(255) NOT NULL,
                org_id VARCHAR(255) NOT NULL,
                old_role VARCHAR(50),
                new_role VARCHAR(50) NOT NULL,
                reason TEXT,
                timestamp VARCHAR(255) NOT NULL
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS security_audit_events (
                id VARCHAR(255) PRIMARY KEY,
                timestamp VARCHAR(255) NOT NULL,
                event_type VARCHAR(100) NOT NULL,
                user_id VARCHAR(255),
                org_id VARCHAR(255),
                target_arn VARCHAR(500),
                ip_address VARCHAR(100),
                details TEXT,
                severity VARCHAR(50) DEFAULT 'HIGH'
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS remediation_approvals (
                id VARCHAR(255) PRIMARY KEY,
                org_id VARCHAR(255) NOT NULL,
                requester_id VARCHAR(255) NOT NULL,
                requester_email VARCHAR(255),
                approver_id VARCHAR(255),
                approver_email VARCHAR(255),
                action VARCHAR(100) NOT NULL,
                resource_id VARCHAR(255) NOT NULL,
                resource_arn VARCHAR(500),
                region VARCHAR(100),
                account_id VARCHAR(255),
                environment VARCHAR(50) DEFAULT 'Production',
                status VARCHAR(50) DEFAULT 'pending',
                reason TEXT,
                requested_at VARCHAR(255),
                reviewed_at VARCHAR(255),
                executed_at VARCHAR(255)
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_audit_logs (
                id VARCHAR(255) PRIMARY KEY,
                timestamp VARCHAR(255) NOT NULL,
                user_id VARCHAR(255),
                user_email VARCHAR(255),
                org_id VARCHAR(255),
                action VARCHAR(100) NOT NULL,
                target_arn VARCHAR(500),
                tier VARCHAR(50),
                approval_chain TEXT,
                result VARCHAR(50) NOT NULL,
                details TEXT
            );
            """)
            try:
                cursor.execute("ALTER TABLE cloud_accounts ADD COLUMN IF NOT EXISTS tier VARCHAR(50) DEFAULT 'readonly';")
                cursor.execute("ALTER TABLE cloud_accounts ADD COLUMN IF NOT EXISTS created_by_user_id VARCHAR(255);")
            except Exception:
                pass
        else:
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS organizations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS org_settings (
                org_id TEXT PRIMARY KEY,
                external_id TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT
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
                last_scanned_at TEXT,
                expires_at TEXT,
                tier TEXT DEFAULT 'readonly',
                created_by_user_id TEXT
            )
            """)
            try:
                cursor.execute("ALTER TABLE cloud_accounts ADD COLUMN expires_at TEXT;")
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE cloud_accounts ADD COLUMN tier TEXT DEFAULT 'readonly';")
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE cloud_accounts ADD COLUMN created_by_user_id TEXT;")
            except Exception:
                pass
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                org_id TEXT NOT NULL,
                role TEXT DEFAULT 'finops',
                status TEXT DEFAULT 'active',
                domain_verified INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS org_domains (
                domain TEXT PRIMARY KEY,
                org_id TEXT NOT NULL,
                verified INTEGER DEFAULT 0,
                verification_token TEXT NOT NULL,
                created_at TEXT
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS role_promotion_audit (
                id TEXT PRIMARY KEY,
                promoted_user_id TEXT NOT NULL,
                promoted_by_user_id TEXT NOT NULL,
                org_id TEXT NOT NULL,
                old_role TEXT,
                new_role TEXT NOT NULL,
                reason TEXT,
                timestamp TEXT NOT NULL
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS security_audit_events (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                user_id TEXT,
                org_id TEXT,
                target_arn TEXT,
                ip_address TEXT,
                details TEXT,
                severity TEXT DEFAULT 'HIGH'
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS remediation_approvals (
                id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL,
                requester_id TEXT NOT NULL,
                requester_email TEXT,
                approver_id TEXT,
                approver_email TEXT,
                action TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                resource_arn TEXT,
                region TEXT,
                account_id TEXT,
                environment TEXT DEFAULT 'Production',
                status TEXT DEFAULT 'pending',
                reason TEXT,
                requested_at TEXT,
                reviewed_at TEXT,
                executed_at TEXT
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_audit_logs (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                user_id TEXT,
                user_email TEXT,
                org_id TEXT,
                action TEXT NOT NULL,
                target_arn TEXT,
                tier TEXT,
                approval_chain TEXT,
                result TEXT NOT NULL,
                details TEXT
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

def get_or_create_org_external_id(org_id: str) -> str:
    """Retrieve or generate a permanent high-entropy (256-bit) External ID for an organization."""
    try:
        import secrets
        conn, db_type = get_connection()
        cursor = conn.cursor()
        param_placeholder = "%s" if db_type == "postgres" else "?"
        cursor.execute(f"SELECT external_id FROM org_settings WHERE org_id = {param_placeholder}", (org_id,))
        row = cursor.fetchone()
        if row and row[0]:
            conn.close()
            return row[0]
        
        # Generate 256-bit cryptographically secure token
        new_ext_id = f"ext_{secrets.token_hex(32)}"
        now_str = datetime.now(timezone.utc).isoformat()
        
        if db_type == "postgres":
            query = """
            INSERT INTO org_settings (org_id, external_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (org_id) DO UPDATE SET updated_at = EXCLUDED.updated_at
            """
            cursor.execute(query, (org_id, new_ext_id, now_str, now_str))
        else:
            query = """
            INSERT INTO org_settings (org_id, external_id, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (org_id) DO UPDATE SET updated_at = excluded.updated_at
            """
            cursor.execute(query, (org_id, new_ext_id, now_str, now_str))
            
        conn.commit()
        conn.close()
        return new_ext_id
    except Exception as e:
        logger.error(f"Error getting or creating external_id for org {org_id}: {e}")
        import secrets
        return f"ext_{secrets.token_hex(32)}"

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
    """Save or update budget and alert notification channels for a user."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        now_str = datetime.now(timezone.utc).isoformat()
        param_placeholder = "%s" if db_type == "postgres" else "?"
        
        if db_type == "postgres":
            query = """
            INSERT INTO budget_configs (user_id, threshold, slack_webhooks, emails, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                threshold = EXCLUDED.threshold,
                slack_webhooks = EXCLUDED.slack_webhooks,
                emails = EXCLUDED.emails,
                updated_at = EXCLUDED.updated_at
            """
        else:
            query = """
            INSERT INTO budget_configs (user_id, threshold, slack_webhooks, emails, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (user_id) DO UPDATE SET
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

def save_cloud_account(account_id: str, org_id: str, account_alias: str, aws_account_id: str, role_arn: str, external_id: str, regions: list = None, status: str = "active", expires_at: str = None, tier: str = "readonly", created_by_user_id: str = None) -> dict:
    """Save or update a connected AWS Cloud Account with its STS AssumeRole ARN, External ID, optional expiration, tier, and creator."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        now_str = datetime.now(timezone.utc).isoformat()
        regions_json = json.dumps(regions or ["us-east-1", "us-east-2", "us-west-2", "eu-west-1"])

        if db_type == "postgres":
            query = """
            INSERT INTO cloud_accounts (id, org_id, account_alias, aws_account_id, role_arn, external_id, status, regions, created_at, last_scanned_at, expires_at, tier, created_by_user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s)
            ON CONFLICT(id) DO UPDATE SET
                account_alias = EXCLUDED.account_alias,
                aws_account_id = EXCLUDED.aws_account_id,
                role_arn = EXCLUDED.role_arn,
                external_id = EXCLUDED.external_id,
                status = EXCLUDED.status,
                regions = EXCLUDED.regions,
                expires_at = EXCLUDED.expires_at,
                tier = EXCLUDED.tier
            """
            cursor.execute(query, (account_id, org_id, account_alias, aws_account_id, role_arn, external_id, status, regions_json, now_str, expires_at, tier, created_by_user_id))
        else:
            query = """
            INSERT INTO cloud_accounts (id, org_id, account_alias, aws_account_id, role_arn, external_id, status, regions, created_at, last_scanned_at, expires_at, tier, created_by_user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                account_alias = excluded.account_alias,
                aws_account_id = excluded.aws_account_id,
                role_arn = excluded.role_arn,
                external_id = excluded.external_id,
                status = excluded.status,
                regions = excluded.regions,
                expires_at = excluded.expires_at,
                tier = excluded.tier
            """
            cursor.execute(query, (account_id, org_id, account_alias, aws_account_id, role_arn, external_id, status, regions_json, now_str, expires_at, tier, created_by_user_id))

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
            "created_at": now_str,
            "expires_at": expires_at,
            "tier": tier,
            "created_by_user_id": created_by_user_id
        }
    except Exception as e:
        logger.error(f"Error saving cloud account {account_id}: {e}")
        raise e

def list_cloud_accounts(org_id: str = "default_org") -> list:
    """Retrieve all connected cloud accounts for an organization or user."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        param_placeholder = "%s" if db_type == "postgres" else "?"
        cursor.execute(
            f"SELECT id, org_id, account_alias, aws_account_id, role_arn, external_id, status, regions, created_at, last_scanned_at, expires_at FROM cloud_accounts WHERE org_id = {param_placeholder} ORDER BY created_at DESC",
            (org_id,)
        )
        rows = cursor.fetchall()
        conn.close()

        now_iso = datetime.now(timezone.utc).isoformat()
        accounts = []
        for r in rows:
            acc_status = r[6]
            expires_at = r[10] if len(r) > 10 else None
            if expires_at and now_iso > expires_at:
                acc_status = "expired"

            accounts.append({
                "id": r[0],
                "org_id": r[1],
                "account_alias": r[2],
                "aws_account_id": r[3],
                "role_arn": r[4],
                "external_id": r[5],
                "status": acc_status,
                "regions": json.loads(r[7]) if r[7] else [],
                "created_at": r[8],
                "last_scanned_at": r[9],
                "expires_at": expires_at
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
                f"SELECT id, org_id, account_alias, aws_account_id, role_arn, external_id, status, regions, created_at, last_scanned_at, expires_at FROM cloud_accounts WHERE id = {param_placeholder} AND org_id = {param_placeholder}",
                (account_id, org_id)
            )
        else:
            cursor.execute(
                f"SELECT id, org_id, account_alias, aws_account_id, role_arn, external_id, status, regions, created_at, last_scanned_at, expires_at FROM cloud_accounts WHERE id = {param_placeholder}",
                (account_id,)
            )
        r = cursor.fetchone()
        conn.close()
        if r:
            now_iso = datetime.now(timezone.utc).isoformat()
            acc_status = r[6]
            expires_at = r[10] if len(r) > 10 else None
            if expires_at and now_iso > expires_at:
                acc_status = "expired"

            return {
                "id": r[0],
                "org_id": r[1],
                "account_alias": r[2],
                "aws_account_id": r[3],
                "role_arn": r[4],
                "external_id": r[5],
                "status": acc_status,
                "regions": json.loads(r[7]) if r[7] else [],
                "created_at": r[8],
                "last_scanned_at": r[9],
                "expires_at": expires_at
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


# =====================================================================
# --- Section 3: Org-Binding & Confused Deputy Prevention ---
# =====================================================================

def get_cloud_account_by_arn(role_arn: str) -> dict | None:
    """Finds any existing cloud account bound to the specified role ARN across all orgs."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        param_placeholder = "%s" if db_type == "postgres" else "?"
        cursor.execute(
            f"SELECT id, org_id, account_alias, aws_account_id, role_arn, external_id, status, regions, created_at, last_scanned_at, expires_at, tier, created_by_user_id FROM cloud_accounts WHERE role_arn = {param_placeholder}",
            (role_arn.strip(),)
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
                "last_scanned_at": r[9],
                "expires_at": r[10] if len(r) > 10 else None,
                "tier": r[11] if len(r) > 11 else "readonly",
                "created_by_user_id": r[12] if len(r) > 12 else None
            }
        return None
    except Exception as e:
        logger.error(f"Error finding account by ARN: {e}")
        return None


def log_security_event(event_type: str, user_id: str, org_id: str, target_arn: str = None, ip_address: str = None, details: dict = None, severity: str = "HIGH") -> str:
    """Logs a security violation or anomaly into the immutable security_audit_events table."""
    try:
        import uuid
        conn, db_type = get_connection()
        cursor = conn.cursor()
        event_id = f"sec_{uuid.uuid4().hex[:12]}"
        now_str = datetime.now(timezone.utc).isoformat()
        details_json = json.dumps(details or {})
        param_placeholder = "%s" if db_type == "postgres" else "?"

        query = f"""
        INSERT INTO security_audit_events (id, timestamp, event_type, user_id, org_id, target_arn, ip_address, details, severity)
        VALUES ({param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder})
        """
        cursor.execute(query, (event_id, now_str, event_type, user_id, org_id, target_arn, ip_address, details_json, severity))
        conn.commit()
        conn.close()
        logger.warning(f"[SECURITY EVENT] [{severity}] {event_type} | User: {user_id} | Org: {org_id} | ARN: {target_arn}")
        return event_id
    except Exception as e:
        logger.error(f"Failed to log security event: {e}")
        return "error_logging_event"


def get_security_events(org_id: str = None, limit: int = 50) -> list:
    """Retrieve security audit events, optionally filtered by org."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        param_placeholder = "%s" if db_type == "postgres" else "?"
        if org_id:
            cursor.execute(
                f"SELECT id, timestamp, event_type, user_id, org_id, target_arn, ip_address, details, severity FROM security_audit_events WHERE org_id = {param_placeholder} ORDER BY timestamp DESC LIMIT {limit}",
                (org_id,)
            )
        else:
            cursor.execute(
                f"SELECT id, timestamp, event_type, user_id, org_id, target_arn, ip_address, details, severity FROM security_audit_events ORDER BY timestamp DESC LIMIT {limit}"
            )
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "id": r[0],
                "timestamp": r[1],
                "event_type": r[2],
                "user_id": r[3],
                "org_id": r[4],
                "target_arn": r[5],
                "ip_address": r[6],
                "details": json.loads(r[7]) if r[7] else {},
                "severity": r[8]
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Error fetching security events: {e}")
        return []


def check_and_bind_account(org_id: str, user_id: str, user_role: str, account_alias: str, aws_account_id: str, role_arn: str, external_id: str, tier: str = "readonly", duration_days: int = None, regions: list = None, ip_address: str = None) -> tuple[bool, str, dict | None]:
    """
    Confused-Deputy & Org-Binding Prevention:
    1. Rejects if role_arn is already bound to another org (logs CROSS_ORG_ACCOUNT_TAKEOVER_ATTEMPT).
    2. If no binding exists: requires user_role == 'admin'. Non-admins are rejected.
    3. If validation succeeds, registers/updates the account.
    """
    cleaned_arn = role_arn.strip()
    existing_acc = get_cloud_account_by_arn(cleaned_arn)

    # 1. Cross-Org Takeover Check
    if existing_acc and existing_acc.get("org_id") != org_id:
        log_security_event(
            event_type="CROSS_ORG_ACCOUNT_TAKEOVER_ATTEMPT",
            user_id=user_id,
            org_id=org_id,
            target_arn=cleaned_arn,
            ip_address=ip_address,
            details={
                "attempted_org": org_id,
                "victim_org": existing_acc.get("org_id"),
                "alias": account_alias
            },
            severity="CRITICAL"
        )
        # Generic error message to prevent leaking whether the ARN exists in another tenant
        return False, "Unable to verify and bind this AWS Role. Please check your credentials or contact support.", None

    # 2. Passed validation — save binding
    import uuid
    account_id = existing_acc["id"] if existing_acc else f"acc_{uuid.uuid4().hex[:12]}"
    expires_at = None
    if duration_days and duration_days > 0:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=duration_days)).isoformat()
    elif existing_acc:
        expires_at = existing_acc.get("expires_at")

    saved_acc = save_cloud_account(
        account_id=account_id,
        org_id=org_id,
        account_alias=account_alias,
        aws_account_id=aws_account_id,
        role_arn=cleaned_arn,
        external_id=external_id,
        regions=regions,
        status="active",
        expires_at=expires_at,
        tier=tier,
        created_by_user_id=user_id
    )

    return True, "Account binding verified successfully.", saved_acc


# =====================================================================
# --- Section 4: Identity, Domain Verification & Role Promotion ---
# =====================================================================

def get_or_create_user_profile(user_id: str, email: str, org_id: str = None, default_role: str = "finops") -> dict:
    """Retrieves or initializes a database-backed user profile with lowest privilege default."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        param_placeholder = "%s" if db_type == "postgres" else "?"
        cursor.execute(
            f"SELECT user_id, email, org_id, role, status, domain_verified, created_at, updated_at FROM user_profiles WHERE user_id = {param_placeholder}",
            (user_id,)
        )
        row = cursor.fetchone()
        now_str = datetime.now(timezone.utc).isoformat()

        if row:
            conn.close()
            return {
                "user_id": row[0],
                "email": row[1],
                "org_id": row[2],
                "role": row[3],
                "status": row[4],
                "domain_verified": bool(row[5]),
                "created_at": row[6],
                "updated_at": row[7]
            }

        effective_org = org_id or user_id or "default_org"
        assigned_role = default_role

        if db_type == "postgres":
            query = """
            INSERT INTO user_profiles (user_id, email, org_id, role, status, domain_verified, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, 0, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
            """
        else:
            query = """
            INSERT INTO user_profiles (user_id, email, org_id, role, status, domain_verified, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?)
            ON CONFLICT (user_id) DO NOTHING
            """
        cursor.execute(query, (user_id, email, effective_org, assigned_role, "active", now_str, now_str))
        conn.commit()
        conn.close()

        return {
            "user_id": user_id,
            "email": email,
            "org_id": effective_org,
            "role": assigned_role,
            "status": "active",
            "domain_verified": False,
            "created_at": now_str,
            "updated_at": now_str
        }
    except Exception as e:
        logger.error(f"Error in get_or_create_user_profile: {e}")
        return {
            "user_id": user_id,
            "email": email,
            "org_id": org_id or "default_org",
            "role": default_role,
            "status": "active",
            "domain_verified": False
        }


def get_user_profile_db(user_id: str) -> dict | None:
    """Reads verified user profile and role directly from database."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        param_placeholder = "%s" if db_type == "postgres" else "?"
        cursor.execute(
            f"SELECT user_id, email, org_id, role, status, domain_verified, created_at, updated_at FROM user_profiles WHERE user_id = {param_placeholder}",
            (user_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "user_id": row[0],
                "email": row[1],
                "org_id": row[2],
                "role": row[3],
                "status": row[4],
                "domain_verified": bool(row[5]),
                "created_at": row[6],
                "updated_at": row[7]
            }
        return None
    except Exception as e:
        logger.error(f"Error reading user profile for {user_id}: {e}")
        return None


def update_user_role_db(user_id: str, new_role: str, promoted_by_user_id: str, org_id: str, reason: str = "") -> bool:
    """Promotes or demotes a user's role with immutable audit trail logging."""
    try:
        import uuid
        conn, db_type = get_connection()
        cursor = conn.cursor()
        now_str = datetime.now(timezone.utc).isoformat()
        param_placeholder = "%s" if db_type == "postgres" else "?"

        # Get old role
        cursor.execute(f"SELECT role FROM user_profiles WHERE user_id = {param_placeholder} AND org_id = {param_placeholder}", (user_id, org_id))
        r = cursor.fetchone()
        if not r:
            conn.close()
            return False
        old_role = r[0]

        # Update profile
        cursor.execute(
            f"UPDATE user_profiles SET role = {param_placeholder}, updated_at = {param_placeholder} WHERE user_id = {param_placeholder} AND org_id = {param_placeholder}",
            (new_role, now_str, user_id, org_id)
        )

        # Log to role promotion audit table
        audit_id = f"prom_{uuid.uuid4().hex[:12]}"
        cursor.execute(
            f"INSERT INTO role_promotion_audit (id, promoted_user_id, promoted_by_user_id, org_id, old_role, new_role, reason, timestamp) VALUES ({param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder})",
            (audit_id, user_id, promoted_by_user_id, org_id, old_role, new_role, reason, now_str)
        )

        conn.commit()
        conn.close()
        logger.info(f"[ROLE PROMOTION] User {user_id} promoted {old_role} -> {new_role} by {promoted_by_user_id} in org {org_id}")
        return True
    except Exception as e:
        logger.error(f"Error updating user role: {e}")
        return False


def list_org_users_db(org_id: str) -> list:
    """Lists all users belonging to an organization."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        param_placeholder = "%s" if db_type == "postgres" else "?"
        cursor.execute(
            f"SELECT user_id, email, org_id, role, status, domain_verified, created_at, updated_at FROM user_profiles WHERE org_id = {param_placeholder} ORDER BY created_at ASC",
            (org_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "user_id": r[0],
                "email": r[1],
                "org_id": r[2],
                "role": r[3],
                "status": r[4],
                "domain_verified": bool(r[5]),
                "created_at": r[6],
                "updated_at": r[7]
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Error listing org users for {org_id}: {e}")
        return []


def create_org_domain_challenge(org_id: str, domain: str) -> str:
    """Generates a cryptographic DNS TXT / Domain challenge token for org ownership."""
    try:
        import secrets
        conn, db_type = get_connection()
        cursor = conn.cursor()
        token = f"cloudcost-verify-{secrets.token_hex(16)}"
        now_str = datetime.now(timezone.utc).isoformat()
        param_placeholder = "%s" if db_type == "postgres" else "?"

        if db_type == "postgres":
            query = """
            INSERT INTO org_domains (domain, org_id, verified, verification_token, created_at)
            VALUES (%s, %s, 0, %s, %s)
            ON CONFLICT (domain) DO UPDATE SET verification_token = EXCLUDED.verification_token
            """
        else:
            query = """
            INSERT INTO org_domains (domain, org_id, verified, verification_token, created_at)
            VALUES (?, ?, 0, ?, ?)
            ON CONFLICT (domain) DO UPDATE SET verification_token = excluded.verification_token
            """
        cursor.execute(query, (domain.lower(), org_id, token, now_str))
        conn.commit()
        conn.close()
        return token
    except Exception as e:
        logger.error(f"Error creating domain challenge: {e}")
        return f"cloudcost-verify-{domain}"


def verify_org_domain(org_id: str, domain: str, verification_token: str, admin_user_id: str) -> bool:
    """Verifies domain ownership challenge and promotes the initial claimant to Admin."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        param_placeholder = "%s" if db_type == "postgres" else "?"
        cursor.execute(
            f"SELECT verification_token, verified FROM org_domains WHERE domain = {param_placeholder} AND org_id = {param_placeholder}",
            (domain.lower(), org_id)
        )
        r = cursor.fetchone()
        if not r:
            conn.close()
            return False

        stored_token = r[0]
        if stored_token != verification_token:
            conn.close()
            return False

        # Mark domain verified
        cursor.execute(
            f"UPDATE org_domains SET verified = 1 WHERE domain = {param_placeholder} AND org_id = {param_placeholder}",
            (domain.lower(), org_id)
        )
        cursor.execute(
            f"SELECT user_id FROM user_profiles WHERE user_id = {param_placeholder}",
            (admin_user_id,)
        )
        existing_u = cursor.fetchone()
        now_str = datetime.now(timezone.utc).isoformat()
        if existing_u:
            cursor.execute(
                f"UPDATE user_profiles SET domain_verified = 1, role = 'admin', updated_at = {param_placeholder} WHERE user_id = {param_placeholder}",
                (now_str, admin_user_id)
            )
        else:
            if db_type == "postgres":
                cursor.execute(
                    """
                    INSERT INTO user_profiles (user_id, email, org_id, role, status, domain_verified, created_at, updated_at)
                    VALUES (%s, %s, %s, 'admin', 'active', 1, %s, %s)
                    """,
                    (admin_user_id, f"{admin_user_id}@{domain}", org_id, now_str, now_str)
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO user_profiles (user_id, email, org_id, role, status, domain_verified, created_at, updated_at)
                    VALUES (?, ?, ?, 'admin', 'active', 1, ?, ?)
                    """,
                    (admin_user_id, f"{admin_user_id}@{domain}", org_id, now_str, now_str)
                )
        conn.commit()
        conn.close()
        logger.info(f"Domain {domain} verified successfully for org {org_id}. User {admin_user_id} promoted to verified Admin.")
        return True
    except Exception as e:
        logger.error(f"Error verifying domain: {e}")
        return False


# =====================================================================
# --- Section 5: Dual-Control Approvals for Production ---
# =====================================================================

def create_remediation_approval(org_id: str, requester_id: str, requester_email: str, action: str, resource_id: str, resource_arn: str = None, region: str = "us-east-1", account_id: str = None, environment: str = "Production", reason: str = "") -> dict:
    """Creates a pending approval request for dangerous/production remediation actions."""
    try:
        import uuid
        conn, db_type = get_connection()
        cursor = conn.cursor()
        approval_id = f"appr_{uuid.uuid4().hex[:12]}"
        now_str = datetime.now(timezone.utc).isoformat()
        param_placeholder = "%s" if db_type == "postgres" else "?"

        query = f"""
        INSERT INTO remediation_approvals (id, org_id, requester_id, requester_email, approver_id, approver_email, action, resource_id, resource_arn, region, account_id, environment, status, reason, requested_at, reviewed_at, executed_at)
        VALUES ({param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, NULL, NULL, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, 'pending', {param_placeholder}, {param_placeholder}, NULL, NULL)
        """
        cursor.execute(query, (approval_id, org_id, requester_id, requester_email, action, resource_id, resource_arn, region, account_id, environment, reason, now_str))
        conn.commit()
        conn.close()
        return {
            "id": approval_id,
            "org_id": org_id,
            "requester_id": requester_id,
            "requester_email": requester_email,
            "action": action,
            "resource_id": resource_id,
            "resource_arn": resource_arn,
            "region": region,
            "account_id": account_id,
            "environment": environment,
            "status": "pending",
            "reason": reason,
            "requested_at": now_str
        }
    except Exception as e:
        logger.error(f"Error creating remediation approval: {e}")
        raise e


def review_remediation_approval(approval_id: str, approver_id: str, approver_email: str, decision: str = "approved", org_id: str = "default_org") -> dict | None:
    """
    Reviews a pending approval.
    Enforces dual-control: Requester cannot approve their own action.
    """
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        param_placeholder = "%s" if db_type == "postgres" else "?"
        cursor.execute(
            f"SELECT id, org_id, requester_id, status FROM remediation_approvals WHERE id = {param_placeholder} AND org_id = {param_placeholder}",
            (approval_id, org_id)
        )
        r = cursor.fetchone()
        if not r:
            conn.close()
            return None

        requester_id = r[2]
        current_status = r[3]

        if current_status != "pending":
            conn.close()
            raise ValueError(f"Approval request is already in status '{current_status}'.")

        if approver_id == requester_id:
            conn.close()
            raise ValueError("Dual-control violation: Requester cannot approve their own remediation request.")

        new_status = "approved" if decision.lower() == "approved" else "rejected"
        now_str = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            f"UPDATE remediation_approvals SET status = {param_placeholder}, approver_id = {param_placeholder}, approver_email = {param_placeholder}, reviewed_at = {param_placeholder} WHERE id = {param_placeholder} AND org_id = {param_placeholder}",
            (new_status, approver_id, approver_email, now_str, approval_id, org_id)
        )
        conn.commit()
        conn.close()

        return get_remediation_approval(approval_id, org_id)
    except Exception as e:
        logger.error(f"Error reviewing approval {approval_id}: {e}")
        raise e


def get_remediation_approval(approval_id: str, org_id: str) -> dict | None:
    """Fetches a specific remediation approval record."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        param_placeholder = "%s" if db_type == "postgres" else "?"
        cursor.execute(
            f"SELECT id, org_id, requester_id, requester_email, approver_id, approver_email, action, resource_id, resource_arn, region, account_id, environment, status, reason, requested_at, reviewed_at, executed_at FROM remediation_approvals WHERE id = {param_placeholder} AND org_id = {param_placeholder}",
            (approval_id, org_id)
        )
        r = cursor.fetchone()
        conn.close()
        if r:
            return {
                "id": r[0],
                "org_id": r[1],
                "requester_id": r[2],
                "requester_email": r[3],
                "approver_id": r[4],
                "approver_email": r[5],
                "action": r[6],
                "resource_id": r[7],
                "resource_arn": r[8],
                "region": r[9],
                "account_id": r[10],
                "environment": r[11],
                "status": r[12],
                "reason": r[13],
                "requested_at": r[14],
                "reviewed_at": r[15],
                "executed_at": r[16]
            }
        return None
    except Exception as e:
        logger.error(f"Error fetching approval {approval_id}: {e}")
        return None


def list_remediation_approvals(org_id: str, status_filter: str = None) -> list:
    """Lists remediation approval requests for an organization."""
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        param_placeholder = "%s" if db_type == "postgres" else "?"
        if status_filter:
            cursor.execute(
                f"SELECT id, org_id, requester_id, requester_email, approver_id, approver_email, action, resource_id, resource_arn, region, account_id, environment, status, reason, requested_at, reviewed_at, executed_at FROM remediation_approvals WHERE org_id = {param_placeholder} AND status = {param_placeholder} ORDER BY requested_at DESC",
                (org_id, status_filter)
            )
        else:
            cursor.execute(
                f"SELECT id, org_id, requester_id, requester_email, approver_id, approver_email, action, resource_id, resource_arn, region, account_id, environment, status, reason, requested_at, reviewed_at, executed_at FROM remediation_approvals WHERE org_id = {param_placeholder} ORDER BY requested_at DESC",
                (org_id,)
            )
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "id": r[0],
                "org_id": r[1],
                "requester_id": r[2],
                "requester_email": r[3],
                "approver_id": r[4],
                "approver_email": r[5],
                "action": r[6],
                "resource_id": r[7],
                "resource_arn": r[8],
                "region": r[9],
                "account_id": r[10],
                "environment": r[11],
                "status": r[12],
                "reason": r[13],
                "requested_at": r[14],
                "reviewed_at": r[15],
                "executed_at": r[16]
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Error listing approvals for org {org_id}: {e}")
        return []


# =====================================================================
# --- Section 6: Immutable Activity Audit Trail ---
# =====================================================================

def log_activity_event(user_id: str, user_email: str, org_id: str, action: str, target_arn: str = None, tier: str = None, approval_chain: str = None, result: str = "success", details: dict = None) -> str:
    """Logs an auditable activity to the immutable activity_audit_logs table."""
    try:
        import uuid
        conn, db_type = get_connection()
        cursor = conn.cursor()
        log_id = f"aud_{uuid.uuid4().hex[:12]}"
        now_str = datetime.now(timezone.utc).isoformat()
        details_json = json.dumps(details or {})
        param_placeholder = "%s" if db_type == "postgres" else "?"

        query = f"""
        INSERT INTO activity_audit_logs (id, timestamp, user_id, user_email, org_id, action, target_arn, tier, approval_chain, result, details)
        VALUES ({param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder}, {param_placeholder})
        """
        cursor.execute(query, (log_id, now_str, user_id, user_email, org_id, action, target_arn, tier, approval_chain, result, details_json))
        conn.commit()
        conn.close()
        logger.info(f"[ACTIVITY AUDIT] Action: {action} | User: {user_email} | Org: {org_id} | Result: {result}")
        return log_id
    except Exception as e:
        logger.error(f"Failed to log activity audit event: {e}")
        return "error_logging_activity"


def get_activity_logs(org_id: str, user_id: str = None, limit: int = 100) -> list:
    """
    Retrieve audit trail records.
    If user_id is passed (e.g. for non-admins), results are filtered to their own actions.
    """
    try:
        conn, db_type = get_connection()
        cursor = conn.cursor()
        param_placeholder = "%s" if db_type == "postgres" else "?"
        if user_id:
            cursor.execute(
                f"SELECT id, timestamp, user_id, user_email, org_id, action, target_arn, tier, approval_chain, result, details FROM activity_audit_logs WHERE org_id = {param_placeholder} AND user_id = {param_placeholder} ORDER BY timestamp DESC LIMIT {limit}",
                (org_id, user_id)
            )
        else:
            cursor.execute(
                f"SELECT id, timestamp, user_id, user_email, org_id, action, target_arn, tier, approval_chain, result, details FROM activity_audit_logs WHERE org_id = {param_placeholder} ORDER BY timestamp DESC LIMIT {limit}",
                (org_id,)
            )
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "id": r[0],
                "timestamp": r[1],
                "user_id": r[2],
                "user_email": r[3],
                "org_id": r[4],
                "action": r[5],
                "target_arn": r[6],
                "tier": r[7],
                "approval_chain": r[8],
                "result": r[9],
                "details": json.loads(r[10]) if r[10] else {}
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Error fetching activity logs for org {org_id}: {e}")
        return []


