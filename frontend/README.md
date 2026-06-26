# ⚛️ AI Cloud Cost Detective — React Frontend Application

This directory houses the client-side single-page web app built on **Vite**, **React**, **TypeScript**, and **Tailwind CSS**. It provides a glassmorphic dashboard for triggering audits, visualizing progress, configuring budget guardrails, auditing anomaly logs, and chatting with an AI FinOps assistant.

---

## 🎨 Page & Routing Guides

- **[Login.tsx](file:///c:/ai_log/cloud_cost/frontend/src/pages/Login.tsx) & [Signup.tsx](file:///c:/ai_log/cloud_cost/frontend/src/pages/Signup.tsx):** Handles user session authentication via InsForge JWT APIs.
- **[Dashboard.tsx](file:///c:/ai_log/cloud_cost/frontend/src/pages/Dashboard.tsx):** The core control screen. Lets users pick target AWS regions and trigger new scans. Displays real-time scan statuses.
- **[Report.tsx](file:///c:/ai_log/cloud_cost/frontend/src/pages/Report.tsx):** Renders structured optimization cards returned from Gemini AI, highlighting estimated savings and providing "Remediate" buttons (e.g., to convert gp2 to gp3 storage).
- **[History.tsx](file:///c:/ai_log/cloud_cost/frontend/src/pages/History.tsx):** Displays a timeline log of all completed regional audits.
- **[Budgets.tsx](file:///c:/ai_log/cloud_cost/frontend/src/pages/Budgets.tsx):** Setting cost caps, charting daily spending trends, manual anomaly scanning triggers, and viewing alert delivery histories.

---

## 🧩 Shared Components

- **[ProgressTracker.tsx](file:///c:/ai_log/cloud_cost/frontend/src/components/ProgressTracker.tsx):** Interactive multi-step list linked directly to the backend progress WebSockets. Displays live checkmarks as scanning advances.
- **[FinOpsChat.tsx](file:///c:/ai_log/cloud_cost/frontend/src/components/FinOpsChat.tsx):** Chat drawer component providing direct messaging options with the FinOps assistant. Includes shortcut questions:
  - *"How do I upgrade gp2 to gp3?"*
  - *"Write a Terraform script for these fixes."*
  - *"Explain the high-severity issues."*
- **[Navbar.tsx](file:///c:/ai_log/cloud_cost/frontend/src/components/Navbar.tsx):** Navigation headers, active session displays, and log out options.

---

## 🚀 Getting Started

### 📦 Prerequisites
- **Node.js** (v18 or higher recommended)
- **npm** or **yarn** package manager

### 🛠️ Quick Local Setup

1. **Install Dependencies:**
   ```bash
   npm install
   ```

2. **Configure Environment Variables:**
   Create a `.env` file in the `frontend/` root folder:
   ```env
   VITE_BACKEND_URL=http://localhost:8000
   VITE_INSFORGE_PROJECT_URL=your_insforge_project_url
   VITE_INSFORGE_ANON_KEY=your_insforge_anon_key
   ```

3. **Start Dev Server:**
   ```bash
   npm run dev
   ```
   The application will start on **http://localhost:5173**.

4. **Production Build:**
   ```bash
   npm run build
   ```
   Build outputs will compile to the `dist/` directory.

---

## 🔒 Configuration Explanations

- **`VITE_BACKEND_URL`:** The endpoint location of the FastAPI server.
- **`VITE_INSFORGE_PROJECT_URL`:** The URL of the authentication & database hosting service.
- **`VITE_INSFORGE_ANON_KEY`:** Anonymous API key needed to start initial session authorizations.
