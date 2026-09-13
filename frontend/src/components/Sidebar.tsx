import {
  BarChart3,
  Blocks,
  BookOpenCheck,
  BrainCircuit,
  BriefcaseBusiness,
  Code2,
  FileInput,
  FlaskConical,
  FolderGit2,
  LayoutDashboard,
  LineChart,
  Network,
} from 'lucide-react'
import type { NavKey } from '../types'

const items: { key: NavKey; label: string; icon: typeof LayoutDashboard }[] = [
  { key: 'dashboard', label: '仪表盘', icon: LayoutDashboard },
  { key: 'projects', label: '项目', icon: FolderGit2 },
  { key: 'questions', label: '题库', icon: BookOpenCheck },
  { key: 'coding', label: 'Coding 实验室', icon: Code2 },
  { key: 'playgrounds', label: '沙箱实操', icon: FlaskConical },
  { key: 'interview', label: 'AI 面试', icon: BrainCircuit },
  { key: 'reports', label: '面试报告', icon: LineChart },
  { key: 'learning', label: '学习复习', icon: BarChart3 },
  { key: 'knowledge', label: '知识图谱', icon: Network },
  { key: 'import', label: '题目导入', icon: FileInput },
  { key: 'system', label: '系统设计', icon: Blocks },
  { key: 'portfolio', label: '作品集管理', icon: BriefcaseBusiness },
]

export function Sidebar({ active, onChange }: { active: NavKey; onChange: (key: NavKey) => void }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">IO</div>
        <div>
          <strong>InterviewOS</strong>
          <span>AI 工程师面试工作台</span>
        </div>
      </div>
      <nav className="nav-list">
        {items.map(({ key, label, icon: Icon }) => (
          <button className={active === key ? 'nav-item active' : 'nav-item'} key={key} onClick={() => onChange(key)}>
            <Icon size={18} />
            <span>{label}</span>
          </button>
        ))}
      </nav>
      <div className="sidebar-card">
        <span className="eyebrow">当前目标</span>
        <strong>AI / Agent 工程师</strong>
        <p>项目深挖 · Python · FastAPI · Agent · Coding</p>
      </div>
    </aside>
  )
}
