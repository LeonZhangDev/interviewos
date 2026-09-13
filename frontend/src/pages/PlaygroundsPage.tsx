import { useEffect, useRef, useState } from 'react'
import Editor from '@monaco-editor/react'
import {
  Database,
  Gauge,
  Play,
  RotateCcw,
  ShieldAlert,
  Sparkles,
  Trash2,
  TriangleAlert,
} from 'lucide-react'
import { api } from '../api'
import type {
  FastApiPlaygroundResult,
  PlaygroundKind,
  PlaygroundMeta,
  PlaygroundSessionInfo,
  RedisPlaygroundResult,
  SqlPlaygroundResult,
} from '../types'

/** api.ts throws Error(response.text()) — the text is a JSON body with "detail". */
function errorDetail(error: unknown): string {
  const text = String(error).replace(/^Error:\s*/, '')
  try { return JSON.parse(text).detail || text } catch { return text }
}

function showValue(value: unknown): string {
  if (value === null) return 'NULL'
  if (typeof value === 'string') return value
  try { return JSON.stringify(value) } catch { return String(value) }
}

const KIND_LABEL: Record<PlaygroundKind, string> = { sql: 'SQL', redis: 'Redis', fastapi: 'FastAPI' }

export function PlaygroundsPage() {
  const [kind, setKind] = useState<PlaygroundKind>('sql')
  const [meta, setMeta] = useState<PlaygroundMeta | null>(null)

  useEffect(() => { api.playgroundMeta().then(setMeta).catch(() => setMeta(null)) }, [])

  const sample = meta?.samples?.[kind]?.code || ''
  const policy = meta?.policy?.[kind] || ''

  return (
    <div className="page-stack">
      <div className="page-header">
        <div>
          <span className="eyebrow">面试实操沙箱</span>
          <h1>Playgrounds 沙箱</h1>
          <p>SQL / Redis / FastAPI 面试实操环境：会话级数据隔离，危险语句双重拦截，随时重置重来。</p>
        </div>
      </div>

      <div className="mode-tabs">
        {(['sql', 'redis', 'fastapi'] as PlaygroundKind[]).map((key) => (
          <button key={key} className={kind === key ? 'active' : ''} onClick={() => setKind(key)}>{KIND_LABEL[key]}</button>
        ))}
      </div>

      {policy ? (
        <div className="sandbox-note">
          <ShieldAlert size={15} />
          <span>{policy}</span>
        </div>
      ) : null}

      {kind === 'sql' && <SqlSandbox sample={sample} meta={meta} />}
      {kind === 'redis' && <RedisSandbox sample={sample} meta={meta} />}
      {kind === 'fastapi' && <FastApiSandbox sample={sample} meta={meta} />}
    </div>
  )
}

/** Lazily create the sandbox session; auto-recreate once when it expired (410). */
function useSandboxSession(kind: 'sql' | 'redis') {
  const [session, setSession] = useState<PlaygroundSessionInfo | null>(null)
  const [busy, setBusy] = useState(false)

  async function ensure(): Promise<number> {
    if (session) return session.session_id
    setBusy(true)
    try {
      const created = await api.createPlaygroundSession(kind)
      setSession(created)
      return created.session_id
    } finally { setBusy(false) }
  }

  async function recreate(): Promise<number> {
    setBusy(true)
    try {
      const created = await api.createPlaygroundSession(kind)
      setSession(created)
      return created.session_id
    } finally { setBusy(false) }
  }

  return { session, busy, ensure, recreate, setSession }
}

function SessionBar({ session, ttlHours, onNew, onReset, busy, dirty }: {
  session: PlaygroundSessionInfo | null
  ttlHours?: number
  onNew: () => void
  onReset: () => void
  busy: boolean
  dirty: boolean
}) {
  return (
    <div className="pg-session-bar">
      <Database size={14} />
      {session
        ? <span>沙箱会话 <strong>#{session.session_id}</strong> · 独立 schema{ttlHours ? ` · ${ttlHours}h 后过期` : ''} · 重置只影响你自己的沙箱</span>
        : <span>尚无会话 — 首次执行时自动创建</span>}
      <span className="pg-session-actions">
        {dirty ? <button className="secondary" onClick={onReset} disabled={busy || !session}><Trash2 size={13} /> 清空重置</button> : null}
        <button className="secondary" onClick={onNew} disabled={busy}><Sparkles size={13} /> 新会话</button>
      </span>
    </div>
  )
}

function SqlSandbox({ sample, meta }: { sample: string; meta: PlaygroundMeta | null }) {
  const fallback = "CREATE TABLE candidates (\n  id serial PRIMARY KEY,\n  name text NOT NULL,\n  score int NOT NULL\n);\n\nINSERT INTO candidates (name, score) VALUES ('Alice', 88), ('Bob', 72), ('Carol', 95);\n\nSELECT name, score FROM candidates ORDER BY score DESC;"
  const [code, setCode] = useState(sample || fallback)
  const [result, setResult] = useState<SqlPlaygroundResult | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const { session, busy, ensure, recreate, setSession } = useSandboxSession('sql')
  const retried = useRef(false)

  useEffect(() => { if (sample) setCode(sample) }, [sample])

  async function run() {
    if (!code.trim() || running) return
    setRunning(true); setError('')
    try {
      const sessionId = await ensure()
      try {
        setResult(await api.runPlaygroundSql(sessionId, code))
      } catch (err) {
        const detail = errorDetail(err)
        if (detail.toLowerCase().includes('expired') && !retried.current) {
          retried.current = true
          const fresh = await recreate()
          setResult(await api.runPlaygroundSql(fresh, code))
          setError('之前的会话已过期，已自动创建新会话并重跑（旧数据已清空）。')
        } else {
          setError(detail)
        }
      }
    } catch (err) { setError(errorDetail(err)) } finally { setRunning(false); retried.current = false }
  }

  async function reset() {
    if (!session) return
    setRunning(true); setError('')
    try {
      await api.resetPlayground(session.session_id)
      setResult(null)
      setError('沙箱已重置：建表和数据都清空了。')
    } catch (err) { setError(errorDetail(err)) } finally { setRunning(false) }
  }

  async function newSession() {
    setError('')
    try {
      setSession(await api.createPlaygroundSession('sql'))
      setResult(null)
      setError('已切换到新沙箱会话（全新 schema）。')
    } catch (err) { setError(errorDetail(err)) }
  }

  return (
    <div className="pg-layout">
      <section className="card pg-editor-card">
        <div className="ide-toolbar">
          <div><span className="dot" /><strong>session.sql</strong></div>
          <div className="button-row">
            <button className="secondary" onClick={() => setCode(sample || fallback)}><RotateCcw size={14} /> 示例</button>
            <button className="primary" onClick={run} disabled={running || busy}><Play size={14} /> {running ? '执行中…' : '执行'}</button>
          </div>
        </div>
        <Editor height="380px" language="sql" value={code} onChange={(v) => setCode(v ?? '')} theme="vs-dark"
          options={{ minimap: { enabled: false }, fontSize: 14, padding: { top: 14 }, wordWrap: 'on', automaticLayout: true }} />
        <SessionBar session={session} ttlHours={meta?.limits.session_ttl_hours} onNew={newSession} onReset={reset} busy={running || busy} dirty={Boolean(result)} />
      </section>

      <aside className="card pg-result-pane">
        <div className="console-title"><Gauge size={15} /> 执行结果 {result ? `· ${result.duration_ms}ms` : ''}</div>
        {error ? <div className="pg-error"><TriangleAlert size={14} /><span>{error}</span></div> : null}
        {!result ? (
          <div className="pg-empty">整批 SQL 在会话专属 schema 中作为一个事务执行：任一语句失败，整批回滚。<br />DROP DATABASE / CREATE ROLE / pg_sleep 等危险语句会被拦截。</div>
        ) : !result.ok ? (
          <div className="pg-error"><TriangleAlert size={14} /><span>{result.error || '执行失败'}</span></div>
        ) : (
          <div className="pg-statements">
            {result.statements.map((statement, i) => (
              <div key={i} className="pg-statement">
                <div className="pg-statement-head">
                  <b>#{i + 1}</b>
                  <span>{statement.rowcount} 行受影响</span>
                  {statement.truncated ? <em>结果已截断</em> : null}
                </div>
                {statement.columns.length ? (
                  <div className="pg-table-scroll">
                    <table className="pg-table">
                      <thead><tr>{statement.columns.map((col) => <th key={col}>{col}</th>)}</tr></thead>
                      <tbody>
                        {statement.rows.map((row, r) => (
                          <tr key={r}>{row.map((cell, c) => <td key={c}>{showValue(cell)}</td>)}</tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : <div className="pg-empty">（无返回行）</div>}
              </div>
            ))}
          </div>
        )}
      </aside>
    </div>
  )
}

type RedisHistoryEntry = { command: string; ok: boolean; result: RedisPlaygroundResult }

function RedisSandbox({ sample, meta }: { sample: string; meta: PlaygroundMeta | null }) {
  const fallback = 'SET candidate:1 \'{"name":"Alice","score":88}\''
  const [command, setCommand] = useState(sample || fallback)
  const [history, setHistory] = useState<RedisHistoryEntry[]>([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const { session, busy, ensure, recreate, setSession } = useSandboxSession('redis')
  const retried = useRef(false)

  useEffect(() => { if (sample) setCommand(sample) }, [sample])

  async function run() {
    if (!command.trim() || running) return
    setRunning(true); setError('')
    const text = command.trim()
    try {
      const sessionId = await ensure()
      const entry: RedisHistoryEntry = { command: text, ok: true, result: {} as RedisPlaygroundResult }
      try {
        entry.result = await api.runPlaygroundRedis(sessionId, command)
      } catch (err) {
        const detail = errorDetail(err)
        if (detail.toLowerCase().includes('expired') && !retried.current) {
          retried.current = true
          const fresh = await recreate()
          entry.result = await api.runPlaygroundRedis(fresh, command)
          setError('之前的会话已过期，已自动创建新会话并重跑（旧数据已清空）。')
        } else {
          entry.ok = false
          entry.result = { ok: false, result: null, duration_ms: 0, error: detail }
        }
      }
      setHistory((items) => [entry, ...items].slice(0, 50))
    } catch (err) { setError(errorDetail(err)) } finally { setRunning(false); retried.current = false }
  }

  async function reset() {
    if (!session) return
    setRunning(true); setError('')
    try {
      await api.resetPlayground(session.session_id)
      setHistory([])
      setError('沙箱已重置：当前会话的所有 key 已清空。')
    } catch (err) { setError(errorDetail(err)) } finally { setRunning(false) }
  }

  async function newSession() {
    setError('')
    try {
      setSession(await api.createPlaygroundSession('redis'))
      setHistory([])
      setError('已切换到新沙箱会话（独立 DB index）。')
    } catch (err) { setError(errorDetail(err)) }
  }

  return (
    <div className="pg-redis-layout">
      <section className="card pg-redis-card">
        <div className="pg-redis-input-row">
          <span className="pg-redis-prompt">redis&gt;</span>
          <input
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') run() }}
            placeholder="SET key value · GET key · LPUSH list a b c · EXPIRE key 60 …"
            spellCheck={false}
          />
          <button className="primary" onClick={run} disabled={running || busy}><Play size={14} /> {running ? '执行中…' : '执行'}</button>
        </div>
        <p className="pg-redis-hint">一次一条命令，回车即执行。FLUSHALL / CONFIG / EVAL / SELECT 等危险命令会被拦截；命令与参数分离传输，无法注入第二条命令。</p>
        {error ? <div className="pg-error"><TriangleAlert size={14} /><span>{error}</span></div> : null}
        <SessionBar session={session} ttlHours={meta?.limits.session_ttl_hours} onNew={newSession} onReset={reset} busy={running || busy} dirty={history.length > 0} />
      </section>

      <section className="card pg-history-card">
        <div className="console-title"><Gauge size={15} /> 命令历史 {history.length ? `· ${history.length}` : ''}</div>
        {!history.length ? (
          <div className="pg-empty">还没有执行过命令。试试：<code>SET greeting hello</code>，然后 <code>GET greeting</code>。</div>
        ) : (
          <div className="pg-history-list">
            {history.map((item, i) => (
              <div key={i} className={item.result.ok ? 'pg-history-item' : 'pg-history-item fail'}>
                <code className="pg-history-cmd">{item.command}</code>
                <div className="pg-history-result">
                  {item.result.ok
                    ? <><span className="pg-type-pill">{item.result.result?.type}</span><code>{showValue(item.result.result?.value)}</code>{item.result.result?.truncated ? <em>截断</em> : null}</>
                    : <span className="pg-history-error">{item.result.error}</span>}
                  <small>{item.result.duration_ms}ms</small>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] as const

function FastApiSandbox({ sample, meta }: { sample: string; meta: PlaygroundMeta | null }) {
  const fallback = 'from fastapi import FastAPI\n\napp = FastAPI()\n\n\n@app.get("/hello")\ndef hello(name: str = "world"):\n    return {"message": f"hello {name}"}'
  const [code, setCode] = useState(sample || fallback)
  const [method, setMethod] = useState<(typeof METHODS)[number]>('GET')
  const [path, setPath] = useState('/hello')
  const [body, setBody] = useState('')
  const [result, setResult] = useState<FastApiPlaygroundResult | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { if (sample) { setCode(sample); setPath('/hello') } }, [sample])

  async function run() {
    if (!code.trim() || running) return
    setRunning(true); setError('')
    try {
      setResult(await api.runPlaygroundFastApi({ code, method, path, body }))
    } catch (err) { setError(errorDetail(err)) } finally { setRunning(false) }
  }

  const statusOk = result && result.ok && result.status < 400

  return (
    <div className="pg-layout">
      <section className="card pg-editor-card">
        <div className="ide-toolbar">
          <div><span className="dot" /><strong>app.py</strong></div>
          <div className="button-row">
            <button className="secondary" onClick={() => { setCode(sample || fallback); setPath('/hello'); setBody('') }}><RotateCcw size={14} /> 示例</button>
            <button className="primary" onClick={run} disabled={running}><Play size={14} /> {running ? '请求中…' : '发送请求'}</button>
          </div>
        </div>
        <Editor height="300px" language="python" value={code} onChange={(v) => setCode(v ?? '')} theme="vs-dark"
          options={{ minimap: { enabled: false }, fontSize: 14, padding: { top: 14 }, wordWrap: 'on', automaticLayout: true }} />
        <div className="pg-request-row">
          <select value={method} onChange={(e) => setMethod(e.target.value as (typeof METHODS)[number])}>
            {METHODS.map((m) => <option key={m}>{m}</option>)}
          </select>
          <input value={path} onChange={(e) => setPath(e.target.value)} placeholder="/hello" spellCheck={false} />
          <input className="pg-request-body" value={body} onChange={(e) => setBody(e.target.value)} placeholder='请求体 JSON（可选，例如 {"name":"AI"}）' spellCheck={false} />
        </div>
        <div className="pg-session-bar">
          <TriangleAlert size={14} />
          <span>无状态沙箱：应用在隔离子进程中启动（{meta?.limits.fastapi_max_chars ?? 12000} 字符上限，6s 超时），每次请求都是全新实例 — 适合验证路由 / 依赖 / 校验逻辑。</span>
        </div>
      </section>

      <aside className="card pg-result-pane">
        <div className="console-title"><Gauge size={15} /> 响应 {result ? `· ${result.duration_ms}ms` : ''}</div>
        {error ? <div className="pg-error"><TriangleAlert size={14} /><span>{error}</span></div> : null}
        {!result ? (
          <div className="pg-empty">定义一个 <code>app = FastAPI()</code> 并编写路由，然后选择方法与路径发送请求。</div>
        ) : !result.ok ? (
          <div className="pg-error"><TriangleAlert size={14} /><span>{result.error}</span></div>
        ) : (
          <div className="pg-response">
            <div className={statusOk ? 'pg-status ok' : 'pg-status'}>
              <strong>{result.status}</strong><span>{result.status < 400 ? '成功' : '失败'}</span>
            </div>
            {Object.keys(result.headers).length ? (
              <details open className="pg-headers">
                <summary>响应头</summary>
                {Object.entries(result.headers).map(([key, value]) => <p key={key}><b>{key}</b><code>{value}</code></p>)}
              </details>
            ) : null}
            <div className="pg-body-title">响应体</div>
            <pre>{result.body || '（空响应体）'}</pre>
            {result.stdout ? <details className="pg-headers"><summary>stdout</summary><pre>{result.stdout}</pre></details> : null}
            {result.stderr ? <details className="pg-headers"><summary>stderr</summary><pre>{result.stderr}</pre></details> : null}
          </div>
        )}
      </aside>
    </div>
  )
}
