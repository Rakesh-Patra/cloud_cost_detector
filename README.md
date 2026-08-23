# 🔍 AI Cloud Cost Detective — Enterprise Multi-Tenant FinOps Platform

Welcome to the **AI Cloud Cost Detective** repository! This platform helps engineering, finance, and DevOps teams track, analyze, and optimize cloud expenses across multi-account AWS environments. By combining automated AWS infrastructure scans, **14-day CloudWatch telemetry**, precision regional pricing models, and **Gemini AI**, it identifies orphaned assets, recommends cost-saving modernizations (such as upgrading `gp2` to `gp3` storage for 20% savings), enforces automated safety guardrails, and generates copy-paste **Terraform IaC** fixes.

The platform is designed with an **Enterprise-First Security Model**: zero permanent credentials stored, 1-Click AWS CloudFormation onboarding via `sts:AssumeRole`, **Snapshot-before-Delete** safeguards, and a **7-Day "Tag-and-Wait" Quarantine lifecycle**.

---

## 🗺️ System Architecture Overview

```text
                          ┌──────────────────────────┐
                          │    Vite / React Web UI   │
                          │   (TypeScript/Tailwind)  │
                          └─────────────┬────────────┘
                                        │
                         HTTP & WebSockets (Port 5173/8080)
                                        │
                                        ▼
                          ┌──────────────────────────┐
                          │     FastAPI Backend      │◄─────────┐
                          │        (Python)          │          │
                          └─────┬───────┬───────┬────┘          │
                                │       │       │               │
            Dynamic STS Session │       │       │ Gemini API    │
            (`sts:AssumeRole`)  │       │       │ (Synthesis)   │
                                ▼       │       ▼               ▼
         ┌──────────────────────────┐   │    ┌───────┐ ┌───────────────────┐
         │ Customer AWS Account(s)  │   │    │Gemini │ │  InsForge Cloud   │
         │ - 14-Day CloudWatch CW   │   │    │  AI   │ │  Audit Database   │
         │ - EC2, EBS, RDS Scanner  │   │    └───────┘ └───────────────────┘
         │ - Snapshot / Quarantine  │   │                       ▲
         └──────────────────────────┘   │                       │
                                        ▼                       │
                           ┌─────────────────────────┐          │
                           │  Pricing & Rules Engine │          │
                           │  (Deterministic Tier 1) │          │
                           └────────────┬────────────┘          │
                                        │                       │
                                        │ Local Sync / State    │
                                        ▼                       │
                           ┌─────────────────────────┐          │
                           │ SQLite / Postgres DB    ├──────────┘
                           │ (Orgs, Accounts, Quar)  │
                           └─────────────────────────┘
```

---

## 🚀 Key Platform Features

### 1. Zero-Key Multi-Tenant AWS Onboarding (`sts:AssumeRole`)

- **1-Click CloudFormation Launcher:** Deploy a read-only `SecurityAudit` IAM Role directly into your AWS account with a unique, cryptographically generated `ExternalId` in under 60 seconds.
- **Zero Permanent Credentials:** No root AWS Access Keys or Secrets are ever saved in the platform database. Temporary STS session tokens are created dynamically per scan.
- **Multi-Account Selector:** Switch and scan across different AWS environments (Production, Staging, Dev) seamlessly.

### 2. 14-Day CloudWatch Telemetry & Precision Pricing Engine

- **False-Positive Elimination:** Ingests 14 days of hourly P95/P99 CPU utilization and Network I/O metrics to differentiate between true idle compute ($< 2\%$ CPU) and periodic batch workloads.
- **Precision Pricing Model:** Computes exact regional On-Demand rates, `gp2` $\rightarrow$ `gp3` modernization deltas (\$0.10 vs \$0.08/GB-mo), and idle Elastic IP fees.
- **Two-Tier Processing:** Fast Python deterministic filtering scores 100% of resources in milliseconds, sending only anomalies to Gemini AI—slashing token consumption by 95%.

### 3. Enterprise Safety Guardrails & Quarantine Dashboard

- **Snapshot-Before-Delete:** Every volume termination automatically creates an encrypted, tagged backup snapshot (`CreatedBy: CloudCostDetective`) with an auto-expiry policy before deletion.
- **7-Day "Tag-and-Wait" Quarantine:** Resources flagged for deletion receive AWS tags (`FinOps_Status=Quarantined`) with a 7-day grace period.
- **Quarantine Hub (`/quarantine`):** View quarantined assets, monitor remaining days, and 1-click **"Keep & Whitelist"** or **"Safe Delete Now"**.

### 4. Detailed Cost Analysis & Terraform IaC Generation

- **Optimization Cards:** Displays potential savings per resource with severity badges and accurate dollar amounts.
- **Terraform HCL Fixes:** Provides copy-pasteable Terraform configuration code to remediate findings via Infrastructure-as-Code without creating state drift.
- **Automated CLI Remediation:** 1-click execution to upgrade storage or stop idle compute directly from the UI.

### 5. Budgets & Spend Anomaly Alerts

- **Guardrails:** Configure monthly caps and list email distribution channels.
- **Spend Trends:** View 14-day spending charts featuring highlight indicators on anomalous surges.
- **Automated Notifications:** Dispatches real-time email alerts upon threshold breaches.

---

## 📁 Repository Structure

- [backend/](file:///c:/ai_log/cloud_cost/backend) — FastAPI application code, AWS scanners, Gemini prompt engines, and database clients.
  - [main.py](file:///c:/ai_log/cloud_cost/backend/main.py) — API endpoints, WebSocket connection manager, multi-tenant cloud account & quarantine routes.
  - [aws_scanner.py](file:///c:/ai_log/cloud_cost/backend/aws_scanner.py) — Boto3 scanner, dynamic STS AssumeRole session factory, CloudWatch 14-day telemetry ingestion, snapshot-before-delete, and quarantine tagging.
  - [pricing_engine.py](file:///c:/ai_log/cloud_cost/backend/pricing_engine.py) — Precision AWS pricing catalog and deterministic pre-filter evaluator.
  - [ai_analyzer.py](file:///c:/ai_log/cloud_cost/backend/ai_analyzer.py) — Two-tier cost engine combining deterministic scoring with Gemini 2.5 Flash for executive summaries and Terraform HCL generation.
  - [anomaly_detector.py](file:///c:/ai_log/cloud_cost/backend/anomaly_detector.py) — Cost spike detection and notification router.
  - [database.py](file:///c:/ai_log/cloud_cost/backend/database.py) — Multi-tenant database schemas for organizations, cloud accounts, quarantine items, and budget configs.
  - [tests/](file:///c:/ai_log/cloud_cost/backend/tests) — Comprehensive test suite (30 automated tests) for STS assume role, telemetry, pricing, and quarantine workflows.
- [frontend/](file:///c:/ai_log/cloud_cost/frontend) — Single Page App (SPA) built with Vite, React, TypeScript, and Tailwind CSS.
  - [src/pages/Dashboard.tsx](file:///c:/ai_log/cloud_cost/frontend/src/pages/Dashboard.tsx) — Main dashboard with multi-account switcher and 1-Click AWS Connect launcher.
  - [src/pages/Quarantine.tsx](file:///c:/ai_log/cloud_cost/frontend/src/pages/Quarantine.tsx) — Quarantine management dashboard with grace period countdown and snapshot rollbacks.
  - [src/pages/Report.tsx](file:///c:/ai_log/cloud_cost/frontend/src/pages/Report.tsx) — Cost analysis reports with Terraform IaC snippets and 7-day quarantine actions.
  - [src/components/ConnectCloudModal.tsx](file:///c:/ai_log/cloud_cost/frontend/src/components/ConnectCloudModal.tsx) — 1-Click AWS CloudFormation onboarding modal.
  - [src/components/FinOpsChat.tsx](file:///c:/ai_log/cloud_cost/frontend/src/components/FinOpsChat.tsx) — Anchored FinOps conversational AI drawer.
- [docker-compose.yml](file:///c:/ai_log/cloud_cost/docker-compose.yml) — Local multi-container development configuration.
- [devops_roadmap.md](file:///c:/ai_log/cloud_cost/devops_roadmap.md) — Future implementation roadmap including CI/CD pipelines, Prometheus/Grafana monitors, IaC configs, and Helm plans.

---

## 🛠️ Prerequisites & Setup Requirements

Before pulling and running the repository on your laptop, ensure you have:

1. **Git** ([Download Git](https://git-scm.com/))
2. **Docker & Docker Compose** ([Download Docker Desktop](https://www.docker.com/products/docker-desktop/))
3. **Google Gemini API Key** ([Get free key from Google AI Studio](https://aistudio.google.com/))
4. **AWS Account Credentials** (Access Key & Secret Key with read permissions for EC2, EBS, RDS)
5. **InsForge Project Credentials** (or your preferred auth endpoint)

---

## ⚡ Quick Start: 3-Step Setup (Run with Docker)

The easiest way to run the entire platform locally is with Docker Compose.

### Step 1: Clone the Repository

Open your terminal or command prompt and clone the repository:

```bash
git clone https://github.com/Rakesh-Patra/cloud_cost_detector.git
cd cloud_cost_detector
```

### Step 2: Configure Environment Variables

Create the `.env` configuration file for the backend:

```bash
# On Linux / macOS / Git Bash:
cp backend/.env.example backend/.env

# On Windows (PowerShell):
Copy-Item backend\.env.example backend\.env
```

Open `backend/.env` in your text editor and fill in your credentials:

```env
# Google Gemini API Key (Required for AI Cost Audits & FinOps Chat)
GEMINI_API_KEY=your_gemini_api_key_here

# InsForge Cloud Database & Authentication Credentials
INSFORGE_PROJECT_URL=https://your-project.us-east.insforge.app/
INSFORGE_ANON_KEY=your_insforge_anon_key_here

# AWS Access Credentials (Required for Scanning AWS Resources)
AWS_ACCESS_KEY_ID=your_aws_access_key_id
AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key
AWS_DEFAULT_REGION=us-east-1
```

> 💡 **Note for AWS credentials:** Alternatively, if you already have the AWS CLI configured on your computer (`aws configure`), Docker Compose will automatically mount your local `~/.aws/credentials` file.

### Step 3: Build & Launch

Start all services (Frontend, Backend, and Vault) with a single command:

```bash
docker compose up --build
```

---

## 🔒 Production HTTPS with Cloudflare Tunnel (Zero-Port Exposure & Google OAuth)

To allow **50+ remote/mobile users** to securely access your AWS EC2 instance without opening inbound ports (80/443/5173) to the public internet, and to enable Google OAuth PKCE authentication:

### 1. Create a Free Cloudflare Tunnel
1. Log in to [Cloudflare Dashboard](https://dash.cloudflare.com/) and navigate to **Zero Trust** > **Networks** > **Tunnels**.
2. Click **Create a Tunnel** > Select **Cloudflared**.
3. Name your tunnel (e.g. `cloud-cost-detector`) and click **Save Tunnel**.
4. In the **Install and run a connector** step, choose **Docker** and copy your **Tunnel Token** (the string after `--token`).

### 2. Configure Public Hostname in Cloudflare
In the Tunnel settings under the **Public Hostname** tab:
* **Subdomain / Domain:** e.g., `cost.yourdomain.com`
* **Service Type:** `HTTP`
* **URL:** `frontend:8080` (or `localhost:5173` if running locally)

### 3. Add Tunnel Token to Your Server
Add the token to your `.env` file on your server / EC2:
```env
CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoi...your_token_here...
```

Start the platform:
```bash
docker compose up -d --build
```
The `cloudflared` container will connect to Cloudflare, and your app will instantly be available over encrypted HTTPS at `https://cost.yourdomain.com`.

### 4. Authorize Google OAuth Redirect URI
1. Open [Google Cloud Console](https://console.cloud.google.com/) > **APIs & Services** > **Credentials**.
2. Select your **OAuth 2.0 Client ID**.
3. Under **Authorized JavaScript origins**, add: `https://cost.yourdomain.com`
4. Under **Authorized redirect URIs**, add: `https://cost.yourdomain.com`
5. Open your [InsForge Dashboard](https://insforge.app) > **Authentication** > **Providers** > **Google**, and ensure `https://cost.yourdomain.com` is in the allowed redirect URLs.

---

## 🌐 Accessing the Local Platform

Once the containers start up, open your web browser to access the application:

| Component | URL | Details |
|---|---|---|
| 💻 **Frontend Web UI** | <http://localhost:5173> (or <http://localhost:8080>) | React + Vite UI dashboard |
| ⚡ **Backend API Docs** | <http://localhost:8000/docs> | Interactive Swagger API documentation |
| 🛡️ **Quarantine Hub** | <http://localhost:5173/quarantine> | 7-day grace period & snapshot safety hub |
| 🔐 **HashiCorp Vault UI** | <http://localhost:8200/ui> | Secrets manager (Root Token: `root` or `hvs...`) |

> ⚡ **Connecting New AWS Accounts:** Once in the dashboard, click **"Connect AWS (1-Click)"** to automatically launch a pre-populated CloudFormation stack in your AWS console using STS AssumeRole. Zero root keys required!

To stop the platform at any time, press `Ctrl + C` in your terminal, or run:

```bash
docker compose down
```

---

## ☸️ Running with Kubernetes (k8s)

To run the microservices stack on a local cluster (Docker Desktop K8s, Minikube, or K3s):

1. **Apply Namespace & Configurations:**

   ```bash
   kubectl apply -f k8s/00-namespace.yaml
   kubectl apply -f k8s/01-configmap.yaml
   ```

2. **Create Cluster Secret:**

   Copy `k8s/02-secret.yaml.example` to `k8s/02-secret.yaml` and set your credentials, or apply dynamically:

   ```bash
   kubectl create secret generic cloud-cost-secret \
     --namespace cloud-cost \
     --from-literal=DATABASE_URL="postgresql://clouduser:cloudpass@cloud-cost-postgres:5432/cloudcost" \
     --from-literal=AWS_ACCESS_KEY_ID="your_aws_key" \
     --from-literal=AWS_SECRET_ACCESS_KEY="your_aws_secret" \
     --from-literal=VITE_INSFORGE_ANON_KEY="your_insforge_key"
   ```

3. **Deploy Microservices Stack (Backend, Frontend, Storage & Vault):**

   ```bash
   kubectl apply -f k8s/
   ```

4. **Verify Pod Status & Access Services:**

   ```bash
   kubectl get pods -n cloud-cost
   
   # Forward Frontend Web UI to port 5173:
   kubectl port-forward svc/cloud-cost-frontend-service 5173:8080 -n cloud-cost
   
   # Forward Backend API Docs to port 8000:
   kubectl port-forward svc/cloud-cost-backend-service 8000:8000 -n cloud-cost
   ```

---

## 💻 Manual Setup: Running Locally (Without Docker)

If you prefer to run the backend and frontend separately outside containers:

### 🐍 1. Backend Setup (FastAPI)

1. Navigate to the backend folder:

   ```bash
   cd backend
   ```

2. Create and activate a python virtual environment:

   ```bash
   python -m venv venv
   # On Windows (CMD):
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. Install requirements:

   ```bash
   pip install -r requirements.txt
   ```

4. Define your environment variables in a `.env` file (see `.env.example`).
5. Ensure your AWS credentials are exported in your terminal session:

   ```powershell
   # PowerShell
   $env:AWS_ACCESS_KEY_ID="your-key"
   $env:AWS_SECRET_ACCESS_KEY="your-secret"
   $env:AWS_DEFAULT_REGION="us-east-1"
   ```

6. Run the FastAPI development server:

   ```bash
   python main.py
   ```

   *(Running on <http://localhost:8000>)*

### ⚛️ 2. Frontend Setup (React/Vite)

1. Navigate to the frontend folder:

   ```bash
   cd ../frontend
   ```

2. Install npm packages:

   ```bash
   npm install
   ```

3. Create your `.env` file containing configuration variables:

   ```env
   VITE_BACKEND_URL=http://localhost:8000
   VITE_INSFORGE_PROJECT_URL=your_insforge_project_url
   VITE_INSFORGE_ANON_KEY=your_insforge_anon_key
   ```

4. Start the Vite server:

   ```bash
   npm run dev
   ```

   *(Running on <http://localhost:5173>)*

---

## 🔍 Common Diagnostics & Troubleshooting

- **"Failed to connect to AWS: AWS credentials not found or incomplete"**
  - **Why:** The backend server cannot find standard AWS credentials.
  - **Fix:** If running manually, verify environment variables are loaded. If running via Docker Compose, ensure the credentials mount `~/.aws:/home/nonroot/.aws:ro` matches your local home directory, or pass credentials in the environment fields of your [docker-compose.yml](file:///c:/ai_log/cloud_cost/docker-compose.yml).
- **"Analysis failed: Could not connect to authentication service"**
  - **Why:** The backend was unable to reach the InsForge endpoint during the startup verification of your token.
  - **Fix:** Verify `INSFORGE_PROJECT_URL` and `INSFORGE_ANON_KEY` in `backend/.env` are correctly typed and that your internet connection is active.
- **"Network request failed: Failed to fetch"**
  - **Why:** The React frontend cannot reach the FastAPI server.
  - **Fix:** Check if the backend container or process is running on port `8000`, and that CORS policies in `main.py` include your local frontend origin.
- **"Failed to connect to AWS: Not Found"**
  - **Why:** The specified AWS target region is invalid or inactive.
  - **Fix:** Double check the region input string in your request.

---

## 🛡️ Git Security & DevSecOps Pipeline

To ensure credentials, keys, and local test configurations never leak, the repository is guarded by a comprehensive **DevSecOps for Git** pipeline.

```text
[Local Code Changes]
      │
      ├──> [Step 1: .gitignore] (Blocks untracked secrets / node_modules)
      │
      ├──> [Step 2: Native Pre-Commit Hook] (Blocks commits containing the word 'secret')
      │
      ├──> [Step 3: Gitleaks Local Hook] (Blocks commits matching credential regex patterns)
      │
      └──> [git commit]
            │
            └──> [git push]
                  │
                  └──> [Step 4: GitHub Actions Gitleaks] (History & PR verification)
```

### 1. `.gitignore` Guidelines

To prevent local configs or database files from ever getting tracked, the following patterns are strictly ignored by Git:

- **`.env` / `.env.*`** — Private credentials and access keys.
- **`*.pem` / `*.key` / `id_rsa`** — Secure Shell (SSH) and encryption keys.
- **`backend/*.sqlite3`** — Local database binaries.
- **`node_modules/` & `dist/`** — Build assets and library dependencies.

### 2. Native Pre-Commit Hook Setup

Git execution hooks block unsafe code from being committed locally.

- **Location:** [`.git/hooks/pre-commit`](file:///c:/ai_log/cloud_cost/.git/hooks/pre-commit)
- To enable execution privileges (macOS/Linux):

  ```bash
  chmod +x .git/hooks/pre-commit
  ```

### 3. Gitleaks Integration

Gitleaks inspects codebase patterns for credentials, private keys, and API tokens based on the config file [`custom-rules.toml`](file:///c:/ai_log/cloud_cost/custom-rules.toml).

- **Setup Gitleaks locally:**
  1. Install Python's `pre-commit` package manager:
     - On Windows (PowerShell/CMD): `pip install pre-commit` or `choco install pre-commit`
     - On macOS: `brew install pre-commit`
  2. Activate Gitleaks hook in this directory:

     ```bash
     pre-commit install
     ```

  3. Scan the local git history:

     ```bash
     gitleaks detect --config custom-rules.toml --verbose
     ```

### 4. Reusable DevSecOps Pipeline & HashiCorp Vault

Our codebase is guarded by a comprehensive, modular **GitHub Actions DevSecOps Orchestrator Pipeline** ([devsecops-pipeline.yml](file:///.github/workflows/devsecops-pipeline.yml)).

- **CI & Linting** ([ci.yml](file:///.github/workflows/ci.yml)): Validates Python syntax, typechecks React frontend, and runs Oxlint/Ruff checks.
- **Security Scans**: Runs SAST and dependency analysis concurrently (Gitleaks, Bandit, Checkov, Trivy, Semgrep, and Dependency Review).
- **Infracost & IaC** ([infracost.yml](file:///.github/workflows/infracost.yml)): Calculates cloud cost differences on Terraform pull requests.
- **OIDC & HashiCorp Vault** ([vault-secrets/action.yml](file:///.github/actions/vault-secrets/action.yml)): Authenticates securely with Vault using GitHub OpenID Connect (OIDC) JWT tokens, fetching secrets directly into runner environments instead of saving static keys on GitHub.
- **Automated Rollback & Drift Detection**: Detects configuration drifts on schedule and alerts you on Slack.

---

## 🔐 HashiCorp Vault Local Setup

We configure a local, dev-mode Vault server to secure project secrets and test OIDC connections locally.

1. **Start & Configure Local Vault**:
   Run the automation script to download the Vault binary, boot it, and configure JWT/OIDC OIDC roles automatically:

   ```bash
   python setup_vault.py
   ```

2. **Access Vault UI**:
   - URL: **<http://127.0.0.1:8200/ui>**
   - Login: Select **Token** and enter `root`.
3. **Manually Add Secrets**:
   Click on the **`secret/`** engine, select **Create secret**, and save keys inside:
   - **`cloud_cost/ci`**: Store `slack_webhook` (Slack alert URL) and `infracost_key` (Infracost pricing key).
   - **`cloud_cost/docker`**: Store `username` and `password` for Docker Hub authentication.

---

Enjoy using the **AI Cloud Cost Detective** platform to optimize your cloud footprint! For roadmap details, please consult [devops_roadmap.md](file:///c:/ai_log/cloud_cost/devops_roadmap.md).
