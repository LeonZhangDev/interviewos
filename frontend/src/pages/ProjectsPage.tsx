import { useEffect, useMemo, useState } from 'react'
import Editor from '@monaco-editor/react'
import { ArrowRight, ClipboardCopy, Code2, Eye, EyeOff, FileCode2, FileText, FolderGit2, GitBranch, Lock, RefreshCw, Search, ShieldCheck, Sparkles, Unlink } from 'lucide-react'
import { api } from '../api'
import { ArchitectureFlow } from '../components/ArchitectureFlow'
import type { ArchitectureGraph, CodeSeed, GitProvider, GitProviderRepo, GitProviderStatus, RepoFile, Repository } from '../types'

const languageMap: Record<string, string> = {
  Python: 'python', TypeScript: 'typescript', 'TypeScript React': 'typescript', JavaScript: 'javascript',
  'JavaScript React': 'javascript', JSON: 'json', Markdown: 'markdown', SQL: 'sql', YAML: 'yaml',
  HTML: 'html', CSS: 'css', Shell: 'shell', Java: 'java', 'C++': 'cpp', C: 'c',
}

export function ProjectsPage({ onOpenCode, focusRepoId }: { onOpenCode: (seed: CodeSeed) => void; focusRepoId?: number }) {
  const [projects, setProjects] = useState<any[]>([])
  const [repos, setRepos] = useState<Repository[]>([])
  const [provider, setProvider] = useState<'github' | 'gitee'>('gitee')
  const [repoInput, setRepoInput] = useState('https://gitee.com/rainyjensen/mind-trip')
  const [branch, setBranch] = useState('master')
  const [syncing, setSyncing] = useState(false)
  const [syncMessage, setSyncMessage] = useState('')
  const [activeRepo, setActiveRepo] = useState<Repository | null>(null)
  const [files, setFiles] = useState<RepoFile[]>([])
  const [fileSearch, setFileSearch] = useState('')
  const [activeFile, setActiveFile] = useState<RepoFile | null>(null)
  const [architecture, setArchitecture] = useState<ArchitectureGraph | null>(null)
  const [archLoading, setArchLoading] = useState(false)
  const [resumeText, setResumeText] = useState('')
  const [resumeBusy, setResumeBusy] = useState(false)
  const [resumeLanguage, setResumeLanguage] = useState<'zh' | 'en'>('zh')
  const [isPrivateInput, setIsPrivateInput] = useState(false)
  const [gitProviders, setGitProviders] = useState<GitProviderStatus[]>([])
  const [providerBusy, setProviderBusy] = useState('')
  const [providerRepos, setProviderRepos] = useState<{ provider: GitProvider; visibility: 'all' | 'public' | 'private'; repos: GitProviderRepo[] } | null>(null)
  const [repoListLoading, setRepoListLoading] = useState(false)

  useEffect(() => {
    Promise.all([api.projects(), api.repos(), api.gitProviders().catch(() => [])]).then(([projectItems, repoItems, providerItems]) => {
      setProjects(projectItems)
      setRepos(repoItems)
      setGitProviders(providerItems)
      if (repoItems[0]) selectRepo(repoItems[0])
    })
  }, [])

  useEffect(() => {
    if (!focusRepoId || activeRepo?.id === focusRepoId) return
    const target = repos.find((x) => x.id === focusRepoId)
    if (target) selectRepo(target)
  }, [focusRepoId, repos])

  async function refreshRepos(preferredId?: number) {
    const items = await api.repos()
    setRepos(items)
    const next = items.find((x) => x.id === preferredId) ?? items[0] ?? null
    if (next) await selectRepo(next)
  }

  async function selectRepo(repo: Repository) {
    setActiveRepo(repo)
    setActiveFile(null)
    setArchitecture(null)
    setResumeText('')
    const repoFiles = await api.repoFiles(repo.id)
    setFiles(repoFiles)
    if (repoFiles[0]) await selectFile(repo.id, repoFiles[0])
  }

  async function selectFile(repoId: number, file: RepoFile) {
    setActiveFile(await api.repoFile(repoId, file.id))
  }

  async function loadArchitecture() {
    if (!activeRepo) return
    setArchLoading(true)
    try { setArchitecture(await api.repoArchitecture(activeRepo.id)) } finally { setArchLoading(false) }
  }

  async function generateResume() {
    if (!activeRepo) return
    setResumeBusy(true)
    try {
      const result = await api.generateResume(activeRepo.id, resumeLanguage, 'technical')
      setResumeText(result.text || '')
    } catch (error) { setResumeText(`生成失败：${String(error)}`) } finally { setResumeBusy(false) }
  }

  async function syncRepo() {
    setSyncing(true)
    setSyncMessage('正在读取仓库、分析文件和知识点…')
    try {
      const synced = await api.syncRepo({ provider, repo: repoInput, branch, is_private: isPrivateInput })
      setSyncMessage(`已同步 ${synced.name} · ${synced.file_count} 个文本/代码文件`)
      await refreshRepos(synced.id)
    } catch (error) {
      setSyncMessage(`同步失败：${errorText(error)}`)
    } finally {
      setSyncing(false)
    }
  }

  async function authorizeProvider(target: GitProvider) {
    setProviderBusy(target)
    try {
      const result = await api.gitAuthorize(target)
      window.location.href = result.authorize_url
    } catch (error) {
      setSyncMessage(`发起授权失败：${errorText(error)}`)
      setProviderBusy('')
    }
  }

  async function disconnectProvider(target: GitProvider) {
    setProviderBusy(target)
    try {
      await api.gitDisconnect(target)
      if (providerRepos?.provider === target) setProviderRepos(null)
      setGitProviders(await api.gitProviders())
      setSyncMessage(`已断开 ${providerLabel(target)} 连接，存储的 token 已删除。`)
    } catch (error) {
      setSyncMessage(`断开失败：${errorText(error)}`)
    } finally {
      setProviderBusy('')
    }
  }

  async function openProviderRepos(target: GitProvider, visibility: 'all' | 'public' | 'private' = 'all') {
    setRepoListLoading(true)
    try {
      const result = await api.gitProviderRepos(target, visibility)
      setProviderRepos({ provider: target, visibility, repos: result.repos })
    } catch (error) {
      setProviderRepos(null)
      setSyncMessage(`读取仓库列表失败：${errorText(error)}`)
    } finally {
      setRepoListLoading(false)
    }
  }

  async function syncProviderRepo(item: GitProviderRepo) {
    if (!providerRepos) return
    setSyncing(true)
    setSyncMessage(`正在同步 ${item.name}（${item.default_branch}）…`)
    try {
      const synced = await api.syncRepo({
        provider: providerRepos.provider,
        repo: item.name,
        branch: item.default_branch,
        is_private: item.private,
      })
      setSyncMessage(`已同步 ${synced.name} · ${synced.file_count} 个文件${item.private ? '（私有仓库：仅你的授权 token 可访问，默认不出现在公开 Portfolio）' : ''}`)
      await refreshRepos(synced.id)
    } catch (error) {
      setSyncMessage(`同步失败：${errorText(error)}`)
    } finally {
      setSyncing(false)
    }
  }

  async function toggleVisibility(repo: Repository) {
    try {
      const result = await api.updateRepoVisibility(repo.id, !repo.is_public)
      setRepos((items) => items.map((x) => (x.id === repo.id ? { ...x, is_public: result.is_public } : x)))
      if (activeRepo?.id === repo.id) setActiveRepo({ ...activeRepo, is_public: result.is_public })
    } catch (error) {
      setSyncMessage(`切换可见性失败：${String(error)}`)
    }
  }

  const filteredFiles = useMemo(() => files.filter((x) => x.path.toLowerCase().includes(fileSearch.toLowerCase())), [files, fileSearch])

  return (
    <div className="page-stack">
      <div className="page-header">
        <div><span className="eyebrow">项目情报</span><h1>项目、源码和面试追问放在同一层。</h1><p>先展示架构，再从真实仓库同步代码，自动提取符号、技术点和可能被追问的问题。</p></div>
      </div>

      <div className="project-grid">
        {projects.map((project) => (
          <article className="card project-card" key={project.name}>
            <div className="project-top"><div className="project-icon"><GitBranch size={21} /></div><span className="pill">重点项目</span></div>
            <h2>{project.name}</h2><p>{project.subtitle}</p>
            <div className="tag-row">{project.focus.map((x: string) => <span className="tag" key={x}>{x}</span>)}</div>
            <div className="pipeline">{project.pipeline.map((x: string, i: number) => <div className="pipeline-step" key={x}><span>{x}</span>{i < project.pipeline.length - 1 ? <ArrowRight size={14} /> : null}</div>)}</div>
            <div className="project-questions"><span className="eyebrow"><Sparkles size={13} /> 面试追问</span>{project.interview_questions.map((x: string) => <p key={x}>• {x}</p>)}</div>
          </article>
        ))}
      </div>

      <section className="card git-providers-panel">
        <div className="section-title">
          <div><span className="eyebrow">Git 账号绑定 · OAuth</span><h2>绑定 GitHub / Gitee 账号</h2><p>授权后可列出并同步你的私有仓库。access token 加密存储在服务端，任何接口都不会返回明文；断开连接即删除。</p></div>
          <ShieldCheck />
        </div>
        <div className="git-provider-grid">
          {gitProviders.map((item) => (
            <div className="git-provider-row" key={item.provider}>
              <div className="git-provider-info">
                <strong>{providerLabel(item.provider)}</strong>
                {item.connected
                  ? <span className="pill connected">已绑定 @{item.login}</span>
                  : <span className="pill">{item.configured ? '未绑定' : '未配置'}</span>}
                {item.connected && item.scopes ? <small>scopes: {item.scopes}</small> : null}
                {!item.configured ? <small>管理员未配置该 provider 的 OAuth 应用（缺少 client id/secret），仅支持公开仓库同步。</small> : null}
              </div>
              <div className="git-provider-actions">
                {item.connected ? <>
                  <button className="secondary" onClick={() => openProviderRepos(item.provider)} disabled={repoListLoading || providerBusy === item.provider}>
                    <FolderGit2 size={13} /> {repoListLoading && providerRepos?.provider === item.provider ? '读取中…' : '选择仓库同步'}
                  </button>
                  <button className="secondary danger" onClick={() => disconnectProvider(item.provider)} disabled={providerBusy === item.provider}>
                    <Unlink size={13} /> 断开
                  </button>
                </> : <button className="primary" onClick={() => authorizeProvider(item.provider)} disabled={!item.configured || providerBusy === item.provider}>
                  {providerBusy === item.provider ? '跳转中…' : '绑定授权'}
                </button>}
              </div>
            </div>
          ))}
          {gitProviders.length === 0 ? <div className="rail-empty">Git provider 状态不可用（接口异常），仍可使用下方公开仓库同步。</div> : null}
        </div>

        {providerRepos ? (
          <div className="git-repo-list">
            <div className="git-repo-list-head">
              <span className="eyebrow">{providerLabel(providerRepos.provider)} 仓库 · 点击右侧同步按钮显式选择要导入的仓库</span>
              <div className="git-repo-filters">
                {(['all', 'public', 'private'] as const).map((mode) => (
                  <button key={mode} className={providerRepos.visibility === mode ? 'active' : ''} onClick={() => openProviderRepos(providerRepos.provider, mode)} disabled={repoListLoading}>
                    {mode === 'all' ? '全部' : mode === 'public' ? '公开' : '私有'}
                  </button>
                ))}
                <button className="close" onClick={() => setProviderRepos(null)} aria-label="关闭仓库列表">×</button>
              </div>
            </div>
            {providerRepos.repos.length ? providerRepos.repos.map((item) => (
              <div className="git-repo-row" key={item.name}>
                <div className="git-repo-row-main">
                  <strong>{item.name}{item.private ? <span className="pill private"><Lock size={9} /> 私有</span> : null}</strong>
                  <small>{item.default_branch} · 更新于 {item.updated_at ? item.updated_at.slice(0, 10) : '未知'}{item.description ? ` · ${item.description}` : ''}</small>
                </div>
                <button className="primary" onClick={() => syncProviderRepo(item)} disabled={syncing}><RefreshCw size={13} className={syncing ? 'spin' : ''} /> 同步</button>
              </div>
            )) : <div className="rail-empty">该过滤条件下没有仓库。</div>}
          </div>
        ) : null}
      </section>

      <section className="card repo-sync-panel">
        <div className="section-title"><div><span className="eyebrow">仓库同步</span><h2>真实项目代码浏览器</h2><p>只接受 GitHub/Gitee HTTPS 仓库；同步过程读取源码但不会执行仓库代码。绑定账号后私有仓库也可同步。</p></div>
          <FolderGit2 />
        </div>
        <div className="repo-sync-form">
          <select value={provider} onChange={(e) => setProvider(e.target.value as 'github' | 'gitee')}><option value="gitee">Gitee</option><option value="github">GitHub</option></select>
          <input value={repoInput} onChange={(e) => setRepoInput(e.target.value)} placeholder="owner/repo 或 https://github.com/owner/repo" />
          <input className="branch-input" value={branch} onChange={(e) => setBranch(e.target.value)} placeholder="master" />
          <button className="primary" onClick={syncRepo} disabled={syncing}><RefreshCw size={15} className={syncing ? 'spin' : ''} /> {syncing ? '同步中…' : '同步'}</button>
        </div>
        <label className="git-private-toggle">
          <input type="checkbox" checked={isPrivateInput} onChange={(e) => setIsPrivateInput(e.target.checked)} />
          <span>这是私有仓库（需要先绑定对应 provider；仅作为元数据标记，不会出现在公开 Portfolio）</span>
        </label>
        {syncMessage ? <div className="inline-status">{syncMessage}</div> : null}
      </section>

      {activeRepo ? <section className="card architecture-panel">
        <div className="section-title"><div><span className="eyebrow">AST + 架构分析</span><h2>仓库架构与调用关系</h2><p>基于 Python AST、import 和代码知识点生成，可拖动、缩放，并可复制 Mermaid。</p></div><button className="secondary" onClick={loadArchitecture} disabled={archLoading}>{archLoading ? '分析中…' : architecture ? '刷新架构图' : '分析架构'}</button></div>
        {architecture ? <>
          <ArchitectureFlow graph={architecture} />
          <div className="architecture-meta"><div><span className="eyebrow">技术主题</span><div className="tag-row">{architecture.topics.map(([name, count]) => <span className="tag" key={name}>{name} · {count}</span>)}</div></div><div><span className="eyebrow">项目面试追问</span>{architecture.questions.slice(0, 8).map((q) => <p key={q}>→ {q}</p>)}</div></div>
          <details className="mermaid-box"><summary>Mermaid 源码</summary><pre>{architecture.mermaid}</pre></details>
        </> : <div className="empty-state compact-empty">点击「分析架构」，从当前同步源码生成架构图。</div>}
      </section> : null}

      {activeRepo ? <section className="card resume-generator">
        <div className="section-title"><div><span className="eyebrow">仓库 → 简历</span><h2>用代码证据生成简历项目描述</h2><p>只使用仓库文件、AST 符号和技术主题；不会虚构 QPS、准确率、用户量或性能提升。</p></div><FileText size={19} /></div>
        <div className="resume-actions"><select value={resumeLanguage} onChange={(e) => setResumeLanguage(e.target.value as 'zh' | 'en')}><option value="zh">中文</option><option value="en">English</option></select><button className="primary" onClick={generateResume} disabled={resumeBusy}>{resumeBusy ? '生成中…' : '生成项目描述'}</button>{resumeText ? <button className="secondary" onClick={() => navigator.clipboard.writeText(resumeText)}><ClipboardCopy size={14} /> 复制</button> : null}</div>
        {resumeText ? <pre className="resume-output">{resumeText}</pre> : <div className="empty-state compact-empty">选择仓库后生成；配置 LLM 时会使用模型润色，没有模型时使用可验证的离线模板。</div>}
      </section> : null}

      {activeRepo?.summary.diff ? <section className="card commit-intel">
        <div className="section-title"><div><span className="eyebrow">Commit 变更 → 面试</span><h2>最近一次同步变更分析</h2></div><GitBranch size={18} /></div>
        <div className="commit-meta"><code>{activeRepo.summary.diff.from_commit || '基线'}</code><ArrowRight size={14} /><code>{activeRepo.summary.diff.to_commit}</code><span>{activeRepo.summary.diff.shortstat || activeRepo.summary.diff.reason || '暂无变更'}</span></div>
        {activeRepo.summary.diff.files?.length ? <div className="diff-files">{activeRepo.summary.diff.files.slice(0, 12).map((item) => <span key={`${item.status}-${item.path}`}><b>{item.status}</b>{item.path}</span>)}</div> : null}
        {activeRepo.summary.diff.questions?.length ? <div className="diff-questions"><span className="eyebrow">自动生成的问题</span>{activeRepo.summary.diff.questions.map((q) => <p key={q}>→ {q}</p>)}</div> : <p className="diff-empty">{activeRepo.summary.diff.reason || '当前 commit 没有新的变更。'}</p>}
      </section> : null}

      <section className="repo-browser card">
        <aside className="repo-rail">
          <div className="repo-rail-title">仓库列表</div>
          {repos.length ? repos.map((repo) => (
            <div key={repo.id} className={activeRepo?.id === repo.id ? 'repo-row active' : 'repo-row'}>
              <button className="repo-row-main" onClick={() => selectRepo(repo)}>
                <FolderGit2 size={15} /><span><strong>{repo.name}</strong><small>{repo.provider} · {repo.branch} · {repo.file_count} 个文件{repo.is_private ? ' · 私有' : ''}</small></span>
              </button>
              <button className={repo.is_public ? 'repo-vis public' : 'repo-vis'} onClick={() => toggleVisibility(repo)} title={repo.is_public ? '公开中：出现在公开 Portfolio' : '私有：不出现在公开 Portfolio'}>
                {repo.is_public ? <Eye size={13} /> : <EyeOff size={13} />}
              </button>
            </div>
          )) : <div className="rail-empty">先同步一个公开仓库。</div>}
        </aside>

        <aside className="file-rail">
          <div className="search-box compact"><Search size={15} /><input value={fileSearch} onChange={(e) => setFileSearch(e.target.value)} placeholder="搜索文件路径" /></div>
          <div className="file-list">
            {filteredFiles.map((file) => (
              <button key={file.id} className={activeFile?.id === file.id ? 'file-row active' : 'file-row'} onClick={() => activeRepo && selectFile(activeRepo.id, file)}>
                <FileCode2 size={14} /><span><strong>{file.path}</strong><small>{file.language} · {Math.ceil(file.size / 1024)} KB</small></span>
              </button>
            ))}
          </div>
        </aside>

        <div className="repo-code-pane">
          {activeFile ? <>
            <div className="repo-code-head">
              <div><strong>{activeFile.path}</strong><small>{activeFile.language}</small></div>
              <button className="secondary" onClick={() => onOpenCode({ title: activeFile.path, code: activeFile.content || '', language: activeFile.language })}><Code2 size={14} /> 送到代码解释模式</button>
            </div>
            <Editor height="410px" language={languageMap[activeFile.language] || 'plaintext'} value={activeFile.content || ''} theme="vs-dark" options={{ readOnly: true, minimap: { enabled: false }, fontSize: 13, wordWrap: 'on', automaticLayout: true }} />
            <div className="repo-analysis">
              <div><span className="eyebrow">知识点</span><div className="tag-row">{activeFile.knowledge.map((x) => <span className="tag selected" key={x}>{x}</span>)}</div></div>
              <div><span className="eyebrow">符号</span><div className="symbol-list">{activeFile.symbols.length ? activeFile.symbols.map((x) => <code key={x}>{x}</code>) : <small>未提取到函数/类符号</small>}</div></div>
              <div className="repo-question-list"><span className="eyebrow">自动面试追问</span>{activeFile.questions?.map((x) => <p key={x}>→ {x}</p>)}</div>
            </div>
          </> : <div className="empty-state">同步仓库后，在左侧选择一个代码文件。</div>}
        </div>
      </section>
    </div>
  )
}

function providerLabel(provider: GitProvider): string {
  return provider === 'github' ? 'GitHub' : 'Gitee'
}

function errorText(error: unknown): string {
  return String(error)
    .replace(/^Error:\s*/, '')
    .replace(/^.*?"detail":"([^"]+)".*$/s, '$1')
}
