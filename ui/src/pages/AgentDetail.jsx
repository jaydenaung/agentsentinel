import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { fmtScore, fmtDate, fmtAgo } from '../lib/utils'
import { StatusBadge, SeverityBadge } from '../components/StatusBadge'
import { ScoreBar } from '../components/ScoreBar'

function Card({ title, children }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/30 overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-800">
        <h2 className="text-sm font-medium text-slate-200">{title}</h2>
      </div>
      <div className="p-4">{children}</div>
    </div>
  )
}

function FindingRow({ finding, onUpdate }) {
  const [updating, setUpdating] = useState(false)

  async function handle(status) {
    setUpdating(true)
    try {
      await api.findings.update(finding.id, status)
      onUpdate()
    } finally {
      setUpdating(false)
    }
  }

  return (
    <div className="py-3 border-b border-slate-800/50 last:border-0">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <SeverityBadge severity={finding.severity} />
            <span className="text-xs font-mono text-slate-400">{finding.rule_id}</span>
            {finding.status !== 'OPEN' && (
              <span className="text-xs text-slate-500 italic">{finding.status.toLowerCase()}</span>
            )}
          </div>
          <p className="text-sm text-slate-300 mt-1.5 leading-relaxed">{finding.message}</p>
          <div className="text-xs text-slate-500 mt-1">{fmtDate(finding.created_at)}</div>
        </div>
        {finding.status === 'OPEN' && (
          <div className="flex gap-1 shrink-0">
            <button
              disabled={updating}
              onClick={() => handle('ACKNOWLEDGED')}
              className="text-xs px-2 py-1 rounded border border-slate-700 text-slate-400 hover:text-yellow-400 hover:border-yellow-500/40 transition-colors disabled:opacity-50"
            >
              Ack
            </button>
            <button
              disabled={updating}
              onClick={() => handle('RESOLVED')}
              className="text-xs px-2 py-1 rounded border border-slate-700 text-slate-400 hover:text-emerald-400 hover:border-emerald-500/40 transition-colors disabled:opacity-50"
            >
              Resolve
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default function AgentDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [agent, setAgent] = useState(null)
  const [findings, setFindings] = useState([])
  const [score, setScore] = useState(null)
  const [loading, setLoading] = useState(true)
  const [rescoring, setRescoring] = useState(false)
  const [findingFilter, setFindingFilter] = useState('OPEN')

  async function load() {
    try {
      const [a, f] = await Promise.all([
        api.agents.get(id),
        api.agents.findings(id),
      ])
      setAgent(a)
      setFindings(f)
      setScore({ trust_score: a.trust_score, posture_score: a.posture_score, behavior_score: a.behavior_score })
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [id])

  async function rescore() {
    setRescoring(true)
    try {
      const s = await api.agents.score(id)
      setScore(s)
      await load()
    } finally {
      setRescoring(false)
    }
  }

  if (loading) return <div className="text-slate-400 py-20 text-center">Loading…</div>
  if (!agent) return <div className="text-red-400 py-20 text-center">Agent not found</div>

  const visibleFindings = findings.filter(f => findingFilter === 'ALL' || f.status === findingFilter)

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <button onClick={() => navigate('/')} className="text-xs text-slate-500 hover:text-slate-300 mb-2 block">
            ← All agents
          </button>
          <h1 className="text-xl font-semibold text-white">{agent.name}</h1>
          <div className="flex items-center gap-3 mt-1 text-sm text-slate-400">
            <span>{agent.agent_type}</span>
            <span>·</span>
            <span className="font-mono text-xs">{agent.model}</span>
            <span>·</span>
            <span>{agent.owner_team}</span>
          </div>
          {agent.description && (
            <p className="text-sm text-slate-400 mt-2">{agent.description}</p>
          )}
        </div>
        <div className="flex flex-col items-end gap-2 shrink-0">
          <StatusBadge status={agent.status} />
          <button
            onClick={rescore}
            disabled={rescoring}
            className="text-xs px-3 py-1.5 rounded border border-violet-500/30 text-violet-400 hover:bg-violet-500/10 transition-colors disabled:opacity-50"
          >
            {rescoring ? 'Scoring…' : '↻ Rescore'}
          </button>
        </div>
      </div>

      {/* Score breakdown */}
      <Card title="Trust Score">
        <div className="flex items-center gap-4 mb-4">
          <div className="text-4xl font-bold text-white">{fmtScore(score?.trust_score ?? agent.trust_score)}</div>
          <div className="text-sm text-slate-400">
            <div>Last scored {fmtAgo(agent.last_scored_at)}</div>
          </div>
        </div>
        <div className="space-y-3">
          <ScoreBar score={score?.posture_score ?? agent.posture_score} label="Posture (×0.45)" />
          <ScoreBar score={score?.behavior_score ?? agent.behavior_score} label="Behavior (×0.45)" />
        </div>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* Tool Grants */}
        <Card title={`Tool Grants (${agent.grants.length})`}>
          {agent.grants.length === 0 ? (
            <p className="text-sm text-slate-500">No grants configured.</p>
          ) : (
            <div className="space-y-2">
              {agent.grants.map(g => (
                <div key={g.id} className="flex items-center justify-between text-sm py-1.5 border-b border-slate-800/50 last:border-0">
                  <div>
                    <span className="text-slate-200 font-mono text-xs">{g.tool_name}</span>
                    {g.scope && <span className="ml-2 text-xs text-slate-500">{g.scope}</span>}
                  </div>
                  <div className="flex items-center gap-2">
                    {g.is_dangerous && (
                      <span className="text-xs px-1.5 py-0.5 rounded border border-red-500/30 text-red-400 bg-red-500/10">
                        dangerous
                      </span>
                    )}
                    <span className="text-xs text-slate-500">{g.call_count_7d}×/7d</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* MCP Connections */}
        <Card title={`MCP Connections (${agent.mcp_connections.length})`}>
          {agent.mcp_connections.length === 0 ? (
            <p className="text-sm text-slate-500">No MCP connections.</p>
          ) : (
            <div className="space-y-2">
              {agent.mcp_connections.map(c => (
                <div key={c.id} className="py-1.5 border-b border-slate-800/50 last:border-0">
                  <div className="text-sm text-slate-200 font-medium">{c.server_name}</div>
                  <div className="text-xs text-slate-500 font-mono mt-0.5 truncate">{c.server_url}</div>
                  {c.capabilities?.length > 0 && (
                    <div className="flex gap-1 mt-1 flex-wrap">
                      {c.capabilities.map(cap => (
                        <span key={cap} className="text-xs px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">{cap}</span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Findings */}
      <Card title="Security Findings">
        <div className="flex gap-2 mb-4">
          {['OPEN', 'ACKNOWLEDGED', 'RESOLVED', 'ALL'].map(s => (
            <button
              key={s}
              onClick={() => setFindingFilter(s)}
              className={`text-xs px-2.5 py-1 rounded border transition-colors
                ${findingFilter === s
                  ? 'border-violet-500/40 bg-violet-500/10 text-violet-300'
                  : 'border-slate-700 text-slate-400 hover:text-slate-200'}`}
            >
              {s}
            </button>
          ))}
        </div>
        {visibleFindings.length === 0 ? (
          <p className="text-sm text-slate-500">No {findingFilter.toLowerCase()} findings.</p>
        ) : (
          <div>
            {visibleFindings.map(f => (
              <FindingRow key={f.id} finding={f} onUpdate={load} />
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
