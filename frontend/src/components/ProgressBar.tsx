export function ProgressBar({ value }: { value: number }) {
  return (
    <div className="progress-track" aria-label={`掌握度 ${value}%`}>
      <div className="progress-fill" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  )
}
