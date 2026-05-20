#!/usr/bin/env python3
"""
AgentSentinel MCP Shim

Sits between any MCP client (agent) and any MCP server (tools).
Every tool call is intercepted, hashed, and reported to AgentSentinel.
The agent and the real MCP server need zero changes.

                    Agent
                      │
           MCP (SSE) │  ← agent points here instead of the real server
                      ▼
         AgentSentinel MCP Shim  ← this script
                  │          │
    forward calls │          │ report (async, fire-and-forget)
                  ▼          ▼
          Real MCP Server   POST /api/v1/events → AgentSentinel
         (SSE or stdio)

Usage — SSE upstream (remote MCP server):
    python demo/mcp_shim.py \\
        --upstream-url http://localhost:8001/sse \\
        --agent-name "my-rag-agent" \\
        --port 8002

Usage — stdio upstream (local MCP server process):
    python demo/mcp_shim.py \\
        --upstream-cmd "npx -y @modelcontextprotocol/server-filesystem /tmp" \\
        --agent-name "my-rag-agent" \\
        --port 8002

Usage — reuse an existing registered agent:
    python demo/mcp_shim.py \\
        --upstream-url http://localhost:8001/sse \\
        --agent-id <uuid-from-agentsentinel> \\
        --port 8002

Then point your agent at http://localhost:8002/sse instead of the real server.
All tool calls are intercepted and reported to AgentSentinel automatically.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shlex
import sys
import time
import uuid
from typing import Any

import httpx
import uvicorn
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.sse import SseServerTransport
from mcp.types import Tool
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Route


# ── Helper ────────────────────────────────────────────────────────────────────

def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


# ── Shim ──────────────────────────────────────────────────────────────────────

class SentinelMCPShim:
    """
    Transparent MCP proxy that auto-reports every tool call to AgentSentinel.

    Exposes itself as an MCP SSE server (agents connect here).
    Maintains a persistent connection to the real upstream MCP server.
    Reports happen async so tool call latency is not affected.
    """

    def __init__(
        self,
        sentinel_url: str,
        agent_id: str,
        session_id: str,
        upstream_url: str | None = None,
        upstream_cmd: str | None = None,
    ) -> None:
        self.sentinel_url = sentinel_url.rstrip("/")
        self.agent_id = agent_id
        self.session_id = session_id
        self.upstream_url = upstream_url
        self.upstream_cmd = upstream_cmd

        self._upstream: ClientSession | None = None
        self._cached_tools: list[Tool] = []
        self._ready = asyncio.Event()   # set once upstream handshake is done
        self._closed = asyncio.Event()  # set to teardown the upstream task

        self.server = Server("sentinel-shim")
        self._register_handlers()

    # ── MCP server side ───────────────────────────────────────────────────────

    def _register_handlers(self) -> None:
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            await self._ready.wait()
            return self._cached_tools

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any] | None) -> list:
            await self._ready.wait()
            inputs = arguments or {}

            t0 = time.time()
            result = await self._upstream.call_tool(name, inputs)
            duration_ms = int((time.time() - t0) * 1000)

            # Hash inputs and outputs — raw content never leaves this process
            input_hash = sha256(json.dumps(inputs, sort_keys=True))
            output_hash = sha256(
                json.dumps([c.model_dump() for c in result.content], sort_keys=True)
            )

            # Report async — doesn't block the tool response back to the agent
            asyncio.create_task(
                self._report(name, input_hash, output_hash, duration_ms)
            )

            return result.content

    # ── Upstream connection (held open as a long-running task) ────────────────

    async def _hold_upstream_sse(self) -> None:
        try:
            async with sse_client(self.upstream_url) as (read, write):
                async with ClientSession(read, write) as session:
                    await self._init_upstream(session)
                    await self._closed.wait()
        except Exception as exc:
            print(f"[shim] upstream SSE connection failed: {exc}", file=sys.stderr)
            sys.exit(1)

    async def _hold_upstream_stdio(self) -> None:
        parts = shlex.split(self.upstream_cmd)
        params = StdioServerParameters(command=parts[0], args=parts[1:])
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await self._init_upstream(session)
                    await self._closed.wait()
        except Exception as exc:
            print(f"[shim] upstream stdio connection failed: {exc}", file=sys.stderr)
            sys.exit(1)

    async def _init_upstream(self, session: ClientSession) -> None:
        self._upstream = session
        await session.initialize()
        tools_result = await session.list_tools()
        self._cached_tools = tools_result.tools
        names = [t.name for t in self._cached_tools]
        print(f"[shim] upstream ready — proxying {len(names)} tools: {names}")
        self._ready.set()

    async def start(self) -> None:
        """Launch the upstream connection task and wait until it's ready."""
        if self.upstream_url:
            asyncio.create_task(self._hold_upstream_sse())
        else:
            asyncio.create_task(self._hold_upstream_stdio())
        await self._ready.wait()

    def stop(self) -> None:
        self._closed.set()

    # ── AgentSentinel reporting ───────────────────────────────────────────────

    async def _report(
        self, tool_name: str, input_hash: str, output_hash: str, duration_ms: int
    ) -> None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(
                    f"{self.sentinel_url}/api/v1/events",
                    json={
                        "agent_id": self.agent_id,
                        "tool_name": tool_name,
                        "input_hash": input_hash,
                        "output_hash": output_hash,
                        "duration_ms": duration_ms,
                        "session_id": self.session_id,
                    },
                )
                r.raise_for_status()
                score = r.json().get("anomaly_score")
                flag = " ⚠️ " if score is not None and score >= 0.7 else ""
                score_str = f"{score:.3f}" if score is not None else "n/a"
                print(f"[shim] tool={tool_name:<20} anomaly={score_str}{flag}")
        except Exception as exc:
            print(f"[shim] report failed ({tool_name}): {exc}", file=sys.stderr)

    # ── Starlette app (SSE MCP server) ────────────────────────────────────────

    def build_app(self) -> Starlette:
        sse_transport = SseServerTransport("/messages/")

        async def handle_sse(request: Request) -> None:
            async with sse_transport.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                init_options = InitializationOptions(
                    server_name="sentinel-shim",
                    server_version="0.1.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                )
                await self.server.run(streams[0], streams[1], init_options)

        async def handle_messages(request: Request) -> None:
            await sse_transport.handle_post_message(
                request.scope, request.receive, request._send
            )

        return Starlette(routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/messages/", endpoint=handle_messages, methods=["POST"]),
        ])


# ── AgentSentinel registration helpers ───────────────────────────────────────

def register_agent(
    sentinel_url: str, name: str, model: str, team: str, description: str
) -> str:
    r = httpx.post(
        f"{sentinel_url}/api/v1/agents",
        json={"name": name, "agent_type": "llm_agent", "model": model,
              "owner_team": team, "description": description},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["id"]


def add_grants(sentinel_url: str, agent_id: str, tools: list[Tool]) -> None:
    for tool in tools:
        httpx.post(
            f"{sentinel_url}/api/v1/agents/{agent_id}/grants",
            json={"tool_name": tool.name, "scope": "read", "is_dangerous": False},
            timeout=10,
        ).raise_for_status()


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="AgentSentinel MCP Shim — transparent tool-call interceptor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    upstream = p.add_mutually_exclusive_group(required=True)
    upstream.add_argument(
        "--upstream-url",
        metavar="URL",
        help="SSE URL of the real MCP server, e.g. http://localhost:8001/sse",
    )
    upstream.add_argument(
        "--upstream-cmd",
        metavar="CMD",
        help="stdio MCP server command, e.g. 'npx -y @modelcontextprotocol/server-filesystem /tmp'",
    )

    agent = p.add_mutually_exclusive_group(required=True)
    agent.add_argument("--agent-id", metavar="UUID", help="Reuse an existing AgentSentinel agent")
    agent.add_argument("--agent-name", metavar="NAME", help="Register a new agent with this name")

    p.add_argument("--sentinel-url", default=os.getenv("SENTINEL_URL", "http://localhost:9000"))
    p.add_argument("--team", default="platform-eng", help="Owner team (used when registering)")
    p.add_argument("--model", default="claude-opus-4-7", help="Model label (used when registering)")
    p.add_argument("--description", default="Agent monitored via AgentSentinel MCP shim")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8002)
    return p.parse_args()


async def main_async(args: argparse.Namespace) -> None:
    sentinel_url = args.sentinel_url
    session_id = f"shim-{uuid.uuid4().hex[:8]}"

    # Resolve agent ID — register or reuse
    if args.agent_id:
        agent_id = args.agent_id
        print(f"[shim] Reusing agent      : {agent_id}")
    else:
        agent_id = register_agent(
            sentinel_url=sentinel_url,
            name=args.agent_name,
            model=args.model,
            team=args.team,
            description=args.description,
        )
        print(f"[shim] Registered agent   : {agent_id} ({args.agent_name})")

    # Build shim and connect to upstream
    shim = SentinelMCPShim(
        sentinel_url=sentinel_url,
        agent_id=agent_id,
        session_id=session_id,
        upstream_url=args.upstream_url,
        upstream_cmd=args.upstream_cmd,
    )
    await shim.start()

    # Auto-register grants for every tool the upstream exposes
    if args.agent_name:  # only when we just registered fresh
        add_grants(sentinel_url, agent_id, shim._cached_tools)
        print(f"[shim] Added {len(shim._cached_tools)} tool grants")

    print(f"[shim] Sentinel URL       : {sentinel_url}")
    print(f"[shim] Session ID         : {session_id}")
    print(f"[shim] Shim listening on  : http://{args.host}:{args.port}/sse")
    print(f"[shim] ← Point your agent here instead of the real MCP server")

    app = shim.build_app()
    config = uvicorn.Config(app, host=args.host, port=args.port, log_level="warning")
    server = uvicorn.Server(config)
    try:
        await server.serve()
    finally:
        shim.stop()


def main() -> None:
    asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    main()
