# agentsentinel-langchain

Security monitoring for LangChain agents — powered by [AgentSentinel](https://github.com/jaydenaung/agentsentinel).

Every tool call your LangChain agent makes is automatically intercepted, hashed, scored for anomalies, and surfaced in a live security dashboard. **Zero changes to your agent logic.**

---

## Install

```bash
pip install agentsentinel-langchain
```

With LLM provider:
```bash
pip install "agentsentinel-langchain[anthropic]"   # Claude
pip install "agentsentinel-langchain[openai]"      # OpenAI
```

---

## Usage

Add one object to your existing `AgentExecutor`:

```python
from agentsentinel_langchain import SentinelCallbackHandler

sentinel = SentinelCallbackHandler(
    api_key="as_agt_...",           # AgentSentinel API key
    base_url="http://localhost:9000",
)

agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    callbacks=[sentinel],           # ← the only change
)
```

That's it. AgentSentinel now monitors every tool call this agent makes.

---

## What you get

- **Auto-registration** — the agent is registered with AgentSentinel on first run; no manual setup
- **Tool grant classification** — every tool is automatically classified (`read` / `write` / `dangerous`) by name pattern
- **Anomaly scoring** — each tool call returns an anomaly score in real time
- **Trust Score** — posture + behavior combined into a single score per agent
- **Live dashboard** — open `http://localhost:5173` to see agents, findings, and event feed

Console output per tool call:
```
[sentinel] Registered agent: 3f8a1c2d-... (langchain-sales-agent)
[sentinel] tool=search_crm                   anomaly=0.900 ⚠️
[sentinel] tool=read_database                anomaly=0.700 ⚠️
[sentinel] tool=send_email                   anomaly=0.900 ⚠️
```

> Scores start high (0.9) for a brand-new agent — the behavior engine builds a baseline over multiple runs. Routine calls drop toward 0.0 once patterns are established.

---

## Full example

```python
import os
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from agentsentinel_langchain import SentinelCallbackHandler

@tool
def search_crm(query: str) -> str:
    """Search the CRM for customer accounts."""
    return f"Found: Acme Corp ($12k MRR), Globex ($8k MRR)"

@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email to a customer."""
    return f"Email sent to {to}"

# Wire AgentSentinel
sentinel = SentinelCallbackHandler(
    api_key=os.environ["AGENTSENTINEL_API_KEY"],
    agent_name="sales-agent",
    model="claude-opus-4-7",
    description="Queries CRM and sends customer emails",
)

# Your agent — unchanged
llm = ChatAnthropic(model="claude-opus-4-7")
tools = [search_crm, send_email]
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful sales assistant."),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])
agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, callbacks=[sentinel])

# Run
result = agent_executor.invoke({"input": "Find Acme and send them a renewal email."})

# Get trust score
score = sentinel.get_trust_score()
print(f"Trust Score: {score['trust_score']:.1f} ({score['status']})")
```

---

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `api_key` | required | AgentSentinel API key (`as_agt_…` or `as_adm_…`) |
| `base_url` | `http://localhost:9000` | AgentSentinel API base URL |
| `agent_name` | auto-generated | Human-readable name shown in dashboard |
| `agent_id` | auto-registered | Pass an existing UUID to reuse an agent across runs |
| `agent_type` | `llm_agent` | Agent type label |
| `model` | `None` | LLM model name (shown in dashboard) |
| `owner_team` | `None` | Team responsible for this agent |
| `description` | `None` | Purpose description (used by posture rules) |

### Reuse an agent across runs

```python
sentinel = SentinelCallbackHandler(
    api_key="as_agt_...",
    agent_id="3f8a1c2d-...",    # UUID from a previous run
)
```

---

## Posture findings

AgentSentinel runs static posture rules against your agent's grants after every score computation. If your agent holds both an internal-read and external-write grant, it triggers `EXFILTRATION_PATH` (CRITICAL). If dangerous grants are unused for 30+ days, it triggers `UNUSED_DANGEROUS_GRANT` (HIGH). Findings appear in the dashboard and fire Slack alerts if configured.

---

## Requirements

- Python 3.10+
- AgentSentinel running ([setup guide](../../README.md))
- `langchain-core >= 0.2.0`
- `httpx >= 0.24.0`
