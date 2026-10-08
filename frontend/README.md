# DevPilot Frontend Redesign

This is a complete UI redesign of the existing DevPilot frontend. File names are intentionally unchanged inside `src/` (`App.tsx`, `styles.css`, `main.tsx`, `vite-env.d.ts`).

## Run

```powershell
npm install
npm run dev
```

Frontend: `http://localhost:5173`
Backend: `http://127.0.0.1:8000`

The frontend talks to the existing DevPilot API at `http://127.0.0.1:8000/api`.

## Primary product areas

- Dashboard / agent launch
- Live GitHub repositories
- GitHub issue intake and analysis
- Agent runs
- AI patch generation and Apply & Test
- Human approval and Pull Request delivery
- Test laboratory
- Audit logs
- Developer profile
- Safety settings
- Ctrl/Cmd + K command center
