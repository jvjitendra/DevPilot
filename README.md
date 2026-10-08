# DevPilot

AI-assisted software engineering agent for GitHub repositories.

## V1 workflow
GitHub Issue → Repository Understanding → Hybrid Code Retrieval → Root Cause → Plan → Patch → Tests → Human Approval → Branch → Commit → Pull Request

## Stack
- Frontend: React + TypeScript + Vite
- Backend: Python + FastAPI
- Database: PostgreSQL (Neon-compatible)
- AI: provider abstraction for Gemini/Groq
- Source control/CI: GitHub + GitHub Actions
- Retrieval: deterministic code search + vector retrieval layer

## Safety
- Human approval before branch/commit/PR
- Isolated branch workflow
- Change-scope guard
- Secret redaction
- Safe-command allowlist
- Maximum 3 automated test-repair retries
- Audit logging
- STOP AGENT control

## Development
Frontend:
```bash
cd frontend
npm install
npm run dev
```

Backend:
```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn main:app --reload
```
