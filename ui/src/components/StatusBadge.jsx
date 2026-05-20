import { STATUS_COLORS, SEVERITY_COLORS } from '../lib/utils'

export function StatusBadge({ status }) {
  const c = STATUS_COLORS[status] ?? STATUS_COLORS.WATCH
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border ${c.bg} ${c.text} ${c.border}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {status}
    </span>
  )
}

export function SeverityBadge({ severity }) {
  const c = SEVERITY_COLORS[severity] ?? SEVERITY_COLORS.LOW
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${c.bg} ${c.text} ${c.border}`}>
      {severity}
    </span>
  )
}
