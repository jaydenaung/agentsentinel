import { scoreBar, fmtScore } from '../lib/utils'

export function ScoreBar({ score, label, size = 'md' }) {
  const pct = score === null || score === undefined ? 0 : Math.min(100, Math.max(0, score))
  const color = scoreBar(score)
  const h = size === 'sm' ? 'h-1' : 'h-1.5'

  return (
    <div className="w-full">
      {label && (
        <div className="flex justify-between text-xs text-slate-400 mb-1">
          <span>{label}</span>
          <span className="text-slate-200 font-medium">{fmtScore(score)}</span>
        </div>
      )}
      <div className={`w-full ${h} bg-slate-700 rounded-full overflow-hidden`}>
        <div
          className={`${h} ${color} rounded-full transition-all duration-500`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
