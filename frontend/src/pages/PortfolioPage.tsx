import { useCallback, useEffect, useState } from 'react'
import {
  ArrowDown,
  ArrowUp,
  ArrowUpRight,
  Eye,
  EyeOff,
  GitBranch,
  Pencil,
  Plus,
  Trash2,
} from 'lucide-react'
import { api } from '../api'
import type {
  AuthUser,
  PortfolioProfileInfo,
  PortfolioProfilePayload,
  PortfolioProjectEntry,
  PortfolioProjectPayload,
  Repository,
} from '../types'

type SocialLinkRow = { key: string; value: string }

const EMPTY_PROFILE_FORM = {
  display_name: '',
  headline: '',
  summary: '',
  skills: '',
  resume_url: '',
}

const EMPTY_PROJECT_FORM = {
  title: '',
  subtitle: '',
  description: '',
  architecture: '',
  decisions: '',
  tech_tags: '',
  link: '',
  repository_id: '',
  is_visible: true,
}

function profileToPayload(profile: PortfolioProfileInfo): PortfolioProfilePayload {
  return {
    display_name: profile.display_name,
    headline: profile.headline,
    summary: profile.summary,
    skills: profile.skills,
    resume_url: profile.resume_url,
    social_links: profile.social_links,
    is_published: profile.is_published,
  }
}

function projectToPayload(project: PortfolioProjectEntry, is_visible = project.is_visible): PortfolioProjectPayload {
  return {
    title: project.title,
    subtitle: project.subtitle,
    description: project.description,
    architecture: project.architecture,
    decisions: project.decisions,
    tech_tags: project.tech_tags,
    link: project.link,
    repository_id: project.repository_id,
    is_visible,
  }
}

function errorMessage(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error)
  try {
    const parsed = JSON.parse(raw)
    return parsed.detail || raw
  } catch {
    return raw
  }
}

export function PortfolioPage({ user }: { user: AuthUser }) {
  const portfolioHref = `/portfolio/${encodeURIComponent(user.username)}`
  const [profile, setProfile] = useState<PortfolioProfileInfo | null>(null)
  const [projects, setProjects] = useState<PortfolioProjectEntry[]>([])
  const [repos, setRepos] = useState<Repository[]>([])
  const [profileForm, setProfileForm] = useState({ ...EMPTY_PROFILE_FORM })
  const [socialRows, setSocialRows] = useState<SocialLinkRow[]>([])
  const [savingProfile, setSavingProfile] = useState(false)
  const [profileNotice, setProfileNotice] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<PortfolioProjectEntry | null>(null)
  const [projectForm, setProjectForm] = useState({ ...EMPTY_PROJECT_FORM })
  const [savingProject, setSavingProject] = useState(false)
  const [projectError, setProjectError] = useState('')
  const [busyId, setBusyId] = useState<number | null>(null)

  const load = useCallback(async () => {
    const [savedProfile, projectList, repoList] = await Promise.all([
      api.portfolioCmsProfile(),
      api.portfolioProjects(),
      api.repos(),
    ])
    setProfile(savedProfile)
    setProjects(projectList)
    setRepos(repoList)
    setProfileForm({
      display_name: savedProfile.display_name,
      headline: savedProfile.headline,
      summary: savedProfile.summary,
      skills: savedProfile.skills.join(', '),
      resume_url: savedProfile.resume_url,
    })
    setSocialRows(Object.entries(savedProfile.social_links).map(([key, value]) => ({ key, value })))
  }, [])

  useEffect(() => {
    load().catch((e) => setError(errorMessage(e)))
  }, [load])

  const saveProfile = async () => {
    if (!profile) return
    setSavingProfile(true)
    setProfileNotice('')
    setError('')
    const payload: PortfolioProfilePayload = {
      display_name: profileForm.display_name.trim(),
      headline: profileForm.headline.trim(),
      summary: profileForm.summary.trim(),
      skills: profileForm.skills
        .split(',')
        .map((s) => s.trim().slice(0, 60))
        .filter(Boolean)
        .slice(0, 30),
      resume_url: profileForm.resume_url.trim(),
      social_links: Object.fromEntries(
        socialRows
          .filter((row) => row.key.trim() && row.value.trim())
          .map((row) => [row.key.trim().slice(0, 40), row.value.trim()]),
      ),
      is_published: profile.is_published,
    }
    try {
      const saved = await api.updatePortfolioProfile(payload)
      setProfile(saved)
      setProfileNotice(
        saved.is_published ? '已保存 — 公开页正在展示你的自定义内容。' : '已保存 — 公开页仍为默认内容，点击右上角“发布”生效。',
      )
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setSavingProfile(false)
    }
  }

  const togglePublish = async () => {
    if (!profile || busy) return
    setBusy(true)
    setError('')
    setProfileNotice('')
    try {
      const saved = await api.updatePortfolioProfile({
        ...profileToPayload(profile),
        is_published: !profile.is_published,
      })
      setProfile(saved)
      setProfileNotice(saved.is_published ? '已发布 — 公开页现在展示你的 CMS 内容。' : '已下线 — 公开页恢复为默认内容。')
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const openCreate = () => {
    setEditing(null)
    setProjectForm({ ...EMPTY_PROJECT_FORM })
    setProjectError('')
    setModalOpen(true)
  }

  const openEdit = (project: PortfolioProjectEntry) => {
    setEditing(project)
    setProjectForm({
      title: project.title,
      subtitle: project.subtitle,
      description: project.description,
      architecture: project.architecture,
      decisions: project.decisions,
      tech_tags: project.tech_tags.join(', '),
      link: project.link,
      repository_id: project.repository_id ? String(project.repository_id) : '',
      is_visible: project.is_visible,
    })
    setProjectError('')
    setModalOpen(true)
  }

  const saveProject = async () => {
    if (!projectForm.title.trim()) {
      setProjectError('项目标题不能为空')
      return
    }
    setSavingProject(true)
    setProjectError('')
    const payload: PortfolioProjectPayload = {
      title: projectForm.title.trim(),
      subtitle: projectForm.subtitle.trim(),
      description: projectForm.description.trim(),
      architecture: projectForm.architecture.trim(),
      decisions: projectForm.decisions.trim(),
      tech_tags: projectForm.tech_tags
        .split(',')
        .map((t) => t.trim().slice(0, 40))
        .filter(Boolean)
        .slice(0, 20),
      link: projectForm.link.trim(),
      repository_id: projectForm.repository_id ? Number(projectForm.repository_id) : null,
      is_visible: projectForm.is_visible,
    }
    try {
      const saved = editing
        ? await api.updatePortfolioProject(editing.id, payload)
        : await api.createPortfolioProject(payload)
      setProjects((prev) =>
        editing ? prev.map((p) => (p.id === saved.id ? saved : p)) : [...prev, saved],
      )
      setModalOpen(false)
    } catch (e) {
      setProjectError(errorMessage(e))
    } finally {
      setSavingProject(false)
    }
  }

  const removeProject = async (project: PortfolioProjectEntry) => {
    if (!window.confirm(`删除项目「${project.title}」？该操作不可撤销。`)) return
    setBusyId(project.id)
    setError('')
    try {
      await api.deletePortfolioProject(project.id)
      setProjects((prev) => prev.filter((p) => p.id !== project.id))
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusyId(null)
    }
  }

  const toggleVisible = async (project: PortfolioProjectEntry) => {
    setBusyId(project.id)
    setError('')
    try {
      const saved = await api.updatePortfolioProject(
        project.id,
        projectToPayload(project, !project.is_visible),
      )
      setProjects((prev) => prev.map((p) => (p.id === saved.id ? saved : p)))
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusyId(null)
    }
  }

  const move = async (index: number, delta: -1 | 1) => {
    const target = index + delta
    if (target < 0 || target >= projects.length) return
    const next = [...projects]
    const [item] = next.splice(index, 1)
    next.splice(target, 0, item)
    setProjects(next)
    setError('')
    try {
      const saved = await api.reorderPortfolioProjects(next.map((p) => p.id))
      setProjects(saved)
    } catch (e) {
      setError(errorMessage(e))
      load().catch(() => {})
    }
  }

  const isPublicRepo = (repoId: number | null) =>
    repoId === null || repos.some((r) => r.id === repoId && r.is_public)

  if (!profile) {
    return <div className="page-stack"><div className="empty-state">{error || '正在加载作品集编辑器…'}</div></div>
  }

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">作品集 CMS · v1.0 P2</span>
          <h1>作品集编辑器</h1>
          <p>配置面试官在公开页看到的内容。未发布时公开页展示默认内容；私有仓库绑定仅自己可见。</p>
        </div>
        <div className="pf-header-actions">
          <button
            className={profile.is_published ? 'secondary' : 'primary'}
            onClick={togglePublish}
            disabled={busy}
          >
            {profile.is_published ? '已发布 · 点击下线' : '未发布 · 点击发布'}
          </button>
          <a className="secondary" href={portfolioHref} target="_blank" rel="noreferrer">
            查看公开页 <ArrowUpRight size={14} />
          </a>
        </div>
      </header>

      {error ? <div className="pf-error">{error}</div> : null}

      <section className="card panel">
        <div className="section-title">
          <div>
            <h2>个人资料</h2>
            <p>公开页顶部的姓名、头衔、简介与技能标签。</p>
          </div>
        </div>
        <div className="form-grid pf-form">
          <label>
            显示名称
            <input
              value={profileForm.display_name}
              maxLength={120}
              placeholder={user.display_name || user.username}
              onChange={(e) => setProfileForm({ ...profileForm, display_name: e.target.value })}
            />
          </label>
          <label>
            头衔 / Headline
            <input
              value={profileForm.headline}
              maxLength={200}
              placeholder="AI / Agent Engineer"
              onChange={(e) => setProfileForm({ ...profileForm, headline: e.target.value })}
            />
          </label>
          <label className="span-2">
            简介（公开页大段文案）
            <textarea
              value={profileForm.summary}
              maxLength={4000}
              placeholder="专注于结构化 AI Agent、RAG、确定性执行…"
              onChange={(e) => setProfileForm({ ...profileForm, summary: e.target.value })}
            />
          </label>
          <label>
            技能标签（逗号分隔，最多 30 个）
            <input
              value={profileForm.skills}
              placeholder="Python, FastAPI, RAG, LangGraph"
              onChange={(e) => setProfileForm({ ...profileForm, skills: e.target.value })}
            />
          </label>
          <label>
            简历链接（可选）
            <input
              value={profileForm.resume_url}
              maxLength={500}
              placeholder="https://…"
              onChange={(e) => setProfileForm({ ...profileForm, resume_url: e.target.value })}
            />
          </label>
          <div className="span-2 pf-social">
            <span className="field-label">社交链接（自定义键名，如 GitHub / Blog）</span>
            {socialRows.map((row, i) => (
              <div className="pf-social-row" key={i}>
                <input
                  value={row.key}
                  maxLength={40}
                  placeholder="GitHub"
                  onChange={(e) =>
                    setSocialRows(socialRows.map((r, j) => (i === j ? { ...r, key: e.target.value } : r)))
                  }
                />
                <input
                  value={row.value}
                  maxLength={500}
                  placeholder="https://…"
                  onChange={(e) =>
                    setSocialRows(socialRows.map((r, j) => (i === j ? { ...r, value: e.target.value } : r)))
                  }
                />
                <button
                  className="secondary pf-social-remove"
                  onClick={() => setSocialRows(socialRows.filter((_, j) => j !== i))}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
            <button className="secondary" onClick={() => setSocialRows([...socialRows, { key: '', value: '' }])}>
              <Plus size={13} /> 添加链接
            </button>
          </div>
        </div>
        <div className="button-row">
          <button className="primary" onClick={saveProfile} disabled={savingProfile}>
            {savingProfile ? '保存中…' : '保存资料'}
          </button>
          {profileNotice ? <span className="pf-notice">{profileNotice}</span> : null}
        </div>
      </section>

      <section className="card panel">
        <div className="section-title">
          <div>
            <h2>项目条目（{projects.length}/30）</h2>
            <p>拖动顺序按钮排序；隐藏的项目不会出现在公开页；绑定的私有仓库不会泄露 URL。</p>
          </div>
          <button className="primary" onClick={openCreate}>
            <Plus size={14} /> 新建项目
          </button>
        </div>
        {projects.length === 0 ? (
          <div className="pf-projects-empty">还没有项目条目 — 点击「新建项目」把你的作品搬上公开页。</div>
        ) : (
          <div className="pf-projects">
            {projects.map((project, index) => (
              <article className="pf-project" key={project.id}>
                <div className="pf-project-head">
                  <div className="pf-order">
                    <button
                      title="上移"
                      disabled={index === 0 || busyId !== null}
                      onClick={() => move(index, -1)}
                    >
                      <ArrowUp size={13} />
                    </button>
                    <button
                      title="下移"
                      disabled={index === projects.length - 1 || busyId !== null}
                      onClick={() => move(index, 1)}
                    >
                      <ArrowDown size={13} />
                    </button>
                  </div>
                  <div className="pf-project-title">
                    <strong>{project.title}</strong>
                    <small>{project.subtitle || '—'}</small>
                  </div>
                  <div className="pf-project-badges">
                    {project.repository ? (
                      <span className="pill" title={isPublicRepo(project.repository_id) ? '公开仓库' : '私有仓库 — 公开页不显示链接'}>
                        <GitBranch size={11} /> {project.repository.name}
                        {isPublicRepo(project.repository_id) ? '' : '（私有）'}
                      </span>
                    ) : null}
                    <span className={`pill ${project.is_visible ? 'pill-on' : 'pill-off'}`}>
                      {project.is_visible ? '公开' : '隐藏'}
                    </span>
                  </div>
                  <div className="pf-project-actions">
                    <button
                      title={project.is_visible ? '在公开页隐藏' : '在公开页显示'}
                      disabled={busyId !== null}
                      onClick={() => toggleVisible(project)}
                    >
                      {project.is_visible ? <EyeOff size={13} /> : <Eye size={13} />}
                    </button>
                    <button title="编辑" onClick={() => openEdit(project)}>
                      <Pencil size={13} />
                    </button>
                    <button
                      title="删除"
                      disabled={busyId !== null}
                      onClick={() => removeProject(project)}
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
                {project.tech_tags.length ? (
                  <div className="tag-row">
                    {project.tech_tags.map((tag) => (
                      <span className="tag" key={tag}>{tag}</span>
                    ))}
                  </div>
                ) : null}
                {project.description ? <p className="pf-project-desc">{project.description}</p> : null}
              </article>
            ))}
          </div>
        )}
      </section>

      {modalOpen ? (
        <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && setModalOpen(false)}>
          <div className="modal-card pf-modal">
            <span className="eyebrow">{editing ? '编辑项目' : '新建项目'}</span>
            <h2>{editing ? `编辑「${editing.title}」` : '新建项目条目'}</h2>
            <div className="form-grid pf-form">
              <label>
                标题 *
                <input
                  value={projectForm.title}
                  maxLength={160}
                  onChange={(e) => setProjectForm({ ...projectForm, title: e.target.value })}
                />
              </label>
              <label>
                副标题
                <input
                  value={projectForm.subtitle}
                  maxLength={255}
                  placeholder="Structured travel-planning Agent"
                  onChange={(e) => setProjectForm({ ...projectForm, subtitle: e.target.value })}
                />
              </label>
              <label className="span-2">
                项目描述
                <textarea
                  value={projectForm.description}
                  maxLength={8000}
                  placeholder="做了什么、解决什么问题、你的角色…"
                  onChange={(e) => setProjectForm({ ...projectForm, description: e.target.value })}
                />
              </label>
              <label className="span-2">
                架构说明（可多行）
                <textarea
                  value={projectForm.architecture}
                  maxLength={8000}
                  placeholder={'Retrieve → Plan → Validate → Repair\nLLM 提计划，确定性执行器执行…'}
                  onChange={(e) => setProjectForm({ ...projectForm, architecture: e.target.value })}
                />
              </label>
              <label className="span-2">
                关键工程决策
                <textarea
                  value={projectForm.decisions}
                  maxLength={8000}
                  placeholder="为什么这样设计？面试官最爱从这里开始提问。"
                  onChange={(e) => setProjectForm({ ...projectForm, decisions: e.target.value })}
                />
              </label>
              <label>
                技术标签（逗号分隔）
                <input
                  value={projectForm.tech_tags}
                  placeholder="LangGraph, FastAPI, Redis"
                  onChange={(e) => setProjectForm({ ...projectForm, tech_tags: e.target.value })}
                />
              </label>
              <label>
                项目链接（可选）
                <input
                  value={projectForm.link}
                  maxLength={500}
                  placeholder="https://…"
                  onChange={(e) => setProjectForm({ ...projectForm, link: e.target.value })}
                />
              </label>
              <label>
                绑定同步仓库（可选）
                <select
                  value={projectForm.repository_id}
                  onChange={(e) => setProjectForm({ ...projectForm, repository_id: e.target.value })}
                >
                  <option value="">不绑定</option>
                  {repos.map((repo) => (
                    <option key={repo.id} value={repo.id}>
                      {repo.name} · {repo.provider}
                      {repo.is_public ? '' : '（私有 — 公开页不显示）'}
                    </option>
                  ))}
                </select>
              </label>
              <label className="pf-inline-toggle">
                <input
                  type="checkbox"
                  checked={projectForm.is_visible}
                  onChange={(e) => setProjectForm({ ...projectForm, is_visible: e.target.checked })}
                />
                在公开页显示
              </label>
            </div>
            {projectError ? <p className="form-error">{projectError}</p> : null}
            <div className="modal-actions">
              <button className="secondary" onClick={() => setModalOpen(false)}>取消</button>
              <button className="primary" onClick={saveProject} disabled={savingProject}>
                {savingProject ? '保存中…' : editing ? '保存修改' : '创建项目'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
