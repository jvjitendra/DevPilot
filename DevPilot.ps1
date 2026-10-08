$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$app = Join-Path $frontend 'src\App.tsx'
$css = Join-Path $frontend 'src\styles.css'
$repos = Join-Path $backend 'app\api\repositories.py'
$main = Join-Path $backend 'main.py'
$auth = Join-Path $backend 'app\api\auth.py'

foreach ($p in @($backend,$frontend,$app,$css,$repos,$main,$auth)) {
    if (-not (Test-Path $p)) { throw "Missing required project path: $p" }
}

Write-Host "`n=== DEVPILOT CLEANUP ===" -ForegroundColor Cyan

# Remove only artifacts created by the earlier repair attempts.
$exactJunk = @(
    (Join-Path $root 'DevPilot_Final_Fix.py'),
    (Join-Path $root 'DevPilot_Surgical_Final_Fix.py'),
    (Join-Path $root 'DevPilot_Surgical_Final_Fix_V2.py'),
    (Join-Path $root 'DevPilot_Surgical_Final_Fix_V3.py'),
    (Join-Path $root 'README_APPLY.txt'),
    (Join-Path $root 'DEVPILOT_FULL_STRUCTURE.txt'),
    (Join-Path $root 'backend-patch'),
    (Join-Path $backend 'openapi_debug.json'),
    (Join-Path $backend 'app\github\client.py.backup'),
    (Join-Path $backend 'app\api\session_repositories.py'),
    (Join-Path $frontend 'tsconfig.tsbuildinfo'),
    (Join-Path $frontend 'APPLY.txt'),
    (Join-Path $frontend 'README.txt'),
    (Join-Path $frontend 'src\APPLY.txt'),
    (Join-Path $root 'backend_server.log'),
    (Join-Path $root 'frontend_server.log')
)

foreach ($p in $exactJunk) {
    if (Test-Path $p) {
        Remove-Item $p -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "removed: $p"
    }
}

# Remove duplicate/backup repository copies and generated repair backups.
Get-ChildItem (Join-Path $backend 'app\api') -File -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -in @(
            'repositories(1).py',
            'repositories (1).py'
        ) -or
        $_.Name -like 'repositories.py.surgical_*.bak'
    } |
    Remove-Item -Force -ErrorAction SilentlyContinue

Get-ChildItem (Join-Path $frontend 'src') -File -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -like 'App.tsx.*.bak' -or
        $_.Name -like 'styles.css.*.bak' -or
        $_.Name -like 'App.tsx.before-*' -or
        $_.Name -like 'styles.css.before-*'
    } |
    Remove-Item -Force -ErrorAction SilentlyContinue

Get-ChildItem $backend -Directory -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like '.github_fetch_backup_*' -or $_.Name -like '.github_fetch_fix_backup_*' } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Get-ChildItem $root -Directory -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like '.devpilot_final_fix_backup_*' } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# Python/Vite caches: do not touch backend\.venv.
Get-ChildItem $backend -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notlike "$backend\.venv\*" } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Get-ChildItem $backend -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object {
        ($_.Extension -in @('.pyc','.pyo')) -and
        ($_.FullName -notlike "$backend\.venv\*")
    } |
    Remove-Item -Force -ErrorAction SilentlyContinue

Remove-Item (Join-Path $frontend 'node_modules\.vite') -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $frontend 'node_modules\.vite-temp') -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $frontend 'dist') -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "cleanup done." -ForegroundColor Green

Write-Host "`n=== CANONICAL GITHUB SESSION ROUTE ===" -ForegroundColor Cyan

# Frontend now uses the session-aware routes that already live in one canonical
# repositories.py router. No second session_repositories.py module is needed.
$af = [IO.File]::ReadAllText($app)
$af = $af.Replace('/github/session/repositories/${repo.owner}/${repo.repo}/tree', '/repositories/${repo.owner}/${repo.repo}/tree-session')
$af = $af.Replace('/github/session/repositories/${repo.owner}/${repo.repo}/file?path=', '/repositories/${repo.owner}/${repo.repo}/file-session?path=')
$af = $af.Replace('/github/session/repositories', '/repositories/session')
$af = $af.Replace('const options = repos.filter(r => r.full_name).slice(0, 30)', 'const options = repos.filter(r => r.full_name)')
$af = $af.Replace("const [repo, setRepo] = useState(DEFAULT_REPO)", "const [repo, setRepo] = useState(DEFAULT_REPO)")  # explicit no-op: preserve state shape

$dashboardFetchOld = "  useEffect(() => { api<{ repositories: Repo[] }>('/repositories').then(d => setRepos(d.repositories || [])).catch(() => setRepos([])) }, [])"
$dashboardFetchNew = @'
  useEffect(() => {
    api<{ repositories: Repo[] }>('/repositories/session').then(d => {
      const list = d.repositories || []
      setRepos(list)
      const current = `${repo.owner}/${repo.repo}`
      if (list.length && !list.some(r => r.full_name === current)) {
        const [owner, name] = list[0].full_name.split('/')
        if (owner && name) setRepo({ owner, repo: name })
      }
    }).catch(() => setRepos([]))
  }, [])
'@
if ($af.Contains($dashboardFetchOld)) {
    $af = $af.Replace($dashboardFetchOld, $dashboardFetchNew)
}

# Fix the visible duplicate auth check only when the exact older duplicate is present.
# The primary auth effect stays untouched.
$duplicateAuth = @'
  useEffect(() => { const authSuccess = new URLSearchParams(window.location.search).get('auth') === 'success'; if (authSuccess) { setSignedIn(true); window.history.replaceState({}, '', window.location.pathname) }; api<{ authenticated: boolean }>('/auth/me').then(d => { if (d.authenticated) setSignedIn(true); else if (!authSuccess) setSignedIn(false) }).catch(() => { if (!authSuccess) setSignedIn(false) }) }, [])
'@
if ($af.Contains($duplicateAuth)) {
    $af = $af.Replace($duplicateAuth, '')
}

[IO.File]::WriteAllText($app, $af, (New-Object Text.UTF8Encoding($false)))

# Canonicalize the existing large repository router:
# remove the duplicate trailing session layer only if a separate session module
# had been removed. Instead, retain the trailing session routes and make their
# Request import explicit. The legacy endpoints are also made session-aware.
$rf = [IO.File]::ReadAllText($repos)

if ($rf -notmatch 'from fastapi import [^\r\n]*Request') {
    $rf = $rf.Replace(
        'from fastapi import APIRouter, Cookie, HTTPException',
        'from fastapi import APIRouter, Cookie, HTTPException, Request'
    )
}



$signatureMap = @{
    "def get_repository_tree(`r`n    owner: str,`r`n    repo: str,`r`n):" = "def get_repository_tree(`r`n    owner: str,`r`n    repo: str,`r`n    devpilot_session: str | None = Cookie(default=None),`r`n):"
    "def get_repository_issues(`r`n    owner: str,`r`n    repo: str,`r`n):" = "def get_repository_issues(`r`n    owner: str,`r`n    repo: str,`r`n    devpilot_session: str | None = Cookie(default=None),`r`n):"
    "def search_repository_code(`r`n    owner: str,`r`n    repo: str,`r`n    q: str,`r`n):" = "def search_repository_code(`r`n    owner: str,`r`n    repo: str,`r`n    q: str,`r`n    devpilot_session: str | None = Cookie(default=None),`r`n):"
    "def get_issue_context(`r`n    owner: str,`r`n    repo: str,`r`n    issue_number: int,`r`n):" = "def get_issue_context(`r`n    owner: str,`r`n    repo: str,`r`n    issue_number: int,`r`n    devpilot_session: str | None = Cookie(default=None),`r`n):"
    "def get_issue_context_code(`r`n    owner: str,`r`n    repo: str,`r`n    issue_number: int,`r`n):" = "def get_issue_context_code(`r`n    owner: str,`r`n    repo: str,`r`n    issue_number: int,`r`n    devpilot_session: str | None = Cookie(default=None),`r`n):"
    "def get_repository_file(`r`n    owner: str,`r`n    repo: str,`r`n    path: str,`r`n):" = "def get_repository_file(`r`n    owner: str,`r`n    repo: str,`r`n    path: str,`r`n    devpilot_session: str | None = Cookie(default=None),`r`n):"
}
foreach ($pair in $signatureMap.GetEnumerator()) {
    $rf = $rf.Replace($pair.Key, $pair.Value)
}

[IO.File]::WriteAllText($repos, $rf, (New-Object Text.UTF8Encoding($false)))

# Actual main.py is the FastAPI entrypoint. Keep both local origins valid and
# remove any stale registration of the deleted duplicate router.
$mf = [IO.File]::ReadAllText($main)
$mf = [regex]::Replace(
    $mf,
    'allow_origins\s*=\s*\[[^\]]*\]',
    'allow_origins=["http://localhost:5173","http://127.0.0.1:5173"]',
    1
)
$mf = [regex]::Replace(
    $mf,
    '(?m)^\s*from app\.api\.session_repositories import router as session_repositories_router\s*\r?\n?',
    ''
)
$mf = [regex]::Replace(
    $mf,
    '(?m)^\s*app\.include_router\(session_repositories_router.*\)\s*\r?\n?',
    ''
)
[IO.File]::WriteAllText($main, $mf, (New-Object Text.UTF8Encoding($false)))

$authText = [IO.File]::ReadAllText($auth)
$authText = $authText.Replace('FRONTEND_URL = "http://localhost:5173"', 'FRONTEND_URL = "http://127.0.0.1:5173"')
[IO.File]::WriteAllText($auth, $authText, (New-Object Text.UTF8Encoding($false)))

Write-Host "source cleanup + session canonicalization done." -ForegroundColor Green

# UI-only layer: no Developer Profile geometry/positions/fonts are changed.
$existingCss = [IO.File]::ReadAllText($css)
if ($existingCss -notmatch 'DEVPILOT ONE-CANONICAL UI LAYER') {
$uiCss = @'

/* =========================================================
   DEVPILOT ONE-CANONICAL UI LAYER
   Hover/interaction polish only. Existing profile geometry,
   typography and entrance animations remain untouched.
   ========================================================= */

/* Three dashboard repository shortcuts: distinct hover language. */
.side-live .repo-mini-button{
  cursor:pointer;
  transition:border-color .22s ease,background .22s ease,box-shadow .24s ease,filter .24s ease;
}
.side-live .quick-repo-devpilot:hover{
  background:linear-gradient(90deg,rgba(24,84,111,.18),rgba(8,25,36,.08));
  border-bottom-color:rgba(103,232,249,.30);
  box-shadow:inset 2px 0 rgba(103,232,249,.46),0 0 20px rgba(103,232,249,.08);
}
.side-live .quick-repo-vaani:hover{
  background:linear-gradient(90deg,rgba(55,88,122,.18),rgba(9,23,37,.08));
  border-bottom-color:rgba(126,205,255,.28);
  box-shadow:inset 2px 0 rgba(126,205,255,.40),0 0 20px rgba(126,205,255,.07);
}
.side-live .quick-repo-taskflow:hover{
  background:linear-gradient(90deg,rgba(36,93,83,.17),rgba(8,26,27,.08));
  border-bottom-color:rgba(99,230,174,.27);
  box-shadow:inset 2px 0 rgba(99,230,174,.38),0 0 20px rgba(99,230,174,.06);
}
.side-live .repo-mini-button:focus-visible{
  outline:1px solid rgba(103,232,249,.55);
  outline-offset:2px;
}

/* Chain of custody: 1 -> 2 -> ... -> 9, pause at node, advance link. */
.flow-step .flow-node{
  animation:custodyNode 10.8s linear infinite !important;
}
.flow-step:not(:last-child)::after{
  transform-origin:left center !important;
  animation:custodyLink 10.8s linear infinite !important;
}
.flow-step-1 .flow-node,.flow-step-1::after{animation-delay:0s!important}
.flow-step-2 .flow-node,.flow-step-2::after{animation-delay:1.2s!important}
.flow-step-3 .flow-node,.flow-step-3::after{animation-delay:2.4s!important}
.flow-step-4 .flow-node,.flow-step-4::after{animation-delay:3.6s!important}
.flow-step-5 .flow-node,.flow-step-5::after{animation-delay:4.8s!important}
.flow-step-6 .flow-node,.flow-step-6::after{animation-delay:6s!important}
.flow-step-7 .flow-node,.flow-step-7::after{animation-delay:7.2s!important}
.flow-step-8 .flow-node,.flow-step-8::after{animation-delay:8.4s!important}
.flow-step-9 .flow-node,.flow-step-9::after{animation-delay:9.6s!important}

@keyframes custodyNode{
  0%,3%{color:#577489;border-color:rgba(88,167,213,.22);background:#081722;box-shadow:0 0 0 rgba(78,174,220,0)}
  4%,7%{color:#a1ecff;border-color:#4eaedc;background:rgba(44,126,165,.15);box-shadow:0 0 25px rgba(78,174,220,.34),inset 0 0 12px rgba(103,232,249,.08)}
  8%,100%{color:#577489;border-color:rgba(88,167,213,.22);background:#081722;box-shadow:0 0 0 rgba(78,174,220,0)}
}
@keyframes custodyLink{
  0%,7%{transform:scaleX(0);opacity:.10;background:rgba(92,159,194,.20)}
  8%,11%{transform:scaleX(1);opacity:1;background:linear-gradient(90deg,rgba(103,232,249,.78),rgba(92,159,194,.28))}
  12%,100%{transform:scaleX(1);opacity:.18;background:rgba(92,159,194,.20)}
}

/* Developer Profile: different hover response per section only. */
.developer-modal .about-section:hover{background:linear-gradient(115deg,rgba(9,36,52,.26),rgba(6,18,28,.08));box-shadow:inset 0 1px rgba(103,232,249,.16),0 0 22px rgba(103,232,249,.06)}
.developer-modal .education-section:hover{box-shadow:inset 2px 0 rgba(103,232,249,.30),0 0 20px rgba(72,175,220,.05)}
.developer-modal .leadership-section:hover{box-shadow:0 0 22px rgba(99,230,174,.06),inset 0 1px rgba(99,230,174,.11)}
.developer-modal .build-section:hover{box-shadow:inset 0 -1px rgba(113,180,255,.14),0 0 22px rgba(113,180,255,.06)}
.developer-modal .skills-section:hover{box-shadow:0 0 22px rgba(126,205,255,.06),inset 0 1px rgba(126,205,255,.10)}
.developer-modal .projects-section:hover{background:linear-gradient(135deg,rgba(10,35,50,.16),rgba(4,14,22,.05));box-shadow:0 0 28px rgba(103,232,249,.08)}
.developer-modal .certifications-section:hover{box-shadow:inset 0 1px rgba(103,232,249,.14),0 0 24px rgba(103,232,249,.07)}
.developer-modal .languages-section:hover{box-shadow:inset 3px 0 rgba(126,205,255,.20),0 0 18px rgba(78,166,220,.05)}
.developer-modal .beyond-section:hover{box-shadow:0 0 20px rgba(245,198,109,.05),inset 0 1px rgba(245,198,109,.08)}
.developer-modal .exploring-section:hover{box-shadow:0 0 24px rgba(103,232,249,.08),inset 0 1px rgba(103,232,249,.14)}

/* Repository dropdown: full fetched list, readable scroll. */
.repo-select{position:relative;z-index:30}
.repo-select-menu{
  z-index:60!important;
  max-height:340px;
  overflow-y:auto;
  overscroll-behavior:contain;
  scrollbar-width:thin;
  scrollbar-color:#28637f #06111a;
}
.repo-select-menu::-webkit-scrollbar{width:9px}
.repo-select-menu::-webkit-scrollbar-track{background:#06111a}
.repo-select-menu::-webkit-scrollbar-thumb{background:#28637f;border:2px solid #06111a;border-radius:999px}
.repo-select-menu::-webkit-scrollbar-thumb:hover{background:#3a89aa}

/* Repository inspector: fixed overlay, full available surface. */
.repo-quick-backdrop{
  position:fixed;
  inset:0;
  z-index:1600;
  display:flex;
  justify-content:flex-end;
  background:rgba(1,6,10,.70);
  backdrop-filter:blur(7px);
}
.repo-quick-drawer{
  width:min(1180px,94vw);
  height:100vh;
  display:flex;
  flex-direction:column;
  overflow:hidden;
  background:#06131d;
  border-left:1px solid rgba(87,173,220,.25);
  box-shadow:-26px 0 72px rgba(0,0,0,.45);
  animation:repoDrawerIn .26s ease both;
}
@keyframes repoDrawerIn{from{opacity:0;transform:translateX(22px)}to{opacity:1;transform:translateX(0)}}
.repo-quick-head{
  min-height:88px;
  flex:0 0 88px;
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:16px;
  padding:20px 24px 16px;
  border-bottom:1px solid rgba(255,255,255,.07);
}
.repo-quick-head h2{margin:5px 0 2px;font-size:22px;line-height:1.2;color:#eaf6fb}
.repo-quick-head small{color:#7894a6;font-size:10px}
.repo-quick-body{
  flex:1;
  min-height:0;
  display:grid;
  grid-template-columns:minmax(280px,35%) minmax(0,65%);
}
.repo-quick-tree,.repo-quick-code{
  min-width:0;
  min-height:0;
  display:flex;
  flex-direction:column;
  overflow:hidden;
}
.repo-quick-tree{border-right:1px solid rgba(255,255,255,.06)}
.repo-quick-section-head{
  height:42px;
  flex:0 0 42px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  padding:0 14px;
  border-bottom:1px solid rgba(255,255,255,.06);
  color:#72c8ef;
}
.quick-tree-list{
  flex:1;
  min-height:0;
  overflow:auto;
  scrollbar-width:thin;
  scrollbar-color:#285e78 #06111a;
}
.quick-tree-list::-webkit-scrollbar,.repo-quick-code pre::-webkit-scrollbar{width:10px}
.quick-tree-list::-webkit-scrollbar-track,.repo-quick-code pre::-webkit-scrollbar-track{background:#06111a}
.quick-tree-list::-webkit-scrollbar-thumb,.repo-quick-code pre::-webkit-scrollbar-thumb{background:#285e78;border:2px solid #06111a;border-radius:999px}
.quick-tree-list::-webkit-scrollbar-thumb:hover,.repo-quick-code pre::-webkit-scrollbar-thumb:hover{background:#3a89aa}
.quick-tree-row{
  width:100%;
  min-height:31px;
  display:flex;
  align-items:center;
  gap:8px;
  padding-right:12px;
  border:0;
  border-bottom:1px solid rgba(255,255,255,.025);
  background:transparent;
  color:#9fb6c3;
  text-align:left;
}
button.quick-tree-row.file-row{cursor:pointer}
button.quick-tree-row.file-row:hover{background:rgba(103,232,249,.055);color:#dcf6ff}
.quick-tree-row code{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font:500 10px/1.25 "JetBrains Mono",monospace}
.quick-tree-row>span{width:30px;flex:0 0 30px;color:#5e8193;font:700 7px "JetBrains Mono",monospace}
.repo-quick-code pre{
  flex:1;
  min-height:0;
  overflow:auto;
  margin:0;
  padding:14px 0 24px;
  background:#041019;
  color:#cadde6;
  font:500 11px/1.65 "JetBrains Mono",monospace;
  white-space:pre;
  tab-size:4;
}
.repo-quick-code pre:hover{background:#041019}
.quick-code-empty,.repo-quick-tree .loading,.repo-quick-tree .empty-state{
  flex:1;
  min-height:0;
  display:grid;
  place-items:center;
}
.close-small{
  width:36px;
  height:36px;
  flex:0 0 36px;
  display:grid;
  place-items:center;
  border:1px solid rgba(87,173,220,.28)!important;
  border-radius:9px;
  background:#0a1d2a!important;
  color:#a8c7d5!important;
  cursor:pointer;
  transition:border-color .20s ease,box-shadow .20s ease,background .20s ease,color .20s ease;
}
.close-small:hover{
  border-color:rgba(103,232,249,.55)!important;
  background:#0e2939!important;
  color:#f2fcff!important;
  box-shadow:0 0 18px rgba(103,232,249,.13);
}
@media(max-width:800px){
  .repo-quick-drawer{width:100vw}
  .repo-quick-body{grid-template-columns:42% 58%}
}
'@
    $existingCss += $uiCss
    [IO.File]::WriteAllText($css, $existingCss, (New-Object Text.UTF8Encoding($false)))
}

Write-Host "`n=== VALIDATION ===" -ForegroundColor Cyan

$py = Join-Path $backend '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { throw "Backend venv Python not found: $py" }

& $py -m py_compile $main $auth $repos
if ($LASTEXITCODE -ne 0) { throw 'Backend syntax validation failed.' }

Push-Location $frontend
try {
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
}
finally {
    Pop-Location
}

Write-Host "`n=== STARTING IN THIS VS CODE TERMINAL ===" -ForegroundColor Cyan

Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object {
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    }

Start-Sleep -Seconds 1

$backendProc = Start-Process `
    -FilePath $py `
    -WorkingDirectory $backend `
    -ArgumentList '-m','uvicorn','main:app','--reload','--host','127.0.0.1','--port','8000' `
    -NoNewWindow `
    -PassThru

$frontendProc = Start-Process `
    -FilePath 'cmd.exe' `
    -WorkingDirectory $frontend `
    -ArgumentList '/d','/c','npm.cmd run dev -- --host 127.0.0.1' `
    -NoNewWindow `
    -PassThru

Start-Sleep -Seconds 5

Write-Host "`n=== PORT STATUS ===" -ForegroundColor Green
Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -ErrorAction SilentlyContinue |
    Select-Object LocalAddress,LocalPort,State |
    Format-Table -AutoSize

if (-not (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)) {
    throw 'Backend did not start on port 8000.'
}
if (-not (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue)) {
    throw 'Frontend did not start on port 5173.'
}

Write-Host "`nDevPilot is running in this VS Code terminal." -ForegroundColor Green
Write-Host "Browser: http://127.0.0.1:5173"
Write-Host "Use Ctrl+C in this terminal to stop the launcher." -ForegroundColor DarkGray

try {
    while ($true) {
        Start-Sleep -Seconds 2
        if ($backendProc.HasExited -or $frontendProc.HasExited) {
            Write-Host "`nA DevPilot process stopped. Check the terminal output above." -ForegroundColor Yellow
            break
        }
    }
}
finally {
    if ($backendProc -and -not $backendProc.HasExited) {
        Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
    }
    if ($frontendProc -and -not $frontendProc.HasExited) {
        Stop-Process -Id $frontendProc.Id -Force -ErrorAction SilentlyContinue
    }
}


