export type NavKey = 'dashboard' | 'projects' | 'questions' | 'coding' | 'playgrounds' | 'interview' | 'reports' | 'learning' | 'knowledge' | 'import' | 'system' | 'portfolio'

export type Question = {
  id: number
  slug: string
  category: string
  title: string
  difficulty: number
  answer: string
  code: string
  followups: string
  project_link: string
  archived: number
  tags: string
  updated_at: string | null
}

export type QuestionDraft = {
  category: string
  title: string
  answer: string
  code: string
  followups: string
  difficulty: number
  project_link: string
  tags: string
}

export type QuestionDuplicate = {
  id: number
  title: string
  category: string
  similarity: number
}

export type ImportPreviewRow = {
  row: number
  title: string
  category: string
  status: 'create' | 'error'
  problems: string[]
  duplicates: QuestionDuplicate[]
}

export type ImportPreview = {
  total: number
  to_create: number
  to_skip: number
  rows: ImportPreviewRow[]
  truncated: boolean
}

export type Dashboard = {
  readiness: number
  question_total: number
  question_answered: number
  code_labs: number
  projects: number
  review_due: number
  streak: number
  coding_solved?: number
  coding_wrong?: number
}

export type Weakness = {
  topic: string
  score: number
  due_at: string
  interval_days: number
  due: boolean
  stability: number
  difficulty: number
  retrievability: number
  reps: number
  lapses: number
  last_review_at: string | null
}

export type ReviewLogEntry = {
  id: number
  grade: number
  source: string
  score: number
  stability: number
  difficulty: number
  retrievability: number
  elapsed_days: number
  scheduled_days: number
  reviewed_at: string
}

export type RepoDiff = {
  available: boolean
  changed: boolean
  from_commit: string
  to_commit: string
  shortstat: string
  files: { status: string; path: string }[]
  questions: string[]
  reason?: string
}

export type RepoSummary = {
  languages?: [string, number][]
  topics?: [string, number][]
  commit_message?: string
  diff?: RepoDiff
}

export type Repository = {
  id: number
  provider: 'github' | 'gitee'
  name: string
  url: string
  branch: string
  last_commit: string
  file_count: number
  summary: RepoSummary
  is_public?: boolean
  is_private?: boolean
  synced_at: string
}

export type GitProvider = 'github' | 'gitee'

export type GitProviderStatus = {
  provider: GitProvider
  configured: boolean
  connected: boolean
  login: string
  scopes: string
  connected_at: string | null
}

export type GitAuthorizeResult = {
  provider: string
  authorize_url: string
  state: string
  expires_in: number
}

export type GitConnectionResult = {
  provider: string
  connected: boolean
  login: string
  scopes: string
  connected_at: string
}

export type GitProviderRepo = {
  name: string
  private: boolean
  default_branch: string
  updated_at: string
  url: string
  description: string
}

export type GitProviderRepoList = {
  provider: string
  visibility: 'all' | 'public' | 'private'
  page: number
  per_page: number
  repos: GitProviderRepo[]
}

export type RepoFile = {
  id: number
  path: string
  language: string
  size: number
  knowledge: string[]
  symbols: string[]
  content?: string
  questions?: string[]
}

export type CodeSeed = {
  title: string
  code: string
  questionId?: number
  language?: string
}

export type InterviewScriptItem = {
  type: string
  minutes: number
  question_id?: number
  prompt: string
  followups?: string[]
}

export type InterviewSession = {
  id: number
  role: string
  difficulty: string
  duration: number
  persona?: string
  script: InterviewScriptItem[]
}

export type InterviewerPersona = {
  id: string
  label: string
  description: string
  emphasis: string
}

export type MemoryFinding = {
  kind: 'contradiction' | 'evasion' | 'unanswered' | 'avoided_concept' | 'reused_gap'
  detail: string
  turns?: number[]
}

export type MemoryReport = {
  findings: MemoryFinding[]
  summary: string
}

export type TimeModuleRow = {
  index: number
  type: string
  planned_minutes: number
  elapsed_minutes: number
  status: 'pending' | 'active' | 'done'
  over_budget: boolean
}

export type TimeReport = {
  plan_minutes: number
  elapsed_minutes: number
  current_module: number | null
  modules: TimeModuleRow[]
  advisory: string
}

export type TimeStatus = TimeReport & {
  session_id?: number
  persona?: string
}

export type SystemDesignCase = {
  id: string
  title: string
  requirements: string[]
  followups: string[]
  reference: string
}

export type CodingTest = {
  args: unknown[]
  kwargs?: Record<string, unknown>
  expected: unknown
}

export type CodingChallenge = {
  id: number
  slug: string
  title: string
  category: string
  difficulty: number
  description: string
  function_name: string
  starter_code: string
  public_tests: CodingTest[]
  hints: string
  tags: string[]
  solved?: boolean
  wrongbook?: boolean
}

export type WrongBookEntry = {
  id: number
  challenge_id: number
  title: string
  difficulty: number
  tags: string[]
  attempts: number
  last_error: string
  last_code: string
  last_attempt_at: string
}

export type ArchitectureNode = {
  id: string
  label: string
  subtitle?: string
  kind: string
  x: number
  y: number
}

export type ArchitectureEdge = {
  id: string
  source: string
  target: string
  label?: string
}

export type ArchitectureGraph = {
  nodes: ArchitectureNode[]
  edges: ArchitectureEdge[]
  symbols: { id: string; file: string; name: string; kind: string; line: number; calls: string[]; imports: string[] }[]
  topics: [string, number][]
  questions: string[]
  mermaid: string
}

export type InterviewReport = {
  session_id: number | null
  role?: string
  created_at?: string
  turns?: number
  persona?: string
  overall_score: number
  skill_scores: Record<string, number>
  strengths: string[]
  weaknesses: string[]
  review_plan: { day: number; topic: string; task: string }[]
  summary: string
  memory?: MemoryReport
  time?: TimeReport
}

export type PortfolioData = {
  slug: string
  name: string
  title: string
  summary: string
  skills: string[]
  projects: PortfolioProjectView[]
  repositories: { name: string; provider: string; url: string; commit: string; files: number }[]
  latest_interview_score?: number | null
  cms?: boolean
  resume_url?: string
  social?: Record<string, string>
}

export type PortfolioProjectView = {
  name: string
  subtitle: string
  pipeline?: string[]
  decision?: string
  description?: string
  architecture?: string
  decisions?: string
  tech_tags?: string[]
  link?: string
  repository?: { name: string; provider: string; url: string; commit: string; files: number } | null
}

export type PortfolioProfileInfo = {
  username: string
  display_name: string
  headline: string
  summary: string
  skills: string[]
  resume_url: string
  social_links: Record<string, string>
  is_published: boolean
}

export type PortfolioProjectEntry = {
  id: number
  title: string
  subtitle: string
  description: string
  architecture: string
  decisions: string
  tech_tags: string[]
  link: string
  repository_id: number | null
  repository: { name: string; provider: string; url: string; commit: string; files: number } | null
  is_visible: boolean
  order_index: number
}

export type PortfolioProfilePayload = {
  display_name: string
  headline: string
  summary: string
  skills: string[]
  resume_url: string
  social_links: Record<string, string>
  is_published: boolean
}

export type PortfolioProjectPayload = {
  title: string
  subtitle: string
  description: string
  architecture: string
  decisions: string
  tech_tags: string[]
  link: string
  repository_id: number | null
  is_visible: boolean
}

export type AuthUser = {
  id: number
  username: string
  email: string
  display_name: string
  created_at: string
}

export type AuthTokens = {
  access_token: string
  refresh_token: string
  token_type?: string
}

export type KnowledgeGraphNode = {
  id: string
  label: string
  kind: 'category' | 'question' | 'project' | 'repository' | 'topic' | string
  score?: number | null
  category?: string
  difficulty?: number
  provider?: string
}

export type KnowledgeGraphData = {
  nodes: KnowledgeGraphNode[]
  edges: { id: string; source: string; target: string; label?: string }[]
  stats: { questions: number; categories: number; repositories: number; weak_topics: number }
}

export type PrerequisiteNode = {
  slug: string
  label: string
  chain: string
  description: string
  position: number
  layer: number
  blocked: boolean
  weak_prereqs: string[]
}

export type PrerequisiteEdge = {
  from_slug: string
  to_slug: string
  cross_chain: boolean
}

export type PrerequisiteGraph = {
  nodes: PrerequisiteNode[]
  edges: PrerequisiteEdge[]
  chain_mastery: Record<string, {
    score: number | null
    retrievability: number | null
    due: boolean | null
    reps: number
    lapses: number
  }>
  threshold: number
}

export type PrerequisiteRecommendation = {
  chain: string
  score: number | null
  retrievability: number | null
  due: boolean
  blocked_count: number
  first_steps: string[]
  reason: string
}

export type SystemCanvas = {
  id?: number
  case_id: string
  title: string
  nodes: Record<string, unknown>[]
  edges: Record<string, unknown>[]
  updated_at?: string | null
}

export type SearchGroupType = 'question' | 'knowledge_node' | 'repo_file' | 'answer_version' | 'interview_turn'

export type SearchResultItem = {
  id: number | string
  title: string
  subtitle: string
  question_id?: number
  session_id?: number
  repo_id?: number
}

export type SearchGroup = {
  type: SearchGroupType
  label: string
  items: SearchResultItem[]
}

export type SearchResponse = {
  query: string
  groups: SearchGroup[]
  total: number
}

export type SearchFocus = {
  page: NavKey
  questionId?: number
  repoId?: number
  nodeSlug?: string
  sessionId?: number
}

export type PlaygroundKind = 'sql' | 'redis' | 'fastapi'

export type PlaygroundMeta = {
  kinds: PlaygroundKind[]
  limits: { sql_max_chars: number; redis_max_chars: number; fastapi_max_chars: number; session_ttl_hours: number }
  policy: Record<string, string>
  samples: Record<string, { title: string; code: string }>
}

export type PlaygroundSessionInfo = { session_id: number; kind: 'sql' | 'redis'; expires_in: number }

export type SqlStatementResult = {
  columns: string[]
  rows: unknown[][]
  rowcount: number
  truncated: boolean
  error: string
}

export type SqlPlaygroundResult = { ok: boolean; statements: SqlStatementResult[]; duration_ms: number; error: string }

export type RedisPlaygroundResult = {
  ok: boolean
  result: { type: string; value: unknown; truncated: boolean } | null
  duration_ms: number
  error: string
}

export type FastApiPlaygroundResult = {
  ok: boolean
  error: string
  status: number
  headers: Record<string, string>
  body: string
  stdout: string
  stderr: string
  duration_ms: number
}

export type PlaygroundResetResult = { session_id: number; kind: string; ok: boolean; reset_sql: boolean; reset_redis: boolean }
