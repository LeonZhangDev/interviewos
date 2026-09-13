import { useEffect, useMemo, useState } from 'react'
import ReactFlow, { Background, Controls, MiniMap, type Node, type Edge } from 'reactflow'
import { GitBranch, Lightbulb, Lock, Network, Search, Target } from 'lucide-react'
import { api } from '../api'
import type {
  KnowledgeGraphData,
  KnowledgeGraphNode,
  PrerequisiteGraph,
  PrerequisiteNode,
  PrerequisiteRecommendation,
} from '../types'
import 'reactflow/dist/style.css'

const kindLabel: Record<string, string> = { category: '知识分类', question: '面试题', project: '项目', repository: '仓库', topic: '技术主题' }
const statsLabel: Record<string, string> = { questions: '面试题', categories: '知识分类', repositories: '仓库', weak_topics: '弱主题' }

function layoutNode(item: KnowledgeGraphNode, index: number, groups: Record<string, number>): Node {
  const column = { project: 0, repository: 0, topic: 1, category: 2, question: 3 }[item.kind] ?? 2
  const row = groups[item.kind] || 0
  groups[item.kind] = row + 1
  const score = typeof item.score === 'number' ? ` · ${Math.round(item.score)}%` : ''
  return {
    id: item.id,
    position: { x: 70 + column * 320, y: 40 + row * 90 },
    data: { label: `${item.label}${score}` },
    style: {
      width: item.kind === 'question' ? 255 : 210,
      borderRadius: 12,
      border: '1px solid #334155',
      background: item.score != null && item.score < 70 ? '#2a1717' : '#111827',
      color: '#e5e7eb',
      padding: 9,
      fontSize: 12,
    },
  }
}

function prereqLayout(graph: PrerequisiteGraph): { nodes: Node[]; edges: Edge[] } {
  const chains = [...new Set(graph.nodes.map((n) => n.chain))].sort()
  const chainRow: Record<string, number> = {}
  chains.forEach((chain, i) => { chainRow[chain] = i })

  const nodes: Node[] = graph.nodes.map((item: PrerequisiteNode) => {
    const mastery = graph.chain_mastery[item.chain]
    const passed = mastery?.score != null && mastery.score >= graph.threshold
    const weak = mastery?.score != null && mastery.score < graph.threshold
    return {
      id: item.slug,
      position: { x: 40 + item.position * 265, y: 30 + chainRow[item.chain] * 96 },
      data: { label: `${item.blocked ? '🔒 ' : ''}${item.label}` },
      style: {
        width: 225,
        borderRadius: 12,
        border: `1px solid ${weak ? '#5b2b2b' : passed ? '#274a3a' : '#334155'}`,
        background: weak ? '#2a1717' : passed ? '#12211b' : '#111827',
        color: item.blocked ? '#9aa4b2' : '#e5e7eb',
        padding: 9,
        fontSize: 11,
        opacity: item.blocked ? 0.82 : 1,
      },
    }
  })

  const edges: Edge[] = graph.edges.map((e) => ({
    id: `${e.from_slug}->${e.to_slug}`,
    source: e.from_slug,
    target: e.to_slug,
    type: 'smoothstep',
    label: e.cross_chain ? '跨链' : undefined,
    animated: e.cross_chain,
    style: { stroke: e.cross_chain ? '#7c6bd6' : '#475569', strokeDasharray: e.cross_chain ? '6 4' : undefined },
    labelStyle: { fill: '#a5a1e8', fontSize: 9 },
    labelBgStyle: { fill: '#161628' },
  }))
  return { nodes, edges }
}

function RelationsView({ data, query, onQuery }: { data: KnowledgeGraphData | null; query: string; onQuery: (value: string) => void }) {
  const [selected, setSelected] = useState<KnowledgeGraphNode | null>(null)
  const [showQuestions, setShowQuestions] = useState(true)

  const visible = useMemo(() => {
    if (!data) return []
    const q = query.trim().toLowerCase()
    return data.nodes.filter((n) => (showQuestions || n.kind !== 'question') && (!q || n.label.toLowerCase().includes(q) || n.kind.toLowerCase().includes(q)))
  }, [data, query, showQuestions])
  const ids = useMemo(() => new Set(visible.map((x) => x.id)), [visible])
  const flowNodes = useMemo(() => {
    const groups: Record<string, number> = {}
    return visible.map((x, i) => layoutNode(x, i, groups))
  }, [visible])
  const flowEdges: Edge[] = useMemo(() => (data?.edges || []).filter((e) => ids.has(e.source) && ids.has(e.target)).map((e) => ({ ...e, label: e.label, animated: e.label === 'relates', style: { stroke: '#475569' }, labelStyle: { fill: '#94a3b8', fontSize: 10 } })), [data, ids])

  return (
    <section className="knowledge-layout">
      <aside className="card knowledge-controls">
        <div className="search-box compact"><Search size={15} /><input value={query} onChange={(e) => onQuery(e.target.value)} placeholder="搜索 Agent / FastAPI / Session…" /></div>
        <label className="toggle-row"><input type="checkbox" checked={showQuestions} onChange={(e) => setShowQuestions(e.target.checked)} /><span>显示具体题目</span></label>
        <div className="legend"><span><i className="legend-dot weak" />弱点 &lt; 70%</span><span><i className="legend-dot normal" />普通节点</span></div>
        {selected ? <div className="selected-node"><span className="eyebrow">已选中</span><h3>{selected.label}</h3><p>{kindLabel[selected.kind] || selected.kind}</p>{typeof selected.score === 'number' ? <div className="selected-score"><Target size={14} /> 掌握度 {Math.round(selected.score)}%</div> : null}</div> : <div className="selected-node muted"><Network size={18} /><p>点击图中节点查看详情。</p></div>}
      </aside>
      <div className="card knowledge-canvas"><ReactFlow nodes={flowNodes} edges={flowEdges} fitView minZoom={0.2} maxZoom={1.6} onNodeClick={(_, node) => setSelected(data?.nodes.find((x) => x.id === node.id) || null)}><Background gap={26} size={1} /><Controls /><MiniMap pannable zoomable /></ReactFlow></div>
    </section>
  )
}

function PrereqView({ graph, recs, focusSlug }: { graph: PrerequisiteGraph | null; recs: PrerequisiteRecommendation[]; focusSlug?: string }) {
  const [selected, setSelected] = useState<PrerequisiteNode | null>(null)
  const layout = useMemo(() => (graph ? prereqLayout(graph) : { nodes: [], edges: [] }), [graph])

  useEffect(() => {
    if (!focusSlug || !graph) return
    setSelected(graph.nodes.find((n) => n.slug === focusSlug) || null)
  }, [focusSlug, graph])

  if (!graph) return <div className="card empty-state">加载前置依赖图…</div>

  const chains = Object.keys(graph.chain_mastery)
  const blockedCount = graph.nodes.filter((n) => n.blocked).length
  const weakChains = chains.filter((c) => {
    const m = graph.chain_mastery[c]
    return m.score != null && m.score < graph.threshold
  }).length

  return (
    <section className="knowledge-layout prereq-layout">
      <aside className="card knowledge-controls">
        <div className="prereq-stats">
          <div><strong>{chains.length}</strong><span>知识链</span></div>
          <div><strong>{graph.nodes.length}</strong><span>知识点</span></div>
          <div><strong>{blockedCount}</strong><span>被阻塞</span></div>
          <div><strong>{weakChains}</strong><span>弱链</span></div>
        </div>
        <div className="legend"><span><i className="legend-dot weak" />弱链 &lt; {Math.round(graph.threshold)}%</span><span><i className="legend-dot normal" />达标链</span><span><i className="legend-dot lock" />被阻塞</span></div>
        {selected ? (
          <div className="selected-node">
            <span className="eyebrow">{selected.chain}</span>
            <h3>{selected.label}</h3>
            <p>{selected.description}</p>
            {selected.blocked ? <div className="selected-score prereq-lock"><Lock size={14} /> 前置未达标：{selected.weak_prereqs.join('、')}</div> : null}
          </div>
        ) : <div className="selected-node muted"><GitBranch size={18} /><p>点击节点查看说明；🔒 表示前置链未达标。</p></div>}
      </aside>
      <div className="card knowledge-canvas"><ReactFlow nodes={layout.nodes} edges={layout.edges} fitView minZoom={0.15} maxZoom={1.4} onNodeClick={(_, node) => setSelected(graph.nodes.find((x) => x.slug === node.id) || null)}><Background gap={26} size={1} /><Controls /><MiniMap pannable zoomable /></ReactFlow></div>
      <aside className="card prereq-recs">
        <div className="section-title"><Lightbulb size={14} /><b>解锁建议</b><p>按“阻塞的下游知识点数”排序，先补弱前置。</p></div>
        {recs.length === 0 && <p className="history-empty">所有知识链均已达标。</p>}
        {recs.map((rec) => (
          <div className="rec-card" key={rec.chain}>
            <div className="rec-head"><b>{rec.chain}</b>{rec.score != null ? <span>{Math.round(rec.score)}%</span> : <span>未开始</span>}</div>
            <p>{rec.reason}</p>
            <div className="rec-steps">从 <b>{rec.first_steps[0]}</b> → <b>{rec.first_steps[1]}</b> 开始复习</div>
          </div>
        ))}
      </aside>
    </section>
  )
}

export function KnowledgeGraphPage({ focusNodeSlug }: { focusNodeSlug?: string }) {
  const [data, setData] = useState<KnowledgeGraphData | null>(null)
  const [prereq, setPrereq] = useState<PrerequisiteGraph | null>(null)
  const [recs, setRecs] = useState<PrerequisiteRecommendation[]>([])
  const [query, setQuery] = useState('')
  const [view, setView] = useState<'relations' | 'prereq'>('relations')

  useEffect(() => { api.knowledgeGraph().then(setData) }, [])
  useEffect(() => {
    if (view === 'prereq' && !prereq) {
      api.prerequisiteGraph().then(setPrereq)
      api.prerequisiteRecommendations().then(setRecs)
    }
  }, [view, prereq])
  useEffect(() => { if (focusNodeSlug) setView('prereq') }, [focusNodeSlug])

  return (
    <div className="page-stack">
      <div className="page-header">
        <div><span className="eyebrow">知识图谱</span><h1>{view === 'relations' ? '从“我会多少题”变成“我到底卡在哪条知识链”。' : '前置依赖图：先补弱前置，再解锁下游。'}</h1><p>{view === 'relations' ? '把项目、仓库技术、知识分类、面试题和掌握度放到一张关系图里。低于 70% 的已评分节点会被标成弱点。' : '知识点按依赖顺序分层（GIL → 线程 → 竞态 → 锁…）；弱链会把下游知识点标成“被阻塞”，解锁建议告诉你先补哪里。'}</p></div>
        <div className="view-switch">
          <button className={view === 'relations' ? 'active' : ''} onClick={() => setView('relations')}>关系图</button>
          <button className={view === 'prereq' ? 'active' : ''} onClick={() => setView('prereq')}>前置依赖</button>
        </div>
      </div>
      <div className="knowledge-stats">{view === 'relations'
        ? Object.entries(data?.stats || {}).map(([k, v]) => <div className="card" key={k}><strong>{String(v)}</strong><span>{statsLabel[k] ?? k}</span></div>)
        : <>
            <div className="card"><strong>{Object.keys(prereq?.chain_mastery || {}).length}</strong><span>知识链</span></div>
            <div className="card"><strong>{prereq?.nodes.length || 0}</strong><span>知识点</span></div>
            <div className="card"><strong>{prereq?.nodes.filter((n) => n.blocked).length || 0}</strong><span>被阻塞</span></div>
            <div className="card"><strong>{recs.length}</strong><span>弱链</span></div>
          </>}</div>
      {view === 'relations' ? <RelationsView data={data} query={query} onQuery={setQuery} /> : <PrereqView graph={prereq} recs={recs} focusSlug={focusNodeSlug} />}
    </div>
  )
}
