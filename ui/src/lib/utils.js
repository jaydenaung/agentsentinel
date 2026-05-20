export const STATUS_COLORS = {
  TRUSTED: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/30', dot: 'bg-emerald-400' },
  WATCH:   { bg: 'bg-yellow-500/10',  text: 'text-yellow-400',  border: 'border-yellow-500/30',  dot: 'bg-yellow-400' },
  ALERT:   { bg: 'bg-orange-500/10',  text: 'text-orange-400',  border: 'border-orange-500/30',  dot: 'bg-orange-400' },
  CRITICAL:{ bg: 'bg-red-500/10',     text: 'text-red-400',     border: 'border-red-500/30',     dot: 'bg-red-400' },
}

export const SEVERITY_COLORS = {
  CRITICAL: { bg: 'bg-red-500/10',    text: 'text-red-400',    border: 'border-red-500/30' },
  HIGH:     { bg: 'bg-orange-500/10', text: 'text-orange-400', border: 'border-orange-500/30' },
  MEDIUM:   { bg: 'bg-yellow-500/10', text: 'text-yellow-400', border: 'border-yellow-500/30' },
  LOW:      { bg: 'bg-blue-500/10',   text: 'text-blue-400',   border: 'border-blue-500/30' },
}

export function scoreBar(score) {
  if (score === null || score === undefined) return 'bg-slate-700'
  if (score >= 80) return 'bg-emerald-500'
  if (score >= 60) return 'bg-yellow-500'
  if (score >= 40) return 'bg-orange-500'
  return 'bg-red-500'
}

export function fmtScore(v) {
  return v === null || v === undefined ? '—' : v.toFixed(1)
}

export function fmtDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export function fmtAgo(iso) {
  if (!iso) return '—'
  const secs = Math.floor((Date.now() - new Date(iso)) / 1000)
  if (secs < 60) return `${secs}s ago`
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`
  return `${Math.floor(secs / 86400)}d ago`
}
