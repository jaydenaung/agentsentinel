# AgentSentinel

AgentSentinel is an enterprise AI agent security platform that continuously monitors AI agents for over-permissioning and runtime anomalies. It combines static posture analysis (scanning tool grants and MCP server bindings) with live behavior monitoring (baselining tool-call patterns and detecting anomalies) into a single **Trust Score** per agent — giving security teams a unified signal to act on.

![AgentSentinel Dashboard](img/agentsentinel1.png)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        FastAPI (port 8000)                   │
│   /api/v1/agents   /api/v1/events   /api/v1/findings        │
│   /api/v1/agents/{id}/score         /api/v1/agents/{id}/...  │
└──────────────────────┬──────────────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
┌─────────────────┐       ┌──────────────────┐
│  POSTURE ENGINE │       │ BEHAVIOR ENGINE  │
│                 │       │                  │
│  rules.py       │       │  collector.py    │
│  scanner.py     │       │  baseline.py     │
│  scoring.py     │       │  anomaly.py      │
└────────┬────────┘       └───────┬──────────┘
         │                        │
         └────────────┬───────────┘
                      ▼
            ┌──────────────────┐
            │  TRUST ENGINE    │
            │  engine.py       │
            │  (0.45+0.45+0.10)│
            └────────┬─────────┘
                     │
         ┌───────────┴────────────┐
         ▼                        ▼
┌─────────────────┐     ┌──────────────────┐
│   PostgreSQL 16  │     │   Redis Streams  │
│   + TimescaleDB  │     │   agent_events   │
│   (hypertable)   │     └──────────────────┘
└─────────────────┘
         │
         ▼
┌─────────────────┐
│  Slack Alerts   │
│  (CRITICAL only)│
└─────────────────┘
```

---

## Quickstart

```bash
git clone <repo>
cd agentsentinel
cp .env.example .env
docker compose up
```

The API is available at **http://localhost:9000**. Interactive docs at http://localhost:9000/docs.

Run migrations (first time or after pulls):

```bash
docker compose exec api alembic upgrade head
```

**Start the UI** (separate terminal):

```bash
cd ui && npm install && npm run dev
```

Open **http://localhost:5173** — the UI proxies all `/api` requests to the backend.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/agents` | Register a new agent |
| `GET` | `/api/v1/agents` | List agents (filter: `?status=CRITICAL&owner_team=ml`) |
| `GET` | `/api/v1/agents/{id}` | Agent detail with grants, connections, findings |
| `POST` | `/api/v1/agents/{id}/grants` | Add a tool grant to an agent |
| `POST` | `/api/v1/agents/{id}/mcp` | Add an MCP server connection |
| `POST` | `/api/v1/events` | Ingest a tool-call event (returns anomaly score) |
| `GET` | `/api/v1/agents/{id}/findings` | List findings (filter: `?status=OPEN&severity=CRITICAL`) |
| `PATCH` | `/api/v1/findings/{id}` | Update finding status (ACKNOWLEDGED / RESOLVED) |
| `GET` | `/api/v1/agents/{id}/score` | Trigger full trust score recompute |

---

## Trust Score

```
Trust Score = (Posture Score × 0.45) + (Behavior Score × 0.45) + (Recency × 0.10)
```

| Score | Status | Meaning |
|-------|--------|---------|
| 80–100 | **TRUSTED** | Normal operation, no significant concerns |
| 60–79 | **WATCH** | Minor issues; monitor closely |
| 40–59 | **ALERT** | Active risks; investigate soon |
| 0–39 | **CRITICAL** | Immediate action required |

**Recency bonus (+10)**: applied when the agent was seen in the last 5 minutes, rewarding active agents with fresh data.

---

## Register Your First Agent & Send an Event

### 1. Register an agent

```bash
curl -s -X POST http://localhost:9000/api/v1/agents \
  -H "Content-Type: application/json" \
  -d '{
    "name": "sales-rag-bot",
    "agent_type": "rag_agent",
    "model": "claude-sonnet-4-6",
    "owner_team": "sales-eng",
    "description": "Searches and queries the CRM for sales reps"
  }' | jq .
```

Save the returned `id` as `AGENT_ID`.

### 2. Add a tool grant

```bash
curl -s -X POST http://localhost:9000/api/v1/agents/$AGENT_ID/grants \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "crm_search",
    "scope": "read",
    "is_dangerous": false
  }' | jq .
```

### 3. Send a tool-call event

```bash
# Hash your inputs before sending — never send raw content
INPUT_HASH=$(echo -n "query: top accounts" | sha256sum | cut -d' ' -f1)
OUTPUT_HASH=$(echo -n "account list json" | sha256sum | cut -d' ' -f1)

curl -s -X POST http://localhost:9000/api/v1/events \
  -H "Content-Type: application/json" \
  -d "{
    \"agent_id\": \"$AGENT_ID\",
    \"tool_name\": \"crm_search\",
    \"input_hash\": \"$INPUT_HASH\",
    \"output_hash\": \"$OUTPUT_HASH\",
    \"duration_ms\": 120,
    \"session_id\": \"session-abc123\"
  }" | jq .
```

### 4. Get the Trust Score

```bash
curl -s http://localhost:9000/api/v1/agents/$AGENT_ID/score | jq .
```

---

## Live Demo Agent

The `demo/` directory contains a mini agent that generates real traffic so the behavior engine can build baselines and score anomalies in real time.

```
demo/
├── agent.py               # Demo agent — registers, adds grants, runs agentic loop
├── sentinel_middleware.py # Reusable middleware that auto-reports every tool call
└── mcp_shim.py            # MCP shim — transparent interceptor for any MCP server
```

### How it works

`SentinelMiddleware` wraps the Claude agentic loop. Decorate tool functions with `@SentinelTool` and call `mw.run(prompt)` — every tool call is automatically timed, SHA-256 hashed, and reported to AgentSentinel with no manual instrumentation:

```python
@SentinelTool(
    description="Search the CRM for customer records.",
    input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
)
def search_crm(query: str) -> dict:
    return {"results": [...]}

mw = SentinelMiddleware(
    anthropic_client=client,
    sentinel_client=sentinel,
    agent_id=agent_id,
    session_id=session_id,
    tools=[search_crm, ...],
)
mw.run("Who are our top enterprise accounts?")
# → tool call auto-executed, hashed, and POSTed to /api/v1/events
```

### Run the demo

```bash
# Install demo dependencies
pip install anthropic httpx

export ANTHROPIC_API_KEY=sk-ant-...

# Make sure the backend is running
docker compose up -d

python demo/agent.py
```

The agent registers itself, adds 5 tool grants (including dangerous `send_email` and `write_file` which immediately trigger posture findings), then works through 6 realistic prompts. Anomaly scores are printed after each tool call; trust score is fetched every 3 interactions.

Each run creates a new agent in AgentSentinel — open **http://localhost:5173** to watch scores update in real time.

---

## MCP Shim (Zero-Touch Monitoring)

`demo/mcp_shim.py` is a transparent MCP proxy. Point it at any existing MCP server and it intercepts every tool call — the agent and the real MCP server need **zero code changes**.

```
Agent  →  MCP Shim (port 8002)  →  Real MCP Server
                │
                └─► POST /api/v1/events  →  AgentSentinel
```

### Run the shim

```bash
pip install -r demo/requirements.txt
```

**Against a stdio MCP server** (tested — uses the official filesystem MCP server via npx):

```bash
PYTHONUNBUFFERED=1 python demo/mcp_shim.py \
    --upstream-cmd "npx -y @modelcontextprotocol/server-filesystem /tmp" \
    --agent-name "my-filesystem-agent" \
    --port 8002
```

Expected startup output:
```
[shim] Registered agent   : <uuid> (my-filesystem-agent)
[shim] upstream ready — proxying 14 tools: ['read_file', 'list_directory', ...]
[shim] Added 14 tool grants
[shim] Shim listening on  : http://0.0.0.0:8002/sse
[shim] ← Point your agent here instead of the real MCP server
```

**Against an SSE MCP server** (remote or local):

```bash
PYTHONUNBUFFERED=1 python demo/mcp_shim.py \
    --upstream-url http://localhost:8001/sse \
    --agent-name "my-rag-agent" \
    --port 8002
```

Then change one line in your agent config:

```diff
- mcp_server_url = "http://localhost:8001/sse"
+ mcp_server_url = "http://localhost:8002/sse"
```

### Test the shim

With the shim running, use the included test client to verify interception end-to-end:

```bash
python demo/test_shim.py
```

It connects to the shim, lists proxied tools, makes several tool calls, then fetches and prints the AgentSentinel trust score. Each intercepted call appears in the shim log with its anomaly score:

```
[shim] tool=list_directory       anomaly=0.500
[shim] tool=get_file_info        anomaly=0.500
[shim] tool=search_files         anomaly=0.500
```

> **Note:** Anomaly scores start high (~0.9) for a brand-new agent with no baseline. After 20–30 calls the behavior engine builds a normal pattern and scores for routine calls drop toward 0.0–0.3. Unusual tools or call sequences score higher.

### Reuse an existing agent

To avoid registering a new agent on every shim restart, pass the agent UUID instead of a name:

```bash
python demo/mcp_shim.py \
    --upstream-cmd "npx -y @modelcontextprotocol/server-filesystem /tmp" \
    --agent-id <uuid-from-agentsentinel> \
    --port 8002
```

### What the shim does automatically

- Registers a new agent in AgentSentinel (or reuses one with `--agent-id`)
- Discovers and registers grants for every tool the upstream server exposes
- Proxies `tools/list` and `tools/call` transparently to the real server
- SHA-256 hashes every input/output before reporting (raw content never leaves the process)
- Reports to AgentSentinel async — no latency added to tool calls

---

## Running Tests

```bash
# Unit tests (no Postgres required)
.venv/bin/pytest tests/ -v

# With coverage
.venv/bin/pytest tests/ -v --cov=agentsentinel --cov-report=term-missing
```

---

## Posture Rules

| Rule ID | Severity | Trigger |
|---------|----------|---------|
| `EXFILTRATION_PATH` | CRITICAL | Agent holds both internal-read AND external-write grants |
| `PRIVILEGE_EXCESS` | HIGH | write/admin grant on an agent described as read-only |
| `UNUSED_DANGEROUS_GRANT` | HIGH | dangerous grant unused for 30+ days |
| `MCP_OVER_CONNECTION` | MEDIUM | >3 MCP connections with no agent description |
| `CREDENTIAL_SCOPE_MISMATCH` | MEDIUM | admin grant with zero calls in last 7 days |
| `MISSING_RATE_LIMIT` | LOW | dangerous grant with no rate limit configured |
