import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import { PortfolioPage } from '../pages/PortfolioPage'
import type {
  AuthUser,
  PortfolioProfileInfo,
  PortfolioProjectEntry,
  PortfolioProjectPayload,
  Repository,
} from '../types'

vi.mock('../api', () => ({
  api: {
    portfolioCmsProfile: vi.fn(),
    portfolioProjects: vi.fn(),
    repos: vi.fn(),
    updatePortfolioProfile: vi.fn(),
    updatePortfolioProject: vi.fn(),
    createPortfolioProject: vi.fn(),
    deletePortfolioProject: vi.fn(),
    reorderPortfolioProjects: vi.fn(),
  },
}))

const user: AuthUser = {
  id: 1,
  username: 'alice',
  email: 'alice@example.com',
  display_name: 'Alice Zhang',
  created_at: '2026-09-10T00:00:00Z',
}

const baseProfile: PortfolioProfileInfo = {
  username: 'alice',
  display_name: 'Alice CMS',
  headline: 'Agent Infra Engineer',
  summary: 'Building agent infrastructure.',
  skills: ['Python', 'FastAPI'],
  resume_url: '',
  social_links: { blog: 'https://alice.dev' },
  is_published: false,
}

const project = (overrides: Partial<PortfolioProjectEntry> = {}): PortfolioProjectEntry => ({
  id: 1,
  title: 'MindTrip',
  subtitle: 'Travel planning agent',
  description: 'Retrieve, plan, validate.',
  architecture: 'Plan -> Validate -> Execute',
  decisions: 'LLM proposes, executor disposes.',
  tech_tags: ['LangGraph'],
  link: '',
  repository_id: null,
  repository: null,
  is_visible: true,
  order_index: 1,
  ...overrides,
})

const repo = (overrides: Partial<Repository> = {}): Repository => ({
  id: 5,
  provider: 'github',
  name: 'secret-repo',
  url: 'https://github.com/alice/secret-repo',
  branch: 'main',
  last_commit: 'abc123def456',
  file_count: 12,
  summary: {},
  is_public: false,
  is_private: true,
  synced_at: '2026-09-10T00:00:00Z',
  ...overrides,
})

function renderPage() {
  return render(<PortfolioPage user={user} />)
}

beforeEach(() => {
  vi.mocked(api.portfolioCmsProfile).mockResolvedValue({ ...baseProfile })
  vi.mocked(api.portfolioProjects).mockResolvedValue([])
  vi.mocked(api.repos).mockResolvedValue([])
  vi.mocked(api.updatePortfolioProfile).mockReset()
  vi.mocked(api.updatePortfolioProject).mockReset()
  vi.mocked(api.createPortfolioProject).mockReset()
  vi.mocked(api.deletePortfolioProject).mockReset()
  vi.mocked(api.reorderPortfolioProjects).mockReset()
})

describe('PortfolioPage', () => {
  it('populates the profile form and shows the unpublished state', async () => {
    renderPage()

    expect(await screen.findByDisplayValue('Alice CMS')).toBeInTheDocument()
    expect(screen.getByLabelText(/头衔/)).toHaveValue('Agent Infra Engineer')
    expect(screen.getByLabelText(/技能标签/)).toHaveValue('Python, FastAPI')
    expect(screen.getByText('未发布 · 点击发布')).toBeInTheDocument()
    expect(screen.getByText(/0\/30/)).toBeInTheDocument()
    expect(screen.getByText(/还没有项目条目/)).toBeInTheDocument()
  })

  it('publishes and unpublishes through the header switch', async () => {
    vi.mocked(api.updatePortfolioProfile)
      .mockResolvedValueOnce({ ...baseProfile, is_published: true })
      .mockResolvedValueOnce({ ...baseProfile })
    renderPage()

    await userEvent.click(await screen.findByText('未发布 · 点击发布'))

    await waitFor(() =>
      expect(api.updatePortfolioProfile).toHaveBeenCalledWith(
        expect.objectContaining({ is_published: true, headline: 'Agent Infra Engineer' }),
      ),
    )
    expect(await screen.findByText('已发布 · 点击下线')).toBeInTheDocument()
    expect(screen.getByText('已发布 — 公开页现在展示你的 CMS 内容。')).toBeInTheDocument()

    await userEvent.click(screen.getByText('已发布 · 点击下线'))
    await waitFor(() =>
      expect(api.updatePortfolioProfile).toHaveBeenLastCalledWith(
        expect.objectContaining({ is_published: false }),
      ),
    )
    expect(await screen.findByText('未发布 · 点击发布')).toBeInTheDocument()
  })

  it('saves the profile with parsed skills and only non-empty social rows', async () => {
    vi.mocked(api.updatePortfolioProfile).mockResolvedValue({ ...baseProfile })
    renderPage()

    const skills = await screen.findByLabelText(/技能标签/)
    await userEvent.clear(skills)
    await userEvent.type(skills, ' a , b , , c ')

    await userEvent.click(screen.getByText('保存资料'))

    await waitFor(() => expect(api.updatePortfolioProfile).toHaveBeenCalledTimes(1))
    const payload = vi.mocked(api.updatePortfolioProfile).mock.calls[0][0]
    expect(payload.skills).toEqual(['a', 'b', 'c'])
    expect(payload.social_links).toEqual({ blog: 'https://alice.dev' })
    expect(payload.is_published).toBe(false)
  })

  it('rejects a new project without a title', async () => {
    renderPage()

    await userEvent.click(await screen.findByText('新建项目'))
    await userEvent.click(screen.getByText('创建项目', { selector: '.modal-actions button' }))

    expect(screen.getByText('项目标题不能为空')).toBeInTheDocument()
    expect(api.createPortfolioProject).not.toHaveBeenCalled()
  })

  it('creates a project with parsed tech tags and no repository binding', async () => {
    const created = project({ id: 9, title: 'AtlasSplit', tech_tags: ['FastAPI', 'Redis'] })
    vi.mocked(api.createPortfolioProject).mockResolvedValue(created)
    renderPage()

    await userEvent.click(await screen.findByText('新建项目'))
    await userEvent.type(screen.getByLabelText(/标题 \*/), 'AtlasSplit')
    await userEvent.type(screen.getByLabelText(/技术标签/), 'FastAPI, Redis')
    await userEvent.click(screen.getByText('创建项目', { selector: '.modal-actions button' }))

    await waitFor(() => expect(api.createPortfolioProject).toHaveBeenCalledTimes(1))
    const payload: PortfolioProjectPayload = vi.mocked(api.createPortfolioProject).mock.calls[0][0]
    expect(payload).toMatchObject({
      title: 'AtlasSplit',
      tech_tags: ['FastAPI', 'Redis'],
      repository_id: null,
      is_visible: true,
    })
    expect(screen.queryByText('新建项目条目')).not.toBeInTheDocument()
    expect(await screen.findByText('AtlasSplit')).toBeInTheDocument()
  })

  it('reorders projects with the move buttons', async () => {
    const first = project({ id: 1, title: 'First', order_index: 1 })
    const second = project({ id: 2, title: 'Second', order_index: 2 })
    vi.mocked(api.portfolioProjects).mockResolvedValue([first, second])
    vi.mocked(api.reorderPortfolioProjects).mockResolvedValue([
      { ...second, order_index: 1 },
      { ...first, order_index: 2 },
    ])
    const { container } = renderPage()

    await screen.findByText('First')
    await userEvent.click(screen.getAllByTitle('下移')[0])

    await waitFor(() => expect(api.reorderPortfolioProjects).toHaveBeenCalledWith([2, 1]))
    await waitFor(() =>
      expect([...container.querySelectorAll('.pf-project-title strong')].map((el) => el.textContent)).toEqual([
        'Second',
        'First',
      ]),
    )
  })

  it('marks a private repository binding without leaking it as public', async () => {
    vi.mocked(api.portfolioProjects).mockResolvedValue([
      project({
        id: 1,
        repository_id: 5,
        repository: {
          name: 'secret-repo',
          provider: 'github',
          url: 'https://github.com/alice/secret-repo',
          commit: 'abc123def456',
          files: 12,
        },
      }),
    ])
    vi.mocked(api.repos).mockResolvedValue([repo()])
    renderPage()

    expect(await screen.findByText('secret-repo（私有）')).toBeInTheDocument()
  })

  it('toggles a project between public and hidden', async () => {
    const entry = project()
    vi.mocked(api.portfolioProjects).mockResolvedValue([entry])
    vi.mocked(api.updatePortfolioProject).mockResolvedValue(project({ is_visible: false }))
    renderPage()

    await userEvent.click(await screen.findByTitle('在公开页隐藏'))

    await waitFor(() => expect(api.updatePortfolioProject).toHaveBeenCalledTimes(1))
    const [projectId, payload] = vi.mocked(api.updatePortfolioProject).mock.calls[0]
    expect(projectId).toBe(1)
    expect(payload.is_visible).toBe(false)
    expect(await screen.findByText('隐藏')).toBeInTheDocument()
  })

  it('deletes a project after confirmation', async () => {
    vi.mocked(api.portfolioProjects).mockResolvedValue([project()])
    vi.mocked(api.deletePortfolioProject).mockResolvedValue({ deleted: 1 })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderPage()

    await userEvent.click(await screen.findByTitle('删除'))

    await waitFor(() => expect(api.deletePortfolioProject).toHaveBeenCalledWith(1))
    await waitFor(() => expect(screen.queryByText('MindTrip')).not.toBeInTheDocument())
    confirmSpy.mockRestore()
  })
})
