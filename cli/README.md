# agentsentinel-cli

One-command security scanner for AI agents. No server, no Docker, no setup.

```bash
pip install agentsentinel-cli
sentinel scan my_agent.py
```

Detects exfiltration paths, dangerous grants, privilege mismatches, and more —
from static analysis of your Python agent files.

---

## Install

```bash
pip install agentsentinel-cli
```

---

## Usage

```bash
# Scan a single file
sentinel scan my_agent.py

# Scan a directory recursively
sentinel scan ./agents/

# Fail with exit code 1 if CRITICAL findings exist (for CI)
sentinel scan my_agent.py --fail-on CRITICAL

# Output JSON (for piping into other tools)
sentinel scan my_agent.py --format json

# Include live behavior data from a running AgentSentinel instance
sentinel scan my_agent.py --connect http://localhost:9000
```

---

## What it detects

| Rule | Severity | Description |
|------|----------|-------------|
| `EXFILTRATION_PATH` | CRITICAL | Agent holds internal-read AND external-write grants |
| `DANGEROUS_GRANTS` | HIGH | Agent holds dangerous tool grants |
| `PRIVILEGE_EXCESS` | HIGH | Write grants on a read-only described agent |
| `UNDESCRIBED_WRITE_AGENT` | MEDIUM | Write grants with no agent description |
| `MISSING_RATE_LIMIT` | LOW | Dangerous grants without rate limit configuration |

---

## Tool detection

The scanner detects tools defined via:
- `@tool` decorator (LangChain)
- `@SentinelTool` decorator (AgentSentinel middleware)
- `BaseTool` / `StructuredTool` subclasses
- `Tool(name=...)` and `StructuredTool(name=...)` instantiations

---

## CI/CD integration

```yaml
# .github/workflows/security.yml
- name: Scan AI agents
  run: |
    pip install agentsentinel-cli
    sentinel scan ./agents/ --fail-on CRITICAL
```

---

## Requirements

- Python 3.10+
- No running server required for static scan
- `httpx` required for `--connect` flag: `pip install "agentsentinel-cli[connect]"`
