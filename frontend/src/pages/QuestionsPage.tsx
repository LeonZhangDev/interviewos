import { useEffect, useMemo, useState } from 'react'
import { Archive, ArchiveRestore, ChevronRight, GitCompareArrows, Pencil, Plus, Search, Sparkles } from 'lucide-react'
import { api } from '../api'
import type { Question, QuestionDraft, QuestionDuplicate } from '../types'

const EMPTY_DRAFT: QuestionDraft = {
  category: '',
  title: '',
  answer: '',
  code: '',
  followups: '',
  difficulty: 2,
  project_link: '',
  tags: '',
}

/** Parse a thrown 409 from create/update into its duplicate payload. */
function parseDuplicateError(error: unknown): { duplicates: QuestionDuplicate[] } | null {
  try {
    const detail = JSON.parse(String(error).replace(/^Error:\s*/, '')).detail
    if (detail?.duplicates) return { duplicates: detail.duplicates }
  } catch { /* not a duplicate conflict */ }
  return null
}

function QuestionForm({
  initial, busy, duplicates, onCancel, onSubmit, onForce,
}: {
  initial: QuestionDraft
  busy: boolean
  duplicates: QuestionDuplicate[] | null
  onCancel: () => void
  onSubmit: (draft: QuestionDraft) => void
  onForce: (draft: QuestionDraft) => void
}) {
  const [draft, setDraft] = useState<QuestionDraft>(initial)
  const set = (patch: Partial<QuestionDraft>) => setDraft((current) => ({ ...current, ...patch }))
  const valid = draft.category.trim() && draft.title.trim() && draft.answer.trim()

  return (
    <div className="question-form">
      <div className="form-grid">
        <label>分类<input value={draft.category} onChange={(e) => set({ category: e.target.value })} placeholder="Python / Agent / FastAPI…" /></label>
        <label>难度<select value={draft.difficulty} onChange={(e) => set({ difficulty: Number(e.target.value) })}>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{'★'.repeat(n)}</option>)}</select></label>
        <label className="span-2">标题<input value={draft.title} onChange={(e) => set({ title: e.target.value })} placeholder="面试题标题" /></label>
        <label className="span-2">参考答案<textarea rows={5} value={draft.answer} onChange={(e) => set({ answer: e.target.value })} placeholder="标准答案要点" /></label>
        <label className="span-2">示例代码<textarea rows={4} value={draft.code} onChange={(e) => set({ code: e.target.value })} spellCheck={false} placeholder="可选：示例 / 反例代码" /></label>
        <label className="span-2">深挖追问（用 | 分隔）<input value={draft.followups} onChange={(e) => set({ followups: e.target.value })} placeholder="追问1|追问2" /></label>
        <label>项目关联<input value={draft.project_link} onChange={(e) => set({ project_link: e.target.value })} placeholder="可选" /></label>
        <label>标签（用 | 分隔）<input value={draft.tags} onChange={(e) => set({ tags: e.target.value })} placeholder="backend|security" /></label>
      </div>
      {duplicates?.length ? (
        <div className="duplicate-warning">
          <strong>发现疑似重复题目：</strong>
          {duplicates.map((d) => <span key={d.id}>#{d.id} {d.title}（相似度 {(d.similarity * 100).toFixed(0)}%）</span>)}
          <button className="secondary" onClick={() => onForce(draft)} disabled={busy}>仍然保存</button>
        </div>
      ) : null}
      <div className="button-row">
        <button className="primary" onClick={() => onSubmit(draft)} disabled={busy || !valid}>{busy ? '保存中…' : '保存'}</button>
        <button className="secondary" onClick={onCancel} disabled={busy}>取消</button>
      </div>
    </div>
  )
}

export function QuestionsPage({ onOpenCode, focusQuestionId }: { onOpenCode: (q: Question) => void; focusQuestionId?: number }) {
  const [questions, setQuestions] = useState<Question[]>([])
  const [selected, setSelected] = useState<Question | null>(null)
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('All')
  const [answer, setAnswer] = useState('')
  const [result, setResult] = useState<any>(null)
  const [versions, setVersions] = useState<any[]>([])
  const [compareIds, setCompareIds] = useState<number[]>([])

  const [manage, setManage] = useState(false)
  const [archivedView, setArchivedView] = useState(false)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [bulkTagInput, setBulkTagInput] = useState('')
  const [bulkMode, setBulkMode] = useState<'append' | 'set' | 'remove'>('append')
  const [formMode, setFormMode] = useState<'closed' | 'create' | 'edit'>('closed')
  const [formInitial, setFormInitial] = useState<QuestionDraft>(EMPTY_DRAFT)
  const [formBusy, setFormBusy] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [dupConflict, setDupConflict] = useState<QuestionDuplicate[] | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const load = (archived = archivedView) => api.questions(archived).then((items) => { setQuestions(items); setSelected((current) => items.find((x) => x.id === current?.id) ?? items[0] ?? null) })

  useEffect(() => { load() }, [archivedView])
  useEffect(() => {
    if (!focusQuestionId || selected?.id === focusQuestionId) return
    const target = questions.find((q) => q.id === focusQuestionId)
    if (target) choose(target)
  }, [focusQuestionId, questions])

  const categories = useMemo(() => ['All', ...Array.from(new Set(questions.map((x) => x.category)))], [questions])
  const filtered = useMemo(() => questions.filter((x) => (category === 'All' || x.category === category) && `${x.category} ${x.title}`.toLowerCase().includes(query.toLowerCase())), [questions, query, category])
  const compared = compareIds.map((id) => versions.find((x) => x.id === id)).filter(Boolean)

  async function submit() {
    if (!selected || !answer.trim()) return
    const saved = await api.saveAnswer(selected.id, answer.trim())
    setResult(saved)
    setVersions(await api.answerVersions(selected.id))
  }

  async function choose(q: Question) {
    setSelected(q); setAnswer(''); setResult(null); setCompareIds([])
    setVersions(await api.answerVersions(q.id))
  }

  function toggleCompare(id: number) {
    setCompareIds((current) => current.includes(id) ? current.filter((x) => x !== id) : current.length >= 2 ? [current[1], id] : [...current, id])
  }

  function toggleSelected(id: number) {
    setSelectedIds((current) => current.includes(id) ? current.filter((x) => x !== id) : [...current, id])
  }

  function openCreate() {
    setFormMode('create'); setFormInitial(EMPTY_DRAFT); setDupConflict(null); setFormError(null)
  }

  function openEdit(q: Question) {
    setFormMode('edit')
    setFormInitial({
      category: q.category, title: q.title, answer: q.answer, code: q.code,
      followups: q.followups, difficulty: q.difficulty, project_link: q.project_link, tags: q.tags,
    })
    setDupConflict(null); setFormError(null)
  }

  async function saveForm(draft: QuestionDraft, force = false) {
    setFormBusy(true); setFormError(null); setDupConflict(null)
    try {
      if (formMode === 'create') {
        await api.createQuestion(draft, force)
        setNotice('题目已创建。')
      } else if (selected) {
        await api.updateQuestion(selected.id, draft, force)
        setNotice('题目已更新。')
      }
      setFormMode('closed')
      await load()
    } catch (error) {
      const conflict = parseDuplicateError(error)
      if (conflict) setDupConflict(conflict.duplicates)
      else setFormError(String(error))
    } finally { setFormBusy(false) }
  }

  async function toggleArchive(q: Question) {
    if (q.archived) await api.restoreQuestion(q.id)
    else await api.archiveQuestion(q.id)
    setNotice(q.archived ? '题目已恢复到题库。' : '题目已归档，不再出现在练习、搜索与面试中。')
    await load()
  }

  async function applyBulkTags() {
    const tags = bulkTagInput.split(/[|,，]/).map((t) => t.trim()).filter(Boolean)
    if (!tags.length || !selectedIds.length) return
    const { updated } = await api.bulkTagQuestions(selectedIds, tags, bulkMode)
    setNotice(`已更新 ${updated} 道题的标签。`)
    setBulkTagInput('')
    await load()
  }

  return (
    <div className="page-stack">
      <div className="cms-toolbar card">
        <div className="cms-toolbar-main">
          <button className={manage ? 'secondary' : 'primary'} onClick={() => { setManage(!manage); setFormMode('closed'); setSelectedIds([]) }}>
            {manage ? '退出管理' : '管理题库'}
          </button>
          {manage ? <>
            <button className="secondary" onClick={openCreate}><Plus size={14} /> 新建题目</button>
            <label className="inline-toggle">
              <input type="checkbox" checked={archivedView} onChange={(e) => { setArchivedView(e.target.checked); setSelectedIds([]) }} />
              查看已归档
            </label>
            <div className="bulk-tag-row">
              <select value={bulkMode} onChange={(e) => setBulkMode(e.target.value as 'append' | 'set' | 'remove')}>
                <option value="append">添加标签</option>
                <option value="set">设为标签</option>
                <option value="remove">移除标签</option>
              </select>
              <input value={bulkTagInput} onChange={(e) => setBulkTagInput(e.target.value)} placeholder="标签（| 分隔）" />
              <button className="secondary" onClick={applyBulkTags} disabled={!selectedIds.length || !bulkTagInput.trim()}>应用到 {selectedIds.length} 题</button>
            </div>
          </> : null}
        </div>
        {notice ? <p className="cms-notice">{notice}</p> : null}
      </div>

      <div className="question-layout">
        <aside className="question-list card">
          <div className="search-box"><Search size={16} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索 Python / Agent / FastAPI..." /></div>
          <div className="category-strip">{categories.map((x) => <button className={category === x ? 'active' : ''} key={x} onClick={() => setCategory(x)}>{x === 'All' ? '全部' : x}</button>)}</div>
          <div className="question-scroll">
            {filtered.map((q) => (
              <button key={q.id} className={selected?.id === q.id ? 'question-item active' : 'question-item'} onClick={() => choose(q)}>
                <span className="question-meta">
                  {manage ? <span className="select-box" onClick={(event) => { event.stopPropagation(); toggleSelected(q.id) }} role="checkbox" aria-checked={selectedIds.includes(q.id)}>{selectedIds.includes(q.id) ? '☑' : '☐'}</span> : null}
                  <b>{q.category}</b><i>{'★'.repeat(q.difficulty)}</i>
                </span>
                <strong>{q.title}</strong>
                <span className="question-foot">
                  {q.tags ? <em className="q-tags">{q.tags.split('|').map((t) => `#${t}`).join(' ')}</em> : <em>{q.project_link || '通用'}</em>}
                  <ChevronRight size={14} />
                </span>
              </button>
            ))}
          </div>
        </aside>

        <section className="card question-detail">
          {selected ? <>
            <div className="section-title">
              <div><span className="eyebrow">{selected.category} · Q{selected.id}{selected.archived ? ' · 已归档' : ''}</span><h1>{selected.title}</h1></div>
              <span className="pill">{'★'.repeat(selected.difficulty)}</span>
            </div>

            {manage ? (
              <div className="detail-actions">
                <button className="secondary" onClick={() => openEdit(selected)}><Pencil size={14} /> 编辑</button>
                <button className="secondary" onClick={() => toggleArchive(selected)}>
                  {selected.archived ? <><ArchiveRestore size={14} /> 恢复</> : <><Archive size={14} /> 归档</>}
                </button>
              </div>
            ) : null}

            {formMode !== 'closed' ? (
              <div className="card nested-card">
                <span className="eyebrow">{formMode === 'create' ? '新建题目' : `编辑题目 Q${selected.id}`}</span>
                <QuestionForm
                  initial={formInitial}
                  busy={formBusy}
                  duplicates={dupConflict}
                  onCancel={() => setFormMode('closed')}
                  onSubmit={(draft) => saveForm(draft)}
                  onForce={(draft) => saveForm(draft, true)}
                />
                {formError ? <p className="form-error">{formError}</p> : null}
              </div>
            ) : (
              <>
                <div className="answer-editor-block">
                  <label>先用自己的话回答</label><textarea value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="像真实面试一样回答，不要先看标准答案..." />
                  <div className="button-row"><button className="primary" onClick={submit}>提交并保存版本</button><button className="secondary" onClick={() => onOpenCode(selected)}>打开 Code Lab</button></div>
                  {result ? <div className="answer-result"><div className="score-banner"><Sparkles size={16} /> 本次答案评分：<strong>{result.score}</strong> / 100 · 下一次复习 {new Date(result.mastery.next_review).toLocaleDateString()}</div><div className="dimension-grid">{Object.entries(result.dimensions || {}).map(([key, value]) => <div key={key}><span>{key}</span><strong>{String(value)}</strong></div>)}</div>{result.missing_terms?.length ? <p className="missing-line">可以继续补：{result.missing_terms.join(' · ')}</p> : null}</div> : null}
                </div>
                <details className="detail-box"><summary>参考回答</summary><p>{selected.answer}</p></details>
                <details className="detail-box"><summary>深挖追问题链</summary>{selected.followups.split('|').filter(Boolean).map((x) => <p key={x}>→ {x}</p>)}</details>
                <details className="detail-box" open={versions.length > 0}><summary>答案版本记录 ({versions.length})</summary>
                  {versions.length ? <>
                    <div className="version-list">{versions.map((x) => <div className="version-row" key={x.id}><label><input type="checkbox" checked={compareIds.includes(x.id)} onChange={() => toggleCompare(x.id)} /> V{x.id} · {new Date(x.created_at).toLocaleString()}</label><b>{x.score}</b><p>{x.content}</p></div>)}</div>
                    {compared.length === 2 ? <div className="version-compare"><div className="compare-head"><GitCompareArrows size={16} /> 两个答案版本对照</div><div><article><b>V{compared[0].id} · {compared[0].score}</b><p>{compared[0].content}</p></article><article><b>V{compared[1].id} · {compared[1].score}</b><p>{compared[1].content}</p></article></div></div> : <p className="compare-hint">勾选两个版本，可以并排查看回答变化。</p>}
                  </> : <p>还没有历史版本。</p>}
                </details>
              </>
            )}
          </> : <p>请选择一道题。</p>}
        </section>
      </div>
    </div>
  )
}
