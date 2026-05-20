#!/usr/bin/env python3
"""
Demo agent: real Claude agentic loop with automatic AgentSentinel reporting.

Usage:
    pip install anthropic httpx
    export ANTHROPIC_API_KEY=sk-ant-...
    python demo/agent.py
"""

import os
import random
import sys
import time
import uuid
from datetime import datetime

import anthropic
import httpx

from sentinel_middleware import SentinelMiddleware, SentinelTool

# ── Config ────────────────────────────────────────────────────────────────────
SENTINEL_URL = os.getenv("SENTINEL_URL", "http://localhost:9000")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AGENTSENTINEL_API_KEY = os.getenv("AGENTSENTINEL_API_KEY", "")
SESSION_ID = f"demo-{uuid.uuid4().hex[:8]}"

# ── Tool implementations ──────────────────────────────────────────────────────

@SentinelTool(
    description="Search the CRM database for customer records by name, email, or account ID.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "limit": {"type": "integer", "description": "Max results (default 10)"},
        },
        "required": ["query"],
    },
)
def search_crm(query: str, limit: int = 10) -> dict:
    return {
        "results": [
            {"id": f"acct-{random.randint(1000,9999)}", "name": "Acme Corp", "mrr": 12400, "tier": "enterprise"},
            {"id": f"acct-{random.randint(1000,9999)}", "name": "Globex Inc", "mrr": 3200, "tier": "growth"},
        ],
        "total": 2,
    }


@SentinelTool(
    description="Execute a read-only SQL SELECT query against the analytics database.",
    input_schema={
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "SQL SELECT statement"},
            "database": {"type": "string", "description": "Target database name"},
        },
        "required": ["sql"],
    },
)
def read_database(sql: str, database: str = "analytics") -> dict:
    return {
        "rows": [
            {"date": "2026-05-19", "revenue": 84200, "churn_rate": 0.02},
            {"date": "2026-05-18", "revenue": 81500, "churn_rate": 0.018},
        ],
        "query_time_ms": random.randint(20, 150),
    }


@SentinelTool(
    description="Fetch content from an internal API endpoint or web URL.",
    input_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "method": {"type": "string", "enum": ["GET", "POST"], "default": "GET"},
        },
        "required": ["url"],
    },
)
def http_fetch(url: str, method: str = "GET") -> dict:
    return {"status": 200, "body": {"version": "1.4.2", "healthy": True, "latency_p99_ms": 42}}


@SentinelTool(
    description="Send an email to a customer or internal team. Use with caution.",
    input_schema={
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    },
)
def send_email(to: str, subject: str, body: str) -> dict:
    return {"message_id": f"msg-{uuid.uuid4().hex[:12]}", "status": "queued"}


@SentinelTool(
    description="Write or update a file in the shared storage bucket.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    },
)
def write_file(path: str, content: str) -> dict:
    return {"bytes_written": len(content), "path": path, "etag": uuid.uuid4().hex}


# ── AgentSentinel client ──────────────────────────────────────────────────────

class SentinelClient:
    def __init__(self, base_url: str, api_key: str = ""):
        headers = {"X-API-Key": api_key} if api_key else {}
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=10, headers=headers)

    def register_agent(self) -> str:
        r = self._http.post("/api/v1/agents", json={
            "name": f"demo-sales-agent-{uuid.uuid4().hex[:6]}",
            "agent_type": "llm_agent",
            "model": "claude-opus-4-7",
            "owner_team": "sales-eng",
            "description": "Demo RAG agent that answers questions about CRM data, revenue metrics, and customer accounts",
        })
        r.raise_for_status()
        agent_id = r.json()["id"]
        print(f"[sentinel] Registered agent: {agent_id}")
        return agent_id

    def add_grant(self, agent_id: str, tool_name: str, scope: str, is_dangerous: bool = False):
        self._http.post(f"/api/v1/agents/{agent_id}/grants", json={
            "tool_name": tool_name, "scope": scope, "is_dangerous": is_dangerous,
        }).raise_for_status()

    def report_event(self, agent_id: str, tool_name: str, input_hash: str, output_hash: str, duration_ms: int) -> float | None:
        r = self._http.post("/api/v1/events", json={
            "agent_id": agent_id,
            "tool_name": tool_name,
            "input_hash": input_hash,
            "output_hash": output_hash,
            "duration_ms": duration_ms,
            "session_id": SESSION_ID,
        })
        r.raise_for_status()
        return r.json().get("anomaly_score")

    def get_score(self, agent_id: str) -> dict:
        r = self._http.get(f"/api/v1/agents/{agent_id}/score")
        r.raise_for_status()
        return r.json()

    def close(self):
        self._http.close()


# ── Prompts ───────────────────────────────────────────────────────────────────

PROMPTS = [
    "Who are our top 5 enterprise accounts by MRR? Look them up in the CRM.",
    "What was our daily revenue trend over the past week? Query the analytics database.",
    "Check the health of our internal metrics API at http://metrics.internal/health and summarize the response.",
    "Search for accounts named 'Acme' and draft a renewal email to their account owner.",
    "Pull revenue data for yesterday, then write a summary report to reports/daily-2026-05-20.txt.",
    "Find enterprise accounts with MRR over $10k and check the CRM for any recent activity.",
]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not ANTHROPIC_API_KEY:
        print("ERROR: Set ANTHROPIC_API_KEY environment variable.")
        sys.exit(1)
    if not AGENTSENTINEL_API_KEY:
        print("ERROR: Set AGENTSENTINEL_API_KEY environment variable.")
        sys.exit(1)

    sentinel = SentinelClient(SENTINEL_URL, api_key=AGENTSENTINEL_API_KEY)
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    print(f"[demo] AgentSentinel URL : {SENTINEL_URL}")
    print(f"[demo] Session ID        : {SESSION_ID}")
    print(f"[demo] Started at        : {datetime.utcnow().isoformat()}Z")

    agent_id = sentinel.register_agent()

    grants = [
        ("search_crm",    "read",  False),
        ("read_database", "read",  False),
        ("http_fetch",    "read",  False),
        ("send_email",    "write", True),
        ("write_file",    "write", True),
    ]
    for tool_name, scope, dangerous in grants:
        sentinel.add_grant(agent_id, tool_name, scope, dangerous)
    print(f"[sentinel] Added {len(grants)} tool grants\n")

    # Build middleware — all reporting is automatic from here
    mw = SentinelMiddleware(
        anthropic_client=client,
        sentinel_client=sentinel,
        agent_id=agent_id,
        session_id=SESSION_ID,
        tools=[search_crm, read_database, http_fetch, send_email, write_file],
    )

    try:
        for i, prompt in enumerate(PROMPTS, 1):
            print(f"{'═'*60}")
            print(f"[{i}/{len(PROMPTS)}] User: {prompt}")
            print("═"*60)

            mw.run(prompt)

            if i % 3 == 0:
                score = sentinel.get_score(agent_id)
                print(f"\n[sentinel] Trust score: {score.get('trust_score')} ({score.get('status')})")

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n[demo] Interrupted.")
    finally:
        try:
            score = sentinel.get_score(agent_id)
            print(f"\n[sentinel] Final trust score : {score.get('trust_score')} ({score.get('status')})")
            print(f"           posture_score     : {score.get('posture_score')}")
            print(f"           behavior_score    : {score.get('behavior_score')}")
            print(f"           agent_id          : {agent_id}")
        except Exception:
            pass
        sentinel.close()


if __name__ == "__main__":
    main()
