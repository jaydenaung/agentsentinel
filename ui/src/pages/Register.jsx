import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

function Field({ label, children, hint }) {
  return (
    <div>
      <label className="block text-sm font-medium text-slate-300 mb-1.5">{label}</label>
      {children}
      {hint && <p className="text-xs text-slate-500 mt-1">{hint}</p>}
    </div>
  )
}

const inputCls = "w-full px-3 py-2 rounded-md border border-slate-700 bg-slate-800/60 text-slate-200 text-sm placeholder-slate-500 focus:outline-none focus:border-violet-500/60 focus:ring-1 focus:ring-violet-500/30 transition-colors"
const selectCls = inputCls + " cursor-pointer"

function GrantBuilder({ grants, onChange }) {
  function add() {
    onChange([...grants, { tool_name: '', scope: 'read', is_dangerous: false, rate_limit_per_hour: '' }])
  }
  function remove(i) {
    onChange(grants.filter((_, idx) => idx !== i))
  }
  function update(i, key, value) {
    onChange(grants.map((g, idx) => idx === i ? { ...g, [key]: value } : g))
  }

  return (
    <div className="space-y-2">
      {grants.map((g, i) => (
        <div key={i} className="flex gap-2 items-center">
          <input
            className={inputCls + ' flex-1'}
            placeholder="tool_name"
            value={g.tool_name}
            onChange={e => update(i, 'tool_name', e.target.value)}
          />
          <select
            className={selectCls + ' w-28'}
            value={g.scope}
            onChange={e => update(i, 'scope', e.target.value)}
          >
            <option value="read">read</option>
            <option value="write">write</option>
            <option value="admin">admin</option>
          </select>
          <label className="flex items-center gap-1.5 text-xs text-slate-400 shrink-0 cursor-pointer">
            <input
              type="checkbox"
              checked={g.is_dangerous}
              onChange={e => update(i, 'is_dangerous', e.target.checked)}
              className="accent-red-400"
            />
            dangerous
          </label>
          <button type="button" onClick={() => remove(i)} className="text-slate-500 hover:text-red-400 transition-colors text-lg leading-none">×</button>
        </div>
      ))}
      <button type="button" onClick={add} className="text-xs text-violet-400 hover:text-violet-300 transition-colors">
        + Add grant
      </button>
    </div>
  )
}

export default function Register() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    name: '', agent_type: 'llm_agent', model: 'claude-sonnet-4-6',
    owner_team: '', description: '',
  })
  const [grants, setGrants] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  function set(key, value) {
    setForm(f => ({ ...f, [key]: value }))
  }

  async function submit(e) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const agent = await api.agents.create({
        ...form,
        description: form.description || null,
      })
      for (const g of grants) {
        if (!g.tool_name.trim()) continue
        await api.agents.addGrant(agent.id, {
          tool_name: g.tool_name.trim(),
          scope: g.scope,
          is_dangerous: g.is_dangerous,
          rate_limit_per_hour: g.rate_limit_per_hour ? parseInt(g.rate_limit_per_hour) : null,
        })
      }
      navigate(`/agents/${agent.id}`)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-6">
        <button onClick={() => navigate('/')} className="text-xs text-slate-500 hover:text-slate-300 mb-2 block">
          ← All agents
        </button>
        <h1 className="text-xl font-semibold text-white">Register Agent</h1>
        <p className="text-sm text-slate-400 mt-1">Add a new AI agent to AgentSentinel for monitoring.</p>
      </div>

      <form onSubmit={submit} className="space-y-5 rounded-lg border border-slate-800 bg-slate-900/30 p-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <Field label="Agent name *">
            <input className={inputCls} required placeholder="e.g. sales-rag-bot" value={form.name} onChange={e => set('name', e.target.value)} />
          </Field>
          <Field label="Owner team *">
            <input className={inputCls} required placeholder="e.g. platform-eng" value={form.owner_team} onChange={e => set('owner_team', e.target.value)} />
          </Field>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <Field label="Agent type">
            <select className={selectCls} value={form.agent_type} onChange={e => set('agent_type', e.target.value)}>
              <option value="llm_agent">llm_agent</option>
              <option value="rag_agent">rag_agent</option>
              <option value="agentic_pipeline">agentic_pipeline</option>
            </select>
          </Field>
          <Field label="Model">
            <input className={inputCls} placeholder="e.g. claude-sonnet-4-6" value={form.model} onChange={e => set('model', e.target.value)} />
          </Field>
        </div>

        <Field label="Description" hint="Describe the agent's purpose — used by posture rules to detect privilege excess.">
          <textarea
            className={inputCls + ' resize-none'}
            rows={2}
            placeholder="e.g. Searches and queries the CRM for sales reps"
            value={form.description}
            onChange={e => set('description', e.target.value)}
          />
        </Field>

        <Field label="Tool grants" hint="Optional. You can add more from the agent detail page later.">
          <GrantBuilder grants={grants} onChange={setGrants} />
        </Field>

        {error && (
          <div className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded px-3 py-2">
            {error}
          </div>
        )}

        <div className="flex gap-3 pt-1">
          <button
            type="submit"
            disabled={loading}
            className="px-5 py-2 rounded bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
          >
            {loading ? 'Registering…' : 'Register agent'}
          </button>
          <button
            type="button"
            onClick={() => navigate('/')}
            className="px-4 py-2 rounded border border-slate-700 text-slate-400 hover:text-slate-200 text-sm transition-colors"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  )
}
