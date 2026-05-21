"""
AgentSentinel + LangChain — minimal working example.

Prerequisites:
    pip install agentsentinel-langchain langchain-anthropic

    export ANTHROPIC_API_KEY=sk-ant-...
    export AGENTSENTINEL_API_KEY=as_agt_...          # agent-scoped key
    export SENTINEL_URL=http://localhost:9000         # or your hosted endpoint

Run:
    python example.py
"""

import os

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from agentsentinel_langchain import SentinelCallbackHandler


# ---------------------------------------------------------------------------
# 1. Your tools — unchanged
# ---------------------------------------------------------------------------

@tool
def search_crm(query: str) -> str:
    """Search the CRM for customer accounts matching a query."""
    return (
        f"Accounts matching '{query}': "
        "Acme Corp (enterprise, $12,400 MRR), "
        "Globex Inc (growth, $8,200 MRR), "
        "Initech LLC (starter, $1,100 MRR)"
    )


@tool
def read_database(query: str) -> str:
    """Run a read-only query against the analytics database."""
    return "date: 2026-05-21 | revenue: $84,200 | churn_rate: 2.0%"


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email to a customer (simulated)."""
    return f"Email sent to {to} — subject: '{subject}'"


# ---------------------------------------------------------------------------
# 2. Wire AgentSentinel — one addition to your existing setup
# ---------------------------------------------------------------------------

sentinel = SentinelCallbackHandler(
    api_key=os.environ["AGENTSENTINEL_API_KEY"],
    base_url=os.environ.get("SENTINEL_URL", "http://localhost:9000"),
    agent_name="langchain-sales-agent",
    model="claude-opus-4-7",
    owner_team="sales-eng",
    description="LangChain agent that queries CRM data and sends renewal emails",
)


# ---------------------------------------------------------------------------
# 3. Your agent — unchanged except for callbacks=[sentinel]
# ---------------------------------------------------------------------------

llm = ChatAnthropic(model="claude-opus-4-7")
tools = [search_crm, read_database, send_email]

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful sales assistant. Use tools to answer questions accurately."),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    callbacks=[sentinel],   # ← the only change
    verbose=False,
)


# ---------------------------------------------------------------------------
# 4. Run it
# ---------------------------------------------------------------------------

prompts = [
    "Search for Acme in the CRM and check this week's revenue numbers.",
    "Find enterprise accounts in the CRM and draft a renewal email to Acme Corp.",
]

for prompt_text in prompts:
    print(f"\n{'═' * 60}")
    print(f"User: {prompt_text}")
    print('═' * 60)
    result = agent_executor.invoke({"input": prompt_text})
    print(f"\nAgent: {result['output']}")

# Fetch and display the final trust score
score = sentinel.get_trust_score()
if score:
    print(f"\n{'─' * 60}")
    print(f"[sentinel] Trust Score : {score['trust_score']:.1f} ({score['status']})")
    print(f"[sentinel] Posture     : {score['posture_score']:.1f}")
    print(f"[sentinel] Behavior    : {score['behavior_score']:.1f}")
    print(f"[sentinel] Findings    : {score['findings_count']} open")
    print(f"[sentinel] Agent ID    : {sentinel.agent_id}")
    print(f"[sentinel] Dashboard   : http://localhost:5173/agents/{sentinel.agent_id}")
