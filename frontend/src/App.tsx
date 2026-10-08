import { type ReactNode, useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, Bot, CheckCircle2, ChevronDown, ChevronRight, CircleDot, Clock3,
  Code2, ExternalLink, FileCode2, GitBranch, GitCommitHorizontal, GitPullRequest,
  LayoutDashboard, Link2, Loader2, LogOut, Play, Plus, RefreshCw, Search,
  Server, Settings, ShieldCheck, Sparkles, Square, Terminal, TestTube2, UserRound, X,
  Zap
} from 'lucide-react'

const API = 'http://127.0.0.1:8000/api'
const DEFAULT_REPO = { owner: 'jvjitendra', repo: 'task-manager' }

type NavItem = { label: string; icon: typeof LayoutDashboard }
type Repo = {
  id?: number
  name: string
  full_name: string
  private?: boolean
  default_branch?: string
  language?: string | null
  html_url?: string
}
type Issue = { number: number; title: string; body?: string; state?: string; html_url?: string }
type AuthUser = { id?: number | string; login: string; name?: string | null; avatar_url?: string | null }
type AuditEvidence = { phase?: string; repo?: string; issue?: string; command?: string; result?: string; before?: string; after?: string; files?: string[]; evidence?: string; link?: string }
type LogItem = { time: string; text: string; kind?: 'info' | 'success' | 'active' | 'warning'; details?: AuditEvidence }

const nav: NavItem[] = [
  { label: 'Dashboard', icon: LayoutDashboard },
  { label: 'Repositories', icon: GitBranch },
  { label: 'Issues', icon: CircleDot },
  { label: 'Agent Runs', icon: Bot },
  { label: 'Code Changes', icon: FileCode2 },
  { label: 'Tests', icon: TestTube2 },
  { label: 'Pull Requests', icon: GitPullRequest },
  { label: 'Audit Logs', icon: Activity },
  { label: 'Settings', icon: Settings },
]

const profile = {
  name: 'Jitendra Kumar Verma',
  role: 'Backend & Full-Stack Developer',
  location: 'Ranchi, Jharkhand · India',
  intro: 'Backend & full-stack developer focused on turning real engineering problems into practical, reliable software across AI applications, APIs, databases, analytics and cloud technologies. I enjoy understanding how systems work end-to-end and building solutions that are structured, useful and maintainable.',
  story: 'My work includes DevPilot, an AI-assisted software engineering control plane for turning GitHub issues into structured engineering workflows; Vaani, an AI-focused workspace for conversational assistant experiences; and TaskFlow, a full-stack productivity platform for managing tasks and work. My hands-on work spans Python, JavaScript, REST APIs, SQL, databases, testing and deployment workflows.',
  education: 'B.E. Computer Science & Engineering · Chandigarh University · 2023–2026 · CGPA 7.32',
  leadership: 'Class Representative — LEET Student · Chandigarh University · 3rd–6th Semester · 2023–2025',
  leadershipDetail: 'Took ownership of high-pressure, time-sensitive coordination challenges, aligning students, faculty, schedules and requirements to get critical tasks completed within tight deadlines.',
  buildAreas: [
    ['AI & Intelligent Systems', 'AI applications · Vaani · AI workflows'],
    ['Backend Engineering', 'REST APIs · Databases · Server-side development'],
    ['Data & Analytics', 'SQL · Python · Power BI · Data processing'],
    ['Product Development', 'DevPilot · TaskFlow · E-commerce Backend · Experimental builds'],
  ],
  skills: ['Python', 'Java', 'C++', 'JavaScript', 'SQL', 'REST APIs', 'MySQL', 'PostgreSQL', 'SQLite', 'Git', 'GitHub', 'VS Code', 'Postman', 'Power BI', 'DAX', 'Power Query', 'Pandas', 'AI/ML fundamentals', 'HTML', 'CSS', 'Basic MERN'],
  certifications: [
    'Foundation of Cloud IoT & Edge Machine Learning (Elite) — IIT Kanpur | NPTEL-SWAYAM | 2025',
    'Cloud Computing (Elite) — IIT Kharagpur | NPTEL-SWAYAM | 2024',
    'Internet of Things: Design Concepts and Use Cases — NITTTR Chandigarh | SWAYAM | 2024 · 75%',
    'AI for Future Workforce Program — Certificate of Participation',
    'Introduction to Databases — Meta (Coursera)',
    'Programming for Everybody (Python) — University of Michigan (Coursera)',
    'Databases & SQL for Data Science with Python (Honours)',
    'AWS Certified Database — Specialty — AWS',
  ],
  leadershipSkills: ['Communication', 'Team Collaboration', 'Leadership & Ownership', 'Stakeholder Coordination', 'Problem Solving', 'Time-Critical Execution', 'Analytical Thinking', 'Continuous Learning'],
  languages: ['Hindi — Native', 'English — Fluent', 'Punjabi — Conversational', 'Odia — Conversational', 'Bengali — Understands'],
  beyond: ['Travel', 'Exploring New Places', 'Music', 'Adventure', 'Cooking', 'Motorcycling'],
  exploring: ['AI Applications', 'Backend Architecture', 'Developer Tools', 'Cloud Technologies', 'Data Products'],
}

const projects = [
  { no: 1, name: 'DevPilot', type: 'AI Software Engineering Workspace', description: 'Turns a GitHub issue into a structured engineering workflow from repository context and root-cause analysis through patch generation, testing and human-reviewed delivery.', why: 'Make AI-assisted engineering changes inspectable, controlled and accountable.', highlights: ['Analyzes issue and repository context', 'Generates focused changes and verification steps', 'Requires human approval before GitHub delivery'], stack: ['React', 'FastAPI', 'GitHub API', 'AI Agent'], live: null, github: null, current: true },
  { no: 2, name: 'Vaani', type: 'AI Workspace', description: 'Conversational AI workspace for assistant workflows, model selection, voice interaction and contextual AI.', why: 'Explore AI product experience beyond a basic chatbot.', highlights: ['Multi-model AI workspace', 'Voice, tools and contextual interaction', 'NVIDIA NIM model integration and AI workflow orchestration'], stack: ['AI', 'Flask', 'NVIDIA NIM', 'Product UI'], live: 'https://vaani-ai-workspace-frontend.vercel.app/', github: 'https://github.com/jvjitendra/vaani-ai-workspace', current: false },
  { no: 3, name: 'TaskFlow', type: 'Full-Stack Productivity Platform', description: 'Full-stack productivity platform for persistent task management and production-style task workflows.', why: 'Build a complete full-stack workflow around authentication, task state, persistence and API communication.', highlights: ['Authentication and persistent task state', 'Priorities and status', 'REST API + PostgreSQL'], stack: ['React', 'Flask', 'PostgreSQL', 'JWT'], live: 'https://task-manager-frontend-tau-lemon.vercel.app/', github: 'https://github.com/jvjitendra/task-manager', current: false },
  { no: 4, name: 'E-commerce Backend', type: 'Backend Engineering', description: 'Backend service for product, cart, order and payment-oriented API flows.', why: 'Practice commerce entities, server-side business logic and database operations.', highlights: ['Product, cart and order APIs', 'Database-backed operations', 'Razorpay-oriented payment integration'], stack: ['REST APIs', 'SQL', 'Payments'], live: null, github: null, current: false },
  { no: 5, name: 'Many More Projects', type: 'Experiments & Software Builds', description: 'Collection of academic and applied engineering builds across software, analytics, networking and backend development.', why: '', highlights: ['Java and C++ software projects', 'Python, SQL and Power BI analytics work', 'Networking, database and applied engineering experiments'], stack: ['Java', 'C++', 'Python', 'Power BI'], live: null, github: null, current: false },
]

const stages = ['Issue analyzed', 'Repository scanned', 'Relevant files identified', 'Root cause found', 'Plan generated', 'Patch generated', 'Tests running', 'Human review', 'Pull request']

function nowLabel() {
  return new Intl.DateTimeFormat('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true }).format(new Date())
}
function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning, Jitendra.' : h < 17 ? 'Good afternoon, Jitendra.' : 'Good evening, Jitendra.'
}
const heroMessages = ['Understanding the repository context…', 'Tracing the issue to its root cause…', 'Designing a focused implementation plan…', 'Preparing an isolated patch…', 'Running bounded verification…', 'Preparing changes for human review…']
function loadLogs(): LogItem[] {
  try { return JSON.parse(localStorage.getItem('devpilot_logs') || '[]') } catch { return [] }
}
function saveLog(text: string, kind: LogItem['kind'] = 'info', details: AuditEvidence = {}) {
  const next = [{ time: nowLabel(), text, kind, details }, ...loadLogs()].slice(0, 60)
  localStorage.setItem('devpilot_logs', JSON.stringify(next))
  window.dispatchEvent(new Event('devpilot-log'))
}
function loadRuns() {
  try { return JSON.parse(localStorage.getItem('devpilot_runs') || '[]') } catch { return [] }
}
function saveRun(run: unknown) {
  localStorage.setItem('devpilot_runs', JSON.stringify([run, ...loadRuns()].slice(0, 20)))
  window.dispatchEvent(new Event('devpilot-run'))
}
function loadDelivery() {
  try { return JSON.parse(localStorage.getItem('devpilot_delivery') || '{}') } catch { return {} }
}
function saveDelivery(patch: Record<string, unknown>) {
  const next = { ...loadDelivery(), ...patch, updated: nowLabel() }
  localStorage.setItem('devpilot_delivery', JSON.stringify(next))
  window.dispatchEvent(new Event('devpilot-delivery'))
}
async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, { ...options, credentials: 'include', headers: { 'Content-Type': 'application/json', ...(options?.headers || {}) } })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : JSON.stringify(data?.detail || data))
  return data as T
}

function useLiveClock() {
  const [tick, setTick] = useState(Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setTick(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [])
  return tick
}


function LoginScreen({ onLogin }: { onLogin: () => void }) {
  return <div className="login-screen">
    <section className="login-card">
      <div className="brand-mark" style={{ margin: '0 auto' }}><Code2 size={22} /></div>
      <h1>DevPilot</h1>
      <p>AI Software Engineer · Developer control plane for inspectable issue analysis, code changes, verification and human-approved delivery.</p>
      <button className="primary big" onClick={onLogin}><UserRound size={16} /> Sign in to DevPilot</button>
      <small style={{ display: 'block', marginTop: 10, color: '#678095', fontSize: 9 }}>Local session control · GitHub credentials are not handled by this screen.</small>
    </section>
  </div>
}

function App() {
  useLiveClock()
  const [active, setActive] = useState('Dashboard')
  const [profileOpen, setProfileOpen] = useState(false)
  const [accountOpen, setAccountOpen] = useState(false)
  const [authUser, setAuthUser] = useState<AuthUser | null>(null)
  const [signedIn, setSignedIn] = useState(() => new URLSearchParams(window.location.search).get('auth') === 'success')
  const [authLoading, setAuthLoading] = useState(true)
  const [searchOpen, setSearchOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [repo, setRepo] = useState(DEFAULT_REPO)
  const [issue, setIssue] = useState<Issue | null>(null)
  const [notice, setNotice] = useState<{ title: string; text: string; kind?: string } | null>(null)
  const [quickRepo, setQuickRepo] = useState<{ name: string; owner: string; repo: string } | null>(null)
  const [settings, setSettings] = useState(() => ({
    approval: localStorage.getItem('devpilot_approval') !== 'false',
    retry: localStorage.getItem('devpilot_retry') !== 'false',
    isolation: localStorage.getItem('devpilot_isolation') !== 'false',
    redaction: localStorage.getItem('devpilot_redaction') !== 'false',
  }))

  const filteredNav = useMemo(() => nav.filter(n => n.label.toLowerCase().includes(search.toLowerCase())), [search])

  useEffect(() => {
    let cancelled = false

    api<{ authenticated: boolean; user?: AuthUser }>('/auth/me')
      .then(data => {
        if (cancelled) return
        if (data.authenticated && data.user) {
          setAuthUser(data.user)
          setSignedIn(true)
          localStorage.setItem('devpilot_session', 'signed_in')
        } else {
          setAuthUser(null)
          setSignedIn(false)
          localStorage.removeItem('devpilot_session')
        }
      })
      .catch(() => {
        if (!cancelled) {
          setAuthUser(null)
          setSignedIn(false)
        }
      })
      .finally(() => {
        if (!cancelled) setAuthLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])


  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setSearchOpen(true) }
      if (e.key === 'Escape') { setSearchOpen(false); setProfileOpen(false); setAccountOpen(false) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])



  const go = (label: string) => { setActive(label); setSearchOpen(false); setProfileOpen(false); setAccountOpen(false) }
  const logout = async () => {
    try {
      await api('/auth/logout', { method: 'POST' })
    } catch {
      // Local state is still cleared below.
    } finally {
      localStorage.removeItem('devpilot_session')
      setAccountOpen(false)
      setProfileOpen(false)
      setAuthUser(null)
      setSignedIn(false)
    }
  }

  const login = () => {
    window.location.href = 'http://127.0.0.1:8000/api/auth/github/login'
  }

  const openQuickRepo = async (label: string) => {
    try {
      const data = await api<{ repositories: Repo[] }>('/repositories/session')
      const aliases: Record<string, string[]> = {
        DevPilot: ['devpilot', 'devpilot-control-plane'],
        Vaani: ['vaani-ai-workspace', 'vaani'],
        TaskFlow: ['task-manager', 'taskflow'],
      }
      const names = new Set((aliases[label] || [label]).map(x => x.toLowerCase()))
      const match = (data.repositories || []).find(r => names.has(r.name.toLowerCase()))
      if (!match) {
        setNotice({ title: `${label} repository not found`, text: 'This shortcut only opens repositories available to the currently signed-in GitHub account.' })
        return
      }
      const [owner, repoName] = match.full_name.split('/')
      setQuickRepo({ name: match.name, owner, repo: repoName })
    } catch (e) {
      setNotice({ title: 'GitHub repository unavailable', text: String(e).replace(/^Error:\s*/, '') })
    }
  }

  const setSetting = (key: keyof typeof settings, value: boolean) => {
    setSettings(s => ({ ...s, [key]: value }))
    localStorage.setItem(`devpilot_${key === 'approval' ? 'approval' : key === 'retry' ? 'retry' : key === 'isolation' ? 'isolation' : 'redaction'}`, String(value))
    saveLog(`${key} ${value ? 'enabled' : 'disabled'}`, 'info')
  }

  if (authLoading) {
    return <div className="login-screen">
      <section className="login-card">
        <div className="brand-mark" style={{ margin: '0 auto' }}><Code2 size={22} /></div>
        <h1>DevPilot</h1>
        <p>Checking GitHub session?</p>
        <Loading />
      </section>
    </div>
  }

  if (!signedIn) return <LoginScreen onLogin={login} />

  return (
    <div className="app">
      <aside className="sidebar">
        <button className="brand" onClick={() => go('Dashboard')}>
          <div className="brand-mark"><Code2 size={20} /></div>
          <div><strong>DevPilot</strong><span>AI Software Engineer</span></div>
        </button>

        <div className="side-context"><span className="signal" /><span>Agent core online</span><b>LIVE</b></div>
        <div className="section-label">WORKSPACE</div>
        {nav.slice(0, 3).map(item => <NavButton key={item.label} item={item} active={active} onClick={go} />)}
        <div className="section-label">ENGINEERING</div>
        {nav.slice(3, 7).map(item => <NavButton key={item.label} item={item} active={active} onClick={go} />)}
        <div className="section-label">SYSTEM</div>
        {nav.slice(7).map(item => <NavButton key={item.label} item={item} active={active} onClick={go} />)}

        <div className="sidebar-bottom">
          <div className="side-clock"><Clock3 size={14} /><div><b>{nowLabel()}</b><span>{new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date())}</span></div></div>
          <button className="profile-button" onClick={() => setAccountOpen(true)}>
            <span className="profile-account-icon">
              {authUser?.avatar_url
                ? <img className="avatar-img" src={authUser.avatar_url} alt="" />
                : <UserRound size={18} />}
            </span>
            <div>
              <b>{authUser?.name || authUser?.login || 'GitHub User'}</b>
              <span>Developer</span>
            </div>
            <ChevronRight size={15} />
          </button>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="crumb"><span>DevPilot</span><ChevronRight size={13} /><b>{active}</b></div>
          <div className="top-actions">
            <div className="top-greeting"><small>AI engineering workspace</small></div>
            <button className="search" onClick={() => setSearchOpen(v => !v)}><Search size={15} /><span>Search</span><kbd>Ctrl K</kbd></button>
            <button className="developer-cta" onClick={() => setProfileOpen(true)}>Know the Developer <ChevronRight size={15} /></button>
          </div>
        </header>

        <div className="content">
          {active === 'Dashboard' && <Dashboard repo={repo} setRepo={setRepo} issue={issue} setIssue={setIssue} onNotice={setNotice} onGo={go} onQuickRepo={openQuickRepo} />}
          {active === 'Repositories' && <Repositories onSelect={r => { setRepo({ owner: r.full_name.split('/')[0], repo: r.name }); go('Issues') }} />}
          {active === 'Issues' && <Issues repo={repo} selected={issue} onSelect={setIssue} onNotice={setNotice} onGo={go} />}
          {active === 'Agent Runs' && <AgentRuns />}
          {active === 'Code Changes' && <CodeChanges repo={repo} issue={issue} onNotice={setNotice} />}
          {active === 'Tests' && <Tests repo={repo} issue={issue} onNotice={setNotice} onGo={go} />}
          {active === 'Pull Requests' && <PullRequests repo={repo} onNotice={setNotice} />}
          {active === 'Audit Logs' && <AuditLogs />}
          {active === 'Settings' && <SettingsView settings={settings} setSetting={setSetting} />}
        </div>

        {searchOpen && <div className="search-layer" onMouseDown={e => { if (e.target === e.currentTarget) setSearchOpen(false) }}>
          <div className="search-panel">
            <div className="search-head"><Search size={16} /><input autoFocus value={search} onChange={e => setSearch(e.target.value)} placeholder="Jump to a DevPilot workspace…" /><kbd>ESC</kbd></div>
            <div className="search-list">{filteredNav.map(item => { const Icon = item.icon; return <button key={item.label} onClick={() => go(item.label)}><Icon size={16} /><span>{item.label}</span><ChevronRight size={13} /></button> })}</div>
          </div>
        </div>}

        {profileOpen && <DeveloperProfile onClose={() => setProfileOpen(false)} onLogout={logout} />}
        {accountOpen && authUser && <AccountProfile user={authUser} onClose={() => setAccountOpen(false)} onLogout={logout} />}
        {quickRepo && <RepoQuickDrawer repo={quickRepo} onClose={() => setQuickRepo(null)} />}
        {notice && <Toast notice={notice} onClose={() => setNotice(null)} />}
      </main>
    </div>
  )
}

function NavButton({ item, active, onClick }: { item: NavItem; active: string; onClick: (label: string) => void }) {
  const Icon = item.icon
  return <button className={`nav ${active === item.label ? 'active' : ''}`} onClick={() => onClick(item.label)}><Icon size={17} /><span>{item.label}</span><ChevronRight className="nav-arrow" size={13} /></button>
}


function RepoPicker({ repos, repo, onChange }: { repos: Repo[]; repo: typeof DEFAULT_REPO; onChange: (r: typeof DEFAULT_REPO) => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const current = `${repo.owner}/${repo.repo}`
  useEffect(() => {
    const outside = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', outside)
    return () => document.removeEventListener('mousedown', outside)
  }, [])
  const options = repos.filter(r => r.full_name)
  return <div className="repo-select" ref={ref}>
    <GitBranch size={14} />
    <button type="button" className="repo-select-trigger" onClick={() => setOpen(v => !v)} aria-expanded={open}>
      <span>{current}</span><ChevronDown size={14} className={open ? 'repo-chevron-open' : ''} />
    </button>
    {open && <div className="repo-select-menu">
      {options.map(r => <button type="button" key={r.full_name} className={`repo-select-option ${r.full_name === current ? 'selected' : ''}`} onClick={() => { const [owner, name] = r.full_name.split('/'); onChange({ owner, repo: name }); setOpen(false) }}>
        <span>{r.full_name}</span>{r.full_name === current && <span className="repo-check">✓</span>}
      </button>)}
    </div>}
  </div>
}

const stageIcons = [CheckCircle2, GitBranch, FileCode2, Bot, Sparkles, Code2, TestTube2, UserRound, GitPullRequest]

function FlowStep({ s, i, last }: { s: string; i: number; last: boolean }) {
  const done = i < 3
  const active = i === 3
  const StageIcon = stageIcons[i] || CircleDot
  return <div className={`flow-step flow-step-${i + 1} ${done ? 'done' : active ? 'active' : ''}`}>
    <div className="flow-node"><StageIcon size={14} /></div>
    <b>{s}</b>
    {!last && <i />}
  </div>
}

function Dashboard({ repo, setRepo, issue, setIssue, onNotice, onGo, onQuickRepo }: { repo: typeof DEFAULT_REPO; setRepo: (r: typeof DEFAULT_REPO) => void; issue: Issue | null; setIssue: (i: Issue | null) => void; onNotice: (n: { title: string; text: string; kind?: string }) => void; onGo: (s: string) => void; onQuickRepo: (label: string) => void }) {
  const [repos, setRepos] = useState<Repo[]>([])
  const [issues, setIssues] = useState<Issue[]>([])
  const [busy, setBusy] = useState(false)
  const [heroMessage, setHeroMessage] = useState(0)
  useEffect(() => { const id = window.setInterval(() => setHeroMessage(v => (v + 1) % heroMessages.length), 2800); return () => window.clearInterval(id) }, [])

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
  useEffect(() => { api<Issue[]>(`/repositories/${repo.owner}/${repo.repo}/issues`).then(d => setIssues(Array.isArray(d) ? d : ((d as any).issues || []))).catch(() => setIssues([])) }, [repo])

  const analyze = async () => {
    if (!issue) { onGo('Issues'); onNotice({ title: 'Choose a GitHub issue', text: 'Select an issue first. DevPilot then runs the real analysis pipeline.' }); return }
    setBusy(true); saveLog(`Analysis started for #${issue.number} · ${issue.title}`, 'active', { phase: 'Issue intake', repo: `${repo.owner}/${repo.repo}`, issue: `#${issue.number} · ${issue.title}`, result: 'Running' }); saveDelivery({ analysis: 'running', repository: `${repo.owner}/${repo.repo}`, issue: `#${issue.number}` })
    try {
      const result: any = await api(`/repositories/${repo.owner}/${repo.repo}/issues/${issue.number}/analyze`)
      const analysis = result.analysis?.result || result.analysis || {}
      const analysisSummary = analysis.summary || analysis.root_cause || 'Root-cause analysis is ready.'
      const analysisFiles = (analysis.files || analysis.relevant_files || result.files || []).map((x: any) => typeof x === 'string' ? x : (x.path || x.file || JSON.stringify(x))).slice(0, 12)
      saveRun({ id: `RUN-${Date.now()}`, issue, repo, status: 'Analyzed', created: nowLabel(), result })
      saveDelivery({ analysis: 'passed', repository: `${repo.owner}/${repo.repo}`, issue: `#${issue.number}`, rootCause: analysis.root_cause || 'See analysis evidence', analysisAt: nowLabel() })
      saveLog(`Issue #${issue.number} analyzed successfully`, 'success', { phase: 'Root-cause analysis', repo: `${repo.owner}/${repo.repo}`, issue: `#${issue.number} · ${issue.title}`, result: 'Analysis complete', files: analysisFiles, evidence: String(analysisSummary).slice(0, 1800) })
      onNotice({ title: 'Agent analysis complete', text: String(analysisSummary) })
      onGo('Agent Runs')
    } catch (e) { onNotice({ title: 'Analysis failed', text: String(e) }) }
    finally { setBusy(false) }
  }

  return <div className="dashboard">
    <section className="welcome">
      <div>
        <span className="eyebrow"><span className="live-dot" /> AI ENGINEERING CONTROL PLANE</span>
        <h1>{greeting()}</h1>
        <p>DevPilot turns a GitHub issue into an inspectable engineering run — context, analysis, plan, patch, tests and human-approved delivery.</p><div className="hero-message" key={heroMessage}><span className="hero-message-dot" />{heroMessages[heroMessage]}</div>
      </div>
      <div className="live-console"><span className="orb" /><div><b>Agent core</b><span>Ready for instruction</span></div><i>LIVE</i></div>
    </section>

    <section className="agent-launch">
      <div className="launch-head">
        <div><span className="label">START AN ENGINEERING RUN</span><h2>Give the agent a real issue.</h2><p>No terminal command needed. Pick a repository and GitHub issue; DevPilot handles the workflow.</p></div>
        <RepoPicker repos={repos} repo={repo} onChange={r => { setRepo(r); setIssue(null) }} />
      </div>
      <div className="issue-picker">
        <div className="issue-icon"><CircleDot size={17} /></div>
        <div className="issue-info">
          <span>SELECTED ISSUE</span>
          {issue ? <><b>#{issue.number} · {issue.title}</b><small>{issue.body?.slice(0, 150) || 'GitHub issue selected for analysis.'}</small></> : <button onClick={() => onGo('Issues')}>Choose a GitHub issue to start →</button>}
        </div>
        {issue && <button className="clear-issue" onClick={() => setIssue(null)}><X size={14} /></button>}
      </div>
      <div className="launch-foot">
        <div className="pipeline-mini"><span>Issue</span><i>→</i><span>Context</span><i>→</i><span>AI</span><i>→</i><span>Patch</span><i>→</i><span>Tests</span><i>→</i><span>Review</span></div>
        <button className="primary big" disabled={busy} onClick={analyze}>{busy ? <><Loader2 className="spin" size={16} /> Agent working…</> : <><Zap size={16} fill="currentColor" /> Analyze with DevPilot</>}</button>
      </div>
    </section>

    <div className="dashboard-grid">
      <section className="surface active-run">
        <div className="surface-head"><div><span className="label">AGENT TELEMETRY</span><h3>How DevPilot works</h3></div><span className="status-pill"><span />Human approval gate</span></div>
        <div className="agent-flow">
          <div className="flow-row">{stages.slice(0, 5).map((s, i) => <FlowStep key={s} s={s} i={i} last={i === 4} />)}</div>
          <div className="flow-row flow-row-second">{stages.slice(5).map((s, n) => <FlowStep key={s} s={s} i={n + 5} last={n === 3} />)}</div>
        </div>
      </section>

      <section className="surface side-live">
        <div className="surface-head"><div><span className="label">CONNECTED</span><h3>Engineering surface</h3></div><button className="icon-button" onClick={() => onGo('Repositories')}><Plus size={15} /></button></div>
        <RepoMini name="DevPilot" meta="Current workspace" current onClick={() => onQuickRepo("DevPilot")} quickClass="quick-repo-devpilot" />
        <RepoMini name="Vaani" meta="AI Workspace" onClick={() => onQuickRepo("Vaani")} quickClass="quick-repo-vaani" />
        <RepoMini name="TaskFlow" meta="Productivity platform" onClick={() => onQuickRepo("TaskFlow")} quickClass="quick-repo-taskflow" />
        <div className="guardrail-line"><ShieldCheck size={14} /><span>Safe by default · isolated changes · approval required</span></div>
      </section>
    </div>

    <section className="surface activity-strip">
      <div className="surface-head"><div><span className="label">RECENT SIGNALS</span><h3>Agent activity</h3></div><button className="text-button" onClick={() => onGo('Audit Logs')}>Open audit log</button></div>
      <RecentSignals />
    </section>
  </div>
}

function Repositories({ onSelect }: { onSelect: (r: Repo) => void }) {
  const [repos, setRepos] = useState<Repo[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<Repo | null>(null)
  const [tree, setTree] = useState<any[]>([])
  const [error, setError] = useState('')
  const load = () => { setLoading(true); setError(''); api<{ repositories: Repo[] }>('/repositories/session').then(d => setRepos(d.repositories || [])).catch(e => { setRepos([]); setError(String(e).replace(/^Error:\s*/, '')) }).finally(() => setLoading(false)) }
  useEffect(load, [])
  useEffect(() => { if (!selected) return; const [owner, name] = selected.full_name.split('/'); api<any>(`/repositories/${owner}/${name}/tree-session`).then(d => setTree(d.tree || d.items || d || [])).catch(() => setTree([])) }, [selected])
  const filtered = repos.filter(r => `${r.full_name} ${r.language || ''}`.toLowerCase().includes(query.toLowerCase()))
  return <PageShell eyebrow="REPOSITORY CONTROL" title="Your engineering surface" desc="GitHub repositories are live working surfaces for the agent. Inspect them before asking DevPilot to change anything.">
    <div className="toolbar"><div className="field-search"><Search size={15} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Filter repositories…" /></div><button className="secondary" onClick={load}><RefreshCw size={14} /> Refresh GitHub</button></div>
    {loading ? <Loading /> : error ? <Empty title="GitHub repositories unavailable" text={error} /> : <div className="repo-grid">{filtered.map((r, i) => <button className={`repo-card ${selected?.full_name === r.full_name ? 'selected' : ''}`} key={r.full_name} onClick={() => setSelected(r)}><div className="repo-card-top"><span className="repo-index">0{i + 1}</span><div className="repo-symbol"><GitBranch size={17} /></div><span className="repo-language">{r.private ? 'PRIVATE' : 'PUBLIC'}</span></div><h3>{r.name}</h3><p>{r.full_name}</p><div><span>{r.language || 'Multi-language'}</span><span>{r.default_branch || 'main'}</span></div></button>)}</div>}
    {selected && <div className="drawer"><div className="drawer-head"><div><span className="label">REPOSITORY INSPECTOR</span><h3>{selected.full_name}</h3></div><button className="close-small" onClick={() => setSelected(null)}><X size={16} /></button></div><div className="drawer-actions"><button className="primary" onClick={() => onSelect(selected)}><Bot size={15} /> Use with Agent</button>{selected.html_url && <a className="secondary link-button" href={selected.html_url} target="_blank" rel="noreferrer"><GitBranch size={15} /> Open GitHub</a>}</div><div className="tree-list">{tree.slice(0, 60).map((item: any) => <div className="tree-row" key={item.path || item.name}><span className={item.type === 'tree' ? 'folder' : 'file'}>{item.type === 'tree' ? 'DIR' : 'FILE'}</span><code>{item.path || item.name}</code></div>)}</div></div>}
  </PageShell>
}

function Issues({ repo, selected, onSelect, onNotice, onGo }: { repo: typeof DEFAULT_REPO; selected: Issue | null; onSelect: (i: Issue) => void; onNotice: (n: { title: string; text: string; kind?: string }) => void; onGo: (s: string) => void }) {
  const [issues, setIssues] = useState<Issue[]>([])
  const [loading, setLoading] = useState(true)
  const [analysis, setAnalysis] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const load = () => { setLoading(true); api<any>(`/repositories/${repo.owner}/${repo.repo}/issues`).then(d => setIssues(Array.isArray(d) ? d : d.issues || [])).catch(() => setIssues([])).finally(() => setLoading(false)) }
  useEffect(load, [repo])
  const run = async () => {
    if (!selected) return
    setBusy(true); saveLog(`Agent analysis requested for issue #${selected.number}`, 'active')
    try { const d = await api<any>(`/repositories/${repo.owner}/${repo.repo}/issues/${selected.number}/analyze`); setAnalysis(d); saveRun({ id: `RUN-${Date.now()}`, issue: selected, repo, status: 'Analyzed', created: nowLabel(), result: d }); saveLog(`Issue #${selected.number} analysis complete`, 'success'); onNotice({ title: 'Root-cause analysis ready', text: d.analysis?.result?.summary || d.analysis?.summary || 'Analysis completed.' }) }
    catch (e) { onNotice({ title: 'Analysis failed', text: String(e) }) } finally { setBusy(false) }
  }
  return <PageShell eyebrow="ISSUE INTAKE" title="Issues that can become agent runs" desc={`Live GitHub issues from ${repo.owner}/${repo.repo}. Select one to inspect evidence and hand it to DevPilot.`}>
    <div className="toolbar"><div className="repo-context"><GitBranch size={14} /> {repo.owner}/{repo.repo}</div><button className="secondary" onClick={load}><RefreshCw size={14} /> Refresh</button></div>
    <div className="issue-layout">
      <div className="issue-list">{loading ? <Loading /> : issues.length ? issues.map(i => <button className={`issue-row ${selected?.number === i.number ? 'selected' : ''}`} key={i.number} onClick={() => { onSelect(i); setAnalysis(null) }}><div className="issue-num">#{i.number}</div><div className="issue-row-main"><div className="issue-row-title"><b>{i.title}</b><span className="state">{String(i.state || 'open').toUpperCase()}</span></div><span><strong>Problem</strong>{i.body?.slice(0, 120) || 'No description provided.'}</span></div></button>) : <Empty title="No GitHub issues found" text="Create an issue in GitHub and refresh this workspace." />}</div>
      <section className="issue-detail surface">
        {selected ? <><div className="detail-top"><div><span className="label">ISSUE #{selected.number}</span><h3>{selected.title}</h3></div><button className="primary" disabled={busy} onClick={run}>{busy ? <><Loader2 className="spin" size={14} /> Running</> : <><Bot size={14} /> Analyze</>}</button></div><div className="issue-brief"><div><span className="issue-label">PROBLEM</span><p>{selected.body || 'No problem description provided.'}</p></div><div><span className="issue-label">EXPECTED BEHAVIOR</span><p>Task should immediately reflect the intended state and remain correct after refresh.</p></div></div>{analysis && <AnalysisResult data={analysis} onGo={onGo} />}</> : <Empty title="Select an issue" text="The agent needs an issue as its starting point." />}</section>
    </div>
  </PageShell>
}

function AnalysisResult({ data, onGo }: { data: any; onGo: (s: string) => void }) {
  const result = data.analysis?.result || data.analysis || {}
  return <div className="analysis-result"><div className="metric-row"><Metric label="Provider" value={data.provider || data.analysis?.provider || 'AI'} /><Metric label="Confidence" value={result.confidence || '—'} /><Metric label="Files" value={String(data.context?.selected_file_count ?? '—')} /></div><div className="result-block"><span className="label">ROOT CAUSE</span><p>{result.root_cause || 'No confirmed root cause in supplied evidence.'}</p></div><div className="result-block"><span className="label">SUMMARY</span><p>{result.summary || 'Analysis completed.'}</p></div><div className="evidence">{(result.evidence || []).slice(0, 6).map((e: any, i: number) => <div key={i}><code>{e.file || 'evidence'}</code><span>{e.observation || e.text || JSON.stringify(e)}</span></div>)}</div><button className="secondary" onClick={() => onGo('Code Changes')}><FileCode2 size={14} /> Generate / inspect patch</button></div>
}

function AgentRuns() {
  const [runs, setRuns] = useState<any[]>(loadRuns())
  useEffect(() => { const f = () => setRuns(loadRuns()); window.addEventListener('devpilot-run', f); return () => window.removeEventListener('devpilot-run', f) }, [])
  return <PageShell eyebrow="AGENT EXECUTION" title="Agent runs" desc="Every run is a traceable chain from issue intake to analysis and delivery. No fake run data is generated.">
    {runs.length ? <div className="run-list">{runs.map((r, i) => <article className="run-card" key={r.id || i}><div className="run-number">#{String(i + 1).padStart(2, '0')}</div><div className="run-main"><div><span className="label">{r.id}</span><h3>Issue #{r.issue?.number} · {r.issue?.title}</h3><p>{r.repo?.owner}/{r.repo?.repo} · {r.created}</p></div><span className="status-pill success"><span />{r.status}</span></div><div className="run-progress">{stages.slice(0, 4).map((s, n) => <span key={s} className={n < 3 ? 'done' : ''}><i />{s}</span>)}</div></article>)}</div> : <Empty title="No agent runs yet" text="Choose a GitHub issue and run Analyze with DevPilot from Dashboard or Issues." />}
  </PageShell>
}

function CodeChanges({ repo, issue, onNotice }: { repo: typeof DEFAULT_REPO; issue: Issue | null; onNotice: (n: { title: string; text: string; kind?: string }) => void }) {
  const [data, setData] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [applyBusy, setApplyBusy] = useState(false)
  const generate = async () => {
    if (!issue) { onNotice({ title: 'Select an issue first', text: 'Code Changes uses the selected GitHub issue to generate a real patch.' }); return }
    setBusy(true); saveLog(`Patch generation started for #${issue.number}`, 'active', { phase: 'Patch generation', repo: `${repo.owner}/${repo.repo}`, issue: `#${issue.number} · ${issue.title}`, result: 'Running' })
    try { const d = await api<any>(`/repositories/${repo.owner}/${repo.repo}/issues/${issue.number}/patch`); setData(d); const patchFiles = (d.patch?.files || []).map((f: any) => f.path || f.file || 'unknown').slice(0, 20); const firstEdit = d.patch?.files?.find((f: any) => f.edits?.length)?.edits?.[0]; saveDelivery({ patch: 'generated', files: patchFiles, repository: `${repo.owner}/${repo.repo}`, issue: `#${issue.number}` }); saveLog(`Patch generated for #${issue.number}`, 'success', { phase: 'Patch generation', repo: `${repo.owner}/${repo.repo}`, issue: `#${issue.number} · ${issue.title}`, result: 'Patch generated', files: patchFiles, before: firstEdit?.find ? String(firstEdit.find).slice(0, 1200) : undefined, after: firstEdit?.replace ? String(firstEdit.replace).slice(0, 1200) : undefined, evidence: String(d.patch?.summary || 'Generated patch') }); onNotice({ title: 'Patch generated', text: 'Review the diff. Apply & Test is available only after the patch is visible.' }) }
    catch (e) { onNotice({ title: 'Patch generation failed', text: String(e) }) } finally { setBusy(false) }
  }
  const applyAndTest = async () => {
    const files = data?.patch?.files
    if (!issue || !files?.length) { onNotice({ title: 'Nothing to apply', text: 'Generate a patch with at least one changed file first.' }); return }
    setApplyBusy(true); saveLog(`Apply-and-test started for #${issue.number}`, 'active', { phase: 'Apply & verification', repo: `${repo.owner}/${repo.repo}`, issue: `#${issue.number} · ${issue.title}`, result: 'Running', command: 'pytest -q' })
    try {
      const d = await api<any>(`/repositories/${repo.owner}/${repo.repo}/apply-and-test`, {
        method: 'POST',
        body: JSON.stringify({
          files: files.map((f: any) => ({ path: f.path, edits: (f.edits || []).map((e: any) => ({ find: e.find, replace: e.replace })) })),
          commands: ['pytest -q'],
          branch: 'main',
          timeout_seconds: 120,
          auto_retry: true,
          max_attempts: 3,
          issue: issue,
          plan: data.plan || null,
        }),
      })
      if (d.review) localStorage.setItem('devpilot_review', JSON.stringify({ ...d.review, issue, patch: d.patch, execution: d.execution }))
      const executionStatus = d.execution?.status || d.status || 'completed'
      saveDelivery({ applyTest: d.status, test: executionStatus, review: d.review ? 'pending' : 'not_created', repository: `${repo.owner}/${repo.repo}`, issue: `#${issue.number}` })
      saveLog(`Apply-and-test ${d.status}`, d.status === 'ready_for_review' ? 'success' : 'warning', { phase: 'Apply & verification', repo: `${repo.owner}/${repo.repo}`, issue: `#${issue.number} · ${issue.title}`, result: executionStatus, command: 'pytest -q', files: (d.patch?.files || []).map((f: any) => f.path || f.file).filter(Boolean).slice(0, 20), evidence: String(d.execution?.summary || d.next_action || d.status).slice(0, 2200) })
      onNotice({ title: d.status === 'ready_for_review' ? 'Ready for human review' : 'Workflow stopped', text: d.next_action || d.execution?.summary || d.status })
    } catch (e) { onNotice({ title: 'Apply-and-test failed', text: String(e) }) }
    finally { setApplyBusy(false) }
  }
  const patch = data?.patch || {}
  return <PageShell eyebrow="PATCH WORKSPACE" title="Code changes" desc="Inspect the actual AI-generated patch, then safely apply it in an isolated workspace and run tests.">
    <div className="tool-hero"><div><span className="label">CURRENT CONTEXT</span><h3>{issue ? `Issue #${issue.number} · ${issue.title}` : 'No issue selected'}</h3><p>{repo.owner}/{repo.repo}</p></div><div className="tool-actions"><button className="secondary" disabled={busy} onClick={generate}><Sparkles size={14} /> {busy ? 'Generating…' : 'Generate patch'}</button><button className="primary" disabled={applyBusy || !data?.patch?.files?.length} onClick={applyAndTest}>{applyBusy ? <><Loader2 className="spin" size={15} /> Applying…</> : <><ShieldCheck size={15} /> Apply & Test</>}</button></div></div>
    {data ? <div className="diff-layout"><section className="surface diff-card"><div className="surface-head"><div><span className="label">PATCH RESULT</span><h3>{patch.summary || 'Generated patch'}</h3></div><span className={`status-pill ${patch.status === 'applied' ? 'success' : ''}`}><span />{patch.status || 'generated'}</span></div><div className="diff-stats"><Metric label="Files" value={String(patch.files_changed ?? data.diff?.split('\n').filter((x: string) => x.startsWith('+++')).length ?? 0)} /><Metric label="Added" value={`+${patch.scope?.lines_added ?? 0}`} /><Metric label="Removed" value={`-${patch.scope?.lines_removed ?? 0}`} /></div><pre className="diff-view">{data.diff || patch.diff || 'No diff returned.'}</pre></section><section className="surface evidence-panel"><span className="label">PLAN</span><pre>{JSON.stringify(data.plan || {}, null, 2)}</pre></section></div> : <Empty title="No patch loaded" text="Select an issue, then generate the patch. Review comes before approval." />}
  </PageShell>
}

function Tests({ repo, issue, onNotice, onGo }: { repo: typeof DEFAULT_REPO; issue: Issue | null; onNotice: (n: { title: string; text: string; kind?: string }) => void; onGo: (label: string) => void }) {
  const [plan, setPlan] = useState<any>(null)
  const [command, setCommand] = useState('pytest -q')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [delivery, setDelivery] = useState<any>(loadDelivery())
  const [review, setReview] = useState<any>(() => { try { return JSON.parse(localStorage.getItem('devpilot_review') || 'null') } catch { return null } })
  const [pr, setPr] = useState<any>(() => { try { return JSON.parse(localStorage.getItem('devpilot_pr') || 'null') } catch { return null } })

  useEffect(() => { if (issue) api<any>(`/repositories/${repo.owner}/${repo.repo}/issues/${issue.number}/tests`).then(setPlan).catch(() => setPlan(null)) }, [issue, repo])
  useEffect(() => { const f = () => { setDelivery(loadDelivery()); try { setReview(JSON.parse(localStorage.getItem('devpilot_review') || 'null')); setPr(JSON.parse(localStorage.getItem('devpilot_pr') || 'null')) } catch {} }; window.addEventListener('devpilot-delivery', f); window.addEventListener('devpilot-log', f); return () => { window.removeEventListener('devpilot-delivery', f); window.removeEventListener('devpilot-log', f) } }, [])

  const run = async () => {
    if (!command.trim()) return
    setBusy(true)
    saveLog(`Test execution started for ${repo.owner}/${repo.repo}`, 'active', { phase: 'Verification', repo: `${repo.owner}/${repo.repo}`, issue: issue ? `#${issue.number} · ${issue.title}` : undefined, command, result: 'Running' })
    saveDelivery({ test: 'running', repository: `${repo.owner}/${repo.repo}`, issue: issue ? `#${issue.number}` : undefined, command })
    try {
      const d = await api<any>(`/repositories/${repo.owner}/${repo.repo}/execute-tests`, { method: 'POST', body: JSON.stringify({ commands: [command], timeout_seconds: 120, keep_workspace: false, branch: 'main', auto_retry: true, max_attempts: 3 }) })
      setResult(d)
      const execution = d.execution || d
      const status = execution.status || 'completed'
      const passed = status === 'passed' || status === 'success' || status === 'successful'
      saveDelivery({ test: passed ? 'passed' : 'failed', testSummary: execution.summary || execution.output || status, repository: `${repo.owner}/${repo.repo}` })
      saveLog(`Test execution ${status}`, passed ? 'success' : 'warning', { phase: 'Verification', repo: `${repo.owner}/${repo.repo}`, issue: issue ? `#${issue.number} · ${issue.title}` : undefined, command, result: status, evidence: String(execution.summary || execution.output || JSON.stringify(execution)).slice(0, 3500) })
      onNotice({ title: passed ? 'Verification passed' : 'Verification failed', text: String(execution.summary || execution.output || status) })
    } catch (e) {
      const message = String(e)
      saveDelivery({ test: 'failed', testSummary: message, repository: `${repo.owner}/${repo.repo}` })
      saveLog('Test execution failed to start', 'warning', { phase: 'Verification', repo: `${repo.owner}/${repo.repo}`, issue: issue ? `#${issue.number} · ${issue.title}` : undefined, command, result: 'failed', evidence: message })
      onNotice({ title: 'Tests failed to start', text: message })
    } finally { setBusy(false) }
  }

  const execution = result?.execution || result
  const testStatus = execution?.status || delivery.test || 'pending'
  const normalized = String(testStatus).toLowerCase()
  const testPassed = ['passed', 'success', 'successful'].includes(normalized)
  const testFailed = ['failed', 'failure', 'error'].includes(normalized)
  const stage = (done: boolean, active: boolean, label: string, meta: string) => <div className={`delivery-stage ${done ? 'done' : active ? 'active' : ''}`}><div className="delivery-stage-dot">{done ? <CheckCircle2 size={13} /> : <span />}</div><div><b>{label}</b><small>{meta}</small></div></div>

  return <PageShell eyebrow="VERIFICATION" title="Test laboratory" desc="Run bounded repository tests and see exactly what has been verified — and what still remains before GitHub delivery.">
    <div className="test-layout">
      <section className="surface test-console">
        <div className="surface-head"><div><span className="label">COMMAND</span><h3>Verification command</h3></div><span className={`status-pill ${testPassed ? 'success' : ''}`}><span />{busy ? 'RUNNING' : testPassed ? 'PASSED' : testFailed ? 'FAILED' : 'READY'}</span></div>
        <div className="command-editor"><Terminal size={15} /><input value={command} onChange={e => setCommand(e.target.value)} /><button className="primary" disabled={busy || !command.trim()} onClick={run}>{busy ? <Loader2 className="spin" size={14} /> : <Play size={14} />} {busy ? 'Running…' : 'Run tests'}</button></div>
        {result ? <div className={`test-result-card ${testPassed ? 'passed' : testFailed ? 'failed' : ''}`}><div><span className="label">EXECUTION RESULT</span><h3>{testPassed ? 'Verification passed' : testFailed ? 'Verification failed' : `Execution ${testStatus}`}</h3><p>{execution?.summary || execution?.output || 'The backend returned an execution result.'}</p>{testPassed && <button className="secondary test-next" onClick={() => onGo('Code Changes')}><FileCode2 size={13} /> Continue to Code Changes</button>}</div><div className="test-result-metrics"><Metric label="Status" value={String(testStatus)} /><Metric label="Command" value={command} /></div></div> : <div className="test-empty-state"><TestTube2 size={20} /><b>No verification run yet</b><span>Run the command above. DevPilot will report a real pass/fail result here.</span></div>}
        <pre className="test-output">{result ? JSON.stringify(execution, null, 2) : 'Execution output will appear here after the backend returns.'}</pre>
      </section>
      <section className="surface plan-panel"><span className="label">ISSUE TEST PLAN</span>{issue && plan ? <pre>{JSON.stringify(plan, null, 2)}</pre> : <Empty title="No issue selected" text="Select an issue to load its generated test plan." />}</section>
    </div>

    <section className="surface delivery-tracker">
      <div className="surface-head"><div><span className="label">DELIVERY TRACE</span><h3>From test result to GitHub</h3></div><span className="status-pill"><span />No silent steps</span></div>
      <div className="delivery-flow">
        {stage(testPassed, busy, 'Tests', testPassed ? 'Passed' : testFailed ? 'Failed' : busy ? 'Running' : 'Not run')}
        <i />{stage(Boolean(review), false, 'Patch applied', review ? 'Isolated workspace' : 'Requires Apply & Test')}
        <i />{stage(Boolean(review), Boolean(review && !pr), 'Human review', review ? 'Approval required' : 'Waiting')}
        <i />{stage(Boolean(pr), false, 'GitHub PR', pr ? (pr.github?.pull_request?.html_url || 'Created') : 'Not created')}
      </div>
      <div className="delivery-note"><ShieldCheck size={15} /><span><b>Important:</b> running tests alone never pushes code to GitHub. A passing test only verifies the command. The path continues through <strong>Code Changes → Apply & Test → Human Review → Approve & create PR</strong>.</span></div>
    </section>
  </PageShell>
}

function PullRequests({ repo, onNotice }: { repo: typeof DEFAULT_REPO; onNotice: (n: { title: string; text: string; kind?: string }) => void }) {
  const [review, setReview] = useState<any>(() => { try { return JSON.parse(localStorage.getItem('devpilot_review') || 'null') } catch { return null } })
  const [reason, setReason] = useState('Reviewed generated patch and test results.')
  const [busy, setBusy] = useState(false)
  const approve = async () => {
    if (!review?.review_id) { onNotice({ title: 'No review session', text: 'Run apply-and-test from the backend workflow to create a human review session.' }); return }
    setBusy(true)
    try { const d = await api<any>(`/repositories/${repo.owner}/${repo.repo}/reviews/${review.review_id}/approve`, { method: 'POST', body: JSON.stringify({ approval_reason: reason, commit_message: `fix: ${review.issue?.title || 'DevPilot change'}`, pr_title: `DevPilot: ${review.issue?.title || 'automated change'}`, pr_body: 'Created through DevPilot after tests passed.', draft_pr: false }) }); localStorage.setItem('devpilot_pr', JSON.stringify(d)); saveDelivery({ review: 'approved', pr: 'created', prUrl: d.github?.pull_request?.html_url || '', repository: `${repo.owner}/${repo.repo}` }); saveLog('Approved review and created pull request', 'success', { phase: 'GitHub delivery', repo: `${repo.owner}/${repo.repo}`, issue: review.issue ? `#${review.issue.number} · ${review.issue.title}` : undefined, result: 'Pull request created', files: (review.patch?.files || []).map((f: any) => f.path || f.file).filter(Boolean).slice(0, 20), link: d.github?.pull_request?.html_url || undefined, evidence: 'Human approval recorded; backend created the GitHub pull request.' }); onNotice({ title: 'Pull request created', text: d.github?.pull_request?.html_url || 'GitHub pull request created.' }); setReview(null) }
    catch (e) { onNotice({ title: 'Approval failed', text: String(e) }) } finally { setBusy(false) }
  }
  return <PageShell eyebrow="DELIVERY" title="Pull requests" desc="Human approval is the final gate. DevPilot creates an isolated branch and PR instead of mutating main directly.">
    <div className="pr-layout"><section className="surface pr-main"><div className="surface-head"><div><span className="label">REVIEW QUEUE</span><h3>{review ? 'Approval required' : 'No pending review'}</h3></div><span className={`status-pill ${review ? '' : 'success'}`}><span />{review ? 'WAITING' : 'CLEAR'}</span></div>{review ? <><div className="review-summary"><Metric label="Repository" value={`${repo.owner}/${repo.repo}`} /><Metric label="Files" value={String(review.patch?.files_changed ?? review.patch?.files?.length ?? '—')} /><Metric label="Tests" value={review.execution?.status || 'passed'} /></div><label className="reason-label">Approval reason<textarea value={reason} onChange={e => setReason(e.target.value)} /></label><button className="primary big" disabled={busy} onClick={approve}>{busy ? <><Loader2 className="spin" size={16} /> Creating PR…</> : <><GitPullRequest size={16} /> Approve & create PR</>}</button></> : <Empty title="Human review queue is clear" text="A review appears here after apply-and-test passes." />}</section><section className="surface safety-panel"><ShieldCheck size={22} /><h3>Protected delivery</h3><p>Tests must pass. Only reviewed files are staged. Approval creates an isolated branch.</p><div className="guard-list"><span><CheckCircle2 size={14} /> Main branch protected</span><span><CheckCircle2 size={14} /> Human approval</span><span><CheckCircle2 size={14} /> Selective staging</span></div></section></div>
  </PageShell>
}

function AuditLogs() {
  const [logs, setLogs] = useState<LogItem[]>(loadLogs())
  const [open, setOpen] = useState<number | null>(0)
  useEffect(() => { const f = () => setLogs(loadLogs()); window.addEventListener('devpilot-log', f); return () => window.removeEventListener('devpilot-log', f) }, [])
  return <PageShell eyebrow="TRACEABILITY" title="Audit logs" desc="A readable accountability trail: what happened, what changed, which files were involved, and what evidence DevPilot received at each step.">
    <div className="audit-summary"><div><span>EVENTS</span><b>{logs.length}</b></div><div><span>ACCOUNTABILITY</span><b>Evidence attached</b></div><div><span>DELIVERY</span><b>{loadDelivery().pr === 'created' ? 'PR created' : 'In progress'}</b></div></div>
    <div className="audit-timeline">{logs.length ? logs.map((l, i) => { const d = l.details || {}; const isOpen = open === i; return <article className={`audit-card ${l.kind || ''} ${isOpen ? 'open' : ''}`} key={`${l.time}-${i}`}><button className="audit-card-head" onClick={() => setOpen(isOpen ? null : i)}><div className="audit-marker"><i /></div><div className="audit-main"><div><span>{l.time}</span><em>{d.phase || 'Workspace event'}</em></div><b>{l.text}</b><small>{d.repo || 'DevPilot workspace'}{d.issue ? ` · ${d.issue}` : ''}</small></div><ChevronDown className={isOpen ? 'audit-chevron open' : 'audit-chevron'} size={16} /></button>{isOpen && <div className="audit-evidence"><div className="evidence-grid"><div><span>RESULT</span><b>{d.result || 'Recorded'}</b></div><div><span>COMMAND</span><b>{d.command || '—'}</b></div><div><span>FILES</span><b>{d.files?.length ? String(d.files.length) : '—'}</b></div></div>{(d.before || d.after) && <div className="before-after"><section><span>BEFORE</span><pre>{d.before || 'No source excerpt captured.'}</pre></section><section><span>AFTER</span><pre>{d.after || 'No replacement excerpt captured.'}</pre></section></div>}{d.files?.length ? <div className="evidence-files"><span>FILES TOUCHED / INSPECTED</span><div>{d.files.map((f, n) => <code key={`${f}-${n}`}>{f}</code>)}</div></div> : null}{d.evidence && <div className="evidence-text"><span>EVIDENCE / BACKEND RESPONSE</span><pre>{d.evidence}</pre></div>}{d.link && <a className="audit-link" href={d.link} target="_blank" rel="noreferrer"><GitPullRequest size={14} /> Open GitHub pull request <ExternalLink size={13} /></a>}</div>}</article> }) : <Empty title="No activity yet" text="Run an analysis or test to start the local audit trail." />}</div>
  </PageShell>
}

function SettingsView({ settings, setSetting }: { settings: { approval: boolean; retry: boolean; isolation: boolean; redaction: boolean }; setSetting: (key: keyof typeof settings, value: boolean) => void }) {
  const rows = [
    ['approval', 'Human approval', 'Never create a delivery PR without explicit approval.', settings.approval],
    ['retry', 'Bounded auto-retry', 'Retry failed tests up to three attempts.', settings.retry],
    ['isolation', 'Isolated branches', 'Keep approved source changes away from main until delivery.', settings.isolation],
    ['redaction', 'Secret redaction', 'Keep credentials out of visible agent output.', settings.redaction],
  ] as const
  return <PageShell eyebrow="SYSTEM CONFIGURATION" title="DevPilot controls" desc="These controls shape how the agent operates. Changes are stored locally in this browser.">
    <div className="settings-list">{rows.map(([key, title, desc, value]) => <button className="setting-row" key={key} onClick={() => setSetting(key, !value)}><div className="setting-icon"><ShieldCheck size={16} /></div><div><b>{title}</b><span>{desc}</span></div><span className={`toggle ${value ? 'on' : ''}`}><i /></span></button>)}</div>
  </PageShell>
}

function PageShell({ eyebrow, title, desc, children }: { eyebrow: string; title: string; desc: string; children: ReactNode }) {
  return <section className="page-shell"><div className="page-heading"><div><span className="eyebrow"><Sparkles size={13} /> {eyebrow}</span><h1>{title}</h1><p>{desc}</p></div><div className="heading-pulse"><span /><span /><span /></div></div>{children}</section>
}

function RepoMini({ name, meta, current, onClick, quickClass = '' }: { name: string; meta: string; current?: boolean; onClick?: () => void; quickClass?: string }) {
  const content = <><div className="repo-symbol"><GitBranch size={15} /></div><div><b>{name}</b><span>{meta}</span></div><em className={current ? 'current' : ''}>{current ? 'ACTIVE' : 'READY'}</em></>
  return onClick
    ? <button type="button" className={`repo-mini repo-mini-button ${quickClass}`.trim()} onClick={onClick}>{content}</button>
    : <div className="repo-mini">{content}</div>
}
function RepoQuickDrawer({ repo, onClose }: { repo: { name: string; owner: string; repo: string }; onClose: () => void }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [tree, setTree] = useState<any[]>([])
  const [file, setFile] = useState<{ path: string; content: string } | null>(null)
  const [fileLoading, setFileLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api<any>(`/repositories/${repo.owner}/${repo.repo}/tree-session`)
      .then(data => { if (!cancelled) setTree(Array.isArray(data.tree) ? data.tree : []) })
      .catch(e => { if (!cancelled) setError(String(e).replace(/^Error:\s*/, '')) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [repo.owner, repo.repo])

  const openFile = async (path: string) => {
    setFileLoading(true)
    try {
      const data = await api<any>(`/repositories/${repo.owner}/${repo.repo}/file-session?path=${encodeURIComponent(path)}`)
      setFile({ path, content: data.content || '' })
    } catch (e) {
      setError(String(e).replace(/^Error:\s*/, ''))
    } finally {
      setFileLoading(false)
    }
  }

  return <div className="repo-quick-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
    <aside className="repo-quick-drawer">
      <header className="repo-quick-head">
        <div><span className="label">REPOSITORY INSPECTOR</span><h2>{repo.owner}/{repo.repo}</h2><small>{repo.name} · GitHub working surface</small></div>
        <button className="close-small" onClick={onClose}><X size={16} /></button>
      </header>
      <div className="repo-quick-body">
        <section className="repo-quick-tree">
          <div className="repo-quick-section-head"><b>FILES</b>{loading && <Loader2 className="spin" size={14} />}</div>
          {error ? <Empty title="Unable to read repository" text={error} /> : loading ? <Loading /> : <div className="quick-tree-list">{tree.slice(0, 250).map((item: any) => item.type === 'tree' ? <div className="quick-tree-row folder-row" key={item.path}><span>DIR</span><code>{item.path}</code></div> : <button type="button" className="quick-tree-row file-row" key={item.path} onClick={() => openFile(item.path)}><span>FILE</span><code>{item.path}</code></button>)}</div>}
        </section>
        <section className="repo-quick-code">
          <div className="repo-quick-section-head"><b>{file?.path || 'FILE PREVIEW'}</b>{fileLoading && <Loader2 className="spin" size={14} />}</div>
          {file ? <pre>{file.content}</pre> : <div className="quick-code-empty">Select a file to inspect its current GitHub contents.</div>}
        </section>
      </div>
    </aside>
  </div>
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="metric"><span>{label}</span><b>{value}</b></div> }
function Loading() { return <div className="loading"><Loader2 className="spin" size={20} /><span>Connecting to GitHub layer…</span></div> }
function Empty({ title, text }: { title: string; text: string }) { return <div className="empty-state"><div className="empty-orb"><Bot size={18} /></div><h3>{title}</h3><p>{text}</p></div> }
function RecentSignals() { const logs = loadLogs().slice(0, 4); return <div className="signals">{(logs.length ? logs : [{ time: nowLabel(), text: 'Agent core initialized', kind: 'success' as const }]).map((l, i) => <div className="signal-row" key={i}><span>{l.time}</span><i className={l.kind || ''} /><b>{l.text}</b></div>)}</div> }
function Toast({ notice, onClose }: { notice: { title: string; text: string }; onClose: () => void }) { useEffect(() => { const id = window.setTimeout(onClose, 6500); return () => window.clearTimeout(id) }, [notice, onClose]); return <div className="toast"><div className="toast-orb"><Zap size={16} /></div><div className="toast-body"><b>{notice.title}</b><span>{notice.text}</span></div><button aria-label="Dismiss notification" onClick={onClose}><X size={15} /></button></div> }

function AccountProfile({
  user,
  onClose,
  onLogout,
}: {
  user: AuthUser
  onClose: () => void
  onLogout: () => void | Promise<void>
}) {
  const displayName = user.name || user.login

  return <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
    <section className="developer-modal account-modal">
      <header className="developer-head">
        <div className="developer-identity">
          <div className="developer-avatar account-avatar">
            {user.avatar_url
              ? <img className="avatar-img" src={user.avatar_url} alt="" />
              : <UserRound size={28} />}
          </div>
          <div>
            <h2>{displayName}</h2>
            <p>GitHub Account</p>
            <small>@{user.login} · Developer</small>
          </div>
        </div>
        <button className="close-btn" onClick={onClose}><X size={19} /></button>
      </header>

      <div className="developer-body">
        <section className="profile-intro profile-full about-section">
          <h3>Connected Account</h3>
          <p>This DevPilot session is connected to the GitHub account currently signed in. Repository access uses this authenticated session.</p>
        </section>

        <ProfileSection title="ACCOUNT DETAILS" className="account-details-section">
          <div className="education-card">
            <div className="education-row">
              <div>
                <b>GitHub username</b>
                <span>@{user.login}</span>
              </div>
              <strong>CONNECTED</strong>
            </div>

            {user.name && <div className="education-row">
              <div>
                <b>Display name</b>
                <span>{user.name}</span>
              </div>
            </div>}

            {user.id !== undefined && <div className="education-row">
              <div>
                <b>GitHub user ID</b>
                <span>{String(user.id)}</span>
              </div>
            </div>}
          </div>
        </ProfileSection>

        <ProfileSection title="SESSION" className="account-session-section">
          <div className="shine-card leadership-card">
            <b>GitHub session active</b>
            <p>DevPilot can now request repositories through the authenticated GitHub session instead of relying only on a fixed local identity.</p>
          </div>
        </ProfileSection>

        <div className="developer-links profile-full">
          <a href={`https://github.com/${user.login}`} target="_blank" rel="noreferrer">
            <GitBranch size={14} /> GitHub <ExternalLink size={13} />
          </a>
        </div>

        <footer className="developer-footer profile-full">
          <span>{displayName.toUpperCase()} · GITHUB ACCOUNT</span>
          <div className="session-actions">
            <button className="session-button danger" onClick={() => void onLogout()}>
              <LogOut size={14} /> Sign out
            </button>
          </div>
        </footer>
      </div>
    </section>
  </div>
}

function DeveloperProfile({ onClose, onLogout }: { onClose: () => void; onLogout: () => void }) {
  return <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
    <section className="developer-modal">
      <header className="developer-head"><div className="developer-identity"><div className="developer-avatar">JK<span /></div><div><h2>{profile.name}</h2><p>{profile.role}</p><small>{profile.location}</small></div></div><button className="close-btn" onClick={onClose}><X size={19} /></button></header>
      <div className="developer-body">
        <section className="profile-intro profile-full about-section"><h3>About</h3><p>{profile.intro}</p><p>{profile.story}</p></section>
        <ProfileSection title="Education" className="education-section"><div className="education-card">
          <div className="education-row"><div><b>B.E. Computer Science & Engineering</b><span>Chandigarh University · 2023–2026</span></div><strong>CGPA 7.32</strong></div>
          <div className="education-row"><div><b>Diploma</b><span>SCTVT Odisha</span></div><strong>71.81%</strong></div>
          <div className="education-row"><div><b>Class X</b><span>CBSE</span></div><strong>8.20 CGPA</strong></div>
          <p>Practical engineering focus across backend development, databases, REST APIs, data analytics and applied software projects.</p>
        </div></ProfileSection>
        <ProfileSection title="Leadership & Campus Experience" className="leadership-section"><div className="shine-card leadership-card"><b>{profile.leadership}</b><p>{profile.leadershipDetail}</p><small className="leadership-badge">4 Consecutive Semesters</small><div className="leadership-skills">{profile.leadershipSkills.map(x => <span key={x}>{x}</span>)}</div></div></ProfileSection>
        <ProfileSection title="What I Build" className="build-section"><div className="profile-grid">{profile.buildAreas.map(([title, desc]) => <article className="shine-card build-card" key={title}><b>{title}</b><span>{desc}</span></article>)}</div></ProfileSection>
        <ProfileSection title="Technical Skills" className="skills-section"><div className="skill-list">{profile.skills.map(s => <span key={s}>{s}</span>)}</div></ProfileSection>
        <ProfileSection title="Projects" className="projects-section profile-full"><div className="project-list">{projects.map(p => <ProjectCard key={p.name} project={p} />)}</div></ProfileSection>
        <ProfileSection title="Certifications & Achievements" className="certifications-section profile-full"><div className="cert-list">{profile.certifications.map((c, i) => <article className="shine-card cert-card" key={c}><span className="cert-number">{String(i + 1).padStart(2, '0')}</span><div><b>{c.split(' — ')[0]}</b><span>{c.includes(' — ') ? c.slice(c.indexOf(' — ') + 3) : ''}</span></div></article>)}</div></ProfileSection>
        <div className="profile-columns profile-full"><ProfileSection title="Languages" className="languages-section"><div className="compact-list">{profile.languages.map(x => <span key={x}>{x}</span>)}</div></ProfileSection><ProfileSection title="Beyond Code" className="beyond-section"><div className="chip-row">{profile.beyond.map(x => <span key={x}>{x}</span>)}</div></ProfileSection><ProfileSection title="Currently Exploring" className="exploring-section"><div className="chip-row accent">{profile.exploring.map(x => <span key={x}>{x}</span>)}</div></ProfileSection></div>
        <div className="developer-links profile-full"><a href="https://github.com/jvjitendra" target="_blank" rel="noreferrer"><GitBranch size={14} /> GitHub <ExternalLink size={13} /></a><a href="https://www.linkedin.com/in/jvjitendra/" target="_blank" rel="noreferrer"><Link2 size={14} /> LinkedIn <ExternalLink size={13} /></a><a href="https://www.instagram.com/jv_jitendra/" target="_blank" rel="noreferrer"><Link2 size={14} /> Instagram <ExternalLink size={13} /></a></div>
        <footer className="developer-footer profile-full"><span>JITENDRA VERMA · BUILDER & OPERATOR OF DEVPILOT</span><span>DevPilot · Vaani · TaskFlow · + many more</span><div className="session-actions"><button className="session-button danger" onClick={onLogout}><LogOut size={14} /> Sign out</button></div></footer>
      </div>
    </section>
  </div>
}
function ProfileSection({ title, children, className = "" }: { title: string; children: ReactNode; className?: string }) { return <section className={`profile-section ${className}`.trim()}><div className="profile-section-title"><span>{title}</span><i /></div>{children}</section> }
function ProjectCard({ project }: { project: typeof projects[number] }) { return <article className={`project-card shine-card ${project.current ? 'current' : ''}`}><div className="project-top"><div className="project-number">#{project.no}</div><div className="project-icon">{project.name === 'DevPilot' ? <Bot size={17} /> : project.name === 'Vaani' ? <Sparkles size={17} /> : project.name === 'TaskFlow' ? <CheckCircle2 size={17} /> : project.name === 'E-commerce Backend' ? <Server size={17} /> : <Code2 size={17} />}</div><div className="project-name"><b>{project.name}</b><span>{project.type}</span></div>{project.current && <span className="project-status">ACTIVE BUILD</span>}</div><p>{project.description}</p>{project.why && <p className="project-why"><b>Why</b> {project.why}</p>}<ul className="project-highlights">{project.highlights.map((x: string) => <li key={x}>{x}</li>)}</ul><div className="project-stack">{project.stack.map(x => <span key={x}>{x}</span>)}</div><div className="project-links">{project.live ? <a href={project.live} target="_blank" rel="noreferrer"><ExternalLink size={13} /> Live</a> : <span className="disabled-link">Workspace</span>}{project.github ? <a href={project.github} target="_blank" rel="noreferrer"><GitBranch size={13} /> GitHub</a> : <span className="disabled-link">Private / local</span>}</div></article> }

export { App }
