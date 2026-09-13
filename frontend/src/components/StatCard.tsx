import type { ReactNode } from 'react'

export function StatCard({ label, value, hint, icon }: { label: string; value: ReactNode; hint: string; icon?: ReactNode }) {
  return (
    <div className="stat-card card">
      <div className="stat-card-head">
        <span>{label}</span>
        {icon}
      </div>
      <strong>{value}</strong>
      <small>{hint}</small>
    </div>
  )
}
