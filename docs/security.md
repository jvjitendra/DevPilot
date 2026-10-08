# Security Model

1. Permission gate
2. Change-scope guard
3. Safe command execution
4. Test and validation gate
5. Human approval
6. Audit and recovery

Secrets are redacted before model context/logging. Test repair loops stop after three retries. Main branch is never modified directly by the agent.
