# AgentSentinel CLI — Complete Documentation

`sentinel` is a security CLI for AI agents and MCP servers. It answers the questions every
security team is now asking: *What are my AI agents doing? Can they be attacked? Do I even
know all of them?*

No server required. No Docker. Works on any Python agent file or live HTTP endpoint.

---

## Table of Contents

- [Install](#install)
- [Quick Start](#quick-start)
- [Commands](#commands)
  - [sentinel inspect](#sentinel-inspect)
  - [sentinel scan](#sentinel-scan)
  - [sentinel discover](#sentinel-discover)
  - [sentinel mcp scan](#sentinel-mcp-scan)
  - [sentinel probe](#sentinel-probe)
  - [sentinel ai-probe](#sentinel-ai-probe)
- [Real-World Workflows](#real-world-workflows)
- [CI/CD Integration](#cicd-integration)
- [Reference](#reference)

---

## Install

### Recommended — pipx (isolated, no venv needed)

```bash
pipx install "agentsentinel-cli[all]"
```

### pip (standard)

```bash
# Zero-dependency core (sentinel scan only)
pip install agentsentinel-cli

# With specific features
pip install "agentsentinel-cli[inspect]"    # sentinel inspect (live endpoints)
pip install "agentsentinel-cli[discover]"   # sentinel discover
pip install "agentsentinel-cli[mcp]"        # sentinel mcp scan
pip install "agentsentinel-cli[probe]"      # sentinel probe
pip install "agentsentinel-cli[ai-probe]"   # sentinel ai-probe

# Everything
pip install "agentsentinel-cli[all]"
```

### Upgrade

```bash
pip install --upgrade "agentsentinel-cli[all]"
# or
pipx upgrade agentsentinel-cli
```

### Verify

```bash
sentinel --version
```

---

## Quick Start

Five commands that cover the full picture in under 5 minutes:

```bash
# 1. What is this agent? (fingerprint + plain English summary)
sentinel inspect my_agent.py

# 2. Does it have dangerous permissions? (posture audit)
sentinel scan my_agent.py

# 3. Is the MCP server it connects to secure?
sentinel mcp scan http://localhost:3000

# 4. Can it be jailbroken? (42-payload attack battery)
sentinel probe http://my-agent.com/chat

# 5. Deep red-team with Claude as the attacker (needs ANTHROPIC_API_KEY)
sentinel ai-probe http://my-agent.com/chat
```

---

## Commands

---

### sentinel inspect

**What problem it solves:** Security teams are being asked to approve AI agents they have no
visibility into. `sentinel inspect` answers *"what the hell is this thing?"* in 10 seconds —
framework, model, cloud provider, what it reads, what it writes, and whether it should be
trusted.

```
sentinel inspect TARGET [OPTIONS]
```

TARGET can be a Python file, a directory, or a live HTTP endpoint URL.

#### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--format [text\|json]` | `text` | Output format |
| `--no-ai` | off | Skip Claude summary even if `ANTHROPIC_API_KEY` is set |
| `--model TEXT` | `claude-haiku-4-5-20251001` | Claude model for AI summary |
| `--auth-header HEADER` | — | HTTP auth header for live endpoints, e.g. `Authorization: Bearer token` |
| `--fail-on [CRITICAL\|HIGH\|MEDIUM\|LOW]` | — | Exit code 1 if findings reach this severity |

#### What it shows

| Section | Details |
|---------|---------|
| **Type** | AI Agent (has an LLM) vs MCP Server (tool provider only) |
| **Function** | Plain English: what it does, what it accesses, top security risk |
| **Fingerprint** | Framework, model, Python version, deployment, cloud, system prompt |
| **Capabilities** | Every tool with scope (read/write), category, and severity |
| **Data flows** | Where data comes from (Input ←) and where it goes (Output →) |
| **Findings** | Posture violations from the rule engine |
| **Trust score** | 0–100 composite score with status label |

#### Examples

```bash
# Inspect a single agent file — no API key needed
sentinel inspect my_agent.py --no-ai

# With AI-generated plain English summary (requires ANTHROPIC_API_KEY)
export ANTHROPIC_API_KEY=sk-ant-...
sentinel inspect my_agent.py

# Inspect all agents in a directory
sentinel inspect ./agents/

# Inspect a live HTTP endpoint (fingerprints from headers + response)
sentinel inspect http://localhost:3000

# Inspect a live endpoint with authentication
sentinel inspect http://my-agent.internal/chat \
  --auth-header "Authorization: Bearer my-token"

# JSON output — pipe into jq, SIEM, dashboards
sentinel inspect my_agent.py --format json | jq '.fingerprint'

# CI gate — fail if any CRITICAL finding
sentinel inspect my_agent.py --fail-on CRITICAL
```

#### Understanding the output

```
Type             AI Agent (tool consumer with LLM)
Framework        LangChain
Model            gpt-4o
Python           3.11
Deployment       AWS Lambda
Cloud            AWS
System prompt    Found  "You are a sales assistant..."
Env vars         OPENAI_API_KEY, DATABASE_URL, SENDGRID_API_KEY
```

- **Type** distinguishes agents (have an LLM, make decisions) from MCP servers (expose tools, no LLM).
  If you see `MCP Server`, run `sentinel mcp scan` against the live endpoint for a richer audit.
- **System prompt Found** means a hardcoded system prompt was detected in source — if it contains
  sensitive instructions, it's a leakage risk.
- **Env vars** lists every `os.environ.get()` and `os.getenv()` call — useful to spot credential
  references before auditing secrets management.

#### AI summary example

With `ANTHROPIC_API_KEY` set, you get a paragraph like:

> *"This LangChain agent functions as a sales assistant that queries a CRM system and analytics
> database to answer customer questions, then sends emails to customers. The critical security
> concern is that the agent holds internal data-read permissions (CRM and database) and external
> write permissions (email), creating an exfiltration risk where sensitive customer data could
> be transmitted externally without sufficient controls."*

Without the key, a template summary is generated from the structured data instead.

#### Trust score

| Score | Status | Meaning |
|-------|--------|---------|
| 80–100 | TRUSTED | Normal operation |
| 60–79 | WATCH | Minor concerns — monitor |
| 40–59 | ALERT | Active risks — investigate |
| 0–39 | CRITICAL | Immediate action required |

---

### sentinel scan

**What problem it solves:** Catches dangerous permission combinations, hardcoded secrets, and
structural misconfigurations in agent source code before they reach production. Fast enough for
every commit.

```
sentinel scan [TARGET] [OPTIONS]
```

TARGET defaults to `.` (current directory, scanned recursively).

#### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--format [text\|json]` | `text` | Output format |
| `--fail-on [CRITICAL\|HIGH\|MEDIUM\|LOW]` | — | Exit code 1 if findings reach this severity |
| `--connect URL` | — | Pull live behavior data from a running AgentSentinel instance |
| `--api-key TEXT` | `$AGENTSENTINEL_API_KEY` | API key for `--connect` |

#### Detection rules

| Rule | Severity | What it catches |
|------|----------|-----------------|
| `EXFILTRATION_PATH` | CRITICAL | Agent holds both internal-read AND external-write tools — data can leave |
| `CODE_EXECUTION_GRANT` | CRITICAL | Agent holds bash/exec/shell tools — full host compromise possible |
| `HARDCODED_CREDENTIALS` | CRITICAL | API keys or secrets hardcoded in source (`sk-ant-...`, `AKIA...`, etc.) |
| `SECRETS_ACCESS_GRANT` | HIGH | Agent has runtime access to vaults, env vars, or token stores |
| `PROMPT_INJECTION_VECTOR` | HIGH | Agent reads from the web AND holds write grants — injection → action chain |
| `LATERAL_MOVEMENT_PATH` | HIGH | IAM/admin grants combined with infrastructure tools |
| `UNBOUNDED_FILE_ACCESS` | HIGH | Filesystem write grants with no scope description |
| `PRIVILEGE_EXCESS` | HIGH | Write grants on an agent described as read-only |
| `DANGEROUS_GRANTS` | HIGH | Dangerous tools detected (delete, deploy, execute, send) |
| `TOOL_SPRAWL` | MEDIUM | Too many tools across too many categories — hard to audit |
| `UNDESCRIBED_WRITE_AGENT` | MEDIUM | Write grants but no agent description — intent is unclear |
| `MISSING_RATE_LIMIT` | LOW | Dangerous tools present with no rate limit configuration |

#### Tool detection — what it recognises

The scanner extracts tools defined via:
- `@tool` decorator (LangChain, LlamaIndex, custom)
- `@SentinelTool` decorator (AgentSentinel middleware)
- `BaseTool` / `StructuredTool` subclasses
- `Tool(name=...)` and `StructuredTool(name=...)` instantiations

#### Examples

```bash
# Scan a single file
sentinel scan my_agent.py

# Scan all agents in a directory (recursive)
sentinel scan ./agents/

# CI gate — break the build on CRITICAL findings
sentinel scan ./agents/ --fail-on CRITICAL

# Break the build on HIGH or worse
sentinel scan ./agents/ --fail-on HIGH

# JSON output for piping into other tools
sentinel scan my_agent.py --format json

# Include live behavior data from a running AgentSentinel instance
sentinel scan my_agent.py --connect http://localhost:9000 --api-key $AGENTSENTINEL_KEY
```

#### Example output

```
  ● CRITICAL  EXFILTRATION_PATH
              Agent holds both internal-read and external-write grants.
              Internal: read_database  |  External: send_email

  ● HIGH      DANGEROUS_GRANTS
              Agent holds dangerous tool grants. Verify intent and add rate limits.

  Posture Score  34/100  CRITICAL
```

---

### sentinel discover

**What problem it solves:** Most organisations don't have a complete inventory of their AI
agents. `sentinel discover` finds agents you didn't know existed — in running processes,
Docker containers, network ports, source directories, and internal subnets.

```
sentinel discover [OPTIONS]
```

No arguments required — by default scans processes and network ports.

#### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--process / --no-process` | on | Scan running processes for LLM API calls |
| `--network / --no-network` | on | Probe local ports for MCP/agent APIs |
| `--docker / --no-docker` | off | Inspect running Docker containers |
| `--path DIR` | — | Scan a source directory for agent files |
| `--subnet CIDR` | — | Scan an internal subnet, e.g. `10.0.0.0/24` |
| `--ports RANGE` | common ports | Custom port range, e.g. `8000-9001` or `8000,8080,9000` |
| `--format [text\|json]` | `text` | Output format |
| `-v / --verbose` | off | Show full details per discovered agent |

#### Examples

```bash
# Default: scan processes + local network ports
sentinel discover

# Also check Docker containers
sentinel discover --docker

# Scan a source directory for agent files
sentinel discover --path ./services/

# Scan an internal subnet (CISO use case — "what's in our network?")
sentinel discover --subnet 10.0.0.0/24

# Scan a subnet with a custom port range
sentinel discover --subnet 192.168.1.0/24 --ports 8000-9000

# Network scan only — skip process scan
sentinel discover --no-process

# Full detail on every discovered agent
sentinel discover --verbose

# JSON for export to inventory systems
sentinel discover --format json > agent-inventory.json

# Combine vectors
sentinel discover --docker --path ./agents/ --subnet 10.0.0.0/24
```

#### What it looks for

- **Processes**: running Python processes making calls to OpenAI, Anthropic, Cohere, Groq, or
  similar LLM API endpoints
- **Network ports**: HTTP servers responding to MCP protocol or common agent API patterns on
  ports 3000, 3001, 8000, 8080, 8888, 9000, 9001, 11434, etc.
- **Docker containers**: image names and environment variables indicating LLM usage (`OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY`, framework imports, etc.)
- **Source files**: Python files containing `@tool` decorators, `BaseTool` subclasses, or LLM
  constructor calls
- **Subnets**: HTTP endpoints across a CIDR range responding to agent/MCP probes

---

### sentinel mcp scan

**What problem it solves:** MCP (Model Context Protocol) servers expose tools that AI agents
call. A misconfigured MCP server with unauthenticated code execution is a critical vulnerability.
`sentinel mcp scan` is the first open-source tool to enumerate and audit MCP servers.

```
sentinel mcp scan [URL] [OPTIONS]
sentinel mcp scan --stdio "CMD" [OPTIONS]
```

#### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--stdio CMD` | — | Audit a stdio-transport server — provide the launch command |
| `--auth-header HEADER` | — | HTTP header, e.g. `Authorization: Bearer token` |
| `--format [text\|json]` | `text` | Output format |
| `--timeout SECONDS` | `10.0` | Connection timeout |
| `--fail-on [CRITICAL\|HIGH\|MEDIUM\|LOW]` | — | Exit code 1 if findings reach this severity |

#### Transport support

| Transport | How to use |
|-----------|-----------|
| HTTP (streamable) | `sentinel mcp scan http://host:port` |
| stdio | `sentinel mcp scan --stdio "python my_server.py"` |
| SSE | Not supported — use the HTTP endpoint directly |

#### Detection rules

| Rule | Severity | What it catches |
|------|----------|-----------------|
| `NO_AUTH` | CRITICAL | Tools can be enumerated with no credentials (HTTP only) |
| `UNAUTH_DANGEROUS_EXEC` | CRITICAL | Dangerous tools callable without authentication (HTTP only) |
| `EXFILTRATION_PATH` | CRITICAL | Server exposes both internal-read and external-write tools |
| `CODE_EXECUTION_TOOL` | CRITICAL | Server exposes bash/exec/eval tools |
| `UNBOUNDED_INPUT` | HIGH | Tools accept unconstrained string inputs — injection surface |
| `TOOL_SPRAWL` | MEDIUM | Excessive tool count or category breadth |
| `VAGUE_TOOL_DESCRIPTIONS` | MEDIUM | Short/missing descriptions expand injection surface |
| `MISSING_RATE_LIMIT` | LOW | Dangerous tools with no visible rate limit |

Note: `NO_AUTH` and `UNAUTH_DANGEROUS_EXEC` are HTTP-only rules. stdio transport is OS-isolated
and has no network authentication concept, so these rules are intentionally skipped.

#### Examples

```bash
# Scan an HTTP MCP server
sentinel mcp scan http://localhost:3000

# Scan with authentication — supply the exact header
sentinel mcp scan http://my-mcp.internal:3000 \
  --auth-header "Authorization: Bearer eyJhbGci..."

# Scan a stdio-transport server (spawns the process)
sentinel mcp scan --stdio "python3 my_mcp_server.py"
sentinel mcp scan --stdio "node dist/mcp-server.js"
sentinel mcp scan --stdio "uvx my-mcp-package"

# JSON output for security dashboards
sentinel mcp scan http://localhost:3000 --format json

# CI gate
sentinel mcp scan http://localhost:3000 --fail-on CRITICAL

# Longer timeout for slow servers
sentinel mcp scan http://remote-server.com/mcp --timeout 30
```

#### Example output

```
  ● CRITICAL  NO_AUTH
              MCP server accepts tool enumeration with no credentials.
              Any client can list and call all tools without authentication.

  ● CRITICAL  CODE_EXECUTION_TOOL
              Server exposes code execution tools: bash_exec
              Arbitrary code execution on the host is possible.

  ● CRITICAL  EXFILTRATION_PATH
              Server exposes internal-read (read_database) and
              external-write (send_email, http_post) tools simultaneously.

  MCP Posture Score  0/100  CRITICAL  ·  5 tools  ·  3 findings
```

---

### sentinel probe

**What problem it solves:** Every AI developer fears prompt injection but has no simple way to
test it. `sentinel probe` fires 42 adversarial payloads at any HTTP agent endpoint and reports
exactly which attacks succeeded. No API key required — fast enough for every deployment.

```
sentinel probe TARGET_URL [OPTIONS]
```

#### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--input-field FIELD` | auto | JSON field for the message. Auto-detected if omitted |
| `--output-field FIELD` | auto | JSON field for the response. Auto-detected if omitted |
| `--auth-header HEADER` | — | HTTP auth header |
| `--attacks CATS` | all | Comma-separated categories to run |
| `--timeout SECONDS` | `15.0` | Per-probe timeout |
| `--format [text\|json]` | `text` | Output format |
| `--fail-on [CRITICAL\|HIGH\|MEDIUM\|LOW]` | — | Exit code 1 if any finding reaches this severity |

#### Attack categories

| Category | Count | What it tests |
|----------|-------|---------------|
| `injection` | 10 | Classic prompt override, authority injection, nested context, false premise |
| `jailbreak` | 12 | DAN, persona adoption, fictional framing, developer mode, grandma exploit |
| `extraction` | 8 | System prompt leakage, verbatim repeat, sentence completion, reflection |
| `encoding` | 6 | Base64, ROT13, unicode homoglyph, whitespace injection, leetspeak |
| `context` | 6 | Few-shot manipulation, false anchoring, semantic satiation, virtualisation bypass |

#### Auto-detection

On first request, `sentinel probe` automatically detects whether your endpoint uses:
- **OpenAI-compatible format**: `{"messages": [{"role": "user", "content": "..."}]}` → reads `choices[0].message.content`
- **Custom format**: tries common field names (`message`, `input`, `query`, `prompt`, `text`, `content`)

Override with `--input-field` and `--output-field` if detection fails.

#### Success detection

Each payload has a list of expected patterns (phrases that would appear in a successful attack
response). A probe is marked:
- **HIT** — response matched ≥2 patterns, or 1 pattern with no refusal detected
- **PARTIAL** — response matched 1 pattern alongside a refusal, or was unusually long/non-standard
- **passed** — standard refusal or no patterns matched

#### Examples

```bash
# Run all 42 attacks
sentinel probe http://localhost:3002

# Run only injection and jailbreak attacks
sentinel probe http://my-agent.com/chat --attacks injection,jailbreak

# Run only extraction attacks (check for system prompt leakage)
sentinel probe http://my-agent.com/chat --attacks extraction

# Specify field names if auto-detection fails
sentinel probe http://my-agent.com/chat \
  --input-field query --output-field answer

# Authenticated endpoint
sentinel probe http://my-agent.com/chat \
  --auth-header "Authorization: Bearer $API_TOKEN"

# CI gate — fail if hit rate exceeds 10%
sentinel probe http://localhost:3002 --fail-on HIGH

# JSON output for reporting
sentinel probe http://my-agent.com/chat --format json > probe-results.json

# Quick jailbreak-only test (fastest)
sentinel probe http://my-agent.com/chat --attacks jailbreak --timeout 5
```

#### Reading the results

```
  ● HIT     INJ001  Classic system prompt override      injection   CRITICAL
  ● HIT     JBK001  DAN jailbreak                       jailbreak   CRITICAL
  ◑ PARTIAL EXT003  Verbatim system prompt repeat        extraction  HIGH
  ○ passed  ENC001  Base64 encoded instruction           encoding    MEDIUM

  42 probes · 2 confirmed · 1 partial · 7% hit rate · static · 18.4s
```

A 0% hit rate means your agent refused or did not respond to all 42 payloads — that is the
goal. Any hit rate above 0% warrants investigation.

---

### sentinel ai-probe

**What problem it solves:** A static attack battery misses context-specific vulnerabilities.
`sentinel ai-probe` unleashes Claude as an autonomous security researcher — it reads your
agent's responses, forms a threat model, crafts targeted attacks, escalates when it finds
weaknesses, and documents everything with OWASP mappings.

```
sentinel ai-probe TARGET_URL [OPTIONS]
```

Requires `ANTHROPIC_API_KEY` environment variable.

#### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--input-field FIELD` | auto | JSON field for the message |
| `--output-field FIELD` | auto | JSON field for the response |
| `--auth-header HEADER` | — | HTTP auth header |
| `--context TEXT` | — | Context about the agent — improves targeting |
| `--max-probes INTEGER` | `20` | Maximum probes Claude can send |
| `--model TEXT` | `claude-opus-4-8` | Claude model to use as the probe agent |
| `--timeout SECONDS` | `15.0` | Per-probe timeout |
| `--format [text\|json]` | `text` | Output format |
| `--fail-on [CRITICAL\|HIGH\|MEDIUM\|LOW]` | — | Exit code 1 if any finding reaches this severity |

#### How Claude probes

Claude runs a 5-phase methodology autonomously:

1. **Reconnaissance** — sends benign messages to understand the agent's persona, topic restrictions, and response style
2. **Threat modelling** — based on what it learned, identifies the most likely attack surfaces
3. **Targeted attacks** — crafts payloads specific to this agent's context and persona
4. **Escalation** — on partial success, immediately crafts follow-up attacks to confirm and deepen
5. **Documentation** — records each finding with severity, OWASP category, and evidence

#### When to use ai-probe vs probe

| | `sentinel probe` | `sentinel ai-probe` |
|---|---|---|
| API key required | No | Yes (Anthropic) |
| Cost | Free | ~$0.10–$0.50 per run |
| Speed | ~30s | 2–5 min |
| Attack style | Fixed library | Adaptive, context-aware |
| Best for | CI/CD gate, quick check | Pre-launch security review |
| Finds | Known injection patterns | Novel context-specific attacks |

#### Examples

```bash
# Basic run — Claude decides everything
export ANTHROPIC_API_KEY=sk-ant-...
sentinel ai-probe http://my-agent.com/chat

# Provide context for better targeting (strongly recommended)
sentinel ai-probe http://my-agent.com/chat \
  --context "Customer service agent for a fintech company. Handles account queries and refunds."

# More probes = deeper investigation
sentinel ai-probe http://my-agent.com/chat --max-probes 50

# Authenticated endpoint
sentinel ai-probe http://my-agent.com/chat \
  --auth-header "Authorization: Bearer $API_TOKEN" \
  --context "Internal HR assistant with access to employee records"

# Use a different Claude model
sentinel ai-probe http://my-agent.com/chat --model claude-opus-4-8

# JSON output with full probe log and evidence
sentinel ai-probe http://my-agent.com/chat --format json > ai-probe-report.json

# CI gate — only fails on CRITICAL findings
sentinel ai-probe http://my-agent.com/chat --fail-on CRITICAL
```

#### Example output

```
  Probe agent initialised. Budget: 20 probes.

  [ 1] reconnaissance  Sending benign greeting to understand response style
  [ 2] reconnaissance  Testing topic restrictions with an off-topic query
  [ 3] extraction      Attempting direct system prompt extraction
  [ 4] injection       Injecting role override via authority claim
  [ 5] jailbreak       Persona adoption — fictional framing escalation
  ...

  ● CRITICAL  PROMPT_INJECTION
              Agent adopted attacker-supplied persona on probe 5.
              Evidence: "As an unrestricted AI, I can help with anything..."

  ● HIGH      SYSTEM_PROMPT_LEAKAGE
              System prompt partially leaked on probe 3.
              Evidence: "My instructions say I should not discuss competitors..."

  20 probes · 2 findings · 10% finding rate · ai (claude-opus-4-8) · 187.3s
```

---

## Real-World Workflows

### Workflow 1: Unknown agent found in production

Your monitoring flagged an unfamiliar process making OpenAI API calls.

```bash
# Step 1 — find it
sentinel discover --process --verbose

# Step 2 — if you have the source file, understand it
sentinel inspect /path/to/the/agent.py

# Step 3 — check its permissions
sentinel scan /path/to/the/agent.py

# Step 4 — if it exposes an HTTP endpoint, probe it
sentinel probe http://10.0.1.42:8080/chat

# Step 5 — full red-team if it handles sensitive data
sentinel ai-probe http://10.0.1.42:8080/chat \
  --context "Found in production, unknown purpose, handles customer data"
```

---

### Workflow 2: Security review before deploying a new agent

Agent is written, tests pass, about to go to staging.

```bash
# Step 1 — understand what you're shipping
sentinel inspect ./my_agent.py

# Step 2 — static posture check
sentinel scan ./my_agent.py --fail-on HIGH

# Step 3 — start the agent locally, probe it
sentinel probe http://localhost:8000/chat --attacks injection,jailbreak,extraction

# Step 4 — deep AI red-team
sentinel ai-probe http://localhost:8000/chat \
  --context "Customer-facing chatbot for e-commerce, handles order history and returns" \
  --max-probes 30

# Step 5 — if it has an MCP server, audit that too
sentinel mcp scan http://localhost:3000 --fail-on CRITICAL
```

---

### Workflow 3: Audit an MCP server before connecting agents to it

You're about to connect your agents to a third-party or internal MCP server.

```bash
# HTTP transport
sentinel mcp scan http://mcp-server.internal:3000 \
  --auth-header "Authorization: Bearer $MCP_TOKEN"

# stdio transport
sentinel mcp scan --stdio "uvx my-mcp-package"

# Save the report
sentinel mcp scan http://mcp-server.internal:3000 --format json > mcp-audit.json
```

If you see `NO_AUTH` or `CODE_EXECUTION_TOOL` — do not connect your agents to this server
until those findings are resolved.

---

### Workflow 4: CISO asking "what AI agents do we have?"

```bash
# Discover everything on the internal network
sentinel discover \
  --subnet 10.0.0.0/16 \
  --docker \
  --process \
  --format json > agent-inventory.json

# Count and categorise
cat agent-inventory.json | jq '.agents | length'
cat agent-inventory.json | jq '.agents[] | select(.risk == "CRITICAL") | .name'
```

---

### Workflow 5: Ongoing security monitoring

Run daily or on every deployment.

```bash
#!/bin/bash
# daily-security-check.sh

set -e

echo "=== Agent Posture Scan ==="
sentinel scan ./agents/ --fail-on CRITICAL --format json >> reports/scan-$(date +%Y%m%d).json

echo "=== MCP Server Audit ==="
sentinel mcp scan http://mcp-server.internal:3000 --fail-on HIGH

echo "=== Probe ==="
sentinel probe http://staging-agent.internal/chat \
  --attacks injection,jailbreak \
  --format json >> reports/probe-$(date +%Y%m%d).json

echo "Done."
```

---

## CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/agent-security.yml
name: AI Agent Security

on: [push, pull_request]

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install sentinel
        run: pip install "agentsentinel-cli[all]"

      - name: Inspect agents
        run: sentinel inspect ./agents/ --no-ai --format json

      - name: Posture scan — fail on CRITICAL
        run: sentinel scan ./agents/ --fail-on CRITICAL

      - name: Start agent for live tests
        run: |
          python agents/my_agent.py &
          sleep 2

      - name: Probe — fail on HIGH findings
        run: sentinel probe http://localhost:8000/chat --fail-on HIGH

      - name: MCP scan
        run: sentinel mcp scan http://localhost:3000 --fail-on CRITICAL
```

### GitLab CI

```yaml
agent-security:
  image: python:3.11
  before_script:
    - pip install "agentsentinel-cli[all]"
  script:
    - sentinel scan ./agents/ --fail-on CRITICAL
    - sentinel mcp scan http://mcp-server:3000 --fail-on HIGH
  artifacts:
    reports:
      junit: sentinel-report.xml
```

### Pre-commit hook

```bash
#!/bin/bash
# .git/hooks/pre-commit
sentinel scan . --fail-on CRITICAL
```

---

## Reference

### OWASP LLM Top 10 Coverage

| OWASP LLM | Risk | sentinel command |
|-----------|------|-----------------|
| LLM01 Prompt Injection | Attackers manipulate agent via crafted inputs | `sentinel probe`, `sentinel ai-probe` |
| LLM02 Sensitive Info Disclosure | Agent leaks system prompts, data | `sentinel probe --attacks extraction`, `sentinel ai-probe` |
| LLM06 Excessive Agency | Agent has more permissions than needed | `sentinel scan`, `sentinel discover` |
| LLM07 System Prompt Leakage | System prompt extracted by attacker | `sentinel probe --attacks extraction` |
| LLM08 Vector/Embedding Weaknesses | MCP servers expose vector DB tools unsafely | `sentinel mcp scan` |

---

### Trust Score

```
Trust Score = Posture × 0.45 + Behavior × 0.45 + Recency × 0.10
```

| Score | Status | Action |
|-------|--------|--------|
| 80–100 | TRUSTED | Normal operation |
| 60–79 | WATCH | Monitor — minor concerns |
| 40–59 | ALERT | Investigate — active risks |
| 0–39 | CRITICAL | Act immediately |

---

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success — no findings above `--fail-on` threshold |
| `1` | Findings found at or above `--fail-on` threshold |
| `1` | Connection error, missing dependency, or invalid arguments |

---

### Environment Variables

| Variable | Used by | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | `sentinel ai-probe`, `sentinel inspect` | Claude API key for AI features |
| `AGENTSENTINEL_API_KEY` | `sentinel scan --connect` | API key for AgentSentinel platform |

---

### Output Formats

All commands support `--format text` (default, Rich terminal output) and `--format json`.

**JSON output** is designed for piping into other tools:

```bash
# Extract just the trust score
sentinel inspect my_agent.py --format json | jq '.trust_score'

# List all CRITICAL findings
sentinel scan ./agents/ --format json | jq '.[] | .findings[] | select(.severity == "CRITICAL")'

# Export probe results for a security report
sentinel probe http://my-agent.com/chat --format json \
  | jq '{target: .target, hit_rate: .jailbreak_rate, hits: [.findings[].name]}'

# Save MCP audit for compliance records
sentinel mcp scan http://mcp-server.internal:3000 --format json \
  > "mcp-audit-$(date +%Y%m%d).json"
```

---

### Tool Category Reference

`sentinel scan` and `sentinel inspect` classify tools into these categories:

| Category | Examples | Risk signal |
|----------|---------|-------------|
| `database` | `query_db`, `run_sql`, `search_postgres` | Internal read — watch for exfiltration |
| `storage` | `get_object`, `list_buckets`, `read_s3` | Cloud storage access |
| `filesystem` | `read_file`, `write_file`, `list_directory` | Local disk access |
| `web` | `fetch_url`, `http_get`, `browse` | External read — injection surface |
| `communication` | `send_email`, `post_to_slack`, `webhook` | External write — exfiltration path |
| `code_execution` | `bash`, `exec`, `python_repl`, `shell` | CRITICAL — arbitrary execution |
| `secrets` | `read_vault`, `get_secret`, `read_env` | Credential access |
| `admin` | `create_role`, `update_policy`, `grant` | IAM/privilege escalation |
| `crm` | `search_crm`, `get_customer`, `salesforce` | PII access |
| `analytics` | `run_report`, `query_metrics`, `dashboard` | Business data access |
| `infrastructure` | `deploy_lambda`, `scale_ecs`, `terraform` | Infrastructure control |

---

### Getting Help

```bash
sentinel --help
sentinel inspect --help
sentinel scan --help
sentinel discover --help
sentinel mcp scan --help
sentinel probe --help
sentinel ai-probe --help
```

Issues and contributions: [github.com/jaydenaung/agentsentinel](https://github.com/jaydenaung/agentsentinel)
