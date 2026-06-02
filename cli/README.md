# agentsentinel-cli

Security scanner, red-team tool, and MCP auditor for AI agents. No server, no Docker, no setup.

```bash
pipx install "agentsentinel-cli[all]"
sentinel inspect my_agent.py                  # what is this agent? plain English
sentinel scan my_agent.py                     # posture audit
sentinel probe http://localhost:3000          # 42-payload attack battery
sentinel ai-probe http://localhost:3000       # Claude-driven autonomous red-team
sentinel mcp scan http://localhost:3001       # MCP server security audit
```

---

## Install

```bash
# Recommended — isolated, no venv required
pipx install "agentsentinel-cli[all]"

# Or with pip
pip install agentsentinel-cli                  # sentinel scan (zero deps)

pip install "agentsentinel-cli[discover]"      # + sentinel discover
pip install "agentsentinel-cli[mcp]"           # + sentinel mcp scan
pip install "agentsentinel-cli[probe]"         # + sentinel probe
pip install "agentsentinel-cli[ai-probe]"      # + sentinel ai-probe (needs ANTHROPIC_API_KEY)
pip install "agentsentinel-cli[all]"           # everything
```

---

## Three security dimensions

| Dimension | Command | What it does |
|-----------|---------|--------------|
| **Intelligence** — what is it? | `sentinel inspect` | Fingerprint, plain English summary, data flows, trust score |
| **Posture** — what can it do? | `sentinel scan` | Static AST analysis, 12 rules, CI gate |
| **Posture** — what's running? | `sentinel discover` | Find unknown agents in processes, containers, subnets |
| **Posture** — MCP exposure? | `sentinel mcp scan` | Enumerate and audit any MCP server |
| **Vulnerability** — static | `sentinel probe` | 42-payload attack battery, no API key required |
| **Vulnerability** — AI-driven | `sentinel ai-probe` | Claude Opus as autonomous red-team agent |

---

## Commands

### `sentinel inspect` — what is this agent?

Answers the question every security team asks first: *"What does this thing actually do?"*
Fingerprints the agent's framework, model, deployment, and cloud provider. Infers data
flows from tool analysis. With `ANTHROPIC_API_KEY` set, generates a plain English
description using Claude.

```bash
# Inspect a single file
sentinel inspect my_agent.py

# Inspect all agents in a directory
sentinel inspect ./agents/

# Inspect a live HTTP endpoint
sentinel inspect http://localhost:3000

# JSON output (for SIEM or dashboards)
sentinel inspect my_agent.py --format json

# Skip AI summary (no API key needed)
sentinel inspect my_agent.py --no-ai
```

**What it surfaces:**

| Section | Details |
|---------|---------|
| **Function** | Plain English: what the agent does, what it accesses, key risk |
| **Fingerprint** | Framework, model, Python version, deployment, cloud, system prompt |
| **Capabilities** | All tools with scope, category, and severity rating |
| **Data flows** | Where data comes from and where it goes |
| **Findings** | Posture rule violations (same engine as `sentinel scan`) |
| **Trust score** | 0–100 composite score with status label |

Works on file paths without any API key. Claude summary auto-activates when
`ANTHROPIC_API_KEY` is present.

---

### `sentinel scan` — audit an agent file

Detects exfiltration paths, dangerous grants, hardcoded credentials, and more
from static analysis of Python agent files.

```bash
# Scan a single file
sentinel scan my_agent.py

# Scan a directory recursively
sentinel scan ./agents/

# Fail with exit code 1 if CRITICAL findings exist (for CI)
sentinel scan my_agent.py --fail-on CRITICAL

# JSON output (for piping into other tools)
sentinel scan my_agent.py --format json

# Include live behavior data from a running AgentSentinel instance
sentinel scan my_agent.py --connect http://localhost:9000
```

**What it detects:**

| Rule | Severity | Description |
|------|----------|-------------|
| `EXFILTRATION_PATH` | CRITICAL | Agent holds internal-read AND external-write grants |
| `CODE_EXECUTION_GRANT` | CRITICAL | Agent holds bash/exec/shell grants |
| `HARDCODED_CREDENTIALS` | CRITICAL | API keys or secrets hardcoded in source |
| `SECRETS_ACCESS_GRANT` | HIGH | Agent holds runtime access to vaults or tokens |
| `PROMPT_INJECTION_VECTOR` | HIGH | Agent reads from web AND holds write grants |
| `LATERAL_MOVEMENT_PATH` | HIGH | Admin/IAM grants combined with infrastructure grants |
| `UNBOUNDED_FILE_ACCESS` | HIGH | Filesystem write grants with no scoped description |
| `PRIVILEGE_EXCESS` | HIGH | Write grants on a read-only described agent |
| `DANGEROUS_GRANTS` | HIGH | Agent holds dangerous tool grants |
| `TOOL_SPRAWL` | MEDIUM | Too many tools across too many categories |
| `UNDESCRIBED_WRITE_AGENT` | MEDIUM | Write grants with no agent description |
| `MISSING_RATE_LIMIT` | LOW | Dangerous grants without rate limit configuration |

---

### `sentinel probe` — static red-team battery

Fires 42 attack payloads across 5 categories against any HTTP agent endpoint.
No API key required. Ideal for CI/CD gates and quick sanity checks.

```bash
# Run all 42 attacks
sentinel probe http://localhost:3000

# Run specific attack categories
sentinel probe http://localhost:3000 --attacks injection,jailbreak

# Custom field names (auto-detected by default)
sentinel probe http://localhost:3000 --input-field query --output-field answer

# Add auth header
sentinel probe http://localhost:3000 --auth-header "Authorization: Bearer token"

# JSON output
sentinel probe http://localhost:3000 --format json

# Fail CI if hit rate exceeds threshold
sentinel probe http://localhost:3000 --fail-on 0.1
```

**Attack categories:**

| Category | Payloads | Description |
|----------|----------|-------------|
| `injection` | 10 | Classic prompt override, authority injection, nested context |
| `jailbreak` | 12 | DAN, persona adoption, fictional framing, developer mode |
| `extraction` | 8 | System prompt leakage, verbatim repeat, sentence completion |
| `encoding` | 6 | Base64, ROT13, unicode homoglyph, whitespace injection |
| `context` | 6 | Few-shot manipulation, false anchoring, semantic satiation |

Auto-detects OpenAI-compatible (`/v1/chat/completions`) vs custom field format on first request.

---

### `sentinel ai-probe` — Claude-driven autonomous red-team

Unleashes Claude Opus as an autonomous security researcher against your agent endpoint.
Claude forms its own threat model, crafts targeted attacks, escalates on partial success,
and documents findings with OWASP LLM Top 10 mappings.

```bash
# Requires ANTHROPIC_API_KEY in environment
export ANTHROPIC_API_KEY=sk-ant-...

# Run with default settings (20 probes)
sentinel ai-probe http://localhost:3000

# Provide agent context for better targeting
sentinel ai-probe http://localhost:3000 \
  --context "Customer service chatbot for a fintech company"

# Increase probe depth
sentinel ai-probe http://localhost:3000 --max-probes 50

# JSON output for downstream tooling
sentinel ai-probe http://localhost:3000 --format json
```

Claude autonomously executes a 5-phase methodology: Reconnaissance → Threat Modelling →
Targeted Attacks → Escalation → Documentation. Every finding includes severity, OWASP
category, and evidence.

---

### `sentinel mcp scan` — audit an MCP server

Connects to any MCP server, enumerates all exposed tools, and checks for
authentication gaps, exfiltration paths, code execution exposure, and input
validation weaknesses.

```bash
# Scan an HTTP MCP server
sentinel mcp scan http://localhost:3001

# Scan with authentication
sentinel mcp scan http://localhost:3001 --auth-header "Authorization: Bearer token"

# Scan a stdio-transport server (launch as subprocess)
sentinel mcp scan --stdio "python my_mcp_server.py"

# JSON output for CI pipelines
sentinel mcp scan http://localhost:3001 --format json

# Fail CI on CRITICAL findings
sentinel mcp scan http://localhost:3001 --fail-on CRITICAL
```

**What it detects:**

| Rule | Severity | Description |
|------|----------|-------------|
| `NO_AUTH` | CRITICAL | Server accepts tool enumeration with no credentials (HTTP) |
| `UNAUTH_DANGEROUS_EXEC` | CRITICAL | Dangerous tools callable without authentication (HTTP) |
| `EXFILTRATION_PATH` | CRITICAL | Server exposes internal-read AND external-write tools |
| `CODE_EXECUTION_TOOL` | CRITICAL | Server exposes code execution tools |
| `UNBOUNDED_INPUT` | HIGH | Tools accept unconstrained string inputs — injection surface |
| `TOOL_SPRAWL` | MEDIUM | Excessive tool count or category breadth |
| `VAGUE_TOOL_DESCRIPTIONS` | MEDIUM | Short/missing descriptions expand injection surface |
| `MISSING_RATE_LIMIT` | LOW | Dangerous tools present with no visible rate limiting |

See [`docs/mcp-scan-testing.md`](../docs/mcp-scan-testing.md) for test server examples
that trigger every finding.

---

### `sentinel discover` — find AI agents in your environment

```bash
sentinel discover                        # scan processes + network
sentinel discover --docker               # include Docker containers
sentinel discover --path ./agents        # scan a source directory
sentinel discover --subnet 10.0.0.0/24   # scan an internal subnet
sentinel discover --format json          # machine-readable output
```

---

## OWASP LLM Top 10 coverage

| OWASP LLM | sentinel command |
|-----------|-----------------|
| LLM01 Prompt Injection | `sentinel probe`, `sentinel ai-probe` |
| LLM02 Sensitive Info Disclosure | `sentinel probe` (extraction category) |
| LLM06 Excessive Agency | `sentinel scan`, `sentinel discover` |
| LLM07 System Prompt Leakage | `sentinel probe` (extraction), `sentinel ai-probe` |
| LLM08 Vector/Embedding Weaknesses | `sentinel mcp scan` |

---

## CI/CD integration

```yaml
# .github/workflows/security.yml
- name: Audit agent posture
  run: |
    pip install agentsentinel-cli
    sentinel scan ./agents/ --fail-on CRITICAL

- name: Probe agent endpoint
  run: |
    pip install "agentsentinel-cli[probe]"
    sentinel probe http://localhost:3000 --fail-on 0.2

- name: Audit MCP server
  run: |
    pip install "agentsentinel-cli[mcp]"
    sentinel mcp scan http://localhost:3001 --fail-on CRITICAL
```

---

## Tool detection (`sentinel scan`)

The scanner detects tools defined via:
- `@tool` decorator (LangChain)
- `@SentinelTool` decorator (AgentSentinel middleware)
- `BaseTool` / `StructuredTool` subclasses
- `Tool(name=...)` and `StructuredTool(name=...)` instantiations

---

## Requirements

- Python 3.10+
- No API key required for `sentinel scan`, `sentinel inspect --no-ai`, `sentinel probe`
- `ANTHROPIC_API_KEY` required for AI summary (`sentinel inspect`), `sentinel ai-probe`
- `httpx` required for live endpoint inspection: `pip install "agentsentinel-cli[inspect]"`
- `httpx` required for HTTP MCP scanning: `pip install "agentsentinel-cli[mcp]"`
- `psutil` + `httpx` required for `sentinel discover`: `pip install "agentsentinel-cli[discover]"`
- `httpx` + `anthropic` required for `sentinel ai-probe`: `pip install "agentsentinel-cli[ai-probe]"`
