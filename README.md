# InterviewOS v1.0

InterviewOS 是一个 AI 工程师面试工作台，把项目代码、技术题库、算法挑战、AI 模拟面试、系统设计和间隔复习连接到一起。

v0.9 保留了 v0.8 的全部功能，并加入了高级面试层：七种可选面试官风格（只改变提问与评分侧重，绝不改变事实标准）、跨轮次面试官记忆（检测前后矛盾、回避问题、反复回避的知识缺口并注入实时追问），以及时间控制器（按 30/45/60 分钟面试计划给每个模块分配时间预算，追踪真实耗时（含思考时间），并在该切换模块或收尾时给出建议）。

v1.0 加入 Git 提供商集成（GitHub 与 Gitee 的 OAuth 授权、提供商访问令牌加密存储、通过令牌鉴权克隆同步私有仓库、显式仓库选择器——只有你主动选择的仓库才会进入数据库），面试实操沙箱：SQL、Redis 和 FastAPI 隔离环境，具备按会话数据隔离、双向危险命令拦截和一键重置，可配置的作品集 CMS，完整测试套件（后端 pytest + 前端 Vitest/Playwright），以及 CI/CD + 可观测性基线：带请求 ID 的结构化 JSON 日志、就绪探针、Prometheus 指标、敏感操作审计流水和 GitHub Actions 流水线。

## 包含哪些能力

### 个人工作台 + JWT

- 注册 / 登录界面。
- HS256 JWT 访问令牌 + 轮换刷新令牌。
- 密码使用 PBKDF2-SHA256 与每密码随机盐存储。
- 工作台 `/api/*` 路由要求 Bearer 令牌；前端对即将过期的访问令牌静默刷新。
- 退出登录（当前令牌或全部设备）与修改密码；两者都会通过每用户有效性水位线立即撤销既有令牌。
- 每条私有记录（回答、掌握度、面试会话/轮次/报告、算法提交/错题本、代码讲解、仓库）都归属一个 `user_id`，所有私有查询都限定在当前用户范围内。
- `/api/portfolio/leon` 保持公开用于面试官分享，且只展示显式标记为公开的仓库。
- 任何公开部署前请先更换 `AUTH_SECRET`。

这仍是一个本地优先的面试项目，不是生产级身份平台：暂无邮箱验证、密码重置邮件、MFA 或组织/角色管理。（v1.0 新增的 OAuth 仅用于 Git 提供商的仓库授权——它不是身份/登录提供商。）

### 项目情报

- GitHub/Gitee 公开仓库同步——匿名可用，零配置。
- **v1.0 Git 提供商 OAuth**：在项目页绑定你的 GitHub/Gitee 账号，列出令牌可见的仓库（按 全部/公开/私有 筛选），一键同步私有仓库。
  - 提供商访问令牌静态加密存储（标准库 HMAC-CTR + encrypt-then-MAC，密钥来自 `OAUTH_ENCRYPTION_KEY` / 回退 `AUTH_SECRET`），任何 API 都不会返回、也绝不写日志；断开连接即删除令牌记录。
  - 仓库列表不落库——只有你显式点击“同步”的仓库才会进入数据库。
  - `Repository.is_private` 记录提供商侧可见性；作品集暴露仍由独立的 `is_public` 开关控制，私有仓库保持私有。
- Monaco 源码浏览器。
- Python AST 提取类/函数/异步函数/import/调用。
- React Flow 仓库架构可视化。
- Commit diff → 面试题生成。
- 仓库 → 简历项目描述生成器。
  - 配置了 OpenAI 兼容 LLM 时使用 LLM。
  - 未配置 LLM 时回退到确定性仓库证据。
  - 提示词明确禁止虚构 QPS、延迟、用户量、准确率、团队规模等无依据指标。

### 题库 + CMS

- Python / FastAPI / asyncio / Redis / Database / Agent / RAG / System Design / LeetCode 种子题。
- 回答评分与答案版本历史。
- 题库页**管理模式**：创建和编辑题目（分类、标题、答案、代码、追问、难度、项目关联、标签）。
- 归档 / 恢复（软删除）：归档题目从活跃题库、统一搜索和面试脚本生成中消失，并可在归档视图中恢复。
- 跨选中题目的批量标签操作（追加 / 设置 / 移除，`|` 分隔）。
- 创建/编辑/导入时的重复检测：归一化标题相似度（≥0.9 阻断并返回 HTTP 409 与相似题目列表；`?force=true` 可强制覆盖），≥0.75 在导入预览中以警告提示。
- 导入流程为预览优先：`POST /api/questions/import/preview` 解析并校验每一行（重复 slug、缺失 title/answer、相似标题）但不写入任何内容；只有确认步骤才落库。
- 题目保持共享内容；新建/编辑的行会记录 `created_by` 和 `updated_at`。
- 导入历史。
- 示例文件在 `examples/` 下。

### Coding 面试

- Monaco 在线编辑器。
- 独立 Python Runner 服务。
- 公开与隐藏评测测试。
- 面试锁定模式。
- 复杂度回答检查。
- 错题本与提交历史。

### 实操沙箱（v1.0）

SQL / Redis / FastAPI 隔离环境，用于面试实操练习——不用碰任何真实服务就能“给我一个能随便造数据的库”：

- **SQL**：每个会话在专用沙箱数据库（绝不是主库）上获得独立的 PostgreSQL schema。整批语句作为一个隐式事务执行——任何一条失败都会回滚整批。结果以表格形式渲染并带行数；`DROP DATABASE` / `CREATE ROLE` / `pg_sleep` / 批中途 `SET` 等命令会被拦截。
- **Redis**：每个会话在专用沙箱 Redis 上获得独立的逻辑数据库索引。每次执行一条命令，带类型化结果标签和 50 条历史；`FLUSHALL` / `CONFIG` / `EVAL` / `SELECT` 等命令会被拦截，且参数以独立协议参数传输，一条命令永远无法夹带第二条。
- **FastAPI**：编写应用，选择方法/路径/JSON 请求体，发送一次请求。应用运行在与代码 Runner 相同的隔离子进程中（`-I` 模式、资源限制、6 秒硬超时）——每个请求都是全新实例。
- **隔离**：会话密钥为不可预测的 32 位十六进制值；Runner 由其派生 schema / 数据库索引，会话之间无法互相看到数据。危险输入做双重检查（后端镜像 + Runner，对等测试），会话 24 小时过期，闲置沙箱 schema 会被垃圾回收，清空重置 / 新会话按需擦除或轮换沙箱。
- 沙箱服务（`sandbox-db`、`sandbox-redis`）运行在仅内部可达的 Docker 网络上，不发布任何端口。

### AI 面试 + 语音

- 一键生成面试场景。
- **面试官风格**（v0.9）：生成前从 7 种风格中选择——标准技术面、友好引导、压力面、后端 Leader、AI/Agent Leader、算法面试官、HR 行为面。风格改变开场/收尾提示词、追问风格和评分侧重（结构化 vs 深度 vs 工程判断）；绝不改变参考答案或评分基线。
- **面试官记忆**（v0.9）：确定性跨轮次分析检测前后矛盾（不同轮次对同一概念立场相反）、回避、未正面回答、反复回避的概念以及被标记后仍在复用的知识缺口。发现结果会作为“面试官记忆”上下文注入实时评分/追问提示词，并在报告中汇总。
- **时间控制器**（v0.9）：30/45/60 分钟计划为每个模块分配时间预算（其他时长使用通用分配）。进入模块即记录开始时间，因此思考时间也计入；实时面板显示每个模块的已用 vs 计划分钟数并标记超支、给出切换/收尾建议，报告附带每个模块计划 vs 实际的时间复盘。
- 回答评分与深挖追问。
- 配置 OpenAI 兼容模型时使用 SSE 流式输出。
- 未配置模型时使用确定性离线追问。
- 浏览器 `speechSynthesis` 可朗读当前面试官问题。
- 浏览器 `MediaRecorder` 录制语音回答。
- 在暴露 `SpeechRecognition` / `webkitSpeechRecognition` 的浏览器上，语音实时转写进入回答框。
- 后端保存音频字节与转写元数据。

`SpeechRecognition` 依赖浏览器支持。Chrome/Edge 环境最可能暴露该能力；若不可用，录音仍然有效，候选人可手动输入回答。

### 知识图谱 + 学习

- 项目/仓库 → 技术主题 → 知识分类 → 面试题关系。
- 掌握度分数显示在相关节点上（如有数据）。
- 低于 70% 的弱点节点有视觉区分。
- FSRS-4.5 间隔重复：每次复习（手动 1-5 级评分、题目回答、AI 面试、代码讲解）都会更新稳定性/难度记忆状态，并按 90% 目标保持率调度下次复习。
- 学习页显示每个主题的保持率、稳定性、难度、复习/遗忘次数和完整复习历史。
- 面试/答题/代码讲解表现持续回馈掌握度。
- 前置依赖图视图：8 条知识链（Python/asyncio、FastAPI/Depends、Database/ORM、Redis/Cache、RAG、Agent/Tool Calling、System Design、LeetCode）共 43 个知识点、37 条有向依赖边，含 3 条跨链边。
- 知识点按依赖顺序分层（GIL → 线程 → 竞态 → 锁 → 信号量）；弱链（低于 70% 阈值）会把所有下游节点标记为被阻塞，并通过跨链边传播。
- 可解释的解锁建议：弱链按其阻塞的下游节点数排序，附带首选复习步骤和原因（“先补 Race Condition，再复习 Lock”）。图结构共享；阻塞状态和建议按用户隔离。

### 统一搜索

- 顶栏搜索框调用 `GET /api/search`（250ms 防抖，`⌘K`/`Ctrl+K` 聚焦输入框）。
- 一次查询扇出到五组实体：共享面试题和知识点，加上当前用户的仓库文件、答案版本和面试轮次。
- 结果在下拉框中分组展示（标签 + 副标题 + 每组上限）；按 Enter 跳到第一个结果。
- 点击结果跳转到所属页面并聚焦该条目：题目/答案在题库中选中该题，知识点在前置依赖图中选中该节点，仓库文件在项目情报中打开对应仓库，面试轮次加载该会话的报告。
- 匹配为大小写不敏感的子串搜索（`lower() LIKE`），不是 `tsvector`：种子内容以中文为主，且离线测试套件运行在 SQLite 上（PostgreSQL FTS 在 SQLite 上不存在）。查询中的连字符按单字符通配符处理，因此 `xenon-marker` 也能匹配 `xenon_marker.py` 代码标识符。
- 私有分组严格按用户隔离；搜索其他用户的标记词不会返回任何结果。

### 系统设计实战

- 系统设计题库。
- React Flow 白板。
- 添加 Client/API/FastAPI/Auth/Redis/PostgreSQL/Vector DB/Queue/Worker/LLM/Sandbox 组件。
- 拖动、连线、删除节点。
- 按账号和案例保存/恢复画布。
- 文字设计评价与追问和架构图并存。

### 面试报告 + 作品集

- 技能维度面试报告。
- 优势、弱点与复习计划。
- 风格徽章、面试官记忆发现（前后矛盾 / 回避问题 / 未正面回答 / 反复回避 / 重复薄弱点）附 LLM 汇总，以及时间执行复盘（每模块计划 vs 实际、最终建议）。
- 最近一次面试的录音/转写列表。
- 作品集 CMS（v1.0 P2）：应用内编辑器配置你的公开页——显示名称、头衔、简介、技能标签、简历链接、社交链接，以及最多 30 条项目条目（描述、架构说明、工程决策、技术标签），每条可控制可见性、排序，并可绑定一个已同步的仓库。
- 一个发布开关控制公开视图：未发布用户保持默认静态页；已发布用户在 `/portfolio/{username}` 上展示其 CMS 内容。绑定的仓库只有在仓库本身被标记为公开时才会出现在公开视图——私有仓库绝不泄露 URL。

### 可观测性（v1.0）

所有能力在未配置时都降级为零开销——没有 DSN、没有采集器、没有结构化日志消费者，应用照常启动和服务。

- **结构化日志**：每行一个 JSON 对象（`ts/level/logger/message` 加请求级附加字段）。`LOG_FORMAT=text` 保留人类可读模式用于本地开发。`interviewos.access` 日志器每个请求恰好输出一行结构化日志（方法、路径、路由模板、状态码、耗时、用户）；`/health`、`/ready` 和 `/metrics` 作为基础设施噪音被排除。
- **请求 ID**：每个响应都带 `X-Request-ID`（自动生成，或从入站请求头透传），包括 401——中间件包裹了 JWT 守卫。日志和审计记录通过它关联。
- **就绪探针**：`GET /ready` 探测数据库与缓存连通性，返回 `{"status": "ready"|"not_ready", "checks": {...仅布尔值...}}`，HTTP 200/503。失败细节（主机名、端口、驱动错误、堆栈）绝不泄露到响应中。
- **指标**：`GET /metrics` 暴露 Prometheus 计数器和延迟直方图，按方法和路由模板打标签（`interviewos_http_requests_total`、`interviewos_http_request_duration_seconds`）；未匹配路径收敛为单一标签以控制基数。
- **审计流水**：敏感操作只记录谁/做了什么/何时加操作元数据——注册、登录（含失败登录）、退出登录（两条撤销路径）、修改密码、Git OAuth 授权/绑定/断开、仓库同步、沙箱会话创建。密码、令牌和 OAuth 密钥绝不进入日志流（由测试保证）。
- **错误追踪（可选）**：设置 `SENTRY_DSN` 即初始化 sentry-sdk；配置了 DSN 但未安装 SDK 时记录警告而不中断启动。DSN 留空（默认）则零第三方调用。
- **构建版本**：Vite 构建从 `package.json` 注入 `__APP_VERSION__`——仪表盘主视觉区显示 `v1.0.0` 徽标，你永远知道当前看的是哪个构建。

### CI（v1.0）

`.github/workflows/ci.yml` 在 push/PR 时运行（外加每夜定时和手动触发）：

- **backend** — `uv sync --frozen` → app + runner 的 `compileall` → 离线 pytest 套件（SQLite + 关闭的 Redis 端口；无需任何服务）。
- **frontend** — `npm ci` → `tsc` → vitest → vite build（启用 npm 缓存，lockfile 锁定 registry.npmjs.org）。
- **docker** — 前两条通道通过后：`docker compose config` 校验 + 全部镜像构建。
- **e2e**（仅每夜 02:00 北京时间 + `workflow_dispatch`）— 对真实 docker compose 栈运行 Playwright 套件，使用与 `make frontend-e2e` 相同的 webServer 流程；失败时导出 compose 日志。
- 并发取消被取代的运行；workflow 以只读权限运行。

## 用 Docker 启动

要求：Docker Desktop / Docker Engine with Compose，首次运行需要联网下载镜像/npm/pip 依赖。

```bash
docker compose up --build
```

打开：

- 前端：`http://127.0.0.1:5173`
- Swagger：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/health`
- 就绪探针（DB + 缓存检查）：`http://127.0.0.1:8000/ready`
- Prometheus 指标：`http://127.0.0.1:8000/metrics`
- 公开作品集：`http://127.0.0.1:5173/portfolio/leon`

首次访问请选择**创建账号**。仓库中有意不提交任何默认密码。

## 本地后端开发（uv）

后端依赖由 [uv](https://docs.astral.sh/uv/) 管理（`backend/pyproject.toml` + `uv.lock`）；不要往系统 Python 里 pip install：

```bash
cd backend
uv sync                    # 创建/更新 .venv
uv run pytest              # 测试套件（Alembic 迁移后的临时数据库）
uv run python -m compileall app ../runner
```

编辑 `pyproject.toml` 依赖后，运行 `uv lock` 并提交更新后的 `uv.lock`。后端 Docker 镜像用同一份 lockfile 构建（`uv sync --frozen`）。

## 前端测试（Vitest + Playwright）

```bash
cd frontend
npm run test:run        # Vitest 单元/组件测试（30 个测试，mock fetch/api——不需要后端）
npx playwright test     # 真实 Chromium 中的 E2E 核心流程（需要 docker；自行启动整套栈）
```

- 单元/组件套件（`src/__tests__/`）覆盖 `api.ts` 令牌存储与单飞静默刷新、SSE 流解析、登录页表单校验与请求载荷、作品集 CMS 编辑器交互，以及公开作品集的默认/CMS/404 渲染。
- Playwright（`e2e/`）针对真实后端验证注册 → 工作台、退出守卫 + 重新登录、发布 → 匿名访客看到 CMS 作品集的流程：其 `webServer` 配置会运行 `docker compose up -d --build --wait backend`（`/health` 健康检查让 `--wait` 结果确定）加一个把 `/api` 代理到后端的本地 vite dev server。首次运行需要 `npx playwright install chromium`。测试使用随机后缀用户名，因此可对持久化数据库重复运行。若本机 8000 端口被其他服务占用（Windows netstat 可能看不到 WSL2 转发的隐藏监听），可设置 `BACKEND_HOST_PORT` 换端口运行，例如 PowerShell：`$env:BACKEND_HOST_PORT='8020'; npx playwright test`（compose 映射、健康探测与 vite 代理读取同一个变量，默认仍为 8000）。

## 常用命令（Makefile）

仓库根目录提供 `Makefile` 封装常用命令（需要 GNU make；Windows 上没有 make 时直接使用上面的原始命令）：

```bash
make install          # 后端 uv sync + 前端 npm install
make verify           # 完整校验门：compileall + pytest + vitest + tsc + build
make backend-test     # 仅后端 pytest
make backend-dev      # 后端开发服务器 :8000（热重载）
make migrate          # alembic upgrade head
make migration-new    # 创建迁移：make migration-new m=slug
make frontend-test    # Vitest 单元/组件测试（单次运行）
make frontend-e2e     # Playwright E2E（docker compose 后端 + vite，需要 docker）
make frontend-dev     # Vite 开发服务器 :5173
make docker-up        # docker compose up --build
```

## 可选：LLM 配置

把 `.env.example` 复制为 `.env`，配置任意 OpenAI 兼容 chat-completions 端点：

```env
LLM_BASE_URL=http://host.docker.internal:8080/v1
LLM_API_KEY=
LLM_MODEL=your-served-model-name

AUTH_SECRET=replace-with-a-long-random-secret
```

兼容的托管提供商或本地 vLLM 服务器均可。三个 `LLM_*` 值留空即可让 InterviewOS 以离线确定性模式运行。

认证参数也可在 `.env` 中调整：`AUTH_TOKEN_MINUTES`（短期访问令牌）和 `AUTH_REFRESH_DAYS`（刷新令牌有效期；刷新令牌每次使用都会轮换）。

## Git 提供商 OAuth 配置（v1.0，可选）

要启用私有仓库同步，请在各提供商注册 OAuth 应用并填写对应的 `.env` 值：

- **GitHub** — Developer settings → OAuth Apps → New OAuth App。Homepage URL 填前端源；Authorization callback URL：`http://localhost:5173/oauth/callback`。授权范围 `read:user repo`。
- **Gitee** — 设置 → 第三方应用 → 创建应用。回调地址：同 `http://localhost:5173/oauth/callback`。授权范围 `user_info projects`。

```env
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITEE_CLIENT_ID=
GITEE_CLIENT_SECRET=
OAUTH_ENCRYPTION_KEY=another-long-random-secret
OAUTH_REDIRECT_BASE=http://localhost:5173
```

说明：

- 所有值均可选。client id/secret 留空时项目页隐藏“绑定授权”按钮，仅剩匿名公开仓库同步——其余功能不受影响。
- `OAUTH_ENCRYPTION_KEY` 用于静态加密提供商访问令牌。轮换该密钥会使所有已存令牌失效；受影响用户会看到明确的“断开并重新授权”错误。留空时回退到 `AUTH_SECRET`。
- OAuth `state` 一次性使用、绑定发起用户、10 分钟过期。
- docker-compose 自动从根目录 `.env` 透传全部五个变量。

## 题目导入格式

JSON 接受数组或 `{ "questions": [...] }`。

导入为**预览优先**：导入页先做一次干跑（`POST /api/questions/import/preview`），列出每一行及其结果（将创建 / 跳过）以及重复 slug、缺失字段、相似标题问题，此时不写入任何内容。只有“确认导入”才把有效行落库。

支持的字段：

- `category`
- `title`（必填）
- `difficulty`（1-5）
- `answer`（必填）
- `code`
- `followups`
- `project_link`
- `tags`（`|` 分隔）
- `slug`（可选；缺失时自动生成）

CSV 使用相同列名。参见：

- `examples/questions-import.json`
- `examples/questions-import.csv`

单次导入限制 2,500 行、1.5 MB 源文本。

## 安全边界

- 同步的仓库只做静态分析读取；InterviewOS 不执行仓库代码。
- 用户代码发送给独立的 Runner 服务，而非主 FastAPI 进程内 `exec()`。
- Runner 通过 Docker 资源控制与内部网络隔离。
- 面试录音存储在专用 Docker 卷中。
- v0.8 加入刷新令牌轮换、退出登录/全设备退出撤销、修改密码撤销、每用户令牌有效性水位线和用户范围的私有数据查询。v1.0 加入应用级敏感操作审计流水（认证、Git OAuth、仓库同步、沙箱会话）。公开部署还应额外增加 HTTPS、强密钥管理、限流、引入 cookie 时的 CSRF 策略、基于邮箱的密码找回，以及用于合规的集中式/防篡改日志留存。

## 数据库迁移

v0.8 用 **Alembic** 取代了隐式启动建表：

- `alembic/versions/0001` — v0.7 基线 schema。
- `alembic/versions/0002` — 为每张私有表加入 `user_id` 归属，并回填旧单用户数据。
- `alembic/versions/0003` — 新增 `refresh_tokens` 表和 `users.tokens_valid_after` 水位线。
- `alembic/versions/0004` — 为 `mastery` 加入 FSRS 记忆状态（stability/difficulty/reps/lapses/last_review_at），创建 `review_logs` 表，并回填旧的固定间隔数据行，使成熟度在升级后保留。
- `alembic/versions/0005` — 创建共享的 `knowledge_nodes` 和 `prerequisite_edges` 表；图内容在后端启动时幂等种子化。
- `alembic/versions/0006` — 为 `questions` 加入 CMS 列：`archived`（带索引的软删除标记，默认 0）、`tags`、`created_by`（可空 FK 指向 `users`，`ON DELETE SET NULL`）和 `updated_at`。
- `alembic/versions/0007` — 加入高级面试列：`interview_sessions.persona` 和 `module_starts`（模块进入时间戳 JSON）、`interview_turns.module_index`，以及 `interview_reports.memory_findings` / `time_execution`（JSON 区块）。
- `alembic/versions/0008` — 创建 `git_connections` 表（加密的提供商令牌，每用户+提供商一行）和 `oauth_states` 表（一次性 CSRF state），并加入 `repositories.is_private`（提供商侧可见性元数据）。
- `alembic/versions/0009` — 创建 `playground_sessions` 表（沙箱会话密钥、类型、过期与最近使用追踪）。

后端 Dockerfile 启动时运行 `alembic upgrade head`。新的 schema 变更必须以迁移交付，而不是直接改模型。后端测试针对迁移运行（`pytest` 会先把临时数据库升级到 `head`），因此模型/迁移漂移会导致套件失败。

## v0.9 已执行验证

- Python 源码编译（`python -m compileall backend/app runner`）：通过。
- 后端测试套件（`pytest`，针对 Alembic 迁移后的临时数据库运行）：95 通过——包含 v0.8 覆盖（认证生命周期、跨用户隔离、迁移一致性、隐藏测试隐私、作品集隐私、FSRS、前置依赖图、统一搜索、题目 CMS、离线冒烟）加 19 个高级面试测试：风格接受/持久化/拒绝/列表、生成脚本中的时间预算布局、风格保持事实评分标准（同一答案在不同风格下基线得分相同）、跨轮次矛盾检测（同轮次对照被忽略）、回避/未正面回答、反复回避概念、复用缺口、实时轮次反馈携带记忆上下文、模块开始 + 时间状态生命周期（未知模块 404 与按用户隔离）、报告中记忆/时间区块持久化，以及超预算 / 收尾建议 / 空会话时间计算。
- 前端类型检查 + 构建（`npm run check`、`npm run build`）：通过（构建 5.23s）。
- Docker 端到端启动（`docker compose up --build`）：在 Docker Desktop（WSL2、PostgreSQL 18）上通过。迁移 0007 在已处于 0006 的 PostgreSQL 卷上增量应用。容器栈上的 v0.9 冒烟覆盖：7 风格目录列表、以 `persona=pressure` 创建面试且 45 分钟模块预算正确（3/6/6）、模块开始生命周期（模块 0 激活 → 模块 1 开始后完成）、两轮离线确定性评分、报告记忆发现（检测到矛盾 + 回避概念并带汇总）与 7 模块时间区块、实时时间状态、跨用户时间状态返回 404，以及 5173 上的 Vite dev server 把 `/api` 代理到后端。

## v1.0 已执行验证

- Python 源码编译（`python -m compileall backend/app runner`）：通过。
- 后端测试套件（`pytest`）：170 通过——v0.9 基线（95）加 24 个 Git 提供商 OAuth 测试和 51 个沙箱测试（后端与 Runner 守卫对等、SQL/Redis 拦截矩阵、会话隔离、代理路径、过期生命周期、FastAPI 校验、Runner 故障处理）。
- 前端类型检查 + 构建（`npm run check`、`npm run build`）：通过。
- Docker Compose 配置（`docker compose config`）：有效；栈新增 `sandbox-db`（PostgreSQL 18-alpine）和 `sandbox-redis`（Redis 8，`--databases 64`、内存模式、96mb LRU）于仅内部网络，Runner 同时接入两者。
- 容器端到端（`scripts/e2e_playgrounds.ps1` 对 `docker compose up --build`）：30/30 检查通过。迁移 0009 在已处于 0008 的 PostgreSQL 卷上增量应用。覆盖：SQL 多语句批次与逐语句结果、跨请求会话持久化、字符串字面量包含被拒关键词不误报、`UPDATE … SET` 放行、`DROP DATABASE` 在后端被拦截并返回策略消息、失败语句回滚整批、跨会话与跨用户（404）隔离、重置擦除 schema；Redis SET/GET 持久化、按会话数据库隔离、`FLUSHALL` 拦截、重置擦除键；FastAPI 应用带 JSON 请求体往返、非法 `TRACE` 方法 422 拒绝、纯代码载荷返回 `ok=false` 与驱动错误而非 5xx。
- E2E  pass 在上线前捕获并修复了两个真实沙箱 bug：`redis.Redis.from_url(url, db=…)` 会把所有客户端固定到 URL 的 db（所有会话共享 db 0——现在每个会话有独立索引），以及 starlette 的 `TestClient` 无法在沙箱的 `RLIMIT_NPROC` 下启动 portal 线程（驱动改用单线程的 `httpx.ASGITransport`）。
- 作品集 CMS（P2）验证：后端套件增长到 187 通过（17 个新作品集 CMS 测试，覆盖发布生命周期、CRUD、排序、可见性过滤、仓库绑定归属与跨用户隔离）。前端 `npm run check` + `npm run build` 通过。迁移 0010 在已处于 0009 的 PostgreSQL 卷上增量应用（重建后端镜像；启动时运行 `alembic upgrade head`）。容器冒烟 `scripts/e2e_portfolio_cms.ps1`：39/39 检查通过——认证守卫、未发布档案返回与默认完全一致的形状（保存草稿字段前后各一次）、发布把公开视图切换为 CMS 内容、项目 CRUD/排序/可见性、外部 repository-id 404、跨用户更新/删除 404、删除、取消发布恢复默认形状。
- 前端测试套件（v1.0 Tests）验证：Vitest `npm run test:run` 30/30（令牌存储与单飞静默刷新、认证端点刷新豁免、SSE 解析、登录表单校验、CMS 编辑器保存/发布/排序、公开作品集默认/CMS/404 渲染）；Playwright `npx playwright test` 3/3 针对真实容器化后端（注册 → 工作台、退出守卫 + 重新登录、发布 → 匿名访客看到 CMS 作品集）；`npm run check` + `npm run build` 通过；后端 `uv run pytest` 复确认为 187 通过；加入后端 `/health` 健康检查（使 `docker compose up --wait` 结果确定）后 `docker compose config` 有效。
- CI/CD + 可观测性验证：后端 `uv run pytest` **210 通过**（23 个新可观测性测试——请求 ID 生成/透传、结构化访问日志行、日志无凭据、`/ready` 降级/健康状态与失败细节脱敏、`/metrics` 计数器与路由模板标签、每个敏感操作的审计内容并断言无令牌/密码、Sentry 空操作与缺 SDK 路径、JSON 格式化器形状）。前端 `npm run test:run` 30/30、`npm run check`、`npm run build` 通过并带 `__APP_VERSION__` 注入。`docker compose config` 有效；`LOG_FORMAT` / `LOG_LEVEL` / `SENTRY_DSN` 在 compose 文件中透传。CI workflow YAML 解析通过，其 job 结构（backend / frontend / docker / e2e）在本地验证。首次托管 CI 运行：未运行——仓库未配置 git 远程（无 `.git`）；workflow 将在首次 push 时执行。

## 与编码代理继续开发

本仓库包含面向 Codex / 编码代理的交接说明：

- `AGENT.md` — 权威架构、安全边界、当前完成状态、路线图和完成定义（Definition of Done）。
- `AGENT_PROMPT.md` — 可直接复制的提示词，用于常规续作和下一实施阶段。
- `AGENTS.md` — 供自动发现 `AGENTS.md` 的代理使用的兼容入口。

推荐用法：

```text
先阅读 AGENT.md，然后从既有实现继续 InterviewOS。不要重写项目。从下一个 P0 任务开始，验证后再宣布完成。
```

v1.0 功能已完整：P0（Git 提供商 OAuth 集成）、P1（SQL/Redis/FastAPI 沙箱实操）、P2（作品集 CMS）、前端测试套件（Vitest 30 + Playwright 3）以及 CI/CD + 可观测性（GitHub Actions 流水线、带请求 ID 的结构化日志、就绪探针、Prometheus 指标、审计流水、可选 Sentry 接入）均已完成并验证——后端 210 个测试、前端 30 Vitest + 3 Playwright。Git webhook / 定时同步与 commit diff 通知为延期增强。CI 流水线尚未在托管平台运行：仓库未配置 git 远程；workflow 将在首次 push 时执行。
