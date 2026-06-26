# 🐍 AI Cloud Cost Detective — Backend API Service

This directory contains the FastAPI-based backend microservice. It is responsible for scanning AWS resource inventories, analyzing cost optimization possibilities via Gemini AI, running background anomaly checks, and persisting logs.

---

## ⚙️ Core Service Components

- **[main.py](file:///c:/ai_log/cloud_cost/backend/main.py):** The primary router and server initializer. Houses routes for region listings, budget config updates, manual anomaly scan executions, history retrievals, and WebSocket connections for real-time analysis streaming.
- **[aws_scanner.py](file:///c:/ai_log/cloud_cost/backend/aws_scanner.py):** Performs active AWS inventory sweeps using `boto3`. Scans for:
  - **EC2 instances:** Underutilized or idle nodes.
  - **EBS volumes:** Unattached, orphaned, or outdated standard volumes (e.g. `gp2` that can be upgraded to `gp3`).
  - **RDS databases:** Unused instances.
- **[ai_analyzer.py](file:///c:/ai_log/cloud_cost/backend/ai_analyzer.py):** Orchestrates Prompt Engineering for Google Gemini AI. Packs raw AWS scanned inventories into structured markdown/JSON optimization reports.
- **[anomaly_detector.py](file:///c:/ai_log/cloud_cost/backend/anomaly_detector.py):** Processes cost history trends. Simulates or queries AWS Cost Explorer trends, detects statistical spend anomalies (>20% deviation), and dispatches notifications.
- **[insforge_client.py](file:///c:/ai_log/cloud_cost/backend/insforge_client.py):** Coordinates remote database logs, saves audit records, updates audit progress, and handles session validation.
- **[database.py](file:///c:/ai_log/cloud_cost/backend/database.py):** Local SQLite schema definition used as a local fallback for budget logs and configurations.

---

## 🚀 Getting Started

### 📦 Prerequisites
- Python 3.10+
- Pip (Python Package Installer)
- AWS credentials set up locally (`~/.aws/credentials`)

### 🛠️ Quick Installation & Startup

1. **Activate Python Virtual Environment:**
   ```bash
   python -m venv venv
   # Windows (CMD):
   venv\Scripts\activate
   # macOS/Linux:
   source venv/bin/activate
   ```

2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   Create a `.env` file in this directory (based on `.env.example`):
   ```env
   GEMINI_API_KEY=your_gemini_api_key
   INSFORGE_PROJECT_URL=your_insforge_project_url
   INSFORGE_ANON_KEY=your_insforge_anon_key
   ```

4. **Launch Local Server:**
   ```bash
   python main.py
   ```
   The backend will start on **http://localhost:8000**.
   - Check interactive API documentation: http://localhost:8000/docs
   - WebSocket progress tracker: `ws://localhost:8000/ws/progress/{analysis_id}`

---

## 📁 Environment Variables Guide

| Variable Name | Description | Required? |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | Google Gemini API access token for performing cost recommendations. | Yes |
| `INSFORGE_PROJECT_URL` | Base URL of your InsForge Project instance. | Yes |
| `INSFORGE_ANON_KEY` | Anonymous public API key for InsForge DB connections. | Yes |
| `AWS_ACCESS_KEY_ID` | AWS service access key. | Optional if using standard `~/.aws/credentials` |
| `AWS_SECRET_ACCESS_KEY` | AWS service secret key. | Optional if using standard `~/.aws/credentials` |
| `AWS_SESSION_TOKEN` | AWS service session token. | Optional if using standard `~/.aws/credentials` |
| `AWS_DEFAULT_REGION` | Target AWS region to connect to. | Optional (Defaults to `us-east-1`) |

---

## 🔌 API Endpoints Summary

- **Authentication:**
  - Most endpoints require a valid InsForge session JWT token passed via the `Authorization: Bearer <token>` header.
- **Regions:**
  - `GET /api/regions` — Retrieve list of active target AWS regions.
- **Cost Scanning & Remediations:**
  - `POST /api/analyze` — Trigger an optimization audit. Stream progress messages via WS.
  - `POST /api/remediate` — Trigger boto3-based automated remediation (e.g. upgrade storage type).
- **AI Conversational Chat:**
  - `POST /api/chat` — Conversational assistant interface mapping resource history contexts to Gemini chat models.
- **Budgets & Anomaly Logs:**
  - `GET /api/budgets` — Fetch threshold configs and historical alert logs.
  - `POST /api/budgets` — Save custom budget thresholds and notifications list.
  - `GET /api/budgets/spend` — Fetch 14-day spending charts and highlighted anomalies.
  - `POST /api/budgets/trigger-scan` — Execute manual anomaly audit checks.
