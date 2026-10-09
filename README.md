# DevPilot

> **AI Software Engineering Agent for GitHub Repositories**<br>
> Connects directly to authorized GitHub repositories to analyze issues, navigate code topology, generate surgical diff patches, and execute isolated verification suites with human-in-the-loop approval.

---

## 1. Overview & Verified Features

DevPilot combines deterministic codebase analysis with modern LLM capabilities to automate the issue-to-patch lifecycle while preserving strict code safety and developer control.

- **GitHub OAuth 2.0 with PKCE:** Secure public authentication using Proof Key for Code Exchange (S256), CSRF state cookies, and encrypted session management.
- **Encrypted Session Store:** Fernet AES-128 token encryption at rest backed by SQLite/SQLAlchemy.
- **Repository Surface Explorer:** Inspect live branches, file trees, source files, and open issue trackers directly from GitHub.
- **Deterministic Code Retrieval:** Anchor-weighted keyword extraction, symbol identification, and implementation scoring to locate relevant files without sending entire repositories to LLMs.
- **Multi-Tiered AI Pipeline:**
  - **Analyzer:** Pinpoints root cause, components involved, and confidence score.
  - **Planner:** Generates step-by-step implementation plans and risk assessments.
  - **Patcher:** Produces surgical unified diff patches in memory.
  - **Test Generator:** Synthesizes targeted test plans and test assertions.
  - **Heuristic Fallback Engine:** Deterministic rule-based fallback operates even when external AI providers are offline or rate-limited.
- **Sandbox Patch Safety:** Isolated temporary workspace clones (`tempfile.mkdtemp`) with path-traversal prevention, protected-file guards (`.env`, `.git`), and automatic transactional rollbacks.
- **Liquid Glass Interface:** Fully responsive dark navy and cyan UI with smooth section transitions, keyboard navigation (Ctrl+K), and creator profile attribution.

---

## 2. Architecture & Technology Stack

```
┌────────────────────────────────────────────────────────┐
│             DevPilot SPA (React + TypeScript)          │
│         Liquid Glass Navigation • Real-time UI         │
└───────────────────────────┬────────────────────────────┘
                            │ HTTP / REST (Credentials included)
┌───────────────────────────▼────────────────────────────┐
│                  FastAPI Backend Server                │
│    Auth (PKCE) • Repositories • Analysis • Sandboxing  │
└──────┬────────────────────┬────────────────────┬───────┘
       │                    │                    │
┌──────▼──────┐      ┌──────▼──────┐      ┌──────▼──────┐
│ GitHub API  │      │  AI Engines │      │  SQLite DB  │
│ OAuth, Repos│      │Gemini / Groq│      │Encrypted Ssn│
│ Trees,Issues│      │  + Fallback │      │    Store    │
└─────────────┘      └─────────────┘      └─────────────┘
```

- **Frontend:** React 19, TypeScript, Vite, Lucide Icons
- **Backend:** Python 3.10+, FastAPI, Starlette, Pydantic v2, HTTPX, SQLAlchemy, Cryptography (Fernet)
- **AI Models:**
  - Primary: Google Gemini (`gemini-flash-latest`, `gemini-flash-lite-latest`) via `google-genai` SDK
  - Secondary: Groq Cloud (`qwen/qwen3.8-27b`) via `groq` SDK
  - Fallback: Deterministic AST & regex pattern heuristics
- **Testing:** Pytest, FastAPI TestClient

---

## 3. Project Directory Structure

```
DevPilot/
├── .github/
│   └── workflows/backend.yml   # Continuous Integration workflow
├── backend/
│   ├── app/
│   │   ├── agents/             # Planning, patching, orchestrating agents
│   │   ├── ai/                 # Analyzer & prompt builders
│   │   ├── api/                # FastAPI routers (auth, repos, analysis, patches)
│   │   ├── auth/               # Session store & Fernet token encryption
│   │   ├── core/               # Configuration settings & environment loader
│   │   └── testing/            # Patch applicator, safety guards, sandbox runner
│   ├── tests/                  # Pytest unit & integration test suites
│   ├── .env.example            # Environment configuration template
│   ├── main.py                 # FastAPI application entry point
│   └── requirements.txt        # Backend Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.tsx             # Main application, views, routes & state
│   │   ├── main.tsx            # React application root
│   │   └── styles.css          # Liquid Glass design system & responsive layout
│   ├── index.html              # HTML shell
│   ├── package.json            # Node.js dependencies
│   └── vite.config.ts          # Vite bundler configuration
├── .gitignore                  # Git release exclusion rules
└── README.md                   # Project documentation
```

---

## 4. Prerequisites

- **Python:** 3.10, 3.11, 3.12, or 3.13
- **Node.js:** 18.x or newer (with npm)
- **Git:** Installed and available in PATH
- **GitHub OAuth App:** Required for user login

---

## 5. Getting Started

### 1. Clone Repository
```bash
git clone https://github.com/jvjitendra/DevPilot.git
cd DevPilot
```

### 2. Backend Setup
```bash
cd backend

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
```

Edit `backend/.env` with your credentials:
```ini
APP_ENV=development
GITHUB_CLIENT_ID=your_oauth_client_id
GITHUB_CLIENT_SECRET=your_oauth_client_secret
SESSION_SECRET_KEY=generate_with_python_secrets_token_urlsafe
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-flash-latest
GEMINI_FALLBACK_MODEL=gemini-flash-lite-latest
GROQ_API_KEY=your_groq_key
GROQ_MODEL=qwen/qwen3.8-27b
```

Run backend server:
```bash
uvicorn main:app --reload --port 8000
```
API runs on `http://127.0.0.1:8000`.

### 3. Frontend Setup
```bash
cd ../frontend

# Install dependencies
npm install

# Start development server
npm run dev
```
Application runs on `http://127.0.0.1:5173`.

---

## 6. GitHub OAuth Setup

To enable user sign-in:
1. Go to [GitHub Developer Settings → OAuth Apps](https://github.com/settings/developers).
2. Click **New OAuth App**.
3. Set **Application name:** `DevPilot`
4. Set **Homepage URL:** `http://127.0.0.1:5173`
5. Set **Authorization callback URL:** `http://127.0.0.1:8000/api/auth/github/callback`
6. Copy the **Client ID** and generate a **Client Secret**.
7. Paste into `backend/.env` as `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET`.

---

## 7. Testing & Production Verification

### Backend Test Suite
```bash
cd backend
python -m pytest
```
*Executes all unit tests covering authentication lifecycles, token resolution, health checks, and rollback safety.*

### Frontend Production Build
```bash
cd frontend
npm run build
```
*Compiles TypeScript and runs Vite production bundling into `frontend/dist/`.*

---

## 8. API Documentation

Interactive OpenAPI documentation is generated automatically by FastAPI:
- **Swagger UI:** `http://127.0.0.1:8000/docs`
- **ReDoc:** `http://127.0.0.1:8000/redoc`

Core endpoints:
- `GET /api/health` — Service health probe
- `GET /api/auth/github/login` — Initiates PKCE OAuth authorization
- `GET /api/auth/github/callback` — Handles OAuth code exchange
- `GET /api/auth/me` — Returns current authenticated user
- `POST /api/auth/logout` — Destroys active session
- `GET /api/repositories/session` — Lists user's authorized GitHub repositories
- `GET /api/repositories/{owner}/{repo}/issues` — Fetches open issues
- `GET /api/repositories/{owner}/{repo}/issues/{number}/analyze` — AI issue analysis
- `GET /api/repositories/{owner}/{repo}/issues/{number}/plan` — AI implementation plan
- `GET /api/repositories/{owner}/{repo}/issues/{number}/patch` — In-memory unified diff patch
- `GET /api/repositories/{owner}/{repo}/issues/{number}/tests` — Target test plan generation
- `POST /api/repositories/{owner}/{repo}/apply-patch` — Sandboxed patch application

---

## 9. Known Limitations

- **Groq Free Tier Rate Limits:** The Groq on-demand free tier imposes an Output Token Per Minute (OTPM) quota. If exceeded, the engine backs off and surfaces actionable retry guidance.
- **Local Sandbox Execution:** Automated execution of generated test suites (`apply-and-test`) requires local build tools and language runtimes (e.g. `pytest`, `npm test`) available on the host machine.
- **Private Repository Access:** Accessing private repositories requires the signed-in user's OAuth account to hold collaborator or organization permissions for that repository.

---

## 10. License & Creator Credit

DevPilot is designed and created by **Jitendra Kumar Verma** ([@jvjitendra](https://github.com/jvjitendra)).
Released under the MIT License.
