import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import { PublicPortfolioPage } from '../pages/PublicPortfolioPage'
import type { PortfolioData } from '../types'

vi.mock('../api', () => ({
  api: {
    portfolio: vi.fn(),
  },
}))

const legacyData: PortfolioData = {
  slug: 'alice',
  name: 'Alice Zhang',
  title: 'AI / Agent Engineer',
  summary: 'Focused on structured AI agents.',
  skills: ['Python', 'FastAPI'],
  projects: [
    {
      name: 'MindTrip',
      subtitle: 'Structured travel-planning Agent',
      pipeline: ['Retrieve', 'Plan', 'Validate', 'Repair'],
      decision: '把生成与确定性验证分开。',
    },
  ],
  repositories: [],
  latest_interview_score: null,
}

const cmsData: PortfolioData = {
  slug: 'alice',
  cms: true,
  name: 'Alice CMS',
  title: 'Agent Infra Engineer',
  summary: 'Structured agent systems.',
  skills: ['Python', 'Pydantic'],
  resume_url: 'https://example.com/cv.pdf',
  social: { Blog: 'https://alice.dev' },
  projects: [
    {
      name: 'MindTrip',
      subtitle: 'Travel planning agent',
      description: 'Retrieve, plan, validate.',
      architecture: 'Vitest -> Playwright -> Report',
      decisions: 'UI and API are tested in one flow.',
      tech_tags: ['Playwright'],
      link: '',
      repository: null,
    },
  ],
  repositories: [],
  latest_interview_score: 88.5,
}

beforeEach(() => {
  window.history.replaceState({}, '', '/portfolio/alice')
  vi.mocked(api.portfolio).mockReset()
})

describe('PublicPortfolioPage', () => {
  it('renders the legacy static shape for unpublished users', async () => {
    vi.mocked(api.portfolio).mockResolvedValue(legacyData)

    render(<PublicPortfolioPage />)

    expect(await screen.findByText('AI 工程师作品集')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'Alice Zhang' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3, name: 'MindTrip' })).toBeInTheDocument()
    expect(screen.getByText('Retrieve')).toBeInTheDocument()
    expect(screen.getByText('把生成与确定性验证分开。')).toBeInTheDocument()
    expect(screen.queryByText('简历')).not.toBeInTheDocument()
    expect(screen.getByText('还没有同步任何仓库。')).toBeInTheDocument()
  })

  it('renders CMS content after publishing', async () => {
    vi.mocked(api.portfolio).mockResolvedValue(cmsData)

    render(<PublicPortfolioPage />)

    expect(await screen.findByText('作品集')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'Alice CMS' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Agent Infra Engineer' })).toBeInTheDocument()
    expect(screen.getByText('Python')).toBeInTheDocument()
    expect(screen.getByText('Pydantic')).toBeInTheDocument()
    expect(screen.getByText('Playwright')).toBeInTheDocument()
    expect(screen.getByText('88.5')).toBeInTheDocument()
    expect(screen.getByText('Blog')).toBeInTheDocument()
    expect(screen.getByText('简历')).toBeInTheDocument()
    expect(screen.getByText('Retrieve, plan, validate.')).toBeInTheDocument()
    expect(screen.getByText('架构')).toBeInTheDocument()
    expect(screen.getByText('Vitest -> Playwright -> Report')).toBeInTheDocument()
    expect(screen.getByText('UI and API are tested in one flow.')).toBeInTheDocument()
  })

  it('shows Portfolio not found for unknown users', async () => {
    vi.mocked(api.portfolio).mockRejectedValue(new Error('404'))

    render(<PublicPortfolioPage />)

    expect(await screen.findByRole('heading', { name: '未找到作品集' })).toBeInTheDocument()
    expect(screen.getByText(/alice/)).toBeInTheDocument()
  })
})
