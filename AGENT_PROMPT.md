# InterviewOS Agent Prompt

下面提供两份可直接复制给 Coding Agent / Codex 的提示词。

---

# A. 通用长期接力 Prompt

```text
你现在是 InterviewOS 项目的高级全栈 + AI Agent 工程师，负责在现有仓库上持续开发，不是重新生成一个新项目。

在做任何修改之前：
1. 完整阅读根目录 AGENT.md。
2. 阅读 README.md、CHANGELOG.md、VERSION。
3. 浏览 backend/app、frontend/src、runner 的现有实现，确认当前真实功能。
4. 不要根据文档猜代码；以源码为准。

项目定位：
InterviewOS 是一个 AI-native technical interview preparation + engineering portfolio platform，核心闭环是：项目代码 → 知识点/题库 → Coding/System Design → AI/Voice Interview → 评分/报告 → 薄弱点 → 间隔复习。

必须保留现有能力：
- React + TypeScript + Vite
- Monaco Editor
- React Flow
- FastAPI
- SQLAlchemy async + PostgreSQL
- Redis
- JWT authentication
- independent Runner
- visible/hidden coding judge
- GitHub/Gitee repo sync（公开仓库匿名同步 + v1.0 OAuth 私有仓库同步）
- AST/static analysis
- project architecture graph
- AI interview + offline fallback
- SSE follow-up
- knowledge graph
- spaced review
- voice recording/transcript
- system-design canvas
- question bulk import
- public portfolio + Portfolio CMS（用户可配置的公开作品集）
- SQL / Redis / FastAPI playgrounds（独立沙箱）
- 前端测试体系：Vitest 单元/组件测试（30 个）+ Playwright 核心流程 E2E（3 条，webServer 自动拉起 docker 栈）
- Observability：结构化 JSON 日志 + X-Request-ID 中间件、/ready 就绪探针、/metrics Prometheus 指标、敏感操作审计日志（auth / Git OAuth / repo sync / playground）、可选 Sentry hook（DSN 空白零开销）
- CI/CD：GitHub Actions 流水线（backend / frontend / docker 三条 push-PR lane + 夜间 E2E lane，`.github/workflows/ci.yml`）

硬性安全边界：
- 禁止在主 FastAPI backend 中 exec/eval 用户代码。
- 用户代码只能进入独立 Runner/Sandbox。
- 禁止执行同步下来的 GitHub/Gitee 仓库代码。
- Hidden tests 不能把 input / expected / test source 返回前端。
- LLM 不能虚构项目 QPS、准确率、用户量、延迟、团队规模等无证据数字。
- 个人工作台数据必须按 authenticated user 隔离。
- Public Portfolio 不能泄露错题、答案历史、薄弱点、录音、私有仓库或 auth 信息。

工程原则：
- 增量修改，不推倒重写。
- 不允许创建 placeholder 页面/API 后声称完成。
- 没执行的测试必须写 NOT RUN 及原因，不能写 PASS。
- 没配置 LLM 时，offline mode 仍必须可用。
- 每完成一个功能，都要检查 backend schema/API、frontend 交互、持久化、错误处理、权限边界。
- 完成后更新 README.md 和 CHANGELOG.md。

每次工作流程：
1. 先给出一个简短实施计划。
2. 找到相关现有代码。
3. 实现最小完整闭环。
4. 运行能够运行的编译、type check、tests、docker smoke test。
5. 修复问题。
6. 汇报 changed / validated / not validated / remaining risks。

如果用户没有指定下一功能，则严格按 AGENT.md 的 Roadmap 继续，并优先完成 P0，再做 P1。

现在开始：先阅读 AGENT.md 和仓库代码，然后告诉我你确认到的“当前真实状态”和你准备实施的下一小阶段，随后直接开始编码，不要停留在纯规划。
```

---

# B. 下一阶段 Git Webhook / Scheduled Sync 专用 Prompt

```text
继续开发现有 InterviewOS v1.0（已 feature-complete），目标实现 Git webhook / scheduled sync 与 commit diff 通知（v1.0 遗留增强项）。不要重建项目，不要删除现有功能。

第一步必须阅读：
- AGENT.md（当前完成状态与硬性边界，尤其是第 4 节安全边界、第 7 节验证门禁与 frontend lockfile / registry.npmjs.org 约束）
- README.md、CHANGELOG.md（v1.0 各阶段交付记录）
- backend/app/git_oauth.py、git_routes.py（OAuth 流、加密 token 存取、decrypt_token）
- backend/app/repo_sync.py（clone_and_scan 认证 clone + redact_secrets）
- backend/app/observability.py（audit() 挂点规范——新敏感操作必须审计，只记元数据）
- backend/app/models.py 与 alembic/versions/（现有 schema 与迁移链 0001-0010）
- docker-compose.yml（backend 服务装配与启动迁移）

背景：v1.0 已 feature-complete——tenant isolation、Alembic（0001-0010）、auth lifecycle、FSRS-4.5、knowledge prerequisite graph、unified search、Question CMS、Advanced Interview（personas / memory / time controller）、Git provider OAuth（GitHub/Gitee，token 加密存储，私有仓库同步）、Playgrounds、Portfolio CMS、前端测试（30 Vitest + 3 Playwright）与 CI/CD + Observability（结构化 JSON 日志 / request_id / /ready / /metrics / audit / 可选 Sentry；.github/workflows/ci.yml 四条 lane；后端 210 pytest 全绿）。当前私有仓库同步完全由用户在 Projects 页手动触发；provider token 无自动刷新。

目标：
1. Scheduled sync（定时同步）：
   - 后端周期性（间隔可配置，默认如 6h，带禁用开关）对已连接 provider 且用户开启自动同步的仓库执行后台 re-clone/fetch + AST 重扫
   - 同步结果与失败原因（脱敏后）持久化；失败用有限重试 + 退避，不做重试风暴
   - 不阻塞请求路径；后台任务生命周期与 FastAPI lifespan 集成，测试环境可禁用或注入时钟
2. Commit diff notifications（提交差异通知）：
   - 仓库有新 commit 时计算与上次同步的 diff，生成"新面试题候选"或学习提醒，落入 per-user 通知/动态流（新表必须走 Alembic migration 0011+）
   - 通知列表 API user 作用域 + 已读状态；前端 Projects 或 Dashboard 显示未读角标与列表
   - LLM 未配置时使用确定性 diff 摘要（不虚构数字），沿用现有 offline fallback 模式
3. Webhook（可选，时间允许或用户要求时）：
   - GitHub X-Hub-Signature-256 / Gitee token 签名校验的 push webhook 端点，验证通过后触发对应仓库的即时增量同步
   - webhook secret 加密存储（复用 OAUTH_ENCRYPTION_KEY 方案），签名失败返回 401 且不泄露细节；处理必须幂等（重复投递不重复建通知）
4. Token 生命周期（可选增强）：
   - 同步时检测 token 失效（401/403），标记连接 needs_reauthorization 并在通知流提醒用户重新授权，不静默失败

要求：
- 所有新敏感操作（自动同步、webhook 接收、token 失效标记）挂 audit()，只记 who/what/when + 仓库元数据，不记 token/secret/diff 内容
- webhook 与同步任务绝不执行仓库代码（只 clone/read/AST/diff，边界见 AGENT.md 4.2）
- 新表走 Alembic migration（0011+），禁止隐式建表；迁移在已有 PostgreSQL 卷上增量验证
- 后台调度不引入重型任务队列/消息总线（当前规模进程内 asyncio 调度即可）；新 Python 依赖走 uv add + uv lock，前端新依赖保持 registry.npmjs.org
- 每个能力补 pytest（调度触发可注入时钟、通知 user 隔离、webhook 签名校验正反例、幂等性），保持后端 210+ 全绿；前端改动补 Vitest
- LLM 生成的 diff 面试题遵守"不虚构数字"边界（AGENT.md 4.4）

验收命令：
cd backend && uv run python -m compileall app ../runner && uv run pytest
cd frontend && npm run test:run && npm run check && npm run build
docker compose config
（涉及迁移时：docker compose up --build 后确认 0011+ 在已有卷上增量应用；后台任务与 webhook 在容器内冒烟）

禁止：
- 为了通过测试而放宽任何安全边界或跳过签名校验
- 把 webhook secret、token、diff 内容写入日志或通知 API 响应
- 未执行验证就声称完成；环境不可用时明确写 NOT RUN 及原因
- 推倒重写现有手动同步路径——自动同步必须与手动同步共存复用同一 clone_and_scan

完成后更新 README.md / CHANGELOG.md / AGENT.md（状态与测试数）/ AGENT_PROMPT.md（下一阶段 prompt）。

现在开始实施，不需要再向我询问是否开始。
```

---

# 使用建议

如果 Agent 能自动读取仓库规则：

```text
请按照仓库根目录 AGENT.md 继续开发 InterviewOS，开始下一阶段。
```

通常已经足够。

如果 Agent 第一次接触项目，使用上面的 **A 通用长期接力 Prompt**。

如果准备直接开发下一阶段，使用 **B Git Webhook / Scheduled Sync 专用 Prompt**。
