import sqlite3
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger("database")

DB_PATH = os.path.join(os.path.dirname(__file__), "db.sqlite3")

def init_db():
    """Initialize SQLite tables for budget configurations and alert logs."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Budget configs table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS budget_configs (
            user_id TEXT PRIMARY KEY,
            threshold REAL,
            slack_webhooks TEXT,
            emails TEXT,
            updated_at TEXT
        )
        """)
        
        # Alert logs table
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
        logger.info(f"Local SQLite database initialized at {DB_PATH}")
    except Exception as e:
        logger.error(f"Failed to initialize local database: {str(e)}")

def get_budget_config(user_id: str) -> dict:
    """Retrieve budget and alert configurations for a user. Returns defaults if not found."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT threshold, slack_webhooks, emails FROM budget_configs WHERE user_id = ?",
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
        
    # Default values
    return {
        "threshold": 1000.0,
        "slack_webhooks": [],
        "emails": []
    }

def save_budget_config(user_id: str, threshold: float, slack_webhooks: list, emails: list):
    """Save or update budget and alert configurations for a user."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now_str = datetime.utcnow().isoformat() + "Z"
        
        cursor.execute(
            """
            INSERT INTO budget_configs (user_id, threshold, slack_webhooks, emails, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                threshold = excluded.threshold,
                slack_webhooks = excluded.slack_webhooks,
                emails = excluded.emails,
                updated_at = excluded.updated_at
            """,
            (user_id, threshold, json.dumps(slack_webhooks), json.dumps(emails), now_str)
        )
        conn.commit()
        conn.close()
        logger.info(f"Saved budget config for user {user_id}")
    except Exception as e:
        logger.error(f"Error saving budget config for user {user_id}: {str(e)}")
        raise e

def get_alert_logs(user_id: str) -> list:
    """Retrieve historical alert log records for a user, sorted descending by date."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, date, details, status, channels, created_at FROM alert_logs WHERE user_id = ? ORDER BY created_at DESC",
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
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now_str = datetime.utcnow().isoformat() + "Z"
        
        cursor.execute(
            """
            INSERT INTO alert_logs (id, user_id, date, details, status, channels, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (alert_id, user_id, date, json.dumps(details), status, json.dumps(channels), now_str)
        )
        conn.commit()
        conn.close()
        logger.info(f"Saved alert log {alert_id} for user {user_id}")
    except Exception as e:
        logger.error(f"Error saving alert log for user {user_id}: {str(e)}")
        raise e
