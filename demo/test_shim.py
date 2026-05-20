#!/usr/bin/env python3
"""
Test client for the AgentSentinel MCP shim.

Connects to the shim (which proxies a real MCP server), lists available
tools, and makes several tool calls. Each call should appear in AgentSentinel
with an anomaly score.

Usage (run AFTER the shim is already running on port 8002):
    /opt/homebrew/bin/python3.11 demo/test_shim.py
"""

import asyncio
import json

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client

SHIM_URL = "http://localhost:8002/sse"
SENTINEL_URL = "http://localhost:9000"


async def run():
    print(f"Connecting to shim at {SHIM_URL} ...\n")

    async with sse_client(SHIM_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List tools proxied from upstream
            tools_result = await session.list_tools()
            print(f"Tools available via shim ({len(tools_result.tools)}):")
            for t in tools_result.tools:
                print(f"  • {t.name}: {t.description[:70] if t.description else ''}")
            print()

            if not tools_result.tools:
                print("No tools found — is the shim running and connected to the upstream?")
                return

            # Make several tool calls — shim will auto-report each one
            calls = build_calls(tools_result.tools)
            for tool_name, args in calls:
                print(f"Calling {tool_name}({json.dumps(args)[:60]}) ...")
                result = await session.call_tool(tool_name, args)
                # Print a short preview of the result
                for block in result.content:
                    text = getattr(block, "text", str(block))
                    print(f"  → {text[:120]}")
                print()

    # Fetch events from AgentSentinel to confirm they were recorded
    print("─" * 50)
    print("Checking AgentSentinel for registered agents ...")
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{SENTINEL_URL}/api/v1/agents")
        agents = r.json()
        # Show the most recently created agent (the one the shim registered)
        if agents:
            latest = sorted(agents, key=lambda a: a["created_at"], reverse=True)[0]
            print(f"\nLatest agent : {latest['name']} ({latest['id']})")
            print(f"Trust score  : {latest['trust_score']} ({latest['status']})")
            print(f"Posture      : {latest['posture_score']}")
            print(f"Behavior     : {latest['behavior_score']}")

            # Trigger a fresh score recompute
            r2 = await client.get(f"{SENTINEL_URL}/api/v1/agents/{latest['id']}/score")
            score = r2.json()
            print(f"\nFresh score  : {score.get('trust_score')} ({score.get('status')})")
        else:
            print("No agents registered yet.")


def build_calls(tools):
    """Build a list of (tool_name, args) calls based on what tools are available."""
    calls = []
    tool_names = {t.name for t in tools}

    # Filesystem MCP server tools
    if "list_directory" in tool_names:
        calls.append(("list_directory", {"path": "/tmp"}))
    if "read_file" in tool_names:
        # Try to read something benign
        calls.append(("read_file", {"path": "/tmp"}))
    if "get_file_info" in tool_names:
        calls.append(("get_file_info", {"path": "/tmp"}))
    if "directory_tree" in tool_names:
        calls.append(("directory_tree", {"path": "/tmp"}))
    if "search_files" in tool_names:
        calls.append(("search_files", {"path": "/tmp", "pattern": "*.txt"}))

    # If none of the filesystem tools matched, just call the first tool with empty args
    if not calls:
        first = tools[0]
        calls.append((first.name, {}))

    return calls


if __name__ == "__main__":
    asyncio.run(run())
