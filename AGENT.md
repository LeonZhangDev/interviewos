# InterviewOS Agent Development Guide

> 本文件是 InterviewOS 的长期 Agent 接力开发规范。任何 coding agent 在修改项目之前，都必须先完整阅读本文件，再阅读 `README.md`、`CHANGELOG.md` 与相关源码。
>
> 当前基线：**InterviewOS v1.0（feature-complete）**（v0.8/v0.9 全部功能 + v1.0 P0 Git provider integrations + P1 Playgrounds + P2 Portfolio CMS + 前端测试体系（Vitest 30 + Playwright 3）+ CI/CD + Observability 已完成，后端 210 + 前端 33 个测试全绿）。不要把已有功能退化成 Demo、占位接口或纯静态页面。

---

## 1. 项目目标

InterviewOS 是一个面向 AI / Agent / RAG / Python / FastAPI / Backend 求职者的 **AI-native Technical Interview OS**。

它不是单纯题库，也不是单纯作品集。核心闭环是：

```text
项目代码 / GitHub / Gitee
        ↓
Project Intelligence
        ↓
知识点 / 架构 / 项目面试题
        ↓
题库 + Coding + System Design
        ↓
AI / Voice Mock Interview
        ↓
评分 / 报告 / 答案版本
        ↓
Weakness Map / Knowledge Graph
        ↓
Spaced Review
        ↓
下一轮面试
```

产品最终需要同时满足两种使用场景：

1. **Learner Mode**：本人长期准备面试、刷题、写代码、复习、模拟面试。
2. **Interviewer / Portfolio Mode**：面试官可以快速了解项目、架构、代码、技术决策和工程能力，但不能看到个人错题、薄弱点等隐私学习数据。

---

## 2. 当前真实完成状态（v1.0）

Agent 必须以源码为准，不要因为 Roadmap 中存在同名功能就重复重写。

### 已实现

#### Frontend

- React 18 + TypeScript + Vite
- Monaco Editor
- React Flow
- Dashboard
- Question Bank
- Learning / Weakness（FSRS 保持率/稳定性/难度 + 复习历史面板）
- Coding Interview
- AI Interview（**v0.9**：面试官风格选择器 7 种 persona、时长预设 30/45/60、实时时间控制器面板（已用/计划分钟、分模块 chip active/done/over-budget、切换/收尾 advisory，进入模块/提交回答/30s 轮询刷新）、turn 提交携带 module_index）
- Project Intelligence（**v1.0**：Git provider OAuth 面板——per-provider configured/connected 徽标、"绑定授权"跳转 provider、"选择仓库同步"仓库选择器（全部/公开/私有过滤、私有徽标、一键同步自动填 provider/branch/is_private）、"断开"解除绑定；手动同步表单新增"私有仓库"复选框；仓库列表显示 `· 私有` 标记）
- OAuthCallbackPage（**v1.0**：`/oauth/callback` 路径路由，读取 code/state（或 provider error），调用后端完成授权交换，成功后自动返回项目页）
- Knowledge Graph（关系图 + 前置依赖图视图：分层布局、弱链高亮、被阻塞节点、解锁建议面板）
- System Design Arena
- Interview Reports（**v0.9**：persona 徽标、面试官记忆发现面板（中文 kind 标签 + LLM 摘要）、时间执行复盘（分模块 planned-vs-actual 条形图 + advisory））
- Playgrounds（**v1.0**：SQL/Redis/FastAPI 三标签页——Monaco 多语句 SQL + 分语句结果表、Redis 单命令行 + 类型化结果 pill + 最近 50 条历史、FastAPI method/path/body 请求构造器 + status/headers/body/stdout/stderr 响应面板；会话惰性创建、过期自动重建提示、清空重置/新会话）
- Portfolio（**v1.0 P2 CMS 编辑器**：profile 表单（名称/头衔/简介/技能/简历链接/可增删社交链接行）、已保存 profile 的一键发布/下线（不发布未保存草稿）、项目列表（↑↓ 排序、公开/隐藏切换、编辑、删除、仓库绑定徽标——私有仓库标注"私有"）、新建/编辑 modal（描述/架构/工程决策/技术标签/链接/仓库绑定下拉）、公开页 `/portfolio/{username}` 发布后渲染 CMS 内容（tech tags、描述、可折叠架构说明、工程决策块、简历与社交链接 chip），未发布保持 legacy 渲染）
- Register / Login
- Question Import
- 静默 access token 刷新（refresh 自动续期，单飞并发去重）
- Logout / 全设备登出 / 修改密码 UI
- 仓库 public/private 可见性开关
- **Unified search topbar**：真实 API 搜索框（防抖 250ms、⌘K/Ctrl+K 聚焦、分组下拉、空态/短查询提示、Enter 跳第一个结果），结果点击跳转到对应页面并定位（题目/我的答案 → 题库选中该题；知识点 → 前置依赖图选中该节点；仓库文件 → 项目页选中该仓库；面试轮次 → 报告页加载该 session）
- **前端测试体系**（v1.0）：Vitest + @testing-library/react + jsdom（`vitest.config.ts`，`src/test/setup.ts` 每个测试后自动清理 DOM 与 localStorage），30 个单元/组件测试——`api.ts` token 存取、Authorization 头、401 静默刷新单飞去重（并发共享一次 refresh、重试携带新 token、失败派发 `interviewos:unauthorized` 并清空、无 refresh token 直接跳过、auth 端点永不刷新）、SSE 流解析、AuthPage 表单校验/注册 payload/错误提示、PortfolioPage 编辑器保存/发布/项目 CRUD/排序/可见性、PublicPortfolioPage legacy/CMS/404 渲染；Playwright E2E 3 条（`e2e/`，webServer 自动 `docker compose up -d --build --wait backend` + 本地 vite 代理）：注册→工作台可见、登出后工作台不可访问 + 重新登录恢复、公开 portfolio 未发布 legacy → 发布后 CMS 内容（匿名上下文验证），随机后缀用户名保证可重复运行

#### Backend

- FastAPI
- SQLAlchemy async
- PostgreSQL
- Redis
- JWT access token + refresh token（rotation，哈希存储）
- PBKDF2-SHA256 password hashing
- 用户级 token 撤销水位 `users.tokens_valid_after`
- logout / all-devices logout / change password（立即撤销旧 token）
- **Tenant isolation**：AnswerVersion / Mastery / InterviewSession / InterviewTurn / InterviewReport / CodeExplanationAttempt / CodingSubmission / CodingWrongEntry / Repository 全部带 `user_id` ownership，私有查询按当前用户过滤，跨用户访问返回 404
- **Alembic**：baseline (0001) + ownership backfill (0002) + auth lifecycle (0003) + FSRS (0004) + prerequisites (0005) + question CMS (0006) + advanced interview (0007) + git providers (0008) + playgrounds (0009) + portfolio CMS (0010)，Dockerfile 启动时 `alembic upgrade head`
- Question / Answer Version / Mastery
- **FSRS-4.5 spaced repetition**：`app/fsrs.py` 调度器（stability/difficulty 记忆状态、遗忘曲线保持率、90% 目标保持率、5 级评分含遗忘后回落），`review_logs` 表记录每次复习（manual/answer/interview/code 来源），per-topic review history API（用户隔离）
- **Knowledge prerequisite graph**：`knowledge_nodes` / `prerequisite_edges` 共享图谱（8 链 / 43 知识点 / 37 条边，含 3 条跨链边，启动幂等 seed），`/api/knowledge/prerequisites` 分层无环图 + 用户链掌握度 + 被阻塞节点，`/api/knowledge/prerequisites/recommendations` 可解释解锁建议（按阻塞下游数量排序，user 作用域）
- **Unified search**：`GET /api/search?q=&per_group=` 跨 5 类实体分组搜索（面试题/知识点共享 + 仓库文件/我的答案/面试轮次按 user 作用域），lower() LIKE 子串匹配而非 tsvector（内容以中文为主、离线测试跑 SQLite），查询中的连字符转 `_` 单字符通配使 `xenon-marker` 同时命中 `xenon_marker.py`；非流式 turn 端点补上 `user_id` 写入（与流式端点一致）
- **Question CMS**：`questions` 表新增 `archived`（索引软删除）/`tags`/`created_by`（可空 FK，`ON DELETE SET NULL`）/`updated_at`（迁移 0006）；题目保持全局共享、记录创建者。认证 CRUD（POST / PATCH / GET / archive / restore），`app/question_cms.py` 提供归一化标题 + difflib 相似度重复检测（≥0.9 返回 409 + 相似题清单，`?force=true` 覆盖；≥0.75 在导入预览中提示），`POST /api/questions/bulk-tag` 批量 append/set/remove 标签（≤500 题），`POST /api/questions/import/preview` 导入预览不落库；归档题从默认列表 / unified search / 面试脚本生成中排除；前端题库页管理模式（新建/编辑表单、重复冲突面板、归档视图、多选批量标签）
- **Interviewer personas**（v0.9）：`app/personas.py` 定义 7 种面试官风格（normal/friendly/pressure/backend_lead/agent_lead/algorithm/hr），只改 intro/wrap prompt、追问风格、fallback followups 与评分 emphasis 提示，**绝不改参考答案与评分基线**（测试锁定该约束）；`InterviewSession.persona`（迁移 0007），`GET /api/interviews/personas` 目录，`POST /api/interviews` 接受 persona
- **Interview memory**（v0.9）：`app/interview_memory.py` 确定性跨轮次检测——前后矛盾（同概念不同轮次立场相反，忽略同轮对比）、回避、未回答、反复回避概念、重复使用已暴露缺口；发现注入实时 judge/followup prompt（"面试官记忆"上下文，离线模式附加到 feedback），报告持久化 `memory_findings`（findings + LLM/确定性摘要）
- **Interview time controller**（v0.9）：`app/interview_time.py` 纯函数模块预算（30/45/60 精确计划，其他时长通用分配）+ `InterviewSession.module_starts` 记录进入模块时刻（思考时间计入）+ `compute_time_status` 派生分模块 elapsed vs planned、超预算标记（1.5 分钟宽限）与收尾 advisory（6 分钟保留）；`InterviewTurn.module_index`，`POST /api/interviews/{id}/modules/{index}/start` 与 `GET /api/interviews/{id}/time-status`（均 user 作用域，未知模块 404），报告持久化 `time_execution`
- Interview Session / Turn / Report
- Coding Challenge / Submission / Wrong Book
- Repository sync / source browsing
- **Git provider OAuth**（v1.0）：`app/git_oauth.py` GitHub/Gitee authorization-code 流（authorize URL / token 交换 / profile / 分页仓库列表，统一 httpx 客户端 + 脱敏错误信息），`app/git_routes.py` 五个 user 作用域端点——`GET /api/git/providers`（configured/connected 状态）、`POST /api/git/{provider}/authorize`（单用途 CSRF state，10 分钟过期，回调时原子消费）、`POST /api/git/callback`（code/state 交换，upsert 连接）、`DELETE /api/git/{provider}`（断开即删除 token 行）、`GET /api/git/{provider}/repos`（token 作用域仓库列表，全部/公开/私有过滤，不落库）
- **加密 token 存储**（v1.0）：`git_connections` 表存 GitHub/Gitee access token，stdlib-only 加密（per-record salt → 域分离 HMAC-SHA256 子密钥、HMAC-CTR keystream、encrypt-then-MAC 16 字节 tag，无新加密依赖），密钥 `OAUTH_ENCRYPTION_KEY`（回退 `AUTH_SECRET`）；token 任何 API 不返回、不写日志，密钥轮换表现为明确的"断开后重新授权"400
- **私有仓库同步**（v1.0）：`clone_and_scan` 接受 access token 构造认证 clone URL（GitHub `x-access-token`，Gitee `oauth2`），sync 端点自动附加已存连接 token，`redact_secrets` 脱敏 git 错误输出防 token 泄露；`Repository.is_private` 记录 provider 端可见性（迁移 0008），portfolio 展示仍由 `is_public` 单独控制
- **Playgrounds**（v1.0）：`app/playground.py`（backend 侧拦截 + 会话管理）与 `runner/main.py`（沙箱执行）共享同一 `SQL_DENY_RE` / `REDIS_DENY_COMMANDS` 黑名单（parity 测试锁定），`app/playground_routes.py` 暴露 meta/sessions/sql/redis/fastapi/reset 六个端点；SQL 每会话独立 schema + 5s statement timeout + 结果集上限，Redis 每会话独立逻辑库（blake2b 哈希 + 线性探测），FastAPI 无状态经 `httpx.ASGITransport` 单线程跑一次请求；专用 `sandbox-db` / `sandbox-redis` 仅 internal 网络可达
- **Portfolio CMS**（v1.0 P2，`app/portfolio_routes.py`）：`PortfolioProfile`（display_name/headline/summary/skills/resume_url/social_links/is_published，per-user 唯一）与 `PortfolioProject`（title/subtitle/description/architecture/decisions/tech_tags/link/order_index/is_visible/repository FK，上限 30 条/人，迁移 0010）；`/api/portfolio-cms/*` 全部认证 + user 作用域（foreign id 404、reorder payload 必须精确覆盖本人项目）；`GET /api/portfolio/{username}` 未发布时保持 legacy 静态形状（隐私测试锁定），发布后返回 CMS 内容——项目按 order_index 排序、仅 is_visible、绑定仓库仅在仓库本身 is_public 时在公开视图显示名称/URL（私有仓库对编辑器可见但不对外泄露）
- **Observability**（v1.0，`app/observability.py`）：结构化 JSON 日志（一行一对象，`LOG_FORMAT=text` 本地可读模式），`RequestContextMiddleware` 生成/透传 `X-Request-ID`（含 401 响应）+ 每请求一条访问日志（method/path/route 模板/status/duration/user）+ Prometheus 指标（`interviewos_http_requests_total` / `interviewos_http_request_duration_seconds`，route 模板标签控制基数，`/health`、`/ready`、`/metrics` 不计）；`GET /ready` DB+cache 连通性探针（只返回布尔 checks，不泄露内部细节，503/200）；`audit()` 敏感操作审计（auth 注册/登录/失败登录/登出双路径/改密、git 授权/连接/断开、repo 同步、playground 会话创建——只记元数据，token/密码/secret 永不入日志，测试锁定）；`init_error_tracking()` 可选 Sentry（`SENTRY_DSN` 空为 no-op，SDK 缺失仅警告不阻断启动）；观测失败绝不破坏请求，初始化失败应用照常启动（offline mode 保持）
- **CI pipeline**（v1.0，`.github/workflows/ci.yml`）：push/PR 并行跑 backend（uv sync --frozen → compileall → 离线 pytest）与 frontend（npm ci → tsc → vitest → build），之后 docker lane（compose config 校验 + 全镜像构建）；夜间（北京时间 02:00）+ 手动 dispatch 的 E2E lane 跑 Playwright（复用 `make frontend-e2e` 的 webServer 流程）；uv/npm 缓存、concurrency 取消旧 run、只读权限。⚠️ 仓库当前无 `.git`/remote，workflow 从未在托管平台执行过（首次 push 后运行）
- Python AST analysis
- Repository architecture graph data
- Commit diff -> interview questions
- Repository evidence -> resume description
- System Design canvas persistence
- Interview audio / transcript metadata
- JSON / CSV question import（预览确认后落库）
- OpenAI-compatible LLM adapter with offline fallback
- SSE interview follow-up
- Dashboard Redis cache（per-user key）
- pytest 测试套件（auth lifecycle / tenant isolation / migration parity / hidden-test privacy / portfolio privacy / FSRS scheduler + backfill / prerequisite graph / unified search / question CMS / advanced interview（personas / memory / time）/ **git OAuth（token 加解密往返与防篡改、state 生命周期、callback 校验、跨用户隔离、token 传递与脱敏）** / **Playgrounds（双端 deny 黑名单 parity、SQL/Redis 会话隔离、FastAPI 沙箱请求）** / **Portfolio CMS（profile 生命周期、项目 CRUD/排序校验、公开视图可见性过滤、仓库绑定所有权、跨用户隔离、legacy 形状保持）** / **Observability（request_id 生成/透传、结构化访问日志、凭据不入日志、/ready 降级与健康态与脱敏、/metrics 计数与 route 模板标签、audit 内容断言、Sentry no-op/缺 SDK 路径、JSON formatter）** / offline smoke，210 个测试）
- **uv** 依赖管理（`backend/pyproject.toml` + `uv.lock`，`uv sync` / `uv run pytest`；Docker 镜像用 `uv sync --frozen` 构建）
- 根目录 **Makefile** 封装常用命令（`make verify` / `make backend-test` / `make migrate` / `make docker-up` 等）
- **Docker e2e 已验证**（Docker Desktop 4.71 / WSL2）：`docker compose up --build` 全栈启动（PostgreSQL 18 / Redis 8 / Runner / backend / Vite），迁移 0001→0010 在 PG 真实执行（0006-0010 均在已持有旧版本的卷上增量验证），smoke 覆盖 auth / 题库 / 前置图 / 统一搜索 / FSRS + review_logs / Question CMS（创建含 tags/updated_at、归档后列表与搜索排除、批量标签、重复创建 409）/ v0.9 Advanced Interview（7 persona 目录、pressure persona 创建 + 45 分钟模块预算 3/6/6、模块 start 生命周期、跨轮矛盾记忆检测 + 报告 memory/time 分节、time-status 跨用户 404）/ v1.0 Git providers（`e2e_git_smoke.ps1`：providers 状态 + OAuth state 生命周期 + 断开，伪造凭据不打真实 provider）/ v1.0 Playgrounds（`scripts/e2e_playgrounds.ps1` 30 项全绿：SQL/Redis/FastAPI 场景、会话隔离、危险语句拦截）/ v1.0 P2 Portfolio CMS（`scripts/e2e_portfolio_cms.ps1` 39 项全绿：auth 守卫、未发布 legacy 形状、发布切换、项目 CRUD/排序/可见性、仓库绑定、跨用户 404、下线恢复 legacy）/ 前端 Playwright E2E（3 条核心流程：注册→工作台、登出守卫 + 重新登录、发布→公开 CMS portfolio，webServer 拉起同一 docker 栈 + 本地 vite）/ Runner 可见与隐藏判定（hidden 隐私保持）/ dashboard 缓存 / 离线 AI / Vite 代理；backend 服务带 `/health` healthcheck，`docker compose up --wait` 可确定性等待就绪

#### Runner

- Independent FastAPI Runner service
- User Python code is NOT executed in the main backend process
- Visible tests
- Hidden tests
- Execution timeout
- PID / CPU / file size / FD limits
- Docker memory boundary

### Important incomplete areas

- 没有密码重置邮件 / MFA / 邮箱验证（v1.0 的 OAuth 仅用于 Git provider 仓库授权，不是身份登录方式）。
- System Design whiteboard 还没有 deep AI graph-aware critique。
- Voice transcription 依赖浏览器 SpeechRecognition，没有服务端 Whisper pipeline。
- Git provider 的 webhook / scheduled sync 与 commit diff 通知未实现（当前私有仓库同步仍由用户手动触发）。
- OAuth token 无自动刷新/过期轮换：token 失效后需断开重连（同步失败时会返回明确错误）。
- Playgrounds 沙箱已交付（SQL/Redis/FastAPI），但拦截规则是黑名单式的：`SQL_DENY_RE` / `REDIS_DENY_COMMANDS` 由人工维护，新的绕过手法（如未列入黑名单的 Postgres 管理函数）需要双端同步修补；Redis 逻辑库数量（64）也限制了并发会话上限。SQL schema GC 是每 25 次请求机会式的，不是定时任务。
- Question Bank 的 CMS workflow 已完成（create/edit/archive/bulk tag/重复检测/导入预览），但内容集仍偏小，需要更大的高质量题目内容。
- 已有 pytest 后端测试套件（210）与前端测试体系（Vitest 30 + Playwright 3），且 CI workflow（`.github/workflows/ci.yml`）与 observability 栈已交付；但 workflow 尚未在任何托管平台执行过（仓库无 `.git`/remote，首次 push 后才会有第一笔 run），Playwright 浏览器二进制在 CI 首次仍需 `npx playwright install chromium`。metrics 为进程级（单实例 uvicorn 可用，多副本部署需要 Prometheus 抓取聚合，未做）；日志输出到 stdout，没有集中式收集/留存管道；审计日志为应用级日志流，非防篡改合规存储。

---

## 3. Repository structure

```text
interviewos/
├── backend/
│   ├── Dockerfile          # uv-based build; runs alembic upgrade head on boot
│   ├── pyproject.toml      # uv-managed dependencies (runtime + dev groups)
│   ├── uv.lock             # committed lockfile; Docker builds with --frozen
│   ├── .python-version     # 3.12, matching the Docker base image
│   ├── alembic.ini
│   ├── alembic/
│   │   └── versions/
│   │       ├── 0001_v07_baseline.py
│   │       ├── 0002_v08_ownership.py
│   │       ├── 0003_v08_auth_lifecycle.py
│   │       ├── 0004_v08_fsrs.py
│   │       ├── 0005_v08_prerequisites.py
│   │       ├── 0006_v08_question_cms.py
│   │       ├── 0007_v09_advanced_interview.py
│   │       ├── 0008_v10_git_providers.py
│   │       ├── 0009_v10_p1_playgrounds.py
│   │       └── 0010_v10_p2_portfolio_cms.py
│   ├── tests/
│   │   ├── conftest.py          # temp DB migrated to head per session
│   │   ├── test_auth_lifecycle.py
│   │   ├── test_tenant_isolation.py
│   │   ├── test_fsrs.py         # scheduler properties + backfill + API + isolation
│   │   ├── test_prerequisites.py # graph acyclicity + blocked state + user-scoped recs
│   │   ├── test_search.py       # unified search: cross-entity hits + tenant isolation
│   │   ├── test_question_cms.py # CMS CRUD + duplicate detection + bulk tags + import
│   │   ├── test_advanced_interview.py # personas + memory detection + time controller
│   │   ├── test_git_oauth.py    # token crypto + state lifecycle + callback + isolation
│   │   ├── test_playgrounds.py  # deny-list parity + session isolation + sandbox APIs
│   │   ├── test_portfolio_cms.py # profile/project CRUD + public exposure + isolation
│   │   ├── test_migrations.py   # model vs migration parity
│   │   ├── test_privacy_portfolio.py
│   │   ├── test_offline_workflows.py
│   │   └── test_observability.py # request_id / access logs / ready / metrics / audit / sentry hook
│   └── app/
│       ├── main.py          # existing main APIs / application boot
│       ├── v07.py           # auth/graph/whiteboard/import/recording routes
│       ├── deps.py          # current_user dependency (token watermark check)
│       ├── models.py        # SQLAlchemy models (user_id ownership)
│       ├── schemas.py       # Pydantic schemas
│       ├── db.py
│       ├── config.py
│       ├── auth.py          # access/refresh token issue, hash, verify, rotate
│       ├── fsrs.py          # FSRS-4.5 scheduler (stability/difficulty/retrievability)
│       ├── knowledge_seed.py # shared prerequisite-graph seed data (chains + edges)
│       ├── question_cms.py  # title normalization + difflib duplicate detection + slug helpers
│       ├── personas.py      # v0.9 interviewer personas + time plans (styles only, facts unchanged)
│       ├── interview_memory.py # v0.9 deterministic cross-turn contradiction/evasion/gap detection
│       ├── interview_time.py   # v0.9 module budgets + elapsed/over-budget/advisory computation
│       ├── git_oauth.py     # v1.0 GitHub/Gitee authorization-code flow + profile/repos listing
│       ├── git_routes.py    # v1.0 git provider endpoints (providers/authorize/callback/delete/repos)
│       ├── playground.py    # v1.0 backend-side deny interception + sandbox session management
│       ├── playground_routes.py # v1.0 playground meta/sessions/sql/redis/fastapi/reset
│       ├── portfolio_routes.py # v1.0 P2 portfolio CMS routes + public portfolio view
│       ├── observability.py  # v1.0 JSON logs + request_id middleware + metrics + audit + optional Sentry
│       ├── llm.py           # OpenAI-compatible / vLLM / DeepSeek-compatible adapter
│       ├── ai.py
│       ├── scoring.py
│       ├── repo_sync.py
│       ├── code_intel.py
│       └── seed.py

├── frontend/
│   ├── package.json
│   ├── vitest.config.ts     # unit/component test env (jsdom + setup file)
│   ├── playwright.config.ts # e2e webServer: docker compose backend + local vite
│   ├── e2e/                 # Playwright specs (auth guard / portfolio publish)
│   └── src/
│       ├── App.tsx
│       ├── api.ts           # auth token storage + silent refresh
│       ├── types.ts
│       ├── styles.css
│       ├── __tests__/       # Vitest unit/component tests (api / stream / pages)
│       ├── test/            # setup.ts: per-test DOM + localStorage cleanup
│       ├── components/
│       └── pages/

├── runner/
│   ├── main.py
│   └── Dockerfile

├── examples/
├── .github/workflows/ci.yml # v1.0 CI: backend / frontend / docker / nightly e2e lanes
├── docker-compose.yml
├── .env.example
├── Makefile               # make verify / backend-test / migrate / docker-up …
├── README.md
├── CHANGELOG.md
├── VERSION
├── AGENT.md
└── AGENT_PROMPT.md
```

---

## 4. Architecture boundaries — DO NOT BREAK

这些是硬约束，不是建议。

### 4.1 Untrusted code boundary

**禁止**在主 Backend 中执行用户代码：

```python
exec(user_code)  # 禁止
```

用户代码必须经过独立 Runner / Sandbox。

公共互联网部署时，当前 Runner 仍应进一步升级到 gVisor / Firecracker / Kubernetes sandbox worker 等更强隔离方案。

### 4.2 Repository boundary

GitHub / Gitee 同步的仓库只做：

- clone / fetch
- read
- AST/static analysis
- diff

**禁止自动执行同步下来的仓库源码、setup.py、shell script、tests 或 install hooks。**

### 4.3 Hidden tests

Hidden tests 必须只返回：

- passed count
- total count
- aggregate result

不能把隐藏输入、expected output 或完整 test body 返回前端。

### 4.4 LLM boundary

LLM 是：

- interviewer
- evaluator assistant
- explanation generator
- question generator

LLM 不是事实数据库，也不能伪造项目成果。

生成简历或项目说明时禁止虚构：

- QPS
- latency
- accuracy
- users
- revenue
- team size
- performance improvement
- benchmark numbers

除非这些数据能从用户明确提供的信息或项目证据中得到。

### 4.5 Authentication boundary

所有个人工作台数据 API 应要求认证。

公开 Portfolio 路由可以匿名访问，但绝不能泄露：

- wrong book
- mastery weakness
- private answers
- recordings
- private repository data
- auth data

### 4.6 Database sessions

继续使用 **request-scoped AsyncSession**。

不要把一个 SQLAlchemy Session / AsyncSession 保存成跨请求的全局共享对象。

---

## 5. Engineering rules for Agent

### 5.1 Modify, do not rewrite

优先增量修改现有架构。

不要因为某个模块代码长就把整个系统重新生成一遍。尤其不要删除已有：

- Monaco
- Judge
- Hidden tests
- Repo sync
- AST analysis
- Answer history
- Mastery
- Knowledge graph
- Voice interview
- System Design canvas
- Portfolio

### 5.2 No fake completion

禁止：

- 建一个空页面就说“功能完成”
- 建一个返回 hard-coded JSON 的 API 就说“AI 功能完成”
- 未执行测试却声称“测试通过”
- 留 `TODO` / `pass` / placeholder 后声称阶段已完成

必须明确区分：

- implemented
- partially implemented
- scaffold only
- not implemented
- not tested because environment unavailable

### 5.3 Keep offline mode usable

没有 LLM key 时，InterviewOS 仍应可以：

- 浏览题库
- 运行 Coding Judge
- 查看项目
- 使用 deterministic follow-up / scoring fallback
- 使用学习与复习系统

不要让 LLM provider 成为整个应用启动的硬依赖。

### 5.4 Frontend quality

新增页面应遵守当前 React/Vite 结构：

- 小组件拆分
- `App.tsx` 不要膨胀成所有逻辑的单文件
- API 调用集中在 `api.ts` 或 feature API module
- 类型放在 `types.ts` 或 feature-local type file
- 不要添加 inert buttons
- 关键交互必须更新真实状态
- 保持桌面面试工作台优先，同时避免明显移动端溢出

### 5.5 Backend quality

新增 API：

- 使用 Pydantic schema
- 参数校验明确
- 异常使用合理 HTTP status
- DB write 使用事务边界
- 用户数据查询必须带 tenant/user filter
- 不要将 secret/token 打进日志

### 5.6 Security-first defaults

任何涉及以下能力的功能必须先设计边界：

- code execution
- file upload
- repository clone
- OAuth token
- private repository
- recording
- public portfolio
- webhook

---

## 6. Next roadmap

## v0.8 — Multi-user + Learning Engine

状态：**v0.8 全部完成**——P0（tenant ownership + Alembic + auth lifecycle + isolation tests）、P1（FSRS spaced repetition、knowledge prerequisite graph、unified search）与 P2（Question CMS）均已在 v0.8.0 交付（76 个测试）。v0.9 Advanced Interview 核心三项、v1.0 P0 Git provider integrations、v1.0 P1 Playgrounds、v1.0 P2 Portfolio CMS、v1.0 Tests（前端 Vitest/Playwright）与 v1.0 CI/CD + Observability 也已随后完成——**v1.0 已 feature-complete**（当前后端 210 + 前端 33 个测试）。

### P0 — Full user ownership migration（✅ v0.8.0 已完成）

给以下用户私有数据增加真正的 `user_id` ownership：

- AnswerVersion
- Mastery
- InterviewSession
- InterviewTurn
- InterviewReport
- CodeExplanationAttempt
- Repository（至少 private/user-owned repo）
- CodingSubmission
- CodingWrongEntry
- review queue / review history（若拆表）

要求：

- User A 不能读取/修改 User B 私有数据。
- seed/public question bank 可以继续共享。
- public Portfolio 必须显式选择可公开项目。

同时引入 **Alembic**，不要再依赖“启动时隐式建表”作为长期迁移方案。

### P0 — Auth lifecycle（✅ v0.8.0 已完成）

实现：

- access token
- refresh token
- refresh rotation
- logout / token revocation strategy
- change password

可暂不实现邮件密码重置，但 schema 需为后续扩展留空间。

### P1 — FSRS spaced repetition（✅ v0.8.0 已完成）

把固定 1/3/7/14 天升级为 FSRS-like review scheduling。

调度输入至少考虑：

- manual grade
- AI score
- previous stability/difficulty
- elapsed days
- failures
- hints used（如果可获得）

UI 显示：

- due date
- overdue
- stability / difficulty（可用友好文案包装）
- review history

### P1 — Knowledge prerequisite graph（✅ v0.8.0 已完成）

增加技术依赖关系，例如：

```text
Coroutine
  ↓
Task
  ↓
Event Loop
  ↓
Race Condition
  ↓
Lock
  ↓
Semaphore
```

Weakness recommendation 不只看某题得分，而应给出：

> “先补 Race Condition，再复习 Lock。”

### P1 — Unified search（✅ v0.8.0 已完成）

至少支持跨：

- questions
- repository files/symbols
- answer history
- interview turns
- knowledge nodes

第一版可 PostgreSQL FTS；语义搜索作为后续升级，不要为了 Vector DB 过度设计。

> 实现说明：第一版用 lower() LIKE 子串匹配而非 PostgreSQL FTS——种子内容以中文为主（英文 FTS 分词器无法命中），且离线测试套件跑在 SQLite（无 tsvector）；查询中的连字符转 `_` 单字符通配以兼容代码标识符。语义搜索 / pg_trgm / FTS 升级留到后续版本。

### P2 — Question CMS（✅ v0.8.0 已完成）

实现：

- create
- edit
- archive/delete
- bulk tag
- difficulty
- source
- duplicate detection
- import review

> 实现说明：`questions` 保持全局共享内容（最小变更，所有权单独记录），新增 `archived`（索引软删除）/`tags`/`created_by`（可空 FK）/`updated_at` 列（迁移 0006）。认证 CRUD + archive/restore；`app/question_cms.py` 归一化标题 difflib 相似度重复检测（≥0.9 阻断返回 409 + 相似题清单、`?force=true` 覆盖、≥0.75 导入预览预警）；bulk-tag 支持 append/set/remove（≤500 题）；import 先 `POST /api/questions/import/preview` 预览后确认落库；归档题从默认列表 / unified search / 面试脚本生成中排除。

---

## v0.9 — Advanced Interview

状态：**核心三项已完成**（interview memory / interviewer personas / interview time controller，0.9.0 交付，95 个测试通过）。Server-side ASR、voice delivery analytics、AI System Design Review 为可选增强项，优先级低于 v1.0。

### Interview memory（✅ v0.9.0 已完成）

Agent 应利用当前 session 的历史回答，发现：

- 前后矛盾
- 未回答问题
- 回避关键点
- 之前答错但后面重复使用的概念

> 实现说明：`app/interview_memory.py` 确定性检测五类发现（contradiction / evasion / unanswered / avoided_concept / reused_gap），矛盾检测只看跨轮次同概念立场反转（同轮对比忽略）；发现作为"面试官记忆"上下文注入实时 judge 与 followup prompt，报告持久化 findings + LLM（或确定性）摘要。

### Interviewer personas（✅ v0.9.0 已完成）

- normal
- friendly
- pressure
- backend lead
- AI/Agent lead
- algorithm interviewer
- HR / behavioral

Persona 只改变提问方式和评分 emphasis，不应改变事实标准。

> 实现说明：`app/personas.py` 七种风格，`test_persona_keeps_factual_scoring_standard` 锁定"同一回答在任意 persona 下基线评分一致"的约束；persona 影响 intro/wrap prompt、追问风格、fallback followups 与 judge emphasis 提示。

### Interview time controller（✅ v0.9.0 已完成）

支持 30 / 45 / 60 分钟 interview plan，并根据实际耗时主动切换模块。

> 实现说明：`TIME_PLANS` 30/45/60 精确分配（其他时长通用公式），`module_starts` 记录进入模块时刻（思考时间计入），`compute_time_status` 输出分模块 elapsed/planned、超预算标记（1.5 分钟宽限）与收尾 advisory（剩余 ≤6 分钟提示进入 wrap）；前端实时面板 + 报告时间执行复盘。

### Server-side ASR

实现可选：

- faster-whisper
- OpenAI-compatible transcription provider

浏览器 SpeechRecognition 保留为低成本模式。

### Voice delivery analytics

谨慎增加：

- speaking duration
- answer duration
- pause distribution
- filler word frequency

这些指标只能作为表达反馈，不能伪装成科学的人格/能力诊断。

### AI System Design Review

把白板 nodes/edges 作为结构化输入：

```text
canvas graph + written answer
        ↓
architecture analyzer
        ↓
missing components / bottlenecks / security boundaries
        ↓
follow-up questions
```

---

## v1.0 — Portfolio-ready Production Baseline

### Git provider integrations（✅ v1.0.0 已完成：GitHub OAuth、Gitee OAuth、private repositories、encrypted token storage、explicit repo permissions）

- ~~GitHub OAuth~~（✅ authorization-code 流，`read:user repo` scope）
- ~~Gitee OAuth~~（✅ authorization-code 流，`user_info projects` scope）
- ~~private repositories~~（✅ token 认证 clone + 错误脱敏 + `is_private` 元数据）
- ~~encrypted token storage~~（✅ stdlib HMAC-CTR + EtM，`OAUTH_ENCRYPTION_KEY`/`AUTH_SECRET`）
- ~~explicit repo permissions~~（✅ 仓库列表不落库，仅用户点击同步的仓库入库）
- webhook / scheduled sync（未实现，见 incomplete areas）
- commit diff notifications（未实现）

### Playgrounds（✅ v1.0.0 已完成：SQL/Redis/FastAPI 沙箱、会话级隔离、危险语句双端拦截、一键重置）

- ~~SQL PostgreSQL playground~~（✅ 每会话独立 schema + search_path，5s statement timeout，结果集上限 200 行/50 列/200 字符单元格）
- ~~Redis playground~~（✅ 每会话独立逻辑库（blake2b 哈希 + 线性探测，marker TTL 自释放），命令黑名单 + 参数化，拒绝注入）
- ~~FastAPI playground~~（✅ 无状态：用户代码在 `/run` 同款 `-I` 子进程隔离中通过 httpx.ASGITransport 单线程跑一次请求，6s 超时；TestClient 因 RLIMIT_NPROC 禁止其 portal 线程而不可用）
- ~~隔离 sandbox~~（✅ 专用 `sandbox-db` / `sandbox-redis`，仅在 internal 网络可达，read-only rootfs + no-new-privileges + mem/cpu/pids 限额）
- 危险命令拦截为黑名单式人工维护（残余风险，见 incomplete areas）；SQL schema GC 为机会式触发而非定时任务。

### Portfolio CMS（✅ v1.0.0 已完成：profile + 项目条目 + 排序 + 仓库绑定 + 发布开关，e2e 39 项全绿）

允许用户配置：

- ~~profile~~（✅ display_name/headline/summary/skills/resume_url + 任意 social_links，per-user 唯一，首次访问自动建未发布草稿）
- ~~selected projects~~（✅ 上限 30 条/人：title/subtitle/description/architecture/decisions/tech_tags/link，per-entry is_visible，可绑定本人已同步仓库）
- ~~ordering~~（✅ order_index + 批量 reorder 端点，payload 必须精确覆盖本人项目）
- ~~architecture~~（✅ 架构说明字段，公开页 `<details>` 折叠展示）
- ~~engineering decisions~~（✅ 工程决策字段，公开页独立块展示）
- ~~public/private visibility~~（✅ profile 级 is_published 总开关：未发布时 `GET /api/portfolio/{username}` 保持 legacy 静态形状——隐私测试锁定；绑定仓库仅在仓库本身 is_public 时对外显示）
- ~~resume links~~（✅ resume_url）
- ~~social links~~（✅ 任意 key-value，公开页 chip 展示）

> 实现说明：`PortfolioProfile` / `PortfolioProject`（迁移 0010，repository FK `ON DELETE SET NULL`）；`/api/portfolio-cms/*` 全部认证 + user 作用域（foreign id 404，与 missing 不可区分）；发布后公开视图按 order_index 排序、仅返回 is_visible 项目；`scripts/e2e_portfolio_cms.ps1` 39 项容器化检查全绿。

### Tests（✅ v1.0.0 已完成：Backend pytest 187 + Frontend Vitest 30 + Playwright E2E 3）

Backend（✅ 187 个测试）：

- pytest
- unit tests
- API tests
- auth tenant-isolation tests
- DB transaction tests
- runner tests
- hidden-test privacy tests
- repo static-analysis tests
- LLM mocked tests

Frontend（✅ 30 Vitest + 3 Playwright）：

- ~~Vitest~~（✅ jsdom + @testing-library/react：api token 存取/静默刷新单飞去重/auth 端点豁免、SSE 解析、AuthPage 校验与 payload、PortfolioPage 编辑器交互、PublicPortfolioPage legacy/CMS/404）
- ~~React component tests~~（✅ 同上，mock fetch/api 层不真实打后端）
- ~~Playwright core flows~~（✅ 注册→工作台、登出守卫+重新登录、发布→公开 CMS portfolio；webServer 自动拉起 docker compose backend（`--wait` + healthcheck）+ 本地 vite 代理；断言均为中文界面文案。⚠️ 端口冲突逃生舱：compose backend 宿主端口与 Playwright 健康探测/vite 代理统一读 `BACKEND_HOST_PORT`（默认 8000）——本机 8000/8010 曾被另一项目的 WSL2 隐藏监听占用（Windows netstat 不可见，`/health` 均返回 200 导致 `reuseExistingServer` 误复用、注册 404），此时用 `BACKEND_HOST_PORT=8020 npx playwright test` 即可在任意空闲端口跑通全栈 E2E）

> 实现说明：`npm run test`（watch）/ `npm run test:run`（单次）/ `npx playwright test`；Makefile `make frontend-test` 并入 `make verify`，`make frontend-e2e` 独立（需 docker）；测试均断言真实行为（渲染输出/状态变化/mock 调用参数），随机后缀用户名保证 E2E 可重复运行。

### CI/CD（✅ v1.0.0 已完成：GitHub Actions backend/frontend/docker 分道 + 夜间 E2E）

- ~~CI pipeline~~（✅ `.github/workflows/ci.yml`：push/PR 并行 backend（uv sync --frozen → compileall app+runner → 离线 pytest）与 frontend（npm ci → tsc → vitest → vite build）lane，通过后 docker lane 校验 compose config 并构建全部镜像）
- ~~Playwright E2E in CI~~（✅ 夜间 schedule（北京时间 02:00）+ workflow_dispatch 单独 e2e lane，复用 `make frontend-e2e` 的 webServer 流程拉起 docker compose 栈，失败时 dump compose 日志）
- ~~依赖缓存~~（✅ setup-uv enable-cache + setup-node npm cache，lockfile 均已锁定）
- ⚠️ 托管平台首跑 NOT RUN——仓库无 `.git`/remote，workflow 尚未在 GitHub Actions 上执行过（首次 push 后运行）

> 实现说明：workflow 只读权限（`permissions: contents: read`）+ `concurrency` 取消同分支旧 run；后端测试套件本身离线（SQLite + 关闭的 Redis 端口），CI 无需拉起服务容器。

### Observability（✅ v1.0.0 已完成：结构化日志 + request_id + /ready + /metrics + audit + 可选 Sentry）

- ~~structured logs~~（✅ `JsonFormatter` 一行一对象，`interviewos.access` 每请求一条：method/path/route 模板/status/duration_ms/user；`LOG_FORMAT=text` 本地可读模式）
- ~~request_id~~（✅ `RequestContextMiddleware` 生成/透传 `X-Request-ID`，含 401；contextvar 贯穿 access log 与 audit）
- ~~health/readiness~~（✅ `/health` 已有；新增 `/ready` DB+cache 布尔 checks，503/200，不泄露主机/端口/驱动/堆栈）
- ~~metrics~~（✅ prometheus-client：`interviewos_http_requests_total`（method/route/status）+ `interviewos_http_request_duration_seconds`（method/route），route 模板控基数，`/health` `/ready` `/metrics` 不计）
- ~~error tracking hooks~~（✅ `init_error_tracking()`：`SENTRY_DSN` 空白为 no-op 零开销；DSN 已设但 SDK 未装仅告警不阻断启动）
- ~~audit log for sensitive actions~~（✅ auth.register/login/login_failed/logout×2/change_password、git.authorize_started/connected/disconnected、repo.sync、playground.session_created——只记元数据，密码/token/secret 不入日志，23 个新测试锁定，套件 210 个）

---

## 7. Required validation gates

Agent 每完成一个阶段，至少执行可用环境允许的以下检查。

### Backend（uv 管理环境）

后端依赖与虚拟环境统一由 [uv](https://docs.astral.sh/uv/) 管理（`backend/pyproject.toml` + `uv.lock`），不要往系统 Python 里 pip install。

```bash
cd backend
uv sync                    # 创建/更新 .venv（首次或依赖变更后）
uv run pytest              # 测试套件（基线 210 个，新增功能需保持全绿）
uv run python -m compileall app ../runner   # 语法检查
```

改动 `pyproject.toml` 依赖后必须 `uv lock` 并提交更新后的 `uv.lock`。

### Frontend

```bash
cd frontend
npm install
npm run test:run            # Vitest 单元/组件测试（30 个，mock fetch/api，无需后端）
npx playwright test         # E2E 核心流程（webServer 自动拉起 docker compose backend + vite；首次需 npx playwright install chromium）
                           # 8000 被其他本机服务占用时：$env:BACKEND_HOST_PORT='8020'; npx playwright test
npm run check
npm run build
```

前端新增依赖后必须确认 `frontend/package-lock.json` 中新增项的 `resolved` URL 仍为 `registry.npmjs.org`（见下方 Docker 约束）。

### Docker

```bash
docker compose config
docker compose up --build
```

已在本机验证通过（Docker Desktop 4.71 / engine 29.4.1 / WSL2，PostgreSQL 18）：全栈启动、0001→0010 迁移在 PG 上执行（0006-0010 均在已持有旧版本的卷上增量验证）、smoke 覆盖 auth/题库/前置图/搜索/FSRS + review_logs/Question CMS（创建含 tags/updated_at、归档后列表与搜索排除、批量标签、重复创建 409）/v0.9 Advanced Interview（personas 目录、persona 创建 + 模块预算、模块 start 生命周期、跨轮矛盾记忆检测、报告 memory/time 分节、time-status 跨用户隔离）/v1.0 Git providers（伪造凭据冒烟，不打真实 provider）/v1.0 Playgrounds（`scripts/e2e_playgrounds.ps1` 30 项）/v1.0 P2 Portfolio CMS（`scripts/e2e_portfolio_cms.ps1` 39 项）/Runner 隐私/dashboard/离线 AI/Vite 代理。

约束（改动前必读）：
- frontend 容器用 `npm ci` 从 lockfile 安装，Vite 必须绑定 `0.0.0.0` 才能被端口映射访问。
- `frontend/package-lock.json` 的 `resolved` URL 必须保持 `registry.npmjs.org`：npmmirror URL 在容器网络内 TLS 握手被重置，会导致容器内 `npm ci` 全量失败。宿主机 `~/.npmrc` 已于 2026-09-06 切换为 `https://registry.npmjs.org/`（npmmirror 当时从本机整体不可达）；若日后又被改回 npmmirror，新增依赖后需把新写入的 mirror URL 规范化回 npmjs。

### Makefile（仓库根目录）

以上常用命令已封装为根目录 `Makefile`（tab 缩进，标准 GNU make 语法；Windows 无 make 时直接用上面的原始命令）：

```bash
make install          # backend uv sync + frontend npm install
make verify           # 完整验收门禁：compileall + pytest + vitest + tsc + build
make backend-test     # 仅后端测试
make frontend-test    # 仅前端 Vitest（单次）
make frontend-e2e     # Playwright E2E（需 docker；自动拉起 backend 栈 + vite）
make migrate          # alembic upgrade head
make migration-new    # 新迁移：make migration-new m=slug
make docker-up        # docker compose up --build
```

然后至少验证：

```text
GET /health
frontend loads
register
login
/api/auth/me
question list
coding visible tests
coding hidden submit
project sync (when network is available)
AI offline mode
public portfolio without login
```

### Security regression

必须确认：

- hidden tests 未泄漏
- runner 不在 backend 内执行用户代码
- repository sync 不执行 repo code
- authenticated user cannot read another user's private records
- public portfolio contains no private learning data

如果某检查因为环境（网络、Docker、provider key）无法执行，必须明确写：

> NOT RUN — reason: ...

不能写“passed”。

---

## 8. Agent work protocol

每次接手任务按以下流程执行：

1. 阅读 `AGENT.md`。
2. 阅读 `README.md`、`CHANGELOG.md`。
3. 浏览相关源码，确认已有功能，不凭文档猜。
4. 写一个简短 implementation plan。
5. 先修改 backend/data model，再修改 frontend contract（如果功能需要）。
6. 完成真实交互，不留 inert UI。
7. 执行测试/编译/构建。
8. 修复发现的问题。
9. 更新：
   - `README.md`
   - `CHANGELOG.md`
   - `VERSION`（只有真正发布新版本时）
10. 汇报：
   - changed
   - validated
   - not validated
   - remaining risks

---

## 9. Definition of Done

一个功能只有同时满足以下条件才算 Done：

- 数据结构/接口存在（如果需要）
- 前端可真正操作（如果是用户功能）
- 状态可持久化或明确是 ephemeral
- auth / ownership 边界正确
- error state 有处理
- 没有 placeholder / pass / fake data 冒充生产结果
- 至少通过相应静态/单元/集成验证
- README/CHANGELOG 已同步

---

## 10. Recommended first task for the next Agent

**Start Git webhook / scheduled sync + commit diff notifications.**（v0.8 全部、v0.9 Advanced Interview 核心三项、v1.0 P0 Git provider integrations、P1 Playgrounds、P2 Portfolio CMS、Tests（后端 210 + 前端 30 Vitest / 3 Playwright）与 CI/CD + Observability 均已完成——**v1.0 feature-complete**）

不要同时开十个大功能。

推荐顺序：

```text
1. Git webhook / scheduled sync + commit diff notifications（下一个任务，v1.0 遗留项）
2. （可选）把仓库推送到 GitHub 并观察第一笔 CI run——workflow 文件已就绪，
   push 到 main 即触发 backend/frontend/docker lane；夜间 schedule 会自动跑 E2E
3. （可选增强）语音面试 server-side ASR / AI System Design Review（v0.9 遗留可选项）
```

每完成一项都要：

- 走 Alembic migration（禁止隐式建表/改表）
- 私有数据查询保持 user_id 作用域（沿用 `current_user` 依赖）
- 新增敏感操作挂 `audit()`（`app/observability.py`），只记元数据
- 保持后端 210+ pytest 与前端 30+ Vitest / 3+ Playwright 全绿（CI pipeline 的核心职责就是跑这些）
- 同步 README / CHANGELOG 后再进入下一项
