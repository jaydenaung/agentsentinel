import { useEffect, useState, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { fmtAgo } from '../lib/utils'

function AnomalyBar({ score }) {
  if (score === null || score === undefined) return <span className="text-slate-500 text-xs">—</span>
  const pct = score * 100
  const color = score >= 0.8 ? 'bg-red-500' : score >= 0.7 ? 'bg-orange-500' : score >= 0.5 ? 'bg-yellow-500' : 'bg-emerald-500'
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`text-xs font-mono ${score >= 0.7 ? 'text-red-400' : score >= 0.5 ? 'text-yellow-400' : 'text-emerald-400'}`}>
        {score.toFixed(2)}
      </span>
    </div>
  )
}

export default function Events() {
  const [events, setEvents] = useState([])
  const [agentList, setAgentList] = useState([])
  const [filterAgent, setFilterAgent] = useState('')
  const [sending, setSending] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState({ agent_id: '', tool_name: '', duration_ms: '', session_id: '' })
  const [result, setResult] = useState(null)
  const intervalRef = useRef(null)
  const navigate = useNavigate()

  const loadEvents = useCallback(async () => {
    try {
      const params = { limit: 100 }
      if (filterAgent) params.agent_id = filterAgent
      const data = await api.events.list(params)
      setEvents(data)
    } catch (err) {
      console.error('Failed to load events', err)
    } finally {
      setLoading(false)
    }
  }, [filterAgent])

  async function loadAgents() {
    const list = await api.agents.list()
    setAgentList(list)
    if (list.length > 0 && !form.agent_id) {
      setForm(f => ({ ...f, agent_id: list[0].id }))
    }
  }

  useEffect(() => {
    loadAgents()
  }, [])

  useEffect(() => {
    loadEvents()
  }, [loadEvents])

  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(loadEvents, 5000)
    } else {
      clearInterval(intervalRef.current)
    }
    return () => clearInterval(intervalRef.current)
  }, [autoRefresh, loadEvents])

  async function sendEvent(e) {
    e.preventDefault()
    setSending(true)
    setResult(null)
    try {
      const encoder = new TextEncoder()
      const buf = await crypto.subtle.digest('SHA-256', encoder.encode(form.tool_name + Date.now()))
      const hex = Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('')
      const outBuf = await crypto.subtle.digest('SHA-256', encoder.encode('output' + Date.now()))
      const outHex = Array.from(new Uint8Array(outBuf)).map(b => b.toString(16).padStart(2, '0')).join('')

      const res = await api.events.ingest({
        agent_id: form.agent_id,
        tool_name: form.tool_name,
        input_hash: hex,
        output_hash: outHex,
        duration_ms: form.duration_ms ? parseInt(form.duration_ms) : null,
        session_id: form.session_id || null,
      })
      setResult(res)
      await loadEvents()
    } catch (err) {
      setResult({ error: err.message })
    } finally {
      setSending(false)
    }
  }

  function set(k, v) { setForm(f => ({ ...f, [k]: v })) }

  const inputCls = "w-full px-3 py-2 rounded-md border border-slate-700 bg-slate-800/60 text-slate-200 text-sm placeholder-slate-500 focus:outline-none focus:border-violet-500/60 focus:ring-1 focus:ring-violet-500/30 transition-colors"

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Send event form */}
        <div className="lg:col-span-2">
          <div className="rounded-lg border border-slate-800 bg-slate-900/30 overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-800">
              <h2 className="text-sm font-medium text-slate-200">Send Test Event</h2>
            </div>
            <form onSubmit={sendEvent} className="p-4 space-y-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1">Agent</label>
                <select
                  className={inputCls + ' cursor-pointer'}
                  required
                  value={form.agent_id}
                  onChange={e => set('agent_id', e.target.value)}
                >
                  <option value="">Select agent…</option>
                  {agentList.map(a => (
                    <option key={a.id} value={a.id}>{a.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Tool name</label>
                <input
                  className={inputCls}
                  required
                  placeholder="e.g. crm_search"
                  value={form.tool_name}
                  onChange={e => set('tool_name', e.target.value)}
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Duration (ms)</label>
                  <input className={inputCls} type="number" placeholder="100" value={form.duration_ms} onChange={e => set('duration_ms', e.target.value)} />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Session ID</label>
                  <input className={inputCls} placeholder="optional" value={form.session_id} onChange={e => set('session_id', e.target.value)} />
                </div>
              </div>
              <button
                type="submit"
                disabled={sending}
                className="w-full py-2 rounded bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
              >
                {sending ? 'Sending…' : '⚡ Send event'}
              </button>
            </form>

            {result && (
              <div className={`mx-4 mb-4 p-3 rounded border text-xs font-mono ${result.error
                ? 'border-red-500/30 bg-red-500/10 text-red-400'
                : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'}`}>
                {result.error ? (
                  <span>Error: {result.error}</span>
                ) : (
                  <div className="space-y-1">
                    <div>event_id: <span className="text-slate-400 break-all">{result.event_id}</span></div>
                    <div className="flex items-center gap-2">
                      anomaly_score: <AnomalyBar score={result.anomaly_score} />
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Event feed */}
        <div className="lg:col-span-3">
          <div className="rounded-lg border border-slate-800 bg-slate-900/30 overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between gap-3">
              <h2 className="text-sm font-medium text-slate-200 shrink-0">
                Event Feed
                <span className="ml-2 text-slate-500 font-normal text-xs">({events.length})</span>
              </h2>

              {/* Agent filter */}
              <select
                className="flex-1 max-w-[180px] px-2 py-1 rounded border border-slate-700 bg-slate-800/60 text-slate-300 text-xs focus:outline-none focus:border-violet-500/60 cursor-pointer"
                value={filterAgent}
                onChange={e => setFilterAgent(e.target.value)}
              >
                <option value="">All agents</option>
                {agentList.map(a => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>

              {/* Live toggle */}
              <label className="flex items-center gap-2 text-xs text-slate-400 cursor-pointer shrink-0">
                <div
                  onClick={() => setAutoRefresh(r => !r)}
                  className={`w-8 h-4 rounded-full transition-colors cursor-pointer ${autoRefresh ? 'bg-violet-500' : 'bg-slate-700'} relative`}
                >
                  <div className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all ${autoRefresh ? 'left-4' : 'left-0.5'}`} />
                </div>
                Live
              </label>
            </div>

            {loading ? (
              <div className="py-16 text-center text-slate-500 text-sm">Loading…</div>
            ) : events.length === 0 ? (
              <div className="py-16 text-center text-slate-500 text-sm">
                <p>No events yet.</p>
                <p className="mt-1 text-xs">Run the demo agent or send a test event.</p>
              </div>
            ) : (
              <div className="overflow-auto max-h-[480px]">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-slate-900">
                    <tr className="border-b border-slate-800 text-xs text-slate-500 uppercase tracking-wide">
                      <th className="text-left px-4 py-2.5">Agent</th>
                      <th className="text-left px-4 py-2.5">Tool</th>
                      <th className="text-left px-4 py-2.5">Anomaly</th>
                      <th className="text-left px-4 py-2.5">When</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.map((ev, i) => (
                      <tr
                        key={ev.event_id}
                        className={`border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors cursor-pointer ${i === 0 ? 'bg-violet-500/5' : ''}`}
                        onClick={() => navigate(`/agents/${ev.agent_id}`)}
                      >
                        <td className="px-4 py-2.5 text-slate-300 max-w-[120px] truncate">{ev.agent_name}</td>
                        <td className="px-4 py-2.5 font-mono text-xs text-slate-400">{ev.tool_name}</td>
                        <td className="px-4 py-2.5"><AnomalyBar score={ev.anomaly_score} /></td>
                        <td className="px-4 py-2.5 text-xs text-slate-500 whitespace-nowrap">{fmtAgo(ev.timestamp)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
