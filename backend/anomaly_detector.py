import os
import logging
import asyncio
from datetime import datetime, timedelta
import random
import httpx
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger("anomaly_detector")

def fetch_daily_spend(region: str, threshold: float = 1000.0) -> dict:
    """
    Fetch daily unblended costs for the past 21 days using AWS Cost Explorer.
    The past 21 days provides a complete 7-day preceding rolling average baseline
    for the last 14 days of spend.
    If Cost Explorer is disabled or credentials are missing, falls back to generating mock data.
    Returns: {"daily_costs": list, "is_simulated": bool}
    """
    try:
        # Cost Explorer client is global, but typically accessed via us-east-1 endpoint
        client = boto3.client('ce', region_name='us-east-1')
        
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=21)
        
        logger.info(f"Querying AWS Cost Explorer from {start_date} to {end_date} for region {region}")
        
        response = client.get_cost_and_usage(
            TimePeriod={
                'Start': start_date.strftime('%Y-%m-%d'),
                'End': end_date.strftime('%Y-%m-%d')
            },
            Granularity='DAILY',
            Metrics=['UnblendedCost'],
            Filter={
                'Dimensions': {
                    'Key': 'REGION',
                    'Values': [region]
                }
            }
        )
        
        daily_costs = []
        for day in response.get('ResultsByTime', []):
            start = day['TimePeriod']['Start']
            amount = float(day['Total']['UnblendedCost']['Amount'])
            daily_costs.append({
                'date': start,
                'amount': amount
            })
            
        # Ensure it's sorted by date
        daily_costs.sort(key=lambda x: x['date'])
        
        # If CE returned empty results (e.g. no active spend), throw exception to trigger fallback
        if not daily_costs:
            raise ValueError("Cost Explorer returned empty list")
            
        logger.info(f"Successfully retrieved {len(daily_costs)} days of costs from Cost Explorer")
        return {"daily_costs": daily_costs, "is_simulated": False}
        
    except Exception as e:
        logger.warning(f"Failed to fetch spend from AWS Cost Explorer: {str(e)}. Falling back to high-fidelity mock data.")
        
        # Generate realistic mock data for past 21 days scaled to budget threshold
        daily_costs = []
        end_date = datetime.utcnow().date()
        daily_base = max(5.0, threshold / 30.0)
        
        # We seed random using dates to keep the results stable across requests but realistic
        for i in range(21, 0, -1):
            date_str = (end_date - timedelta(days=i)).strftime('%Y-%m-%d')
            random.seed(date_str)
            
            # Base daily cost within +/- 15% of daily_base
            variation = daily_base * 0.15
            amount = round(daily_base + (random.random() * 2 - 1) * variation, 2)
            
            daily_costs.append({
                'date': date_str,
                'amount': amount
            })
            
        return {"daily_costs": daily_costs, "is_simulated": True}


def detect_cost_anomalies(daily_costs: list) -> list:
    """
    Calculate cost anomalies using a 7-day rolling average.
    An anomaly is flagged if the current day's cost exceeds the preceding 7-day average
    by > 20% and is higher than a noise threshold of $5/day.
    """
    anomalies = []
    
    # We need at least 8 days of data to compute a rolling average of the past 7 days for the 8th day
    if len(daily_costs) < 8:
        return anomalies
        
    for i in range(7, len(daily_costs)):
        current_day = daily_costs[i]
        preceding_days = daily_costs[i-7:i]
        
        avg_cost = sum(d['amount'] for d in preceding_days) / 7.0
        current_amount = current_day['amount']
        
        is_anomaly = False
        pct_increase = 0.0
        
        if avg_cost > 0:
            pct_increase = (current_amount - avg_cost) / avg_cost
            # Flag if cost exceeds average by > 20% AND current cost exceeds baseline noise threshold ($5/day)
            # and the absolute difference is also > $5 to avoid flagging minor fluctuations
            if pct_increase > 0.20 and current_amount > 5.0 and (current_amount - avg_cost) > 5.0:
                is_anomaly = True
        else:
            if current_amount > 5.0:
                is_anomaly = True
                pct_increase = 1.0  # 100% increase
                
        if is_anomaly:
            anomalies.append({
                'date': current_day['date'],
                'amount': round(current_amount, 2),
                'average': round(avg_cost, 2),
                'percent_increase': round(pct_increase * 100, 2)
            })
            
    return anomalies

async def send_slack_alert(webhook_url: str, anomaly_detail: dict) -> bool:
    """Send structured Slack notification to a Webhook URL using Block Kit."""
    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🚨 Cost Anomaly Detected!"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*AWS Cloud Spend Spike Alert*\nA sudden cost increase has been detected in your AWS environment."
                }
            },
            {"type": "divider"},
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Date:*\n{anomaly_detail['date']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Current Cost:*\n${anomaly_detail['amount']:.2f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*7-Day Rolling Average:*\n${anomaly_detail['average']:.2f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Percentage Increase:*\n+{anomaly_detail['percent_increase']:.1f}%"
                    }
                ]
            },
            {"type": "divider"},
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Sent by _AI Cloud Cost Detective_ • /budgets to configure thresholds"
                    }
                ]
            }
        ]
    }
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(webhook_url, json=payload, timeout=5.0)
            if resp.status_code in (200, 201):
                logger.info(f"Slack webhook alert successfully sent to {webhook_url[:30]}...")
                return True
            else:
                logger.error(f"Slack webhook rejected payload: {resp.status_code} - {resp.text}")
                return False
    except Exception as e:
        logger.error(f"Failed to post to Slack webhook: {str(e)}")
        return False

async def _send_via_smtp(host: str, port: int, username: str, password: str,
                         sender: str, to: str, subject: str, html: str, text: str):
    """Shared SMTP sending helper used by Gmail and generic SMTP paths."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"AI Cloud Cost Detective <{sender}>"
    msg['To'] = to
    msg.attach(MIMEText(text, 'plain'))
    msg.attach(MIMEText(html, 'html'))

    def _send():
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=10)
        else:
            server = smtplib.SMTP(host, port, timeout=10)
            server.ehlo()
            server.starttls()
            server.ehlo()
        server.login(username, password)
        server.sendmail(sender, to, msg.as_string())
        server.quit()

    await asyncio.to_thread(_send)


async def send_email_alert(email_address: str, anomaly_detail: dict, is_test: bool = False, is_simulated: bool = False) -> str | bool:
    """
    Send an HTML formatted cost spike alert email.
    Priority order:
      1. Gmail SMTP  (GMAIL_USER + GMAIL_APP_PASSWORD)
      2. SendGrid    (SENDGRID_API_KEY)
      3. Generic SMTP (SMTP_HOST)
      4. AWS SES     (only when SES_ENABLED=true)
      5. Simulation  (fallback for local dev)
    Returns True on real dispatch success, False on dispatch failure,
    and "simulated" if no dispatch method was configured.
    """
    prefix = ""
    banner_html = ""
    banner_text = ""
    
    if is_test:
        prefix = "[TEST] "
        banner_html = """
        <div style="background-color: rgba(59, 130, 246, 0.15); border: 1px solid #3b82f6; padding: 12px; border-radius: 8px; margin-bottom: 20px; color: #60a5fa; font-size: 13px;">
          <strong>ℹ️ Test Notification</strong><br>
          This is a test alert triggered manually to verify your email notification settings.
        </div>
        """
        banner_text = "ℹ️ TEST NOTIFICATION: This is a test alert triggered manually to verify email settings.\n\n"
    elif is_simulated:
        prefix = "[SIMULATED] "
        banner_html = """
        <div style="background-color: rgba(245, 158, 11, 0.15); border: 1px solid #f59e0b; padding: 12px; border-radius: 8px; margin-bottom: 20px; color: #fbbf24; font-size: 13px;">
          <strong>⚠️ Simulated Data Notice</strong><br>
          This alert is based on simulated data because actual AWS Cost Explorer data is currently unavailable (e.g. permission limits or data ingestion pending in AWS).
        </div>
        """
        banner_text = "⚠️ SIMULATED DATA NOTICE: This alert is based on simulated data because actual AWS Cost Explorer is currently unavailable.\n\n"

    subject = f"{prefix}\U0001f6a8 AWS Cost Spike Detected: ${anomaly_detail['amount']:.2f} Spend Anomaly"

    body_html = f"""
    <html>
      <head>
        <style>
          body {{ font-family: 'Segoe UI', Arial, sans-serif; background-color: #0b0c10; color: #c5c6c7; margin: 0; padding: 20px; }}
          .container {{ max-width: 600px; margin: 0 auto; background-color: #1f2833; padding: 30px; border-radius: 12px; border: 1px solid #45f3ff; }}
          h2 {{ color: #ff4d4d; margin-top: 0; }}
          .metric-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
          .metric-table td {{ padding: 10px 0; border-bottom: 1px solid #333; }}
          .metric-label {{ font-weight: bold; color: #888; }}
          .metric-value {{ text-align: right; font-weight: bold; color: #fff; }}
          .spike {{ color: #ff4d4d; }}
          .footer {{ font-size: 11px; color: #666; text-align: center; margin-top: 20px; }}
        </style>
      </head>
      <body>
        <div class="container">
          {banner_html}
          <h2>\U0001f6a8 AWS Spend Anomaly Alert</h2>
          <p>The AI Cloud Cost Detective has identified a sudden daily spend increase exceeding your normal patterns.</p>
          <table class="metric-table">
            <tr>
              <td class="metric-label">Spike Date:</td>
              <td class="metric-value">{anomaly_detail['date']}</td>
            </tr>
            <tr>
              <td class="metric-label">Current Cost:</td>
              <td class="metric-value spike">${anomaly_detail['amount']:.2f}</td>
            </tr>
            <tr>
              <td class="metric-label">7-Day Rolling Average:</td>
              <td class="metric-value">${anomaly_detail['average']:.2f}</td>
            </tr>
            <tr>
              <td class="metric-label">Percentage Increase:</td>
              <td class="metric-value spike">+{anomaly_detail['percent_increase']:.1f}%</td>
            </tr>
          </table>
          <p class="footer">Sent automatically by AI Cloud Cost Detective.</p>
        </div>
      </body>
    </html>
    """

    body_text = f"""
    {banner_text}\U0001f6a8 AWS Spend Anomaly Alert

    The AI Cloud Cost Detective has identified a sudden daily spend increase.

    Spike Date: {anomaly_detail['date']}
    Current Cost: ${anomaly_detail['amount']:.2f}
    7-Day Rolling Average: ${anomaly_detail['average']:.2f}
    Percentage Increase: +{anomaly_detail['percent_increase']:.1f}%

    Sent automatically by AI Cloud Cost Detective.
    """

    attempted_any = False

    # ── 1. Gmail SMTP (primary) ───────────────────────────────────────────────
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
    if gmail_user and gmail_pass:
        attempted_any = True
        try:
            logger.info(f"Attempting to send email via Gmail SMTP to {email_address}")
            await _send_via_smtp(
                host="smtp.gmail.com",
                port=587,
                username=gmail_user,
                password=gmail_pass,
                sender=gmail_user,
                to=email_address,
                subject=subject,
                html=body_html,
                text=body_text,
            )
            logger.info(f"Gmail SMTP email successfully sent to {email_address}")
            return True
        except Exception as e:
            logger.warning(f"Gmail SMTP failed: {str(e)}")

    # ── 2. SendGrid fallback ──────────────────────────────────────────────────
    sg_key = os.environ.get("SENDGRID_API_KEY")
    sender = os.environ.get("SES_SENDER_EMAIL", "alerts@cloudcostdetective.com")
    if sg_key:
        attempted_any = True
        sg_url = "https://api.sendgrid.com/v3/mail/send"
        sg_payload = {
            "personalizations": [{"to": [{"email": email_address}]}],
            "from": {"email": sender, "name": "AI Cloud Cost Detective"},
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": body_text},
                {"type": "text/html", "value": body_html}
            ]
        }
        sg_headers = {
            "Authorization": f"Bearer {sg_key}",
            "Content-Type": "application/json"
        }
        try:
            logger.info(f"Attempting to send email via SendGrid to {email_address}")
            async with httpx.AsyncClient() as client:
                resp = await client.post(sg_url, json=sg_payload, headers=sg_headers, timeout=5.0)
                if resp.status_code in (200, 202):
                    logger.info(f"SendGrid email successfully sent to {email_address}")
                    return True
                else:
                    logger.error(f"SendGrid API rejected email: {resp.status_code} - {resp.text}")
        except Exception as sg_err:
            logger.error(f"SendGrid email dispatch failed: {str(sg_err)}")

    # ── 3. Generic SMTP fallback ──────────────────────────────────────────────
    smtp_host = os.environ.get("SMTP_HOST")
    if smtp_host:
        attempted_any = True
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        smtp_user = os.environ.get("SMTP_USER")
        smtp_pass = os.environ.get("SMTP_PASSWORD")
        try:
            logger.info(f"Attempting to send email via generic SMTP ({smtp_host}:{smtp_port}) to {email_address}")
            await _send_via_smtp(
                host=smtp_host,
                port=smtp_port,
                username=smtp_user,
                password=smtp_pass,
                sender=smtp_user or sender,
                to=email_address,
                subject=subject,
                html=body_html,
                text=body_text,
            )
            logger.info(f"Generic SMTP email successfully sent to {email_address}")
            return True
        except Exception as smtp_err:
            logger.error(f"Generic SMTP email dispatch failed: {str(smtp_err)}")

    # ── 4. AWS SES (optional, requires SES_ENABLED=true) ─────────────────────
    if os.environ.get("SES_ENABLED", "false").lower() == "true":
        attempted_any = True
        ses_sender = os.environ.get("SES_SENDER_EMAIL", "alerts@cloudcostdetective.com")
        try:
            ses_client = boto3.client('ses', region_name=os.environ.get("AWS_REGION", "us-east-1"))
            logger.info(f"Attempting to send email via AWS SES to {email_address}")
            await asyncio.to_thread(
                ses_client.send_email,
                Source=ses_sender,
                Destination={'ToAddresses': [email_address]},
                Message={
                    'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                    'Body': {
                        'Html': {'Data': body_html, 'Charset': 'UTF-8'},
                        'Text': {'Data': body_text, 'Charset': 'UTF-8'}
                    }
                }
            )
            logger.info(f"AWS SES email successfully sent to {email_address}")
            return True
        except Exception as ses_err:
            logger.warning(f"AWS SES email failed: {str(ses_err)}.")

    if attempted_any:
        logger.error("All configured real email delivery channels failed.")
        return False

    # ── 5. Simulation (local dev fallback) ───────────────────────────────────
    logger.info(f"[SIMULATION] Email alert simulated successfully for {email_address}")
    logger.info(f"Subject: {subject}")
    logger.info(f"Body: {body_text.strip()}")
    return "simulated"


async def send_alert(anomaly_detail: dict, channels: list, is_test: bool = False, is_simulated: bool = False) -> list:
    """
    Dispatches alerts to all configured notification emails.
    Returns a list of channels that were successfully notified.
    """
    notified = []
    
    # Run notifications concurrently to prevent linear latency delays
    tasks = []
    channel_mapping = []
    
    for ch in channels:
        ch_clean = ch.strip()
        if not ch_clean:
            continue
            
        if "@" in ch_clean:
            # Email Address
            tasks.append(send_email_alert(ch_clean, anomaly_detail, is_test=is_test, is_simulated=is_simulated))
            channel_mapping.append(f"Email: {ch_clean}")
        else:
            logger.warning(f"Ignored non-email channel configuration: {ch_clean}")
            
    if not tasks:
        return notified
        
    results = await asyncio.gather(*tasks)
    
    for success, label in zip(results, channel_mapping):
        if success is True:
            notified.append(label)
        elif success == "simulated":
            notified.append(f"{label} (Simulated)")
            
    return notified
