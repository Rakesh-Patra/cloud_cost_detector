# FinOps Cost Detective — DevSecOps & Git Safety

This repository contains the containerized **AI Cloud Cost Detective Dashboard** (FastAPI backend + Vite/React frontend). 

To ensure credentials, keys, and local test configurations never leak, the repository is guarded by a comprehensive **DevSecOps for Git** pipeline. This document outlines how to safely configure, test, and push the codebase.

---

## 🛡️ Git Security Architecture

```
[Local Code Changes]
      │
      ├──> [Step 1: .gitignore] (Blocks untracked secrets / node_modules)
      │
      ├──> [Step 2: Native Pre-Commit Hook] (Blocks commits with word 'secret')
      │
      ├──> [Step 3: Gitleaks Local Hook] (Blocks commits with regex/AWS credentials)
      │
      └──> [git commit]
            │
            └──> [git push]
                  │
                  └──> [Step 4: GitHub Actions Gitleaks] (History & PR verification)
```

---

## 1️⃣ `.gitignore` — First Line of Defense

### Purpose
To prevent sensitive files, local environment variables, build outputs, and bulky dependencies from ever being tracked by Git.

### Common Security Files Ignored in this Project
- **`.env` / `.env.*`** — Stores SMTP passwords, API keys, and private database credentials.
- **`*.pem` / `*.key` / `id_rsa`** — Private SSH and encryption keys.
- **`backend/*.sqlite3`** — Local database files containing audit configurations.
- **`node_modules/`** — Frontend dependencies.
- **`dist/`** — Compiled production assets.

> [!WARNING]
> `.gitignore` **only** prevents untracked files from being added. It **does NOT** protect or remove secrets that have *already* been committed in Git history.

---

## 2️⃣ Local Verification (Shift-Left Commit Guards)

### A. Native Git Pre-Commit Hook (Custom Script)
A native pre-commit hook is a bash script executed automatically by Git before any commit is finalized.

- **Location:** Located at [`.git/hooks/pre-commit`](file:///c:/ai_log/cloud_cost/.git/hooks/pre-commit)
- **Exit Codes:**
  - `0`: Commit allowed (passed).
  - `≠ 0`: Commit blocked (failed).

#### Activation (Git Bash / Linux / macOS):
To make the native hook executable:
```bash
chmod +x .git/hooks/pre-commit
```

---

### B. Gitleaks Integration (Local Hook Config)
Gitleaks is a SAST tool designed to scan files for credentials, private keys, and API tokens.

We have configured a pre-commit config framework [`.pre-commit-config.yaml`](file:///c:/ai_log/cloud_cost/.pre-commit-config.yaml):
```yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.24.2
    hooks:
      - id: gitleaks
```

#### How to install and activate Gitleaks locally:
1. **Install python pre-commit package manager:**
   - On Windows (PowerShell/CMD): `pip install pre-commit` or `choco install pre-commit`
   - On macOS: `brew install pre-commit`
2. **Register the Gitleaks hook in Git:**
   - Run: `pre-commit install`
3. **Optional (Auto-update hooks to latest versions):**
   - Run: `pre-commit autoupdate`

---

## 3️⃣ Repository & History Scanning

### Custom Detection Rules
We use a [`custom-rules.toml`](file:///c:/ai_log/cloud_cost/custom-rules.toml) ruleset to define custom checks, such as blocking assignment of strings containing passwords:
```toml
[[rules]]
id = "generic-password"
description = "Detect any PASSWORD assignment"
regex = '''(?i)password\s*=\s*["'][^"']+["']'''
tags = ["password", "custom"]
```

### Scan Local History
To scan your local commit logs and file history for leaks:
```bash
gitleaks detect --config custom-rules.toml --verbose
```

---

## 4️⃣ Remote Security Verification (GitHub Integration)

### A. GitHub Actions (Continuous Secret Scanning)
On push or pull requests to the remote repository, GitHub automatically spins up a Gitleaks runner via the configuration at [`.github/workflows/gitleaks.yml`](file:///c:/ai_log/cloud_cost/.github/workflows/gitleaks.yml) to scan all historic commits:

```yaml
name: gitleaks
on: [pull_request, push, workflow_dispatch]
jobs:
  scan:
    name: gitleaks
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### B. CODEOWNERS Review Rules
We use [`.github/CODEOWNERS`](file:///c:/ai_log/cloud_cost/.github/CODEOWNERS) to enforce review guidelines on critical files before merging pull requests:
- `/.github/` files (Workflows/Security policies) require approval from `@security-team`.
- `/backend/` code requires approval from `@cloud-team`.

### C. Dependabot Automated Updates
Dependabot is active via [`.github/dependabot.yml`](file:///c:/ai_log/cloud_cost/.github/dependabot.yml) to inspect your `npm` packages and `pip` requirements weekly and automatically open Pull Requests when vulnerable versions or updates are found.

---

## 🔑 GitHub Administrative Security Policies

When you push this codebase to GitHub, configure these **Settings** on your remote repository:

### 🛡️ 1. Branch Protection Rules (For the `main` branch)
1. Go to **Settings > Branches > Add branch protection rule**.
2. Set Branch name pattern to: `main`.
3. Check the following:
   - **Require a pull request before merging:** Enforces code reviews; blocks direct pushing to `main`.
   - **Require approvals:** Set to at least `1` reviewer.
   - **Require status checks to pass before merging:** Enable this and search for the `gitleaks` status check (preventing code with secrets from merging).
   - **Do not allow force pushes:** Prevents malicious developers from rewriting history to cover up secret leaks.

### 👥 2. RBAC (Least Privilege Access Control)
Limit access to your repository by assigning roles:
- **Admin:** Enforces repository settings, branch protection rules, and secrets configuration.
- **Maintainer:** Reviews and merges pull requests, handles releases.
- **Developer:** Cannot merge to `main` directly. Must write code on a branch, run tests, and open pull requests.
- **Auditor:** Read-only access to view logs and configurations.

---

## 🏁 Step-by-Step Guide to Push Code

Follow these commands in sequence to verify, commit, and push this codebase safely:

### Step 1: Verify Ignored Files
Verify that `.env` files and SQLite databases are NOT staged:
```bash
git status
```
*(Ensure `.env` and `db.sqlite3` do not appear under "Untracked files")*

### Step 2: Test the Native Pre-commit Hook
1. Create a file containing a mock secret:
   ```bash
   echo "my_secret_token = 'ABC1234'" > test.txt
   ```
2. Attempt to commit it:
   ```bash
   git add test.txt
   git commit -m "test commit"
   ```
3. **Verify:** Git must block the commit and exit with `❌ Secret detected. Commit blocked.`
4. Remove the test file:
   ```bash
   git reset test.txt
   rm test.txt
   ```

### Step 3: Run the initial Git commit
Once clean, stage the valid project files and commit them:
```bash
git add .
git commit -m "Initial DevSecOps containerized setup"
```

### Step 4: Push to GitHub
Create the remote repository on GitHub, then link and push:
```bash
# Rename branch to main
git branch -M main

# Add your remote GitHub repo URL
git remote add origin https://github.com/your-username/cloud-cost-detective.git

# Push the code
git push -u origin main
```
