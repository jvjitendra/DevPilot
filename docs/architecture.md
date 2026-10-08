# DevPilot Architecture

## V1
Frontend (React/TypeScript) → FastAPI API → agent orchestration → GitHub/AI/retrieval/testing services → PostgreSQL.

### Retrieval
Use hybrid retrieval: deterministic filename/content search plus semantic vector retrieval. Both feed a common context builder. Vector retrieval is an optimization and must not be the only retrieval path.

### Agent safety boundary
Repository content is untrusted input. Tool permissions and security rules always outrank repository instructions. Destructive shell commands, force pushes, secrets access, repository deletion and permission changes are blocked or require explicit intervention.

### Mutation flow
AI analysis → plan → patch → tests → diff/scope review → human approval → isolated branch → commit → PR.
