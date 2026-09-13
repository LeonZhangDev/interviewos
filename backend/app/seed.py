from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .timeutil import utc_now

from .models import (
    AnswerVersion,
    CodeExplanationAttempt,
    CodingChallenge,
    CodingSubmission,
    CodingWrongEntry,
    InterviewReport,
    InterviewSession,
    InterviewTurn,
    KnowledgeNode,
    Mastery,
    PrerequisiteEdge,
    Question,
    Repository,
    User,
)
from .fsrs import legacy_state


QUESTIONS = [
    {
        "slug": "python-gil", "category": "Python", "title": "Python GIL 是什么？它是否意味着 Python 不能并发？", "difficulty": 2,
        "answer": "传统 CPython 中，GIL 让同一进程内通常只有一个线程执行 Python 字节码。它限制 CPU 密集型线程并行，但 I/O 密集型线程仍可在等待时让出执行权；多进程和 asyncio 仍可用于不同并发场景。",
        "code": "import time\nfrom concurrent.futures import ThreadPoolExecutor\n\ndef io_task(i):\n    time.sleep(0.2)\n    return i\n\nwith ThreadPoolExecutor(max_workers=4) as pool:\n    print(list(pool.map(io_task, range(4))))",
        "followups": "为什么 CPython 需要 GIL？|I/O 密集为什么线程仍有价值？|多进程和线程如何选择？", "project_link": "MindTrip",
    },
    {
        "slug": "python-mutable-default", "category": "Python", "title": "为什么不建议把可变对象作为函数默认参数？", "difficulty": 2,
        "answer": "函数默认参数在定义函数时求值一次，而不是每次调用都重新创建。list、dict 等可变对象会在多次调用之间共享状态，常用 None 作为哨兵并在函数内部创建新对象。",
        "code": "def bad(x, items=[]):\n    items.append(x)\n    return items\n\nprint(bad(1))\nprint(bad(2))\n\ndef good(x, items=None):\n    items = [] if items is None else items\n    items.append(x)\n    return items\n\nprint(good(1))\nprint(good(2))",
        "followups": "默认参数什么时候求值？|tuple 作为默认参数一定安全吗？|None 哨兵有什么含义？", "project_link": "General",
    },
    {
        "slug": "python-generator", "category": "Python", "title": "迭代器和生成器是什么关系？生成器有什么优势？", "difficulty": 2,
        "answer": "迭代器实现逐个取值协议；生成器是创建迭代器的一种便捷方式，函数中使用 yield 会保存执行现场并按需产生值。它适合流式处理和大数据序列，可降低一次性内存占用。",
        "code": "def numbers(n):\n    for i in range(n):\n        yield i * i\n\nfor x in numbers(4):\n    print(x)",
        "followups": "yield 和 return 的区别？|生成器什么时候结束？|生成器可以重复遍历吗？", "project_link": "InterviewOS",
    },
    {
        "slug": "asyncio-lock", "category": "Python", "title": "单线程协程为什么仍会有竞态？Lock 和 Semaphore 有什么区别？", "difficulty": 3,
        "answer": "协程会在 await 处交错执行，如果共享状态的读改写跨越 await，就可能发生竞态。Lock 保护临界区；Semaphore 控制同时进入某类操作的任务数量。",
        "code": "import asyncio\n\ncount = 0\nlock = asyncio.Lock()\n\nasync def add():\n    global count\n    async with lock:\n        old = count\n        await asyncio.sleep(0.05)\n        count = old + 1\n\nasync def main():\n    await asyncio.gather(*(add() for _ in range(3)))\n    print(count)\n\nasyncio.run(main())",
        "followups": "为什么 await 是切换点？|Semaphore(3) 表示什么？|什么时候会造成死锁？", "project_link": "MindTrip",
    },
    {
        "slug": "asyncio-task-future", "category": "Python", "title": "Coroutine、Task 和 Future 分别是什么？", "difficulty": 3,
        "answer": "Coroutine 是 async def 调用得到的可等待对象；Task 把协程调度到事件循环中执行，并保存完成状态；Future 是更底层的异步结果占位对象，Task 本质上建立在 Future 语义之上。",
        "code": "import asyncio\n\nasync def work():\n    await asyncio.sleep(0.05)\n    return 42\n\nasync def main():\n    task = asyncio.create_task(work())\n    print(type(task).__name__)\n    print(await task)\n\nasyncio.run(main())",
        "followups": "直接 await coroutine 和 create_task 有什么区别？|Task 如何取消？|Future 通常由谁创建？", "project_link": "MindTrip",
    },
    {
        "slug": "fastapi-depends", "category": "FastAPI", "title": "FastAPI 的 Depends 解决了什么问题？", "difficulty": 2,
        "answer": "Depends 把认证、数据库 Session、分页和公共校验等横切逻辑从路由业务代码中抽离，便于复用、组合和测试替换。",
        "code": "from fastapi import Depends, FastAPI\n\napp = FastAPI()\n\ndef get_user():\n    return 'Leon'\n\n@app.get('/hello')\ndef hello(user: str = Depends(get_user)):\n    return {'user': user}",
        "followups": "为什么数据库 Session 适合 Depends？|Middleware 和 Depends 怎么选？|依赖可以嵌套吗？", "project_link": "InterviewOS",
    },
    {
        "slug": "fastapi-middleware", "category": "FastAPI", "title": "Middleware 和依赖注入分别适合什么场景？", "difficulty": 3,
        "answer": "Middleware 适合几乎所有请求都要经过的横切逻辑，例如 request_id、CORS、统一耗时；Depends 更适合路由级认证、Session、权限和可组合校验，并且更方便测试替换。",
        "code": "from fastapi import FastAPI, Request\n\napp = FastAPI()\n\n@app.middleware('http')\nasync def timing(request: Request, call_next):\n    response = await call_next(request)\n    response.headers['x-demo'] = '1'\n    return response",
        "followups": "Middleware 的执行顺序是什么？|异常发生时中间件还能拿到响应吗？|认证应该放 Middleware 还是 Depends？", "project_link": "InterviewOS",
    },
    {
        "slug": "fastapi-sse", "category": "FastAPI", "title": "SSE 和 WebSocket 分别适合什么场景？", "difficulty": 3,
        "answer": "SSE 基于 HTTP 长连接，主要是服务器到客户端单向推送，协议简单、自动重连友好，适合 LLM token 流式输出；WebSocket 是全双工连接，更适合高频双向实时交互。",
        "code": "import asyncio\n\nasync def token_stream(text):\n    for ch in text:\n        await asyncio.sleep(0.02)\n        yield f'data: {ch}\\n\\n'\n\nasync def main():\n    async for event in token_stream('hello'):\n        print(event.strip())\n\nasyncio.run(main())",
        "followups": "SSE 为什么常用于 LLM 流式输出？|EventSource 有哪些限制？|什么时候必须用 WebSocket？", "project_link": "MindTrip",
    },
    {
        "slug": "fastapi-session", "category": "FastAPI", "title": "为什么每个请求应该使用独立数据库 Session？", "difficulty": 3,
        "answer": "Session 内部维护连接、事务和 ORM 对象状态，不适合作为跨请求共享的全局可变状态。每请求独立 Session 可以隔离事务与对象状态，并在请求结束时统一提交、回滚和释放资源。",
        "code": "# FastAPI + SQLAlchemy 常见依赖形态\nasync def get_db():\n    async with SessionLocal() as session:\n        yield session",
        "followups": "AsyncSession 为什么也不能在多个并发 Task 共享？|什么时候 commit？|异常时如何 rollback？", "project_link": "InterviewOS",
    },
    {
        "slug": "sqlalchemy-n-plus-one", "category": "Database", "title": "什么是 ORM N+1 查询？怎样发现和解决？", "difficulty": 3,
        "answer": "先查询 N 个父对象，再逐个懒加载子对象，会产生 1+N 次查询。可通过 SQL 日志、APM 或 profiler 发现，并使用 joinedload、selectinload 或显式 JOIN 批量加载。",
        "code": "# SQLAlchemy 示例（概念）\n# stmt = select(User).options(selectinload(User.tasks))\n# users = (await session.scalars(stmt)).all()\nprint('Use selectinload/joinedload to avoid repeated child queries')",
        "followups": "joinedload 和 selectinload 怎么选？|JOIN 为什么可能产生重复行？|分页时有什么坑？", "project_link": "InterviewOS",
    },
    {
        "slug": "database-index", "category": "Database", "title": "数据库索引为什么能加速查询？什么时候反而不该加？", "difficulty": 3,
        "answer": "索引通过额外数据结构减少全表扫描，但会增加存储和写入维护成本。应围绕 WHERE、JOIN、ORDER BY、选择性和实际执行计划设计，并用 EXPLAIN ANALYZE 验证。",
        "code": "print('EXPLAIN ANALYZE SELECT * FROM tasks WHERE user_id = 42 ORDER BY created_at DESC;')",
        "followups": "选择性是什么意思？|联合索引列顺序怎么考虑？|为什么给每一列都建索引不好？", "project_link": "InterviewOS",
    },
    {
        "slug": "transaction-isolation", "category": "Database", "title": "事务的 ACID 是什么？隔离级别解决什么问题？", "difficulty": 3,
        "answer": "ACID 是原子性、一致性、隔离性、持久性。隔离级别控制并发事务之间可见性，权衡一致性与并发性能，用于处理脏读、不可重复读、幻读等问题。",
        "code": "balance = 100\namount = 30\n# 事务应让扣款和流水写入成为一个原子业务操作\nif balance >= amount:\n    balance -= amount\nprint(balance)",
        "followups": "READ COMMITTED 能避免什么？|为什么业务一致性不只靠数据库隔离级别？|死锁如何出现？", "project_link": "AtlasSplit",
    },
    {
        "slug": "redis-cache-aside", "category": "Backend", "title": "缓存与数据库不一致时怎么处理？", "difficulty": 3,
        "answer": "先明确一致性要求。常见做法是 Cache-Aside：读时先缓存、未命中查库并回填；写时先更新数据库再删除缓存，并为删除失败设计重试或消息补偿。数据库通常是最终事实源。",
        "code": "def update_user(db, cache, user_id, payload):\n    db.update(user_id, payload)\n    try:\n        cache.delete(f'user:{user_id}')\n    except Exception:\n        print('enqueue cache retry')",
        "followups": "为什么通常删除而不是更新缓存？|删除缓存失败怎么办？|延迟双删解决什么问题？", "project_link": "MindTrip",
    },
    {
        "slug": "redis-lock", "category": "Backend", "title": "Redis SET key token NX PX 为什么常用于最小分布式锁？", "difficulty": 4,
        "answer": "NX 表示 Key 不存在时才写入，PX 设置毫秒级过期时间，因此获取锁和过期时间设置是一个原子命令。value 应使用唯一 token，释放时比较 token 后再删除，避免误删别人的锁。",
        "code": "token = 'request-123'\ncommand = ['SET', 'job:42', token, 'NX', 'PX', 5000]\nprint(' '.join(map(str, command)))",
        "followups": "为什么需要唯一 token？|长任务怎么续期？|分布式锁为什么不能替代数据库唯一约束和幂等？", "project_link": "AtlasSplit",
    },
    {
        "slug": "agent-tool-calling", "category": "Agent", "title": "Tool Calling 是什么？为什么 Tool Schema 很重要？", "difficulty": 2,
        "answer": "Tool Calling 让模型决定是否调用外部能力，并产生结构化参数。Tool Schema 是模型与执行器之间的契约，清晰的参数类型、约束和描述能降低错误调用，并为校验、授权和审计提供边界。",
        "code": "def get_weather(city: str) -> dict:\n    return {'city': city, 'weather': 'sunny'}\n\ncall = {'tool': 'get_weather', 'arguments': {'city': '成都'}}\nprint(get_weather(**call['arguments']))",
        "followups": "Tool Calling 和 MCP 有什么区别？|工具失败怎么重试？|危险工具怎么做审批？", "project_link": "AtlasSplit",
    },
    {
        "slug": "agent-deterministic-executor", "category": "Agent", "title": "为什么 Agent 不应该直接执行 LLM 生成的任意代码？", "difficulty": 4,
        "answer": "LLM 输出具有非确定性。高风险操作应先生成结构化 Plan，再经过 Schema 校验、权限检查和审批，最后交给可测试、可复现的确定性执行器，并保留审计记录。",
        "code": "plan = {'action': 'allocate', 'rows': [1, 2, 3]}\nallowed_actions = {'allocate'}\nif plan['action'] not in allowed_actions:\n    raise ValueError('action rejected')\nprint('approved plan:', plan)",
        "followups": "Prompt 为什么不能替代权限边界？|Approval 应放在哪里？|如何保证幂等和可审计？", "project_link": "AtlasSplit",
    },
    {
        "slug": "agent-state", "category": "Agent", "title": "Agent 中的 State 为什么重要？", "difficulty": 3,
        "answer": "State 是跨步骤保存可验证中间结果、上下文和控制信息的显式载体。它让节点之间的数据契约清晰，也便于 checkpoint、重试、恢复、审计和确定哪些字段允许被修改。",
        "code": "state = {'query': '成都三日游', 'documents': [], 'plan': None, 'errors': []}\nstate['documents'] = ['doc-1', 'doc-2']\nprint(state)",
        "followups": "State 和聊天历史有什么区别？|哪些字段应该不可变？|如何做 checkpoint？", "project_link": "MindTrip",
    },
    {
        "slug": "agent-retry", "category": "Agent", "title": "Agent Retry 应该怎样设计边界？", "difficulty": 4,
        "answer": "重试应该针对可恢复错误并设置次数、退避和总预算；带副作用的工具必须先保证幂等或使用 idempotency key。结构化校验失败可以修复后重试，但权限拒绝和业务规则失败通常不应盲目重试。",
        "code": "for attempt in range(3):\n    try:\n        print('attempt', attempt + 1)\n        break\n    except TimeoutError:\n        pass",
        "followups": "哪些错误不应该重试？|指数退避解决什么问题？|重试和补偿有什么区别？", "project_link": "MindTrip / AtlasSplit",
    },
    {
        "slug": "rag-reranker", "category": "RAG", "title": "为什么向量召回之后还需要 Reranker？", "difficulty": 3,
        "answer": "Embedding 检索适合高效粗召回，但相似度不等于最终任务相关性。Reranker 可以对少量候选做更精细的 query-document 相关性判断，提高进入 LLM 上下文的证据质量。",
        "code": "candidates = [('doc-a', 0.81), ('doc-b', 0.79), ('doc-c', 0.74)]\nreranked = sorted(candidates, key=lambda x: {'doc-a': 2, 'doc-b': 3, 'doc-c': 1}[x[0]], reverse=True)\nprint(reranked)",
        "followups": "Reranker 为什么不能直接替代向量检索？|Top-K 怎么选？|如何评估 rerank 是否真的提升？", "project_link": "MindTrip",
    },
    {
        "slug": "rag-chunking", "category": "RAG", "title": "RAG 的 Chunk 大小和 overlap 应该怎么选？", "difficulty": 3,
        "answer": "Chunk 需要在语义完整性、召回粒度、上下文成本之间权衡。应根据文档结构、问题类型和 embedding 模型评测，不存在通用最优值；overlap 可以减少跨边界信息丢失，但会增加索引冗余。",
        "code": "text = 'ABCDEFGHIJKLMN'\nsize, overlap = 6, 2\nstep = size - overlap\nprint([text[i:i+size] for i in range(0, len(text), step)])",
        "followups": "为什么 chunk 越大不一定越好？|按标题结构切分有什么优势？|如何评测 chunking？", "project_link": "MindTrip",
    },
    {
        "slug": "leetcode-two-sum", "category": "LeetCode", "title": "Two Sum：如何从 O(n²) 优化到 O(n)？", "difficulty": 2,
        "answer": "先说明暴力双循环是 O(n²)，再观察到每个元素只需要查找 target - num 是否已出现，因此用 HashMap 记录值到下标，把查找降到均摊 O(1)，总时间 O(n)，空间 O(n)。",
        "code": "def two_sum(nums, target):\n    seen = {}\n    for i, num in enumerate(nums):\n        need = target - num\n        if need in seen:\n            return [seen[need], i]\n        seen[num] = i\n    return []\n\nprint(two_sum([2, 7, 11, 15], 9))",
        "followups": "为什么不能先把当前元素写入 seen？|存在重复数字时是否正确？|空间复杂度是多少？", "project_link": "Coding Interview",
    },
    {
        "slug": "leetcode-sliding-window", "category": "LeetCode", "title": "什么时候适合使用滑动窗口？", "difficulty": 3,
        "answer": "滑动窗口常用于连续子数组或子串问题，当右边界扩展、左边界收缩可以维护某种单调或可增量更新的约束时，把重复扫描优化为线性或接近线性的遍历。",
        "code": "def longest_unique(s):\n    left = 0\n    seen = {}\n    best = 0\n    for right, ch in enumerate(s):\n        if ch in seen and seen[ch] >= left:\n            left = seen[ch] + 1\n        seen[ch] = right\n        best = max(best, right - left + 1)\n    return best\n\nprint(longest_unique('abcabcbb'))",
        "followups": "窗口里应该维护什么状态？|什么时候双指针但不叫滑动窗口？|为什么通常是 O(n)？", "project_link": "Coding Interview",
    },
    {
        "slug": "system-design-code-runner", "category": "System Design", "title": "如何设计一个在线 Python 代码执行平台？", "difficulty": 4,
        "answer": "前端编辑器提交代码到 API，API 将任务发送给独立 Runner。Runner 在受限环境运行，限制 CPU、内存、时间、进程、网络和文件系统，并返回 stdout/stderr。生产环境应使用强隔离沙箱和队列，而不是在主 API 进程 exec 用户代码。",
        "code": "print('Browser -> API -> Queue -> Sandbox Runner -> Result')",
        "followups": "while True 怎么处理？|fork bomb 怎么处理？|网络访问应该默认开还是关？", "project_link": "InterviewOS",
    },
    {
        "slug": "project-mindtrip-validation", "category": "Project", "title": "MindTrip 为什么把 Validate 设计成独立步骤？", "difficulty": 4,
        "answer": "生成模型擅长提出计划但不能天然保证预算、时间冲突、结构契约等硬约束。独立 Validate 可以用确定性规则检查 TripPlan，把可行性和生成能力解耦，并为 Repair 提供明确错误信息。",
        "code": "plan = {'budget': 1300, 'limit': 1000}\nerrors = []\nif plan['budget'] > plan['limit']:\n    errors.append('budget exceeded')\nprint(errors)",
        "followups": "为什么不直接再 Prompt 一次让模型自检？|Validate 应包含哪些确定性规则？|Repair 连续失败怎么办？", "project_link": "MindTrip",
    },
    {
        "slug": "project-atlassplit-approval", "category": "Project", "title": "AtlasSplit 的 Approval Boundary 为什么必须在执行器之前？", "difficulty": 4,
        "answer": "审批的对象应该是已经结构化、校验过但尚未产生副作用的 Plan。执行后再审批已经失去风险控制意义；审批通过后还应保证执行器只执行批准过的不可变计划，并记录 hash 以防篡改。",
        "code": "import hashlib, json\nplan = {'action': 'allocate', 'rows': [1, 2]}\nraw = json.dumps(plan, sort_keys=True).encode()\nprint(hashlib.sha256(raw).hexdigest()[:16])",
        "followups": "审批后 Plan 还能改吗？|如何证明执行的是被批准的版本？|批处理如何做幂等？", "project_link": "AtlasSplit",
    },
]


CODING_CHALLENGES = [
    {
        "slug": "two-sum", "title": "两数之和", "difficulty": 1,
        "description": "给定整数数组 nums 和整数 target，返回两个不同元素的下标，使它们之和等于 target。假设每组输入只有一个有效答案。",
        "function_name": "two_sum",
        "starter_code": "def two_sum(nums, target):\n    # TODO: 返回两个下标\n    pass",
        "reference_solution": "def two_sum(nums, target):\n    seen = {}\n    for i, num in enumerate(nums):\n        need = target - num\n        if need in seen:\n            return [seen[need], i]\n        seen[num] = i",
        "public_tests": '[{"args":[[2,7,11,15],9],"expected":[0,1]},{"args":[[3,2,4],6],"expected":[1,2]}]',
        "hidden_tests": '[{"args":[[3,3],6],"expected":[0,1]},{"args":[[-3,4,3,90],0],"expected":[0,2]},{"args":[[1,5,8,2],10],"expected":[2,3]}]',
        "expected_time": "O(n)", "expected_space": "O(n)",
        "hints": "想想能否在遍历当前元素时，快速判断另一个数是否已经见过。", "tags": "数组|哈希表",
    },
    {
        "slug": "valid-anagram", "title": "有效字母异位词", "difficulty": 1,
        "description": "给定两个只包含小写字母的字符串 s 和 t，判断它们是否由完全相同的字符及出现次数组成。",
        "function_name": "is_anagram",
        "starter_code": "def is_anagram(s, t):\n    pass",
        "reference_solution": "def is_anagram(s, t):\n    if len(s) != len(t):\n        return False\n    count = {}\n    for ch in s:\n        count[ch] = count.get(ch, 0) + 1\n    for ch in t:\n        if ch not in count:\n            return False\n        count[ch] -= 1\n        if count[ch] < 0:\n            return False\n    return True",
        "public_tests": '[{"args":["anagram","nagaram"],"expected":true},{"args":["rat","car"],"expected":false}]',
        "hidden_tests": '[{"args":["",""],"expected":true},{"args":["aacc","ccac"],"expected":false},{"args":["listen","silent"],"expected":true}]',
        "expected_time": "O(n)", "expected_space": "O(k)",
        "hints": "排序可以做，但计数表通常更直接。", "tags": "哈希表|字符串|计数",
    },
    {
        "slug": "max-profit", "title": "买卖股票的最佳时机", "difficulty": 2,
        "description": "给定每天价格 prices，只允许先买一次、后卖一次。返回能获得的最大利润；如果无法盈利则返回 0。",
        "function_name": "max_profit",
        "starter_code": "def max_profit(prices):\n    pass",
        "reference_solution": "def max_profit(prices):\n    min_price = float('inf')\n    best = 0\n    for price in prices:\n        min_price = min(min_price, price)\n        best = max(best, price - min_price)\n    return best",
        "public_tests": '[{"args":[[7,1,5,3,6,4]],"expected":5},{"args":[[7,6,4,3,1]],"expected":0}]',
        "hidden_tests": '[{"args":[[1,2]],"expected":1},{"args":[[2,4,1]],"expected":2},{"args":[[3,3,5,0,0,3,1,4]],"expected":4}]',
        "expected_time": "O(n)", "expected_space": "O(1)",
        "hints": "遍历到某一天时，只需要知道此前最低价格。", "tags": "数组|贪心|单次遍历",
    },
    {
        "slug": "binary-search", "title": "二分查找", "difficulty": 1,
        "description": "给定升序且元素不重复的整数数组 nums 和 target，找到 target 的下标；不存在则返回 -1。",
        "function_name": "binary_search",
        "starter_code": "def binary_search(nums, target):\n    pass",
        "reference_solution": "def binary_search(nums, target):\n    left, right = 0, len(nums) - 1\n    while left <= right:\n        mid = (left + right) // 2\n        if nums[mid] == target:\n            return mid\n        if nums[mid] < target:\n            left = mid + 1\n        else:\n            right = mid - 1\n    return -1",
        "public_tests": '[{"args":[[-1,0,3,5,9,12],9],"expected":4},{"args":[[-1,0,3,5,9,12],2],"expected":-1}]',
        "hidden_tests": '[{"args":[[5],5],"expected":0},{"args":[[5],-5],"expected":-1},{"args":[[1,2,3,4,5,6],1],"expected":0}]',
        "expected_time": "O(log n)", "expected_space": "O(1)",
        "hints": "明确你的区间是闭区间还是半开区间，并保持循环条件一致。", "tags": "数组|二分查找",
    },
    {
        "slug": "longest-substring", "title": "无重复字符的最长子串", "difficulty": 2,
        "description": "给定字符串 s，返回其中不含重复字符的最长连续子串长度。",
        "function_name": "length_of_longest_substring",
        "starter_code": "def length_of_longest_substring(s):\n    pass",
        "reference_solution": "def length_of_longest_substring(s):\n    last = {}\n    left = 0\n    best = 0\n    for right, ch in enumerate(s):\n        if ch in last and last[ch] >= left:\n            left = last[ch] + 1\n        last[ch] = right\n        best = max(best, right - left + 1)\n    return best",
        "public_tests": '[{"args":["abcabcbb"],"expected":3},{"args":["bbbbb"],"expected":1}]',
        "hidden_tests": '[{"args":[""],"expected":0},{"args":["pwwkew"],"expected":3},{"args":["abba"],"expected":2}]',
        "expected_time": "O(n)", "expected_space": "O(k)",
        "hints": "右指针只向前移动；出现重复字符时，让左边界直接跳过上次位置。", "tags": "字符串|滑动窗口|哈希表",
    },
]


async def seed(session: AsyncSession) -> None:
    existing_slugs = set((await session.scalars(select(Question.slug))).all())
    new_questions = [Question(**item) for item in QUESTIONS if item["slug"] not in existing_slugs]
    if new_questions:
        session.add_all(new_questions)

    existing_challenges = set((await session.scalars(select(CodingChallenge.slug))).all())
    new_challenges = [CodingChallenge(**item) for item in CODING_CHALLENGES if item["slug"] not in existing_challenges]
    if new_challenges:
        session.add_all(new_challenges)

    await _seed_prerequisite_graph(session)
    await session.commit()


async def _seed_prerequisite_graph(session: AsyncSession) -> None:
    """Idempotently seed the shared knowledge prerequisite graph. Structure is
    global; per-user progress lives in Mastery (chain == Mastery topic)."""
    from .knowledge_seed import PREREQUISITE_EDGES, knowledge_node_rows

    existing_nodes = set((await session.scalars(select(KnowledgeNode.slug))).all())
    new_nodes = [KnowledgeNode(**row) for row in knowledge_node_rows() if row["slug"] not in existing_nodes]
    if new_nodes:
        session.add_all(new_nodes)

    rows = (await session.execute(select(PrerequisiteEdge.from_slug, PrerequisiteEdge.to_slug))).all()
    existing_edges = {(r[0], r[1]) for r in rows}
    new_edges = [
        PrerequisiteEdge(from_slug=f, to_slug=t)
        for f, t in PREREQUISITE_EDGES
        if (f, t) not in existing_edges
    ]
    if new_edges:
        session.add_all(new_edges)


INITIAL_MASTERY = [
    ("Python / asyncio", 61), ("FastAPI / Depends", 78), ("Database / ORM", 64),
    ("Redis / Cache", 58), ("RAG", 86), ("Agent / Tool Calling", 74),
    ("System Design", 52), ("LeetCode / Algorithms", 57), ("Project", 72),
]

LEGACY_OWNERSHIP_TABLES = (
    AnswerVersion,
    Mastery,
    InterviewSession,
    CodeExplanationAttempt,
    CodingSubmission,
    CodingWrongEntry,
    Repository,
)

# Children of interview_sessions inherit the owner from their claimed session.
LEGACY_SESSION_CHILDREN = (InterviewTurn, InterviewReport)


async def bootstrap_user_workspace(session: AsyncSession, user: User) -> None:
    """Give a brand-new account its initial mastery map and, when this is the
    first account on the instance, claim the pre-auth single-user workbench data
    (rows with user_id NULL) so nothing from a v0.6/v0.7 upgrade is lost."""
    user_count = await session.scalar(select(func.count()).select_from(User)) or 0
    if user_count == 1:
        for model in LEGACY_OWNERSHIP_TABLES:
            await session.execute(update(model).where(model.user_id.is_(None)).values(user_id=user.id))
        owned_sessions = select(InterviewSession.id).where(InterviewSession.user_id == user.id)
        for model in LEGACY_SESSION_CHILDREN:
            await session.execute(
                update(model)
                .where(model.user_id.is_(None), model.session_id.in_(owned_sessions))
                .values(user_id=user.id)
            )

    mastery_count = await session.scalar(
        select(func.count()).select_from(Mastery).where(Mastery.user_id == user.id)
    ) or 0
    if mastery_count == 0:
        now = utc_now()
        rows = []
        for i, (topic, score) in enumerate(INITIAL_MASTERY):
            interval = max(1, i % 5)
            stability, difficulty = legacy_state(score, interval)
            rows.append(Mastery(
                user_id=user.id,
                topic=topic,
                score=score,
                due_at=now + timedelta(days=(i % 3)),
                interval_days=interval,
                stability=stability,
                difficulty=difficulty,
            ))
        session.add_all(rows)
    await session.commit()
