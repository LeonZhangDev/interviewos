"""Shared prerequisite-graph seed data.

Chains map 1:1 onto the seeded Mastery topics (INITIAL_MASTERY in seed.py),
so every user's mastery score applies to the chain as a whole while the
graph structure (nodes, edges, layers) stays identical for everyone.

A handful of cross-chain edges encode real dependencies between tracks,
e.g. FastAPI async endpoints need the asyncio event loop, distributed Redis
locks and database isolation levels both build on understanding race
conditions.
"""
from __future__ import annotations

KNOWLEDGE_CHAINS: dict[str, list[dict]] = {
    "Python / asyncio": [
        {"slug": "gil", "label": "GIL", "description": "CPython 全局解释器锁：同进程内通常只有一个线程执行字节码。"},
        {"slug": "thread", "label": "Thread", "description": "线程与 GIL 的交互；I/O 等待时释放执行权。"},
        {"slug": "coroutine", "label": "Coroutine 协程", "description": "协程对象与 await 挂起/恢复机制。"},
        {"slug": "task", "label": "Task", "description": "事件循环对协程的调度单元。"},
        {"slug": "event-loop", "label": "Event Loop 事件循环", "description": "单线程调度器：就绪回调、定时器、I/O 多路复用。"},
        {"slug": "race-condition", "label": "Race Condition 竞态", "description": "单线程协程在 await 边界交错导致的共享状态问题。"},
        {"slug": "lock", "label": "Lock", "description": "asyncio.Lock 保护临界区。"},
        {"slug": "semaphore", "label": "Semaphore", "description": "限并发访问的信号量。"},
    ],
    "FastAPI / Depends": [
        {"slug": "decorator", "label": "Decorator 装饰器", "description": "路由装饰器把函数注册为端点。"},
        {"slug": "router", "label": "Router", "description": "路由分组与前缀组织。"},
        {"slug": "depends", "label": "Depends 依赖注入", "description": "声明式依赖：解析、缓存、横切逻辑。"},
        {"slug": "middleware", "label": "Middleware 中间件", "description": "请求/响应管线中的横切处理。"},
        {"slug": "async-endpoint", "label": "Async Endpoint", "description": "异步端点与事件循环的配合。"},
    ],
    "Database / ORM": [
        {"slug": "index", "label": "Index 索引", "description": "B-Tree 索引与查询代价。"},
        {"slug": "join", "label": "Join", "description": "连接的类型与笛卡尔积陷阱。"},
        {"slug": "n-plus-one", "label": "N+1 查询", "description": "循环触发的隐式查询问题。"},
        {"slug": "eager-load", "label": "Eager Load 预加载", "description": "joinedload / selectinload 消除 N+1。"},
        {"slug": "transaction", "label": "Transaction 事务", "description": "原子性、提交与回滚边界。"},
        {"slug": "isolation", "label": "Isolation 隔离级别", "description": "脏读/不可重复读/幻读与隔离级别选择。"},
    ],
    "Redis / Cache": [
        {"slug": "cache-aside", "label": "Cache-Aside", "description": "旁路缓存模式：读缓存、miss 回源、写更新。"},
        {"slug": "ttl", "label": "TTL 过期", "description": "过期时间与缓存一致性窗口。"},
        {"slug": "nx-lock", "label": "SET NX 锁", "description": "SET key value NX PX 的原子加锁。"},
        {"slug": "distributed-lock", "label": "Distributed Lock", "description": "锁续期、误删防护（token）与 Redlock 争议。"},
    ],
    "RAG": [
        {"slug": "chunking", "label": "Chunking 分块", "description": "文档切分策略对检索粒度的影响。"},
        {"slug": "embedding", "label": "Embedding", "description": "文本向量化与语义相似度。"},
        {"slug": "vector-search", "label": "Vector Search 向量检索", "description": "ANN 索引与 top-k 召回。"},
        {"slug": "reranker", "label": "Reranker 重排", "description": "交叉编码器精排提升相关性。"},
        {"slug": "rag-pipeline", "label": "RAG Pipeline", "description": "Retrieve → Rerank → Generate 全链路。"},
    ],
    "Agent / Tool Calling": [
        {"slug": "tool-schema", "label": "Tool Schema", "description": "JSON Schema 描述工具参数。"},
        {"slug": "tool-calling", "label": "Tool Calling", "description": "模型输出结构化调用并回注结果。"},
        {"slug": "agent-loop", "label": "Agent Loop", "description": "计划-执行-观察循环与终止条件。"},
        {"slug": "approval", "label": "Approval 审批边界", "description": "高风险动作前的显式确认。"},
        {"slug": "audit", "label": "Audit 审计", "description": "可追溯的执行记录与幂等保障。"},
    ],
    "System Design": [
        {"slug": "queue", "label": "Queue 消息队列", "description": "削峰、解耦与重投递语义。"},
        {"slug": "worker", "label": "Worker", "description": "消费者组、水平扩展与背压。"},
        {"slug": "idempotency", "label": "Idempotency 幂等", "description": "重试/重投下结果一致：唯一键与去重。"},
        {"slug": "rate-limit", "label": "Rate Limit 限流", "description": "令牌桶/漏桶保护下游。"},
        {"slug": "scale-out", "label": "Scale Out 水平扩展", "description": "无状态化与分区扩展路径。"},
    ],
    "LeetCode / Algorithms": [
        {"slug": "complexity", "label": "Complexity 复杂度", "description": "时间/空间复杂度分析。"},
        {"slug": "hash-map", "label": "Hash Map 哈希表", "description": "O(1) 查找与去重。"},
        {"slug": "binary-search", "label": "Binary Search 二分查找", "description": "有序区间收缩与边界。"},
        {"slug": "two-pointers", "label": "Two Pointers 双指针", "description": "对撞/快慢指针。"},
        {"slug": "sliding-window", "label": "Sliding Window 滑动窗口", "description": "可变窗口与状态维护。"},
    ],
}

# from -> to: "to" requires "from" first. Cross-chain edges are the last three.
PREREQUISITE_EDGES: list[tuple[str, str]] = [
    # Python / asyncio
    ("gil", "thread"),
    ("thread", "race-condition"),
    ("coroutine", "task"),
    ("task", "event-loop"),
    ("event-loop", "race-condition"),
    ("race-condition", "lock"),
    ("lock", "semaphore"),
    # FastAPI / Depends
    ("decorator", "router"),
    ("router", "depends"),
    ("depends", "middleware"),
    ("router", "async-endpoint"),
    # Database / ORM
    ("index", "join"),
    ("join", "n-plus-one"),
    ("n-plus-one", "eager-load"),
    ("transaction", "isolation"),
    # Redis / Cache
    ("cache-aside", "ttl"),
    ("ttl", "nx-lock"),
    ("nx-lock", "distributed-lock"),
    # RAG
    ("chunking", "embedding"),
    ("embedding", "vector-search"),
    ("vector-search", "reranker"),
    ("reranker", "rag-pipeline"),
    # Agent / Tool Calling
    ("tool-schema", "tool-calling"),
    ("tool-calling", "agent-loop"),
    ("agent-loop", "approval"),
    ("approval", "audit"),
    # System Design
    ("queue", "worker"),
    ("queue", "idempotency"),
    ("worker", "rate-limit"),
    ("rate-limit", "scale-out"),
    # LeetCode / Algorithms
    ("complexity", "hash-map"),
    ("complexity", "binary-search"),
    ("hash-map", "sliding-window"),
    ("sliding-window", "two-pointers"),
    # cross-chain
    ("async-endpoint", "event-loop"),
    ("isolation", "race-condition"),
    ("nx-lock", "race-condition"),
]


def knowledge_node_rows() -> list[dict]:
    rows: list[dict] = []
    for chain, items in KNOWLEDGE_CHAINS.items():
        for position, item in enumerate(items):
            rows.append({
                "slug": item["slug"],
                "label": item["label"],
                "chain": chain,
                "description": item["description"],
                "position": position,
            })
    return rows
