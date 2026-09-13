import { useEffect, useMemo, useState } from 'react'
import Editor from '@monaco-editor/react'
import {
  BrainCircuit,
  CheckCircle2,
  Clock3,
  EyeOff,
  History,
  LockKeyhole,
  Play,
  RotateCcw,
  Send,
  Terminal,
  TriangleAlert,
  XCircle,
} from 'lucide-react'
import { api } from '../api'
import type { CodeSeed, CodingChallenge, WrongBookEntry } from '../types'

const FALLBACK = `import asyncio

async def worker(name, delay):
    print(f"{name} start")
    await asyncio.sleep(delay)
    print(f"{name} end")

async def main():
    await asyncio.gather(
        worker("A", 0.2),
        worker("B", 0.1),
    )

asyncio.run(main())`

const languageMap: Record<string, string> = {
  Python: 'python', TypeScript: 'typescript', 'TypeScript React': 'typescript', JavaScript: 'javascript',
  JSON: 'json', SQL: 'sql', Markdown: 'markdown', Vue: 'html',
}

type Mode = 'challenge' | 'run' | 'explain'

function fmtSeconds(total: number) {
  const m = Math.floor(total / 60).toString().padStart(2, '0')
  const s = (total % 60).toString().padStart(2, '0')
  return `${m}:${s}`
}

function showValue(value: unknown) {
  try { return JSON.stringify(value) } catch { return String(value) }
}

export function CodingPage({ initialSeed }: { initialSeed: CodeSeed | null }) {
  const [mode, setMode] = useState<Mode>(initialSeed ? 'run' : 'challenge')
  const [code, setCode] = useState(initialSeed?.code || FALLBACK)
  const [output, setOutput] = useState('点击「运行」执行代码。')
  const [running, setRunning] = useState(false)
  const [explanation, setExplanation] = useState('')
  const [explainResult, setExplainResult] = useState<any>(null)

  const [challenges, setChallenges] = useState<CodingChallenge[]>([])
  const [selectedChallenge, setSelectedChallenge] = useState<CodingChallenge | null>(null)
  const [wrongBook, setWrongBook] = useState<WrongBookEntry[]>([])
  const [showWrongBook, setShowWrongBook] = useState(false)
  const [judgeResult, setJudgeResult] = useState<any>(null)
  const [timeComplexity, setTimeComplexity] = useState('')
  const [spaceComplexity, setSpaceComplexity] = useState('')
  const [lockMode, setLockMode] = useState(false)
  const [startedAt, setStartedAt] = useState<number | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [submissions, setSubmissions] = useState<any[]>([])

  useEffect(() => {
    Promise.all([api.codingChallenges(), api.wrongBook()]).then(([challengeItems, wrongItems]) => {
      setChallenges(challengeItems)
      setWrongBook(wrongItems)
      if (!initialSeed && challengeItems[0]) chooseChallenge(challengeItems[0])
    })
  }, [])

  useEffect(() => {
    if (!initialSeed) return
    setCode(initialSeed.code || FALLBACK)
    setMode(initialSeed.language && initialSeed.language !== 'Python' ? 'explain' : 'run')
    setExplanation('')
    setExplainResult(null)
    setJudgeResult(null)
    setLockMode(false)
    setStartedAt(null)
  }, [initialSeed])

  useEffect(() => {
    if (!lockMode || startedAt === null) return
    const tick = () => setElapsed(Math.floor((Date.now() - startedAt) / 1000))
    tick()
    const id = window.setInterval(tick, 1000)
    return () => window.clearInterval(id)
  }, [lockMode, startedAt])

  const canRun = useMemo(() => !initialSeed?.language || initialSeed.language === 'Python', [initialSeed])
  const activeSeedCode = mode === 'challenge' && selectedChallenge ? selectedChallenge.starter_code : (initialSeed?.code || FALLBACK)

  async function refreshCodingData(challengeId?: number) {
    const [challengeItems, wrongItems] = await Promise.all([api.codingChallenges(), api.wrongBook()])
    setChallenges(challengeItems)
    setWrongBook(wrongItems)
    if (challengeId) setSubmissions(await api.challengeSubmissions(challengeId))
  }

  async function chooseChallenge(item: CodingChallenge, previousCode?: string) {
    setSelectedChallenge(item)
    setMode('challenge')
    setCode(previousCode || item.starter_code)
    setJudgeResult(null)
    setTimeComplexity('')
    setSpaceComplexity('')
    setLockMode(false)
    setStartedAt(null)
    setElapsed(0)
    setSubmissions(await api.challengeSubmissions(item.id))
  }

  async function chooseWrong(entry: WrongBookEntry) {
    const item = challenges.find((x) => x.id === entry.challenge_id) ?? await api.codingChallenge(entry.challenge_id)
    await chooseChallenge(item, entry.last_code)
    setShowWrongBook(false)
  }

  async function run() {
    if (!canRun) return
    setRunning(true); setOutput('运行中…')
    try {
      const result = await api.runCode(code)
      setOutput(`${result.stdout || ''}${result.stderr ? `\n${result.stderr}` : ''}\n\nexit=${result.exit_code} · ${result.duration_ms}ms`)
    } catch (error) { setOutput(String(error)) } finally { setRunning(false) }
  }

  async function runVisibleTests() {
    if (!selectedChallenge) return
    setRunning(true); setJudgeResult(null)
    try {
      const result = await api.runChallenge(selectedChallenge.id, { code, time_complexity: timeComplexity, space_complexity: spaceComplexity, mode: lockMode ? 'lock' : 'practice' })
      setJudgeResult({ ...result, kind: 'public' })
    } catch (error) { setJudgeResult({ error: String(error) }) } finally { setRunning(false) }
  }

  async function submitChallenge() {
    if (!selectedChallenge) return
    setRunning(true); setJudgeResult(null)
    try {
      const result = await api.submitChallenge(selectedChallenge.id, { code, time_complexity: timeComplexity, space_complexity: spaceComplexity, mode: lockMode ? 'lock' : 'practice' })
      setJudgeResult({ ...result, kind: 'submit', elapsed_seconds: elapsed })
      if (lockMode) setLockMode(false)
      await refreshCodingData(selectedChallenge.id)
    } catch (error) { setJudgeResult({ error: String(error) }) } finally { setRunning(false) }
  }

  function startLockMode() {
    if (!selectedChallenge) return
    setCode(selectedChallenge.starter_code)
    setJudgeResult(null)
    setTimeComplexity('')
    setSpaceComplexity('')
    setElapsed(0)
    setStartedAt(Date.now())
    setLockMode(true)
  }

  async function evaluateExplanation() {
    if (!explanation.trim()) return
    setRunning(true)
    try {
      setExplainResult(await api.explainCode({ code, explanation, question_id: initialSeed?.questionId, source_title: initialSeed?.title || 'Code Lab' }))
    } catch (error) { setExplainResult({ score: 0, feedback: String(error), knowledge: [], symbols: [] }) } finally { setRunning(false) }
  }

  const visibleTests = judgeResult?.public?.cases || []

  return (
    <div className="page-stack" onCopy={(event) => { if (lockMode) event.preventDefault() }} onContextMenu={(event) => { if (lockMode) event.preventDefault() }}>
      <div className="page-header">
        <div><span className="eyebrow">Coding 面试 · 在线 IDE</span><h1>{mode === 'challenge' ? (selectedChallenge?.title || 'Coding 面试') : (initialSeed?.title || 'Python 代码实验')}</h1><p>练习模式看公开测试；提交时再跑隐藏测试。面试锁定模式会关闭提示、复制和自动补全，并记录答题时间。</p></div>
        {lockMode ? <div className="lock-timer"><LockKeyhole size={16} /><span>面试锁定</span><strong>{fmtSeconds(elapsed)}</strong></div> : null}
      </div>

      <div className="mode-tabs">
        <button className={mode === 'challenge' ? 'active' : ''} onClick={() => setMode('challenge')}>Coding 面试</button>
        <button className={mode === 'run' ? 'active' : ''} onClick={() => setMode('run')}>自由运行</button>
        <button className={mode === 'explain' ? 'active' : ''} onClick={() => setMode('explain')}>代码解释模式</button>
      </div>

      {mode === 'challenge' ? (
        <div className="coding-layout">
          <aside className="coding-rail card">
            <div className="coding-rail-head"><strong>{showWrongBook ? '错题本' : '题目列表'}</strong><button className={showWrongBook ? 'active' : ''} onClick={() => setShowWrongBook((v) => !v)}><History size={14} /> {wrongBook.length}</button></div>
            <div className="challenge-list">
              {showWrongBook ? wrongBook.map((entry) => <button key={entry.id} className="challenge-row wrong" onClick={() => chooseWrong(entry)}><span><b>{entry.title}</b><small>失败 {entry.attempts} 次 · {new Date(entry.last_attempt_at).toLocaleDateString()}</small></span><XCircle size={14} /></button>) : challenges.map((item) => <button key={item.id} className={selectedChallenge?.id === item.id ? 'challenge-row active' : 'challenge-row'} onClick={() => chooseChallenge(item)}><span><b>{item.title}</b><small>{'★'.repeat(item.difficulty)} · {item.tags.join(' / ')}</small></span>{item.solved ? <CheckCircle2 size={14} /> : item.wrongbook ? <XCircle size={14} /> : null}</button>)}
            </div>
          </aside>

          <section className="coding-main card">
            {selectedChallenge ? <>
              <div className="challenge-brief">
                <div><span className="eyebrow">算法题 · {'★'.repeat(selectedChallenge.difficulty)}</span><h2>{selectedChallenge.title}</h2><p>{selectedChallenge.description}</p><div className="tag-row">{selectedChallenge.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}</div></div>
                <div className="challenge-actions">{!lockMode ? <button className="secondary" onClick={startLockMode}><LockKeyhole size={14} /> 面试锁定模式</button> : <button className="secondary danger-ghost" onClick={() => setLockMode(false)}>退出锁定</button>}</div>
              </div>

              {!lockMode ? <div className="sample-tests"><span className="eyebrow">公开测试</span>{selectedChallenge.public_tests.map((test, i) => <div key={i}><b>#{i + 1}</b><code>{showValue(test.args)}</code><span>→</span><code>{showValue(test.expected)}</code></div>)}<details><summary>提示</summary><p>{selectedChallenge.hints}</p></details></div> : <div className="lock-banner"><EyeOff size={16} /><div><strong>面试锁定中</strong><span>提示隐藏 · 禁止复制 · 自动补全关闭 · 隐藏测试不可见</span></div></div>}

              <div className="challenge-editor-grid">
                <div className="editor-pane">
                  <div className="ide-toolbar"><div><span className="dot" /><strong>solution.py</strong></div><div className="button-row"><button className="secondary" onClick={() => setCode(activeSeedCode)} disabled={lockMode}><RotateCcw size={14} /> 重置</button><button className="secondary" onClick={runVisibleTests} disabled={running}><Play size={14} /> 运行公开测试</button><button className="primary" onClick={submitChallenge} disabled={running}><Send size={14} /> 提交全部测试</button></div></div>
                  <Editor height="500px" language="python" value={code} onChange={(v) => setCode(v ?? '')} theme="vs-dark" options={{ minimap: { enabled: false }, fontSize: 14, padding: { top: 16 }, wordWrap: 'on', automaticLayout: true, quickSuggestions: lockMode ? false : undefined, suggestOnTriggerCharacters: !lockMode, parameterHints: { enabled: !lockMode }, wordBasedSuggestions: lockMode ? 'off' : 'matchingDocuments', contextmenu: !lockMode }} />
                </div>
                <aside className="judge-pane">
                  <div className="complexity-box"><label>时间复杂度<input value={timeComplexity} onChange={(e) => setTimeComplexity(e.target.value)} placeholder="例如 O(n)" /></label><label>空间复杂度<input value={spaceComplexity} onChange={(e) => setSpaceComplexity(e.target.value)} placeholder="例如 O(1)" /></label></div>
                  <div className="console-title"><Terminal size={15} /> 评测结果</div>
                  {!judgeResult ? <div className="judge-empty">先运行公开测试，调试完成后再提交全部测试。</div> : judgeResult.error ? <div className="judge-error">{judgeResult.error}</div> : <>
                    <div className={judgeResult.all_passed ? 'judge-score success' : 'judge-score'}><strong>{judgeResult.score ?? `${judgeResult.public?.passed}/${judgeResult.public?.total}`}</strong><span>{judgeResult.kind === 'submit' ? (judgeResult.all_passed ? '通过' : '未通过') : '公开测试'}</span></div>
                    <div className="test-case-list">{visibleTests.map((test: any) => <div className={test.passed ? 'test-case pass' : 'test-case fail'} key={test.index}><b>测试 {test.index}</b><span>{test.passed ? '通过' : '失败'}</span>{!test.passed ? <small>{test.error || `实际 ${showValue(test.actual)} · 期望 ${showValue(test.expected)}`}</small> : null}</div>)}</div>
                    {judgeResult.kind === 'submit' ? <div className="hidden-result"><EyeOff size={14} /><span>隐藏测试</span><b>{judgeResult.hidden.passed}/{judgeResult.hidden.total}</b></div> : null}
                    {judgeResult.complexity ? <div className="complexity-result"><p>时间：<b className={judgeResult.complexity.time.match ? 'ok' : ''}>{timeComplexity || '未填写'}</b>{judgeResult.complexity.time.expected ? ` · 期望 ${judgeResult.complexity.time.expected}` : ''}</p><p>空间：<b className={judgeResult.complexity.space.match ? 'ok' : ''}>{spaceComplexity || '未填写'}</b>{judgeResult.complexity.space.expected ? ` · 期望 ${judgeResult.complexity.space.expected}` : ''}</p></div> : null}
                    {judgeResult.reference_solution ? <details className="solution-unlock"><summary>已通过全部测试 · 查看参考解</summary><pre>{judgeResult.reference_solution}</pre></details> : null}
                  </>}
                  {submissions.length ? <details className="submission-history"><summary>最近提交 ({submissions.length})</summary>{submissions.slice(0, 6).map((item) => <p key={item.id}><span>{item.passed ? '✓' : '×'} 公开 {item.public} + 隐藏 {item.hidden}</span><b>{item.score}</b></p>)}</details> : null}
                </aside>
              </div>
            </> : <div className="empty-state">请选择一道 Coding 挑战。</div>}
          </section>
        </div>
      ) : (
        <div className="ide-shell card">
          <div className="ide-toolbar">
            <div><span className="dot" /><strong>main.py</strong></div>
            <div className="button-row"><button className="secondary" onClick={() => setCode(activeSeedCode)}><RotateCcw size={15} /> 重置</button>{mode === 'run' ? <button className="primary" onClick={run} disabled={running || !canRun}><Play size={15} /> {canRun ? (running ? '运行中…' : '运行') : '仅 Python 可运行'}</button> : <button className="primary" onClick={evaluateExplanation} disabled={running || !explanation.trim()}><BrainCircuit size={15} /> {running ? '评价中…' : '评价我的解释'}</button>}</div>
          </div>
          <div className="ide-grid">
            <div className="editor-pane"><Editor height="560px" language={languageMap[initialSeed?.language || 'Python'] || 'plaintext'} value={code} onChange={(v) => setCode(v ?? '')} theme="vs-dark" options={{ minimap: { enabled: false }, fontSize: 14, padding: { top: 16 }, wordWrap: 'on', automaticLayout: true }} /></div>
            {mode === 'run' ? <div className="console-pane"><div className="console-title"><Terminal size={16} /> 控制台</div><pre>{output}</pre><div className="sandbox-note"><TriangleAlert size={15} /><span>Runner 与主 API 隔离，并限制 CPU/内存/进程/时间；公网生产仍建议升级到更强沙箱。</span></div></div> :
              <div className="explain-pane"><div className="console-title"><BrainCircuit size={16} /> 面试官：请解释这段代码</div><p className="explain-hint">建议按：<b>职责 → 输入输出 → 关键控制流 → 并发/异常边界 → 可优化点</b> 来讲。</p><textarea className="explain-textarea" value={explanation} onChange={(e) => setExplanation(e.target.value)} placeholder="像真实面试一样，用自己的话解释代码。" />{explainResult ? <div className="explain-result"><div className="result-score"><CheckCircle2 size={18} /><strong>{explainResult.score}</strong><span>/ 100 · {explainResult.mode === 'llm' ? 'LLM' : '离线'}</span></div><p>{explainResult.feedback}</p><div className="tag-row">{explainResult.knowledge?.map((x: string) => <span className="tag selected" key={x}>{x}</span>)}</div><div className="followup-box"><span className="eyebrow">下一追问</span><p>{explainResult.followup}</p></div></div> : null}</div>}
          </div>
        </div>
      )}
    </div>
  )
}
