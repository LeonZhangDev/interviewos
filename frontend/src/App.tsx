import { useEffect, useRef, useState } from 'react'
import { Bell, KeyRound, LogOut, Search } from 'lucide-react'
import { api, authToken, setAuthTokens } from './api'
import { Sidebar } from './components/Sidebar'
import { AuthPage } from './pages/AuthPage'
import { CodingPage } from './pages/CodingPage'
import { DashboardPage } from './pages/DashboardPage'
import { InterviewPage } from './pages/InterviewPage'
import { KnowledgeGraphPage } from './pages/KnowledgeGraphPage'
import { ReportsPage } from './pages/ReportsPage'
import { PublicPortfolioPage } from './pages/PublicPortfolioPage'
import { LearningPage } from './pages/LearningPage'
import { PortfolioPage } from './pages/PortfolioPage'
import { ProjectsPage } from './pages/ProjectsPage'
import { OAuthCallbackPage } from './pages/OAuthCallbackPage'
import { PlaygroundsPage } from './pages/PlaygroundsPage'
import { QuestionImportPage } from './pages/QuestionImportPage'
import { QuestionsPage } from './pages/QuestionsPage'
import { SystemDesignPage } from './pages/SystemDesignPage'
import type { AuthUser, CodeSeed, NavKey, Question, SearchFocus, SearchGroup, SearchGroupType, SearchResultItem } from './types'

export default function App() {
  const [route, setRoute] = useState(() => window.location.pathname)
  const [pendingNav, setPendingNav] = useState<NavKey | null>(null)

  if (route.startsWith('/portfolio/')) return <PublicPortfolioPage />
  if (route.startsWith('/oauth/callback')) {
    return (
      <OAuthCallbackPage
        onFinished={() => {
          window.history.replaceState(null, '', '/')
          setPendingNav('projects')
          setRoute('/')
        }}
      />
    )
  }
  return <AuthenticatedWorkbench initialNav={pendingNav ?? undefined} />
}

function AuthenticatedWorkbench({ initialNav }: { initialNav?: NavKey }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [checking, setChecking] = useState(Boolean(authToken()))

  useEffect(() => {
    const unauthorized = () => { setAuthTokens('', ''); setUser(null); setChecking(false) }
    window.addEventListener('interviewos:unauthorized', unauthorized)
    if (authToken()) api.me().then(setUser).catch(unauthorized).finally(() => setChecking(false))
    return () => window.removeEventListener('interviewos:unauthorized', unauthorized)
  }, [])

  if (checking) return <div className="boot-screen"><div className="brand-mark">IO</div><strong>正在启动 InterviewOS…</strong></div>
  if (!user) return <AuthPage onAuthenticated={setUser} />
  return <WorkbenchApp user={user} onUserChanged={setUser} initialNav={initialNav} />
}

function WorkbenchApp({ user, onUserChanged, initialNav }: { user: AuthUser; onUserChanged: (user: AuthUser | null) => void; initialNav?: NavKey }) {
  const [active, setActive] = useState<NavKey>(initialNav || 'dashboard')
  const [codeSeed, setCodeSeed] = useState<CodeSeed | null>(null)
  const [passwordOpen, setPasswordOpen] = useState(false)
  const [searchFocus, setSearchFocus] = useState<SearchFocus | null>(null)

  function openQuestionCode(q: Question) {
    setCodeSeed({ title: q.title, code: q.code, questionId: q.id, language: 'Python' })
    setActive('coding')
  }

  function openProjectCode(seed: CodeSeed) {
    setCodeSeed(seed)
    setActive('coding')
  }

  function handleSearchNavigate(target: SearchFocus) {
    setSearchFocus(target)
    setActive(target.page)
  }

  function logout() {
    api.logout({ all_devices: true }).catch(() => undefined)
    setAuthTokens('', '')
    onUserChanged(null)
  }

  return (
    <div className="app-shell">
      <Sidebar active={active} onChange={setActive} />
      <main className="main-shell">
        <header className="topbar">
          <TopSearch onNavigate={handleSearchNavigate} />
          <div className="top-actions"><button className="icon-button" aria-label="通知"><Bell size={18} /></button><div className="top-user"><div className="avatar">{(user.display_name || user.username).slice(0, 2).toUpperCase()}</div><span><strong>{user.display_name || user.username}</strong><small>@{user.username}</small></span></div><button className="icon-button" aria-label="修改密码" title="修改密码" onClick={() => setPasswordOpen(true)}><KeyRound size={17} /></button><button className="icon-button" aria-label="退出登录" title="退出登录（撤销所有设备令牌）" onClick={logout}><LogOut size={17} /></button></div>
        </header>
        <div className="content-shell">
          {active === 'dashboard' && <DashboardPage />}
          {active === 'projects' && <ProjectsPage onOpenCode={openProjectCode} focusRepoId={searchFocus?.page === 'projects' ? searchFocus.repoId : undefined} />}
          {active === 'questions' && <QuestionsPage onOpenCode={openQuestionCode} focusQuestionId={searchFocus?.page === 'questions' ? searchFocus.questionId : undefined} />}
          {active === 'coding' && <CodingPage initialSeed={codeSeed} />}
          {active === 'playgrounds' && <PlaygroundsPage />}
          {active === 'interview' && <InterviewPage />}
          {active === 'reports' && <ReportsPage focusSessionId={searchFocus?.page === 'reports' ? searchFocus.sessionId : undefined} />}
          {active === 'learning' && <LearningPage />}
          {active === 'knowledge' && <KnowledgeGraphPage focusNodeSlug={searchFocus?.page === 'knowledge' ? searchFocus.nodeSlug : undefined} />}
          {active === 'import' && <QuestionImportPage />}
          {active === 'system' && <SystemDesignPage />}
          {active === 'portfolio' && <PortfolioPage user={user} />}
        </div>
      </main>
      {passwordOpen ? <ChangePasswordModal user={user} onClose={() => setPasswordOpen(false)} onUserChanged={onUserChanged} /> : null}
    </div>
  )
}

function searchTarget(item: SearchResultItem, type: SearchGroupType): SearchFocus {
  if (type === 'question' || type === 'answer_version') return { page: 'questions', questionId: item.question_id }
  if (type === 'knowledge_node') return { page: 'knowledge', nodeSlug: String(item.id) }
  if (type === 'repo_file') return { page: 'projects', repoId: item.repo_id }
  return { page: 'reports', sessionId: item.session_id }
}

function TopSearch({ onNavigate }: { onNavigate: (target: SearchFocus) => void }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [results, setResults] = useState<SearchGroup[] | null>(null)
  const [loading, setLoading] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const seqRef = useRef(0)

  useEffect(() => {
    const term = query.trim()
    if (term.length < 2) { setResults(null); setLoading(false); return }
    setLoading(true)
    const timer = setTimeout(() => {
      const seq = ++seqRef.current
      api.search(term).then((data) => {
        if (seq !== seqRef.current) return
        setResults(data.groups)
        setLoading(false)
      }).catch(() => {
        if (seq !== seqRef.current) return
        setResults(null)
        setLoading(false)
      })
    }, 250)
    return () => clearTimeout(timer)
  }, [query])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
        setOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  function choose(item: SearchResultItem, type: SearchGroupType) {
    onNavigate(searchTarget(item, type))
    setOpen(false)
    inputRef.current?.blur()
  }

  const firstHit = results?.find((g) => g.items.length > 0)
  const term = query.trim()

  return (
    <div className="top-search-wrap" ref={boxRef}>
      <div className="top-search">
        <Search size={16} />
        <input
          ref={inputRef}
          value={query}
          placeholder="搜索题目、知识点、仓库代码、我的答案…"
          onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') { setOpen(false); inputRef.current?.blur() }
            if (e.key === 'Enter' && firstHit) choose(firstHit.items[0], firstHit.type)
          }}
        />
        <kbd>⌘ K</kbd>
      </div>
      {open ? (
        <div className="search-dropdown card">
          {term.length < 2 ? (
            <p className="search-empty">输入至少 2 个字符，跨面试题、知识点、仓库文件、我的答案和面试轮次搜索。</p>
          ) : loading ? (
            <p className="search-empty">搜索中…</p>
          ) : results && results.some((g) => g.items.length > 0) ? (
            results.filter((g) => g.items.length > 0).map((group) => (
              <div key={group.type} className="search-group">
                <div className="search-group-label">{group.label}</div>
                {group.items.map((item) => (
                  <button className="search-item" key={`${group.type}-${item.id}`} onClick={() => choose(item, group.type)}>
                    <strong>{item.title}</strong>
                    <small>{item.subtitle}</small>
                  </button>
                ))}
              </div>
            ))
          ) : (
            <p className="search-empty">没有找到与 “{term}” 相关的内容。</p>
          )}
        </div>
      ) : null}
    </div>
  )
}

function ChangePasswordModal({ user, onClose, onUserChanged }: { user: AuthUser; onClose: () => void; onUserChanged: (user: AuthUser) => void }) {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)

  async function submit() {
    if (newPassword !== confirmPassword) { setError('两次输入的新密码不一致。'); return }
    setBusy(true); setError('')
    try {
      const result = await api.changePassword(currentPassword, newPassword)
      setAuthTokens(result.access_token, result.refresh_token)
      onUserChanged(result.user)
      setDone(true)
    } catch (err) {
      setError(String(err).replace(/^Error:\s*/, '').replace(/^.*?"detail":"([^"]+)".*$/, '$1'))
    } finally { setBusy(false) }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <section className="auth-panel modal-card" onClick={(e) => e.stopPropagation()}>
        {done ? <>
          <h2>密码已更新</h2>
          <p>所有设备上的旧令牌均已撤销，本页面已使用新会话继续。</p>
          <button className="primary wide" onClick={onClose}>完成</button>
        </> : <>
          <h2>修改密码</h2>
          <p>当前账号 @{user.username}。修改成功后其他设备的登录状态会立即失效。</p>
          <label className="field-label">当前密码</label>
          <input className="auth-input" type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} autoComplete="current-password" />
          <label className="field-label">新密码（至少 8 位）</label>
          <input className="auth-input" type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} autoComplete="new-password" />
          <label className="field-label">确认新密码</label>
          <input className="auth-input" type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} autoComplete="new-password" onKeyDown={(e) => { if (e.key === 'Enter') submit() }} />
          {error ? <div className="auth-error">{error}</div> : null}
          <div className="modal-actions">
            <button className="secondary" onClick={onClose} disabled={busy}>取消</button>
            <button className="primary" onClick={submit} disabled={busy || currentPassword.length < 8 || newPassword.length < 8 || confirmPassword.length < 8}>{busy ? '提交中…' : '确认修改'}</button>
          </div>
        </>}
      </section>
    </div>
  )
}
