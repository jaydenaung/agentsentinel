# AgentSentinel

AgentSentinel is an enterprise AI agent security platform that continuously monitors AI agents for over-permissioning and runtime anomalies. It combines static posture analysis (scanning tool grants and MCP server bindings) with live behavior monitoring (baselining tool-call patterns and detecting anomalies) into a single **Trust Score** per agent — giving security teams a unified signal to act on.

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

The API is available at **http://localhost:8000**. Interactive docs at http://localhost:8000/docs.

Run migrations (first time or after pulls):

```bash
docker compose exec api alembic upgrade head
```

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
curl -s -X POST http://localhost:8000/api/v1/agents \
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
curl -s -X POST http://localhost:8000/api/v1/agents/$AGENT_ID/grants \
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

curl -s -X POST http://localhost:8000/api/v1/events \
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
curl -s http://localhost:8000/api/v1/agents/$AGENT_ID/score | jq .
```

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
