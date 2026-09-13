import { useEffect, useState } from 'react'
import { ArrowRight, ExternalLink, FileText, GitBranch, Globe, ShieldCheck } from 'lucide-react'
import { api } from '../api'
import type { PortfolioData, PortfolioProjectView } from '../types'

function portfolioUsername(): string {
  const segment = window.location.pathname.split('/').filter(Boolean)[1] || ''
  return decodeURIComponent(segment)
}

function CmsProject({ project }: { project: PortfolioProjectView }) {
  return (
    <article>
      <div className="project-icon"><ShieldCheck size={20} /></div>
      <h3>{project.name}</h3>
      <p>{project.subtitle}</p>
      {project.tech_tags?.length ? (
        <div className="public-tags">{project.tech_tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
      ) : null}
      {project.description ? <p className="public-project-desc">{project.description}</p> : null}
      {project.architecture ? (
        <details className="public-detail">
          <summary>架构</summary>
          <pre>{project.architecture}</pre>
        </details>
      ) : null}
      {project.decisions ? <blockquote>{project.decisions}</blockquote> : null}
      {project.repository || project.link ? (
        <div className="public-project-foot">
          {project.repository ? (
            <a href={project.repository.url} target="_blank" rel="noreferrer">
              <GitBranch size={14} /> {project.repository.name} · {project.repository.commit}
            </a>
          ) : null}
          {project.link ? (
            <a href={project.link} target="_blank" rel="noreferrer">
              项目链接 <ExternalLink size={14} />
            </a>
          ) : null}
        </div>
      ) : null}
    </article>
  )
}

function LegacyProject({ project }: { project: PortfolioProjectView }) {
  return (
    <article>
      <div className="project-icon"><ShieldCheck size={20} /></div>
      <h3>{project.name}</h3>
      <p>{project.subtitle}</p>
      <div className="public-pipeline">{(project.pipeline || []).map((x, i) => <span key={x}>{x}{i < (project.pipeline || []).length - 1 ? <ArrowRight size={13} /> : null}</span>)}</div>
      <blockquote>{project.decision}</blockquote>
    </article>
  )
}

export function PublicPortfolioPage() {
  const [data, setData] = useState<PortfolioData | null>(null)
  const [missing, setMissing] = useState('')
  useEffect(() => {
    const username = portfolioUsername()
    api.portfolio(username).then(setData).catch(() => setMissing(username))
  }, [])
  if (missing) return (
    <main className="public-portfolio loading">
      <h1>未找到作品集</h1>
      <p>用户 {missing} 不存在，或尚未公开任何内容。</p>
    </main>
  )
  if (!data) return <div className="public-portfolio loading">正在加载作品集…</div>
  const socialEntries = Object.entries(data.social || {})
  return (
    <main className="public-portfolio">
      <header className="public-nav"><strong>{data.name}</strong><span>{data.cms ? '作品集' : 'AI 工程师作品集'}</span></header>
      <section className="public-hero"><div><h1>{data.name}</h1><h2>{data.title}</h2><p>{data.summary}</p><div className="tag-row">{data.skills.map((x) => <span className="tag" key={x}>{x}</span>)}</div>{data.cms && (socialEntries.length > 0 || data.resume_url) ? <div className="public-links">{data.resume_url ? <a href={data.resume_url} target="_blank" rel="noreferrer"><FileText size={14} />简历</a> : null}{socialEntries.map(([key, value]) => <a key={key} href={value} target="_blank" rel="noreferrer"><Globe size={14} />{key}</a>)}</div> : null}</div><div className="public-score"><span>最近一次模拟面试</span><strong>{data.latest_interview_score ?? '—'}</strong><small>InterviewOS 评分</small></div></section>
      <section className="public-projects">{data.cms ? data.projects.map((project) => <CmsProject key={project.name} project={project} />) : data.projects.map((project) => <LegacyProject key={project.name} project={project} />)}</section>
      <section className="public-repos"><div><span className="eyebrow">实时仓库快照</span><h2>同步的代码证据</h2></div>{data.repositories.length ? data.repositories.map((repo) => <a key={`${repo.provider}-${repo.name}`} href={repo.url} target="_blank" rel="noreferrer"><GitBranch size={16} /><span><strong>{repo.name}</strong><small>{repo.provider} · {repo.commit} · {repo.files} 个文件</small></span><ExternalLink size={14} /></a>) : <p>还没有同步任何仓库。</p>}</section>
    </main>
  )
}
