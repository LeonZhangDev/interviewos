import type {
  AuthTokens,
  AuthUser,
  CodingChallenge,
  Dashboard,
  FastApiPlaygroundResult,
  GitAuthorizeResult,
  GitConnectionResult,
  GitProvider,
  GitProviderRepoList,
  GitProviderStatus,
  ImportPreview,
  InterviewerPersona,
  InterviewSession,
  KnowledgeGraphData,
  PlaygroundMeta,
  PlaygroundResetResult,
  PlaygroundSessionInfo,
  PortfolioData,
  PortfolioProfileInfo,
  PortfolioProfilePayload,
  PortfolioProjectEntry,
  PortfolioProjectPayload,
  PrerequisiteGraph,
  PrerequisiteRecommendation,
  Question,
  QuestionDraft,
  QuestionDuplicate,
  RedisPlaygroundResult,
  RepoFile,
  Repository,
  ReviewLogEntry,
  SearchResponse,
  SqlPlaygroundResult,
  SystemCanvas,
  SystemDesignCase,
  TimeStatus,
  Weakness,
  WrongBookEntry,
} from './types'

const TOKEN_KEY = 'interviewos_token'
const REFRESH_KEY = 'interviewos_refresh'

export function authToken() { return localStorage.getItem(TOKEN_KEY) || '' }
export function refreshAuthToken() { return localStorage.getItem(REFRESH_KEY) || '' }

export function setAuthTokens(access: string, refresh: string) {
  if (access) localStorage.setItem(TOKEN_KEY, access); else localStorage.removeItem(TOKEN_KEY)
  if (refresh) localStorage.setItem(REFRESH_KEY, refresh); else localStorage.removeItem(REFRESH_KEY)
}

/** Backwards-compatible single-token setter; keeps the stored refresh token. */
export function setAuthToken(token: string) { setAuthTokens(token, refreshAuthToken()) }

function headers(init?: RequestInit): Headers {
  const result = new Headers(init?.headers || {})
  const token = authToken()
  if (token) result.set('Authorization', `Bearer ${token}`)
  return result
}

let refreshInFlight: Promise<boolean> | null = null

/** Single-flight refresh: concurrent 401s share one /api/auth/refresh call. */
async function tryRefresh(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const token = refreshAuthToken()
      if (!token) return false
      try {
        const response = await fetch('/api/auth/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: token }),
        })
        if (!response.ok) return false
        const data = await response.json()
        setAuthTokens(data.access_token, data.refresh_token)
        return true
      } catch {
        return false
      }
    })().finally(() => { refreshInFlight = null })
  }
  return refreshInFlight
}

function sessionExpired() {
  setAuthTokens('', '')
  window.dispatchEvent(new Event('interviewos:unauthorized'))
}

async function json<T>(url: string, init?: RequestInit, retry = true): Promise<T> {
  const response = await fetch(url, { ...init, headers: headers(init) })
  if (response.status === 401 && !url.startsWith('/api/auth/')) {
    if (retry && await tryRefresh()) return json<T>(url, init, false)
    sessionExpired()
    throw new Error(await response.text())
  }
  if (!response.ok) throw new Error(await response.text())
  return response.json() as Promise<T>
}

const post = <T>(url: string, body?: unknown) => json<T>(url, {
  method: 'POST',
  headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
})
const put = <T>(url: string, body?: unknown) => json<T>(url, {
  method: 'PUT',
  headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
})
const patch = <T>(url: string, body?: unknown) => json<T>(url, {
  method: 'PATCH',
  headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
})
const del = <T>(url: string) => json<T>(url, { method: 'DELETE' })

export const api = {
  register: (payload: { username: string; email: string; password: string; display_name?: string }) => post<AuthTokens & { user: AuthUser }>('/api/auth/register', payload),
  login: (payload: { identity: string; password: string }) => post<AuthTokens & { user: AuthUser }>('/api/auth/login', payload),
  me: () => json<AuthUser>('/api/auth/me'),
  logout: (payload: { refresh_token?: string; all_devices?: boolean }) => post<{ status: string }>('/api/auth/logout', payload),
  changePassword: (currentPassword: string, newPassword: string) => post<AuthTokens & { user: AuthUser; status: string }>('/api/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
  }),

  dashboard: () => json<Dashboard>('/api/dashboard'),
  search: (q: string, perGroup = 5) => json<SearchResponse>(`/api/search?q=${encodeURIComponent(q)}&per_group=${perGroup}`),
  questions: (archived = false) => json<Question[]>(`/api/questions${archived ? '?archived=true' : ''}`),
  createQuestion: (payload: QuestionDraft, force = false) => post<Question>(`/api/questions${force ? '?force=true' : ''}`, payload),
  updateQuestion: (id: number, payload: Partial<QuestionDraft>, force = false) => patch<Question>(`/api/questions/${id}${force ? '?force=true' : ''}`, payload),
  archiveQuestion: (id: number) => post<Question>(`/api/questions/${id}/archive`),
  restoreQuestion: (id: number) => post<Question>(`/api/questions/${id}/restore`),
  bulkTagQuestions: (ids: number[], tags: string[], mode: 'set' | 'append' | 'remove' = 'append') => post<{ updated: number }>('/api/questions/bulk-tag', { ids, tags, mode }),
  projects: () => json<any[]>('/api/projects'),
  weakness: () => json<Weakness[]>('/api/learning/weakness'),
  reviewTopic: (topic: string, grade: number) => post<any>(`/api/learning/${encodeURIComponent(topic)}/review?grade=${grade}`),
  reviewHistory: (topic: string) => json<ReviewLogEntry[]>(`/api/learning/${encodeURIComponent(topic)}/history`),
  knowledgeGraph: () => json<KnowledgeGraphData>('/api/knowledge-graph'),
  prerequisiteGraph: () => json<PrerequisiteGraph>('/api/knowledge/prerequisites'),
  prerequisiteRecommendations: () => json<PrerequisiteRecommendation[]>('/api/knowledge/prerequisites/recommendations'),

  runCode: (code: string, stdin = '') => post<any>('/api/code/run', { code, stdin }),
  codingChallenges: () => json<CodingChallenge[]>('/api/coding/challenges'),
  codingChallenge: (id: number) => json<CodingChallenge>(`/api/coding/challenges/${id}`),
  runChallenge: (id: number, payload: { code: string; time_complexity?: string; space_complexity?: string; mode?: 'practice' | 'lock' }) => post<any>(`/api/coding/challenges/${id}/run`, payload),
  submitChallenge: (id: number, payload: { code: string; time_complexity?: string; space_complexity?: string; mode?: 'practice' | 'lock' }) => post<any>(`/api/coding/challenges/${id}/submit`, payload),
  wrongBook: () => json<WrongBookEntry[]>('/api/coding/wrongbook'),
  challengeSubmissions: (id: number) => json<any[]>(`/api/coding/challenges/${id}/submissions`),
  explainCode: (payload: { code: string; explanation: string; question_id?: number; source_title: string }) => post<any>('/api/code/explain', payload),

  saveAnswer: (questionId: number, content: string) => post<any>(`/api/questions/${questionId}/answers`, { content }),
  answerVersions: (questionId: number) => json<any[]>(`/api/questions/${questionId}/answers`),
  importPreview: (format: 'json' | 'csv', content: string) => post<ImportPreview>('/api/questions/import/preview', { format, content }),
  importQuestions: (format: 'json' | 'csv', content: string) => post<any>('/api/questions/import', { format, content }),
  importHistory: () => json<any[]>('/api/questions/import/history'),

  createInterview: (payload: object) => post<InterviewSession>('/api/interviews', payload),
  interviewPersonas: () => json<InterviewerPersona[]>('/api/interviews/personas'),
  startInterviewModule: (sessionId: number, moduleIndex: number) => post<TimeStatus>(`/api/interviews/${sessionId}/modules/${moduleIndex}/start`, {}),
  interviewTimeStatus: (sessionId: number) => json<TimeStatus>(`/api/interviews/${sessionId}/time-status`),
  interviewTurn: (sessionId: number, payload: { question_id?: number; module_index?: number; interviewer_prompt: string; answer: string }) => post<any>(`/api/interviews/${sessionId}/turn`, payload),
  interviewTurns: (sessionId: number) => json<any[]>(`/api/interviews/${sessionId}/turns`),
  uploadRecording: async (sessionId: number, blob: Blob) => {
    const response = await fetch(`/api/interviews/${sessionId}/recording`, { method: 'POST', headers: headers({ headers: { 'Content-Type': blob.type || 'audio/webm' } }), body: blob })
    if (!response.ok) throw new Error(await response.text())
    return response.json()
  },
  saveRecordingTranscript: (sessionId: number, recordingId: number, transcript: string, duration_ms: number) => put<any>(`/api/interviews/${sessionId}/recordings/${recordingId}/transcript`, { transcript, duration_ms }),
  interviewRecordings: (sessionId: number) => json<any[]>(`/api/interviews/${sessionId}/recordings`),

  repos: () => json<Repository[]>('/api/repos'),
  syncRepo: (payload: { provider: GitProvider; repo: string; branch: string; is_private?: boolean }) => post<Repository>('/api/repos/sync', payload),
  gitProviders: () => json<GitProviderStatus[]>('/api/git/providers'),
  gitAuthorize: (provider: GitProvider) => post<GitAuthorizeResult>(`/api/git/${provider}/authorize`, {}),
  gitCallback: (payload: { code: string; state: string }) => post<GitConnectionResult>('/api/git/callback', payload),
  gitDisconnect: (provider: GitProvider) => del<{ provider: string; connected: boolean }>(`/api/git/${provider}`),
  gitProviderRepos: (provider: GitProvider, visibility: 'all' | 'public' | 'private' = 'all') => json<GitProviderRepoList>(`/api/git/${provider}/repos?visibility=${visibility}`),
  updateRepoVisibility: (repoId: number, isPublic: boolean) => patch<{ id: number; name: string; is_public: boolean }>(`/api/repos/${repoId}/visibility`, { is_public: isPublic }),
  repoFiles: (repoId: number, q = '') => json<RepoFile[]>(`/api/repos/${repoId}/files${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  repoFile: (repoId: number, fileId: number) => json<RepoFile>(`/api/repos/${repoId}/files/${fileId}`),
  repoArchitecture: (repoId: number) => json<any>(`/api/repos/${repoId}/architecture`),
  generateResume: (repoId: number, language: 'zh' | 'en', style: 'compact' | 'impact' | 'technical') => post<any>(`/api/repos/${repoId}/resume`, { language, style }),
  latestReport: () => json<any>('/api/reports/latest'),
  reportHistory: () => json<any[]>('/api/reports/history'),
  interviewReport: (sessionId: number) => json<any>(`/api/interviews/${sessionId}/report`),
  portfolio: (username: string) => json<PortfolioData>(`/api/portfolio/${encodeURIComponent(username)}`),
  portfolioCmsProfile: () => json<PortfolioProfileInfo>('/api/portfolio-cms/profile'),
  updatePortfolioProfile: (payload: PortfolioProfilePayload) => put<PortfolioProfileInfo>('/api/portfolio-cms/profile', payload),
  portfolioProjects: () => json<PortfolioProjectEntry[]>('/api/portfolio-cms/projects'),
  createPortfolioProject: (payload: PortfolioProjectPayload) => post<PortfolioProjectEntry>('/api/portfolio-cms/projects', payload),
  updatePortfolioProject: (id: number, payload: PortfolioProjectPayload) => put<PortfolioProjectEntry>(`/api/portfolio-cms/projects/${id}`, payload),
  deletePortfolioProject: (id: number) => del<{ deleted: number }>(`/api/portfolio-cms/projects/${id}`),
  reorderPortfolioProjects: (ids: number[]) => put<PortfolioProjectEntry[]>('/api/portfolio-cms/projects/order', { ids }),
  llmStatus: () => json<any>('/api/llm/status'),

  systemDesignCases: () => json<SystemDesignCase[]>('/api/system-design/cases'),
  evaluateSystemDesign: (caseId: string, content: string) => post<any>(`/api/system-design/${caseId}/evaluate`, { content }),
  getCanvas: (caseId: string) => json<SystemCanvas>(`/api/system-design/canvas/${encodeURIComponent(caseId)}`),
  saveCanvas: (payload: SystemCanvas) => put<SystemCanvas>('/api/system-design/canvas', payload),

  playgroundMeta: () => json<PlaygroundMeta>('/api/playground/meta'),
  createPlaygroundSession: (kind: 'sql' | 'redis') => post<PlaygroundSessionInfo>('/api/playground/sessions', { kind }),
  runPlaygroundSql: (sessionId: number, sql: string) => post<SqlPlaygroundResult>('/api/playground/sql', { session_id: sessionId, sql }),
  runPlaygroundRedis: (sessionId: number, command: string) => post<RedisPlaygroundResult>('/api/playground/redis', { session_id: sessionId, command }),
  runPlaygroundFastApi: (payload: { code: string; method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'; path: string; body?: string }) => post<FastApiPlaygroundResult>('/api/playground/fastapi', payload),
  resetPlayground: (sessionId: number) => post<PlaygroundResetResult>('/api/playground/reset', { session_id: sessionId }),
}

export async function streamInterviewTurn(
  sessionId: number,
  payload: { question_id?: number; module_index?: number; interviewer_prompt: string; answer: string },
  onEvent: (event: string, data: any) => void,
  retry = true,
) {
  const response = await fetch(`/api/interviews/${sessionId}/stream-turn`, {
    method: 'POST',
    headers: headers({ headers: { 'Content-Type': 'application/json' } }),
    body: JSON.stringify(payload),
  })
  if (response.status === 401 && retry && await tryRefresh()) return streamInterviewTurn(sessionId, payload, onEvent, false)
  if (!response.ok || !response.body) throw new Error(await response.text())
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''
    for (const frame of frames) {
      const eventLine = frame.split('\n').find((line) => line.startsWith('event:'))
      const dataLine = frame.split('\n').find((line) => line.startsWith('data:'))
      if (!dataLine) continue
      const event = eventLine?.slice(6).trim() || 'message'
      try { onEvent(event, JSON.parse(dataLine.slice(5).trim())) } catch { /* ignore malformed frame */ }
    }
  }
}
