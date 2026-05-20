const BASE = '/api/v1'

async function req(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
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
    ingest: (body) => req('/events', { method: 'POST', body: JSON.stringify(body) }),
  },
  findings: {
    update: (id, status) =>
      req(`/findings/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) }),
  },
}
