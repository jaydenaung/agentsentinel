# Testing `sentinel mcp scan` with Local MCP Servers

This guide shows you how to build minimal MCP servers that let you explore every
security finding `sentinel mcp scan` can produce — no cloud account, no framework
dependency, just Python's standard library.

---

## Prerequisites

```bash
pip install agentsentinel-cli
# or, if testing the HTTP transport:
pip install "agentsentinel-cli[mcp]"
```

Python 3.10+ required. No other dependencies for the stdio examples below.

---

## How the scanner connects

`sentinel mcp scan` supports two transports:

| Transport | Flag | When to use |
|-----------|------|-------------|
| **stdio** | `--stdio "python server.py"` | Server runs as a subprocess; scanner talks via stdin/stdout |
| **HTTP** | `sentinel mcp scan http://host:port` | Server listens on a port; scanner sends POST requests |

For local testing, stdio is simplest — no port management, no server process to start
separately.

---

## Quickstart: your first scan in 60 seconds

Save this as `vulnerable_mcp_server.py`:

```python
#!/usr/bin/env python3
"""Intentionally vulnerable MCP server — for testing sentinel mcp scan."""
import json, sys

TOOLS = [
    {
        "name": "bash_exec",
        "description": "Run shell commands",
        "inputSchema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "read_database",
        "description": "Query the production database",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
        },
    },
    {
        "name": "send_email",
        "description": "Send email",
        "inputSchema": {
            "type": "object",
            "properties": {"to": {"type": "string"}, "body": {"type": "string"}},
        },
    },
    {
        "name": "read_file",
        "description": "Read files from disk",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
        },
    },
]

def respond(req):
    rid, method = req.get("id"), req.get("method", "")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "vulnerable-server", "version": "0.1.0"},
        }}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    return None

for line in sys.stdin:
    if line.strip():
        resp = respond(json.loads(line))
        if resp:
            print(json.dumps(resp), flush=True)
```

Run the scan:

```bash
sentinel mcp scan --stdio "python vulnerable_mcp_server.py"
```

Expected output: **4 CRITICAL findings, posture score 0/100**.

---

## The clean server: what a passing scan looks like

Save as `clean_mcp_server.py`:

```python
#!/usr/bin/env python3
"""Well-configured MCP server — demonstrates a passing security scan."""
import json, sys

TOOLS = [
    {
        "name": "search_documentation",
        "description": (
            "Search the internal documentation index and return matching article excerpts. "
            "Read-only. Does not access external systems."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "maxLength": 200,
                    "description": "Search query string",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_article",
        "description": (
            "Retrieve a single documentation article by its slug. "
            "Read-only. Returns title, body, and metadata."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "pattern": "^[a-z0-9-]+$",
                    "maxLength": 100,
                },
            },
            "required": ["slug"],
        },
    },
]

def respond(req):
    rid, method = req.get("id"), req.get("method", "")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "docs-server", "version": "1.0.0"},
        }}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    return None

for line in sys.stdin:
    if line.strip():
        resp = respond(json.loads(line))
        if resp:
            print(json.dumps(resp), flush=True)
```

```bash
sentinel mcp scan --stdio "python clean_mcp_server.py"
```

Expected output: **TRUSTED, 0 findings, posture score 100/100**.

---

## Rule-by-rule testing reference

Each table row shows which tool configuration triggers that specific finding.

### CRITICAL findings

#### `NO_AUTH` — server requires no credentials (HTTP only)
Triggered on HTTP-transport scans where the server responds without requiring an
`Authorization` header. Does **not** fire for stdio transport.

To trigger: run any HTTP server without auth checking (see HTTP section below).  
To suppress: pass `--auth-header "Authorization: Bearer mytoken"` to the scanner.

---

#### `UNAUTH_DANGEROUS_EXEC` — dangerous tools callable without auth (HTTP only)
Triggered on HTTP-transport scans when any tool name or description contains
execution-related words (`exec`, `run`, `bash`, `shell`, `delete`, `deploy`,
`kill`, `send`, etc.) and no auth header was provided. Does **not** fire for
stdio transport.

Trigger tool names: `bash_exec`, `run_script`, `execute_command`, `shell`,
`deploy_container`, `kill_process`, `delete_records`

```python
{"name": "bash_exec", "description": "Runs arbitrary shell commands", "inputSchema": {}}
```

---

#### `EXFILTRATION_PATH` — internal-read + external-write tools present
Triggered when the server exposes at least one internal-read tool AND at least one
external-write tool simultaneously.

**Internal-read keywords** (in tool name): `db`, `database`, `crm`, `file`,
`filesystem`, `s3_read`, `storage_read`, `read_file`

**External-write keywords** (in tool name): `email`, `smtp`, `webhook`,
`http_post`, `http_external`, `s3_write`, `send`, `slack`

Minimal trigger — add both of these tools:

```python
{"name": "read_database",  "description": "...", "inputSchema": {}},
{"name": "send_email",     "description": "...", "inputSchema": {}},
```

---

#### `CODE_EXECUTION_TOOL` — code execution tools present
Triggered when any tool is classified in the `code_execution` category.

Category is assigned when a tool's name or description contains:
`exec`, `bash`, `shell`, `run_code`, `eval`, `terminal`, `subprocess`, `python_repl`

```python
{"name": "python_repl", "description": "Execute Python code", "inputSchema": {}}
```

---

### HIGH findings

#### `UNBOUNDED_INPUT` — unconstrained string inputs
Triggered when any tool has a `string`-type property in its input schema that lacks
`maxLength`, `enum`, and `pattern` constraints.

**Triggers the finding:**
```python
"inputSchema": {
    "type": "object",
    "properties": {"query": {"type": "string"}},  # no maxLength — triggers
}
```

**Suppresses the finding:**
```python
"inputSchema": {
    "type": "object",
    "properties": {"query": {"type": "string", "maxLength": 500}},  # constrained
}
```

Also triggered when a tool has `"type": "object"` schema but no `properties` at all:
```python
"inputSchema": {}  # no schema — triggers
```

---

### MEDIUM findings

#### `TOOL_SPRAWL` — too many tools or categories
Triggered when the server exposes **more than 10 tools** OR tools spanning
**5 or more distinct categories**.

Categories: `database`, `filesystem`, `web`, `communication`, `code_execution`,
`secrets`, `admin`, `crm`, `analytics`, `infrastructure`

To trigger by category count, add one tool from each of 5 categories:

```python
{"name": "query_db",      ...},  # database
{"name": "read_file",     ...},  # filesystem
{"name": "http_request",  ...},  # web
{"name": "send_email",    ...},  # communication
{"name": "bash_exec",     ...},  # code_execution  ← 5th category triggers it
```

---

#### `VAGUE_TOOL_DESCRIPTIONS` — thin descriptions
Triggered when **2 or more tools** have descriptions shorter than 20 characters
(including empty descriptions).

```python
{"name": "tool_a", "description": "Runs stuff",  ...},  # 10 chars — triggers
{"name": "tool_b", "description": "HTTP",        ...},  # 4 chars  — triggers
```

Fix: write descriptions of 20+ characters that explain what the tool does and
what data it accesses.

---

### LOW findings

#### `MISSING_RATE_LIMIT`
Triggered whenever any dangerous tool is present. Not suppressible via schema —
this is a reminder to enforce limits at the server runtime layer.

---

## A server that triggers every finding

Use this to verify the full output in one run:

```python
#!/usr/bin/env python3
"""Triggers all 8 sentinel mcp scan findings — useful for integration testing."""
import json, sys

TOOLS = [
    # CODE_EXECUTION_TOOL + UNAUTH_DANGEROUS_EXEC + MISSING_RATE_LIMIT
    {"name": "bash_exec",      "description": "Run",        "inputSchema": {}},
    # EXFILTRATION_PATH (internal read)
    {"name": "read_database",  "description": "Read DB",    "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}}},
    # EXFILTRATION_PATH (external write)
    {"name": "send_email",     "description": "Send",       "inputSchema": {}},
    # UNBOUNDED_INPUT
    {"name": "search",         "description": "Search the internal knowledge base for matching documents.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}}},
    # TOOL_SPRAWL (adds web + filesystem categories)
    {"name": "http_fetch",     "description": "Fetch a remote URL and return the response body.", "inputSchema": {}},
    {"name": "read_file",      "description": "Read file",  "inputSchema": {}},
]

def respond(req):
    rid, method = req.get("id"), req.get("method", "")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "all-findings-server", "version": "0.1.0"},
        }}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    return None

for line in sys.stdin:
    if line.strip():
        resp = respond(json.loads(line))
        if resp:
            print(json.dumps(resp), flush=True)
```

```bash
sentinel mcp scan --stdio "python all_findings_server.py"
# Expected: 6 findings — 2 CRITICAL, 1 HIGH, 2 MEDIUM, 1 LOW — posture score 0/100
# Note: NO_AUTH and UNAUTH_DANGEROUS_EXEC only fire on HTTP transport (see below)
```

---

## Testing the HTTP transport

For HTTP scanning, you need a server that listens on a port and speaks MCP's
streamable-HTTP protocol (POST-based JSON-RPC). The example below uses only the
standard library (`http.server`):

```python
#!/usr/bin/env python3
"""Minimal MCP server over HTTP — no framework required."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

TOOLS = [
    {
        "name": "bash_exec",
        "description": "Execute shell commands on the host",
        "inputSchema": {"type": "object", "properties": {"cmd": {"type": "string"}}},
    },
    {
        "name": "read_database",
        "description": "Run a SQL query against the production database",
        "inputSchema": {"type": "object", "properties": {"sql": {"type": "string"}}},
    },
    {
        "name": "send_slack",
        "description": "Post a message to a Slack channel",
        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
    },
]

RESPONSES = {
    "initialize": lambda rid: {
        "jsonrpc": "2.0", "id": rid,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "http-test-server", "version": "0.1.0"},
        },
    },
    "tools/list": lambda rid: {
        "jsonrpc": "2.0", "id": rid,
        "result": {"tools": TOOLS},
    },
}

class MCPHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        method = body.get("method", "")
        rid = body.get("id")

        handler = RESPONSES.get(method)
        if handler:
            resp = json.dumps(handler(rid)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
        else:
            self.send_response(204)
            self.end_headers()

    def log_message(self, *args):
        pass  # suppress request logs

if __name__ == "__main__":
    server = HTTPServer(("localhost", 3000), MCPHandler)
    print("MCP server listening on http://localhost:3000", flush=True)
    server.serve_forever()
```

Start the server, then scan it in a second terminal:

```bash
# Terminal 1
python http_mcp_server.py

# Terminal 2
sentinel mcp scan http://localhost:3000
sentinel mcp scan http://localhost:3000 --format json
sentinel mcp scan http://localhost:3000 --fail-on CRITICAL && echo "passed" || echo "failed"
```

### Testing the auth check (HTTP only)

The `NO_AUTH` finding fires when the scanner successfully enumerates tools without
any credentials. To test the auth-required path, add a credential check to the handler:

```python
def do_POST(self):
    auth = self.headers.get("Authorization", "")
    if auth != "Bearer mysecrettoken":
        self.send_response(401)
        self.end_headers()
        return
    # ... rest of handler
```

```bash
# Scanner gets 401 — reports auth required, no NO_AUTH finding
sentinel mcp scan http://localhost:3000

# Scanner gets through — NO_AUTH finding suppressed
sentinel mcp scan http://localhost:3000 --auth-header "Authorization: Bearer mysecrettoken"
```

---

## Using a real MCP server

If you have the `mcp` Python package installed, you can build a proper server with
full protocol compliance:

```bash
pip install mcp
```

```python
#!/usr/bin/env python3
"""Real MCP server using the official SDK — scan with sentinel mcp scan --stdio."""
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import asyncio

app = Server("real-mcp-server")

@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="search_knowledge_base",
            description=(
                "Search the internal knowledge base and return matching document excerpts. "
                "Read-only access. Does not modify any data."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "maxLength": 300},
                    "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="write_report",
            description="Write a generated report to the internal reports store.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title":   {"type": "string", "maxLength": 200},
                    "content": {"type": "string", "maxLength": 50000},
                },
                "required": ["title", "content"],
            },
        ),
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    return [TextContent(type="text", text=f"[stub] called {name}")]

async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())

asyncio.run(main())
```

```bash
sentinel mcp scan --stdio "python real_mcp_server.py"
```

---

## CI/CD integration

Add MCP server scanning to a GitHub Actions workflow:

```yaml
# .github/workflows/mcp-security.yml
name: MCP Security Scan

on: [push, pull_request]

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install scanner
        run: pip install agentsentinel-cli

      - name: Scan MCP server
        run: |
          sentinel mcp scan --stdio "python your_mcp_server.py" \
            --fail-on CRITICAL \
            --format json \
            > mcp-scan-results.json

      - name: Upload scan results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: mcp-scan-results
          path: mcp-scan-results.json
```

The `--fail-on CRITICAL` flag causes the step to exit with code 1 (failing the
workflow) if any CRITICAL finding is present. Drop to `--fail-on HIGH` for a
stricter gate.

---

## Note on auth and stdio

`NO_AUTH` and `UNAUTH_DANGEROUS_EXEC` only fire on HTTP transport. Stdio processes
communicate through OS-managed pipes — there is no network surface to protect, so
no auth requirement makes sense. The scanner skips those two rules for stdio.

To see the full auth-related finding set, use the HTTP transport examples above
(with or without `--auth-header`).

---

## Summary: which server to use for what

| Goal | Server | Command |
|------|--------|---------|
| See all findings at once | `all_findings_server.py` | `sentinel mcp scan --stdio "python all_findings_server.py"` |
| See a clean/passing scan | `clean_mcp_server.py` | `sentinel mcp scan --stdio "python clean_mcp_server.py"` |
| Test HTTP transport | `http_mcp_server.py` | `sentinel mcp scan http://localhost:3000` |
| Test auth check | `http_mcp_server.py` (with auth) | `sentinel mcp scan http://localhost:3000 --auth-header "Authorization: Bearer token"` |
| Test with real SDK | `real_mcp_server.py` | `sentinel mcp scan --stdio "python real_mcp_server.py"` |
| CI gate | any | add `--fail-on CRITICAL` |
