import { useEffect, useState } from 'react'
import { FileJson2, FileSpreadsheet, SearchCheck, UploadCloud } from 'lucide-react'
import { api } from '../api'
import type { ImportPreview } from '../types'

const jsonExample = `[
  {
    "category": "Agent",
    "title": "Agent 为什么需要状态管理？",
    "difficulty": 2,
    "answer": "状态管理用于保存多步骤执行中的上下文、工具结果和控制信息。",
    "followups": "State 冲突怎么处理？|什么时候需要持久化？",
    "project_link": "MindTrip"
  }
]`

export function QuestionImportPage() {
  const [format, setFormat] = useState<'json' | 'csv'>('json')
  const [content, setContent] = useState(jsonExample)
  const [history, setHistory] = useState<any[]>([])
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [result, setResult] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const load = () => api.importHistory().then(setHistory)
  useEffect(() => { load() }, [])

  async function chooseFile(file?: File) {
    if (!file) return
    const nextFormat = file.name.toLowerCase().endsWith('.csv') ? 'csv' : 'json'
    setFormat(nextFormat)
    setContent(await file.text())
    setPreview(null)
    setResult(null)
  }

  async function runPreview() {
    setBusy(true); setError(null); setResult(null)
    try { setPreview(await api.importPreview(format, content)) } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }

  async function confirmImport() {
    setBusy(true); setError(null)
    try {
      setResult(await api.importQuestions(format, content))
      setPreview(null)
      await load()
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }

  const hasErrors = preview ? preview.to_skip > 0 : false

  return (
    <div className="page-stack">
      <div className="page-header"><div><span className="eyebrow">题目导入</span><h1>把外部面试题真正导入你的题库。</h1><p>支持 JSON / CSV；先预览确认再落库 —— 重复 slug、缺 title/answer 的行和相似标题都会在预览中标出。</p></div></div>
      <section className="two-col import-layout">
        <div className="card panel"><div className="format-tabs"><button className={format === 'json' ? 'active' : ''} onClick={() => setFormat('json')}><FileJson2 size={15} /> JSON</button><button className={format === 'csv' ? 'active' : ''} onClick={() => setFormat('csv')}><FileSpreadsheet size={15} /> CSV</button></div><label className="file-drop"><UploadCloud /><strong>选择 .json / .csv 文件</strong><span>或直接在下面粘贴内容</span><input type="file" accept=".json,.csv,application/json,text/csv" onChange={(e) => chooseFile(e.target.files?.[0])} /></label><textarea className="import-editor" value={content} onChange={(e) => { setContent(e.target.value); setPreview(null) }} spellCheck={false} />
          <div className="button-row">
            <button className="secondary" onClick={runPreview} disabled={busy || content.trim().length < 2}><SearchCheck size={14} /> {busy ? '处理中…' : '预览'}</button>
            <button className="primary" onClick={confirmImport} disabled={busy || content.trim().length < 2 || !preview}>确认导入</button>
          </div>
          {error ? <div className="import-result error">{error}</div> : null}
          {result ? <div className="import-result">{`共 ${result.total} 条 · 新增 ${result.created} · 跳过 ${result.skipped}`}{result.errors?.slice(0, 5).map((x: string) => <small key={x}>{x}</small>)}</div> : null}
        </div>
        <div className="card panel">
          {preview ? (
            <>
              <span className="eyebrow">导入预览</span>
              <h2>预览结果：新增 {preview.to_create} · 跳过 {preview.to_skip}{preview.truncated ? '（仅显示前 100 行）' : ''}</h2>
              <div className="preview-list">
                {preview.rows.map((row) => (
                  <div key={row.row} className={row.status === 'create' ? 'preview-row ok' : 'preview-row bad'}>
                    <b>#{row.row} {row.title || '(无标题)'}</b>
                    <small>{row.category} · {row.status === 'create' ? '将导入' : '跳过'}</small>
                    {row.problems.map((p) => <em key={p} className="problem">{p}</em>)}
                    {row.duplicates.length ? <em className="problem warn">疑似重复：{row.duplicates.map((d) => `#${d.id} ${d.title}（${(d.similarity * 100).toFixed(0)}%）`).join('；')}</em> : null}
                  </div>
                ))}
              </div>
              <p className="preview-hint">
                {preview.to_create === 0
                  ? '没有可导入的行，请修正后再试。'
                  : hasErrors
                    ? `有 ${preview.to_skip} 行将被跳过（错误行不落库）；点击左侧“确认导入”将只导入 ${preview.to_create} 条有效行。`
                    : '全部行有效，点击左侧“确认导入”落库。'}
              </p>
            </>
          ) : (
            <>
              <span className="eyebrow">导入历史</span>
              <h2>最近批次</h2>
              <div className="import-history">{history.length ? history.map((item) => <div className="history-row" key={item.id}><div><strong>批次 #{item.id}</strong><small>{item.format.toUpperCase()} · {new Date(item.created_at).toLocaleString()}</small></div><span>{item.created}/{item.total}</span><b>跳过 {item.skipped} 条</b></div>) : <p>还没有导入记录。</p>}</div>
              <details className="detail-box"><summary>字段格式</summary><p>JSON/CSV 支持：category、title、difficulty、answer、code、followups、project_link、tags、slug。</p><p>slug 可以省略，InterviewOS 会根据 category + title 自动生成。</p></details>
            </>
          )}
        </div>
      </section>
    </div>
  )
}
