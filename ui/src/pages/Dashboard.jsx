import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { fmtScore, fmtAgo } from '../lib/utils'
import { StatusBadge } from '../components/StatusBadge'
import { ScoreBar } from '../components/ScoreBar'

const STATUS_ORDER = { CRITICAL: 0, ALERT: 1, WATCH: 2, TRUSTED: 3 }

export default function Dashboard() {
  const [agents, setAgents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('')
  const navigate = useNavigate()

  async function load() {
    try {
      const data = await api.agents.list()
      setAgents(data.sort((a, b) => (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9)))
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function rescore(e, id) {
    e.stopPropagation()
    await api.agents.score(id)
    load()
  }

  const counts = agents.reduce((acc, a) => {
    acc[a.status] = (acc[a.status] || 0) + 1
    return acc
  }, {})

  const visible = filter
    ? agents.filter(a => a.status === filter)
    : agents

  if (loading) return <div className="text-slate-400 py-20 text-center">Loading agents…</div>
  if (error) return <div className="text-red-400 py-20 text-center">Error: {error}</div>

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'CRITICAL', color: 'border-red-500/40 bg-red-500/5 text-red-400' },
          { label: 'ALERT',    color: 'border-orange-500/40 bg-orange-500/5 text-orange-400' },
          { label: 'WATCH',    color: 'border-yellow-500/40 bg-yellow-500/5 text-yellow-400' },
          { label: 'TRUSTED',  color: 'border-emerald-500/40 bg-emerald-500/5 text-emerald-400' },
        ].map(({ label, color }) => (
          <button
            key={label}
            onClick={() => setFilter(filter === label ? '' : label)}
            className={`rounded-lg border p-4 text-left transition-all ${color} ${filter === label ? 'ring-1 ring-white/20' : 'hover:brightness-125'}`}
          >
            <div className="text-2xl font-bold">{counts[label] ?? 0}</div>
            <div className="text-xs opacity-70 mt-0.5">{label}</div>
          </button>
        ))}
      </div>

      {/* Agents table */}
      <div className="rounded-lg border border-slate-800 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800 bg-slate-900/40">
          <span className="text-sm font-medium text-slate-200">
            {filter ? `${filter} agents` : 'All agents'}
            <span className="ml-2 text-slate-500 font-normal">({visible.length})</span>
          </span>
          <button onClick={load} className="text-xs text-slate-400 hover:text-slate-200 transition-colors">
            ↻ Refresh
          </button>
        </div>

        {visible.length === 0 ? (
          <div className="py-16 text-center text-slate-500 text-sm">
            No agents yet. <button onClick={() => navigate('/register')} className="text-violet-400 hover:underline">Register one →</button>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800 text-xs text-slate-500 uppercase tracking-wide">
                <th className="text-left px-4 py-2.5">Agent</th>
                <th className="text-left px-4 py-2.5 hidden sm:table-cell">Type / Model</th>
                <th className="text-left px-4 py-2.5">Status</th>
                <th className="text-left px-4 py-2.5 hidden md:table-cell">Trust Score</th>
                <th className="text-left px-4 py-2.5 hidden lg:table-cell">Last Scored</th>
                <th className="text-right px-4 py-2.5"></th>
              </tr>
            </thead>
            <tbody>
              {visible.map((agent, i) => (
                <tr
                  key={agent.id}
                  onClick={() => navigate(`/agents/${agent.id}`)}
                  className={`border-b border-slate-800/50 cursor-pointer hover:bg-slate-800/40 transition-colors
                    ${i === visible.length - 1 ? 'border-b-0' : ''}`}
                >
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-100">{agent.name}</div>
                    <div className="text-xs text-slate-500">{agent.owner_team}</div>
                  </td>
                  <td className="px-4 py-3 hidden sm:table-cell">
                    <div className="text-slate-300">{agent.agent_type}</div>
                    <div className="text-xs text-slate-500 font-mono">{agent.model}</div>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={agent.status} />
                  </td>
                  <td className="px-4 py-3 hidden md:table-cell w-36">
                    <div className="space-y-1">
                      <ScoreBar score={agent.trust_score} size="sm" />
                      <div className="text-xs text-slate-400">{fmtScore(agent.trust_score)}</div>
                    </div>
                  </td>
                  <td className="px-4 py-3 hidden lg:table-cell text-xs text-slate-500">
                    {fmtAgo(agent.last_scored_at)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={(e) => rescore(e, agent.id)}
                      className="text-xs text-slate-500 hover:text-violet-400 transition-colors px-2 py-1 rounded hover:bg-violet-500/10"
                    >
                      Rescore
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
