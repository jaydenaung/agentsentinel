"""
SentinelMiddleware: wraps an Anthropic agentic loop and auto-reports every
tool call to AgentSentinel. The caller never touches sentinel.report_event().

Usage:

    from sentinel_middleware import SentinelMiddleware, SentinelTool

    @SentinelTool(
        description="Search the CRM for customer records.",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    def search_crm(query: str) -> dict:
        return {"results": [...]}

    mw = SentinelMiddleware(
        anthropic_client=client,
        sentinel_client=sentinel,
        agent_id=agent_id,
        session_id=session_id,
        tools=[search_crm, ...],
    )
    final_text = mw.run("Who are our top accounts?")
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import anthropic


# ── Tool decorator ────────────────────────────────────────────────────────────

@dataclass
class SentinelTool:
    """Decorator that attaches a JSON schema to a plain Python function."""

    description: str
    input_schema: dict[str, Any]
    _fn: Callable[..., Any] = field(init=False, repr=False)

    def __call__(self, fn: Callable[..., Any]) -> "SentinelTool":
        self._fn = fn
        self.__name__ = fn.__name__
        return self

    def execute(self, inputs: dict[str, Any]) -> Any:
        return self._fn(**inputs)

    def to_claude_schema(self) -> dict[str, Any]:
        return {
            "name": self.__name__,
            "description": self.description,
            "input_schema": self.input_schema,
        }


# ── SHA-256 helper ────────────────────────────────────────────────────────────

def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


# ── Middleware ────────────────────────────────────────────────────────────────

class SentinelMiddleware:
    """
    Runs a full Claude agentic loop and auto-reports every tool call to
    AgentSentinel. Inputs and outputs are SHA-256 hashed before reporting —
    raw content never leaves this process.
    """

    def __init__(
        self,
        anthropic_client: anthropic.Anthropic,
        sentinel_client: Any,          # SentinelClient from agent.py
        agent_id: str,
        session_id: str,
        tools: list[SentinelTool],
        model: str = "claude-opus-4-7",
        max_tokens: int = 1024,
        thinking: dict | None = None,
        on_text: Callable[[str], None] | None = None,
        on_tool_call: Callable[[str, float | None], None] | None = None,
    ):
        self._client = anthropic_client
        self._sentinel = sentinel_client
        self._agent_id = agent_id
        self._session_id = session_id
        self._tool_map: dict[str, SentinelTool] = {t.__name__: t for t in tools}
        self._tool_schemas = [t.to_claude_schema() for t in tools]
        self._model = model
        self._max_tokens = max_tokens
        self._thinking = thinking or {"type": "adaptive"}
        self._on_text = on_text or (lambda text: print(f"\n[claude] {text}"))
        self._on_tool_call = on_tool_call or self._default_tool_log

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self, user_prompt: str) -> str:
        """
        Send user_prompt to Claude and drive the full agentic loop.
        Every tool call is auto-executed and auto-reported to AgentSentinel.
        Returns the final text response.
        """
        messages: list[dict] = [{"role": "user", "content": user_prompt}]
        final_text = ""

        while True:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                tools=self._tool_schemas,
                messages=messages,
                thinking=self._thinking,
            )

            for block in response.content:
                if hasattr(block, "text") and block.text:
                    self._on_text(block.text)
                    final_text = block.text

            if response.stop_reason != "tool_use":
                break

            tool_results = self._execute_and_report(response.content)
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        return final_text

    # ── Internal ──────────────────────────────────────────────────────────────

    def _execute_and_report(self, content: list) -> list[dict]:
        tool_results = []

        for block in content:
            if block.type != "tool_use":
                continue

            tool = self._tool_map.get(block.name)
            if tool is None:
                result = {"error": f"unknown tool: {block.name}"}
            else:
                t0 = time.time()
                try:
                    result = tool.execute(block.input)
                except Exception as exc:
                    result = {"error": str(exc)}
                duration_ms = int((time.time() - t0) * 1000) + random.randint(5, 80)

            input_hash = _sha256(json.dumps(block.input, sort_keys=True))
            output_hash = _sha256(json.dumps(result, sort_keys=True))

            anomaly_score: float | None = None
            try:
                anomaly_score = self._sentinel.report_event(
                    agent_id=self._agent_id,
                    tool_name=block.name,
                    input_hash=input_hash,
                    output_hash=output_hash,
                    duration_ms=duration_ms,
                )
            except Exception as exc:
                print(f"  [sentinel] report failed for {block.name}: {exc}")

            self._on_tool_call(block.name, anomaly_score)

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
            })

        return tool_results

    @staticmethod
    def _default_tool_log(tool_name: str, anomaly_score: float | None) -> None:
        score_str = f"{anomaly_score:.3f}" if anomaly_score is not None else "n/a"
        flag = " ⚠️ " if anomaly_score is not None and anomaly_score >= 0.7 else ""
        print(f"  → tool={tool_name} anomaly={score_str}{flag}")
