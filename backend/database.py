import sqlite3
import json
import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger("database")

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "data", "db.sqlite3"))
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

def get_connection():
    """Returns a database connection (PostgreSQL if DATABASE_URL set, else SQLite)."""
    if DATABASE_URL:
        try:
            import psycopg2
            return psycopg2.connect(DATABASE_URL), "postgres"
        except Exception as e:
            logger.warning(f"Failed to connect to PostgreSQL via DATABASE_URL: {e}. Falling back to SQLite.")
    
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and DB_PATH != ":memory:":
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
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

