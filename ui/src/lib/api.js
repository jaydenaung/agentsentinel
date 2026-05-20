const BASE = '/api/v1'
const API_KEY = import.meta.env.VITE_API_KEY || ''

async function req(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
      ...options.headers,
    },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json()
}

export const api = {
  agents: {
    list: (params = {}) => {
      const qs = new URLSearchParams(params).toString()
      return req(`/agents${qs ? '?' + qs : ''}`)
    },
    get: (id) => req(`/agents/${id}`),
    create: (body) => req('/agents', { method: 'POST', body: JSON.stringify(body) }),
    addGrant: (id, body) => req(`/agents/${id}/grants`, { method: 'POST', body: JSON.stringify(body) }),
    addMcp: (id, body) => req(`/agents/${id}/mcp`, { method: 'POST', body: JSON.stringify(body) }),
    score: (id) => req(`/agents/${id}/score`),
    findings: (id, params = {}) => {
      const qs = new URLSearchParams(params).toString()
      return req(`/agents/${id}/findings${qs ? '?' + qs : ''}`)
    },
  },
  events: {
    list: (params = {}) => {
      const qs = new URLSearchParams(params).toString()
      return req(`/events${qs ? '?' + qs : ''}`)
    },
    ingest: (body) => req('/events', { method: 'POST', body: JSON.stringify(body) }),
  },
  findings: {
    update: (id, status) =>
      req(`/findings/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) }),
  },
}
