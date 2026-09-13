import { useState } from 'react'
import { BrainCircuit, KeyRound, ShieldCheck, UserPlus } from 'lucide-react'
import { api, setAuthTokens } from '../api'
import type { AuthUser } from '../types'

export function AuthPage({ onAuthenticated }: { onAuthenticated: (user: AuthUser) => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [identity, setIdentity] = useState('')
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit() {
    setBusy(true); setError('')
    try {
      const result = mode === 'login'
        ? await api.login({ identity, password })
        : await api.register({ username, email, password, display_name: displayName })
      setAuthTokens(result.access_token, result.refresh_token)
      onAuthenticated(result.user)
    } catch (err) {
      setError(String(err).replace(/^Error:\s*/, ''))
    } finally { setBusy(false) }
  }

  return (
    <div className="auth-shell">
      <section className="auth-story">
        <div className="brand auth-brand"><div className="brand-mark">IO</div><div><strong>InterviewOS</strong><span>AI 工程师面试工作台</span></div></div>
        <div className="auth-copy"><h1>把项目、代码和面试训练放进同一个工作台。</h1><p>v0.7 加入个人账号，让答案版本、复习计划、系统设计白板和录音记录开始真正属于你。</p></div>
        <div className="auth-points"><div><BrainCircuit /><span><strong>AI 面试</strong><small>动态追问与报告</small></span></div><div><ShieldCheck /><span><strong>JWT 会话</strong><small>本地账户与受保护 API</small></span></div><div><KeyRound /><span><strong>私有工作台</strong><small>公开作品集与个人数据分离</small></span></div></div>
      </section>
      <section className="auth-panel">
        <div className="auth-tabs"><button className={mode === 'login' ? 'active' : ''} onClick={() => { setMode('login'); setError('') }}>登录</button><button className={mode === 'register' ? 'active' : ''} onClick={() => { setMode('register'); setError('') }}>创建账号</button></div>
        <h2>{mode === 'login' ? '继续你的面试准备' : '创建 InterviewOS 账号'}</h2>
        <p>{mode === 'login' ? '使用用户名或邮箱登录。' : '第一版账号保存在你自己的 PostgreSQL 中。'}</p>
        {mode === 'register' ? <>
          <label className="field-label">用户名</label><input className="auth-input" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="leon" autoComplete="username" />
          <label className="field-label">邮箱</label><input className="auth-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" autoComplete="email" />
          <label className="field-label">显示名称</label><input className="auth-input" value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Leon Zhang" />
        </> : <><label className="field-label">用户名 / 邮箱</label><input className="auth-input" value={identity} onChange={(e) => setIdentity(e.target.value)} placeholder="leon" autoComplete="username" /></>}
        <label className="field-label">密码</label><input className="auth-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="至少 8 位" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} onKeyDown={(e) => { if (e.key === 'Enter') submit() }} />
        {error ? <div className="auth-error">{error}</div> : null}
        <button className="primary wide auth-submit" onClick={submit} disabled={busy || password.length < 8 || (mode === 'login' ? identity.length < 3 : username.length < 3 || email.length < 5)}>{mode === 'register' ? <UserPlus size={16} /> : <KeyRound size={16} />}{busy ? '处理中…' : mode === 'login' ? '登录' : '创建账号'}</button>
        <small className="auth-note">{'公开作品集 /portfolio/<用户名> 不要求登录，且只展示你主动设为公开的仓库；学习记录和工作台 API 默认需要 JWT。'}</small>
      </section>
    </div>
  )
}
