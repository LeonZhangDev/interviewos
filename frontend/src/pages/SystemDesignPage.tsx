import { useCallback, useEffect, useState } from 'react'
import ReactFlow, { Background, Controls, MiniMap, addEdge, useEdgesState, useNodesState, type Connection, type Node } from 'reactflow'
import { BrainCircuit, CheckCircle2, Cloud, Database, Network, Save, Server, Trash2, Workflow } from 'lucide-react'
import { api } from '../api'
import type { SystemDesignCase } from '../types'
import 'reactflow/dist/style.css'

const palette = ['Client', 'API Gateway', 'FastAPI', 'Auth', 'Redis', 'PostgreSQL', 'Vector DB', 'Queue', 'Worker', 'LLM', 'Sandbox']

export function SystemDesignPage() {
  const [cases, setCases] = useState<SystemDesignCase[]>([])
  const [active, setActive] = useState<SystemDesignCase | null>(null)
  const [answer, setAnswer] = useState('')
  const [result, setResult] = useState<any>(null)
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [canvasMessage, setCanvasMessage] = useState('')

  useEffect(() => { api.systemDesignCases().then((items) => { setCases(items); setActive(items[0] ?? null) }) }, [])
  useEffect(() => {
    if (!active) return
    api.getCanvas(active.id).then((saved) => {
      setNodes((saved.nodes || []) as Node[])
      setEdges((saved.edges || []) as any[])
      setCanvasMessage(saved.updated_at ? `上次保存：${new Date(saved.updated_at).toLocaleString()}` : '还没有保存白板')
    })
  }, [active, setNodes, setEdges])

  const onConnect = useCallback((connection: Connection) => setEdges((eds) => addEdge({ ...connection, label: '调用', animated: true }, eds)), [setEdges])

  function addComponent(label: string) {
    const index = nodes.length
    setNodes((current) => [...current, {
      id: `node-${Date.now()}-${index}`,
      position: { x: 70 + (index % 4) * 190, y: 60 + Math.floor(index / 4) * 125 },
      data: { label },
      style: { width: 150, padding: 10, borderRadius: 12, border: '1px solid #334155', background: '#111827', color: '#e5e7eb', fontSize: 12, fontWeight: 650 },
    }])
  }

  async function saveCanvas() {
    if (!active) return
    const saved = await api.saveCanvas({ case_id: active.id, title: active.title, nodes: nodes as any[], edges: edges as any[] })
    setCanvasMessage(`已保存：${new Date(saved.updated_at || Date.now()).toLocaleString()}`)
  }

  async function evaluate() {
    if (!active || !answer.trim()) return
    setResult(await api.evaluateSystemDesign(active.id, answer.trim()))
  }

  function chooseCase(item: SystemDesignCase) {
    setActive(item); setAnswer(''); setResult(null); setNodes([]); setEdges([]); setCanvasMessage('加载白板…')
  }

  return (
    <div className="page-stack">
      <div className="page-header"><div><span className="eyebrow">系统设计实战</span><h1>先在白板上搭架构，再解释为什么。</h1><p>v0.7 把系统设计升级成可拖动/连线/保存的 React Flow 白板。架构图负责“你画了什么”，文字回答负责“你为什么这么设计”。</p></div></div>
      <div className="system-layout">
        <aside className="card system-case-list">{cases.map((item) => <button key={item.id} className={active?.id === item.id ? 'active' : ''} onClick={() => chooseCase(item)}><Network size={16} /><span>{item.title}</span></button>)}</aside>
        <section className="card panel system-workspace">
          {active ? <>
            <span className="eyebrow">案例</span><h1>{active.title}</h1>
            <div className="requirements-row">{active.requirements.map((x) => <span className="tag" key={x}>{x}</span>)}</div>
            <div className="whiteboard-toolbar"><div className="component-palette">{palette.map((x) => <button key={x} onClick={() => addComponent(x)}>{x === 'PostgreSQL' || x.includes('DB') ? <Database size={13} /> : x === 'LLM' ? <Cloud size={13} /> : x === 'Queue' || x === 'Worker' ? <Workflow size={13} /> : <Server size={13} />}{x}</button>)}</div><div className="button-row"><button className="secondary" onClick={() => { setNodes([]); setEdges([]) }}><Trash2 size={14} /> 清空</button><button className="primary" onClick={saveCanvas}><Save size={14} /> 保存白板</button></div></div>
            <div className="system-whiteboard"><ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} fitView deleteKeyCode={['Backspace', 'Delete']}><Background gap={24} /><Controls /><MiniMap pannable /></ReactFlow></div>
            <small className="canvas-status">{canvasMessage} · 拖动节点边缘连接组件，选中后 Delete 可删除。</small>
            <label className="field-label">你的设计解释</label><textarea className="system-answer" value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="建议写：需求假设 → 核心组件 → 数据流 → 容量 → 失败恢复 → 安全 → 可观测…" />
            <button className="primary" onClick={evaluate} disabled={!answer.trim()}><BrainCircuit size={15} /> 评价设计</button>
            {result ? <div className="system-result"><div className="result-score"><CheckCircle2 /><strong>{result.score}</strong><span>/100</span></div><p>{result.feedback}</p><div className="dimension-grid">{Object.entries(result.dimensions || {}).map(([k, v]) => <div key={k}><span>{k}</span><strong>{String(v)}</strong></div>)}</div><div className="followup-box"><span className="eyebrow">面试官追问</span><p>{result.next_followup}</p></div></div> : null}
            <details className="detail-box"><summary>题目自带追问</summary>{active.followups.map((x) => <p key={x}>→ {x}</p>)}</details>
          </> : null}
        </section>
      </div>
    </div>
  )
}
