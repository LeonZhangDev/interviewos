import { useEffect, useState } from 'react'
import { Flame, FolderGit2, RotateCcw, TerminalSquare } from 'lucide-react'
import { api } from '../api'
import { ProgressBar } from '../components/ProgressBar'
import { StatCard } from '../components/StatCard'
import type { Dashboard, Weakness } from '../types'

export function DashboardPage() {
  const [stats, setStats] = useState<Dashboard | null>(null)
  const [weakness, setWeakness] = useState<Weakness[]>([])

  useEffect(() => {
    Promise.all([api.dashboard(), api.weakness()]).then(([a, b]) => {
      setStats(a)
      setWeakness(b)
    })
  }, [])

  return (
    <div className="page-stack">
      <section className="hero card">
        <div>
          <div className="hero-head">
            <span className="eyebrow">面试准备工作台</span>
            <span className="pill">v{__APP_VERSION__}</span>
          </div>
          <h1>把学习、代码、项目和面试连成一条线。</h1>
          <p>InterviewOS 会把题库、Code Lab、项目深挖、模拟面试和复习记录放到同一个工作台里。</p>
        </div>
        <div className="readiness-ring">
          <span>准备度</span>
          <strong>{stats?.readiness ?? '--'}%</strong>
          <small>综合准备度</small>
        </div>
      </section>

      <section className="stats-grid">
        <StatCard label="题库" value={`${stats?.question_answered ?? 0}/${stats?.question_total ?? 0}`} hint="已留下答案版本" icon={<RotateCcw size={18} />} />
        <StatCard label="Coding 实验" value={stats?.code_labs ?? '--'} hint={`已解 ${stats?.coding_solved ?? 0} 题 · ${stats?.coding_wrong ?? 0} 道错题待复盘`} icon={<TerminalSquare size={18} />} />
        <StatCard label="项目" value={stats?.projects ?? '--'} hint="MindTrip · AtlasSplit · InterviewOS" icon={<FolderGit2 size={18} />} />
        <StatCard label="连续打卡" value={`${stats?.streak ?? 0} 天`} hint={`${stats?.review_due ?? 0} 个主题待复习`} icon={<Flame size={18} />} />
      </section>

      <section className="two-col">
        <div className="card panel">
          <div className="section-title">
            <div>
              <span className="eyebrow">薄弱点地图</span>
              <h2>当前薄弱点</h2>
            </div>
            <span className="pill">动态</span>
          </div>
          <div className="topic-list">
            {weakness.slice(0, 5).map((item) => (
              <div className="topic-row" key={item.topic}>
                <div className="topic-row-head"><span>{item.topic}</span><strong>{item.score}%</strong></div>
                <ProgressBar value={item.score} />
              </div>
            ))}
          </div>
        </div>

        <div className="card panel">
          <div className="section-title">
            <div>
              <span className="eyebrow">今日</span>
              <h2>建议练习链</h2>
            </div>
          </div>
          <ol className="practice-list">
            <li><span>01</span><div><strong>Python · asyncio</strong><small>先回答，再跑 Lock 示例</small></div></li>
            <li><span>02</span><div><strong>FastAPI · Depends</strong><small>回答后进入项目代码模式</small></div></li>
            <li><span>03</span><div><strong>Agent · Tool Calling</strong><small>完成 3 层 AI 深挖追问</small></div></li>
            <li><span>04</span><div><strong>系统设计</strong><small>设计在线 Python Runner</small></div></li>
          </ol>
        </div>
      </section>
    </div>
  )
}
