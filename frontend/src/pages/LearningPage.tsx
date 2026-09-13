import { useEffect, useState } from 'react'
import { Brain, CalendarClock, History, RotateCcw } from 'lucide-react'
import { api } from '../api'
import { ProgressBar } from '../components/ProgressBar'
import type { ReviewLogEntry, Weakness } from '../types'

const grades = [{ n: 1, label: '不会' }, { n: 2, label: '模糊' }, { n: 3, label: '会' }, { n: 4, label: '熟练' }, { n: 5, label: '很熟' }]
const gradeLabels = ['', '不会', '模糊', '会', '熟练', '很熟']
const sourceLabels: Record<string, string> = { manual: '手动复习', answer: '答题', coding: '刷题', explain: '代码讲解', interview: 'AI 面试' }

function fmtDate(value: string | null) {
  return value ? new Date(value).toLocaleDateString() : '—'
}

function MasteryCard({ item, busy, onReview }: { item: Weakness; busy: boolean; onReview: (topic: string, grade: number) => void }) {
  const [history, setHistory] = useState<ReviewLogEntry[] | null>(null)
  const [openHistory, setOpenHistory] = useState(false)

  async function toggleHistory() {
    if (openHistory) { setOpenHistory(false); return }
    if (!history) setHistory(await api.reviewHistory(item.topic))
    setOpenHistory(true)
  }

  return (
    <div className={item.due ? 'card mastery-card due-card' : 'card mastery-card'}>
      <div className="mastery-head">
        <div><span className="eyebrow">{item.due ? '待复习' : '掌握度'}</span><h3>{item.topic}</h3></div>
        <strong>{Math.round(item.score)}%</strong>
      </div>
      <ProgressBar value={item.score} />
      <div className="fsrs-stats">
        <div><b>{Math.round(item.retrievability * 100)}%</b><span>保持率</span></div>
        <div><b>{item.stability}d</b><span>稳定性</span></div>
        <div><b>{item.difficulty}</b><span>难度</span></div>
        <div><b>{item.reps}次</b><span>复习{item.lapses > 0 ? `·遗忘${item.lapses}` : ''}</span></div>
      </div>
      <div className="mastery-foot">
        <span><CalendarClock size={14} /> 下次 {fmtDate(item.due_at)}</span>
        <span>间隔 {item.interval_days} 天</span>
      </div>
      <div className="review-grades">{grades.map((grade) => <button disabled={busy} key={grade.n} onClick={() => onReview(item.topic, grade.n)}><b>{grade.n}</b><span>{grade.label}</span></button>)}</div>
      <button className="history-toggle" onClick={toggleHistory}><History size={12} /> 复习历史</button>
      {openHistory && (
        <div className="history-list">
          {(history ?? []).length === 0 && <p className="history-empty">还没有复习记录</p>}
          {(history ?? []).map((log) => (
            <div className="history-row" key={log.id}>
              <b className={`grade-chip grade-${log.grade}`}>{log.grade} {gradeLabels[log.grade]}</b>
              <span>{sourceLabels[log.source] ?? log.source}</span>
              <span>稳定 {log.stability}d</span>
              <span>难度 {log.difficulty}</span>
              <span>保持 {Math.round(log.retrievability * 100)}%</span>
              <span>{new Date(log.reviewed_at).toLocaleString()}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function LearningPage() {
  const [items, setItems] = useState<Weakness[]>([])
  const [busy, setBusy] = useState('')
  const load = () => api.weakness().then(setItems)
  useEffect(() => { load() }, [])

  async function review(topic: string, grade: number) {
    setBusy(topic)
    try { await api.reviewTopic(topic, grade); await load() } finally { setBusy('') }
  }

  const dueCount = items.filter((x) => x.due).length
  const avgRetention = items.length ? Math.round(items.reduce((sum, x) => sum + x.retrievability, 0) / items.length * 100) : 0

  return (
    <div className="page-stack">
      <div className="page-header">
        <div>
          <span className="eyebrow">学习引擎</span>
          <h1>薄弱点地图 + FSRS 间隔复习</h1>
          <p>答题和 AI 面试会更新掌握度；FSRS-4.5 根据每次评分动态计算保持率与下次复习时间。</p>
        </div>
        <div className="fsrs-summary">
          <div><b>{dueCount}</b><span>待复习</span></div>
          <div><b>{avgRetention}%</b><span>平均保持率</span></div>
        </div>
      </div>
      <div className="learning-grid">
        {items.map((item) => <MasteryCard busy={busy === item.topic} item={item} key={item.topic} onReview={review} />)}
      </div>
      <div className="card panel learning-note">
        <RotateCcw size={18} />
        <div>
          <strong><Brain size={13} style={{ display: 'inline', marginRight: 4, verticalAlign: -2 }} />FSRS 记忆模型已接通</strong>
          <p>保持率（当前还记得多少）按遗忘曲线随时间衰减；稳定性（间隔还能撑多久）随复习增长，遗忘会回落。用“不会 → 很熟”评分后，下次出现时间由 FSRS 重新计算。</p>
        </div>
      </div>
    </div>
  )
}
