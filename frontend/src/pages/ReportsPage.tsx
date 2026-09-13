import { useEffect, useMemo, useState } from 'react'
import { BarChart3, BrainCircuit, CalendarClock, History, Mic2, ShieldAlert, Timer } from 'lucide-react'
import { api } from '../api'
import type { InterviewReport, InterviewerPersona, MemoryFinding } from '../types'

const findingKindLabels: Record<MemoryFinding['kind'], string> = {
  contradiction: '前后矛盾',
  evasion: '回避问题',
  unanswered: '未正面回答',
  avoided_concept: '反复回避',
  reused_gap: '重复薄弱点',
}

export function ReportsPage({ focusSessionId }: { focusSessionId?: number }) {
  const [report, setReport] = useState<InterviewReport | null>(null)
  const [history, setHistory] = useState<any[]>([])
  const [recordings, setRecordings] = useState<any[]>([])
  const [personas, setPersonas] = useState<InterviewerPersona[]>([])

  useEffect(() => {
    let stale = false
    api.interviewPersonas().then((items) => { if (!stale) setPersonas(items) }).catch(() => undefined)
    Promise.all([focusSessionId ? api.interviewReport(focusSessionId) : api.latestReport(), api.reportHistory()])
      .then(async ([latest, items]) => {
        if (stale) return
        setReport(latest)
        setHistory(items)
        if (latest.session_id) setRecordings(await api.interviewRecordings(latest.session_id))
      })
      .catch(() => undefined)
    return () => { stale = true }
  }, [focusSessionId])

  const maxSkill = useMemo(() => Math.max(100, ...Object.values(report?.skill_scores || {})), [report])
  const personaLabel = useMemo(() => personas.find((p) => p.id === report?.persona)?.label, [personas, report])

  if (!report) return <div className="empty-state">正在读取面试报告…</div>

  return (
    <div className="page-stack">
      <div className="page-header"><div><span className="eyebrow">面试分析</span><h1>从一次面试，回到下一轮学习动作。</h1><p>报告把回答得分按技能聚合，并把薄弱方向直接转换成复习计划；v0.9 起附带面试官记忆发现与时间执行复盘。</p></div></div>

      <section className="report-hero card">
        <div className="report-score"><span>总分</span><strong>{report.overall_score}</strong><small>/ 100</small></div>
        <div className="report-summary"><BrainCircuit size={22} /><h2>{report.role || 'AI 工程师模拟面试'}{personaLabel ? <span className="persona-badge">{personaLabel}</span> : null}</h2><p>{report.summary}</p><div className="tag-row">{report.strengths.map((x) => <span key={x} className="tag selected">优势 · {x}</span>)}{report.weaknesses.map((x) => <span key={x} className="tag">待复习 · {x}</span>)}</div></div>
      </section>

      <section className="two-col">
        <div className="card panel"><div className="section-title"><div><span className="eyebrow">能力得分</span><h2>能力分布</h2></div><BarChart3 /></div>
          <div className="skill-bars">{Object.entries(report.skill_scores).map(([name, score]) => <div className="skill-row" key={name}><div><strong>{name}</strong><span>{score}</span></div><div className="skill-track"><i style={{ width: `${Math.min(100, score / maxSkill * 100)}%` }} /></div></div>)}</div>
        </div>
        <div className="card panel"><div className="section-title"><div><span className="eyebrow">后续复习</span><h2>自动复习计划</h2></div><CalendarClock /></div>
          <div className="review-plan">{report.review_plan.length ? report.review_plan.map((item) => <div className="review-plan-row" key={`${item.day}-${item.topic}`}><b>D{item.day}</b><div><strong>{item.topic}</strong><p>{item.task}</p></div></div>) : <p>完成一轮面试后自动生成。</p>}</div>
        </div>
      </section>

      <section className="two-col">
        <div className="card panel"><div className="section-title"><div><span className="eyebrow">面试官记忆</span><h2>面试官记忆发现</h2></div><ShieldAlert /></div>
          <div className="memory-findings">
            {report.memory?.summary ? <p className="memory-summary">{report.memory.summary}</p> : null}
            {report.memory?.findings?.length ? report.memory.findings.map((finding, i) => (
              <div className="memory-finding" key={i}>
                <span className="finding-kind">{findingKindLabels[finding.kind] || finding.kind}</span>
                <p>{finding.detail}</p>
              </div>
            )) : <p>没有发现矛盾、回避或重复薄弱点——跨轮次一致性良好。</p>}
          </div>
        </div>
        <div className="card panel"><div className="section-title"><div><span className="eyebrow">时间执行</span><h2>时间执行复盘</h2></div><Timer /></div>
          <div className="time-execution">
            <div className="time-execution-overview">计划 <b>{report.time?.plan_minutes ?? 0}</b> min · 实际 <b>{report.time?.elapsed_minutes?.toFixed(1) ?? '0.0'}</b> min</div>
            {report.time?.modules?.length ? report.time.modules.map((module) => (
              <div className={`time-execution-row ${module.status}${module.over_budget ? ' over' : ''}`} key={module.index}>
                <strong>{module.type}</strong>
                <div className="time-execution-track"><i style={{ width: `${Math.min(100, module.planned_minutes ? module.elapsed_minutes / module.planned_minutes * 100 : 0)}%` }} /></div>
                <span>{module.elapsed_minutes.toFixed(1)}m / {module.planned_minutes}m</span>
              </div>
            )) : <p>进入模块后自动记录耗时。</p>}
            {report.time?.advisory ? <p className="time-advisory">{report.time.advisory}</p> : null}
          </div>
        </div>
      </section>

      <section className="card panel"><div className="section-title"><div><span className="eyebrow">历史</span><h2>最近面试</h2></div><History /></div>
        <div className="report-history">{history.length ? history.map((item) => <div className="history-row" key={item.session_id}><div><strong>面试 #{item.session_id}</strong><small>{item.role} · {new Date(item.created_at).toLocaleString()}</small></div><span>{item.turns} 轮</span><b>{item.overall_score}</b></div>) : <p>还没有历史记录。</p>}</div>
      </section>

      <section className="card panel"><div className="section-title"><div><span className="eyebrow">语音记录</span><h2>本轮录音与转写</h2></div><Mic2 /></div>
        <div className="recording-history">{recordings.length ? recordings.map((item) => <div className="recording-row" key={item.id}><div><strong>录音 #{item.id}</strong><small>{item.mime_type} · {Math.round((item.duration_ms || 0)/1000)}s · {new Date(item.created_at).toLocaleString()}</small></div><p>{item.transcript || '当前录音没有自动转写文本。'}</p></div>) : <p>最近一轮面试还没有录音。</p>}</div>
      </section>
    </div>
  )
}
