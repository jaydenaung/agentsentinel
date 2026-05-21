"""LangChain callback handler for AgentSentinel security monitoring."""

import hashlib
import time
import uuid
from typing import Any, Dict, Optional, Union

import httpx
from langchain_core.callbacks import BaseCallbackHandler

_DEFAULT_BASE_URL = "http://localhost:9000"

_WRITE_PATTERNS = (
    "write", "edit", "create", "delete", "remove", "move", "rename",
    "execute", "run", "exec", "patch", "update", "insert", "drop",
    "truncate", "send", "post", "put", "upload", "deploy", "reset", "kill",
)
_DANGEROUS_PATTERNS = (
    "delete", "remove", "drop", "truncate", "execute", "run", "exec",
    "send", "deploy", "reset", "kill",
)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _classify_tool(tool_name: str) -> tuple[str, bool]:
    lower = tool_name.lower()
    is_dangerous = any(p in lower for p in _DANGEROUS_PATTERNS)
    is_write = is_dangerous or any(p in lower for p in _WRITE_PATTERNS)
    return ("write" if is_write else "read"), is_dangerous


class SentinelCallbackHandler(BaseCallbackHandler):
    """Drop-in LangChain callback that reports every tool call to AgentSentinel.

    Add it to any AgentExecutor or chain in one line — no changes to your
    agent logic, tools, or prompts required.

    Example::

        from agentsentinel_langchain import SentinelCallbackHandler

        sentinel = SentinelCallbackHandler(api_key="as_agt_...",)
        agent_executor = AgentExecutor(agent=agent, tools=tools, callbacks=[sentinel])
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = _DEFAULT_BASE_URL,
        agent_name: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_type: str = "llm_agent",
        model: Optional[str] = None,
        owner_team: Optional[str] = None,
        description: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.session_id = f"lc-{uuid.uuid4().hex[:8]}"
        self._headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
        self._tool_names: Dict[str, str] = {}
        self._tool_start_times: Dict[str, float] = {}
        self._tool_inputs: Dict[str, str] = {}
        self._registered_tools: set[str] = set()

        if agent_id:
            self.agent_id: str = agent_id
            print(f"[sentinel] Using existing agent: {agent_id}")
        else:
            self.agent_id = self._register_agent(
                name=agent_name or f"langchain-agent-{uuid.uuid4().hex[:6]}",
                agent_type=agent_type,
                model=model,
                owner_team=owner_team,
                description=description,
            )

    # ------------------------------------------------------------------
    # Registration helpers
    # ------------------------------------------------------------------

    def _register_agent(
        self,
        name: str,
        agent_type: str,
        model: Optional[str],
        owner_team: Optional[str],
        description: Optional[str],
    ) -> str:
        payload: Dict[str, Any] = {"name": name, "agent_type": agent_type}
        if model:
            payload["model"] = model
        if owner_team:
            payload["owner_team"] = owner_team
        if description:
            payload["description"] = description

        try:
            with httpx.Client(timeout=10.0) as client:
                r = client.post(
                    f"{self.base_url}/api/v1/agents",
                    json=payload,
                    headers=self._headers,
                )
                r.raise_for_status()
                agent_id = r.json()["id"]
                print(f"[sentinel] Registered agent: {agent_id} ({name})")
                return agent_id
        except Exception as exc:
            fallback = str(uuid.uuid4())
            print(f"[sentinel] Warning: registration failed ({exc}) — using local ID {fallback}")
            return fallback

    def _add_grant(self, tool_name: str) -> None:
        """Auto-register a tool grant on first encounter."""
        if tool_name in self._registered_tools:
            return
        scope, is_dangerous = _classify_tool(tool_name)
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.post(
                    f"{self.base_url}/api/v1/agents/{self.agent_id}/grants",
                    json={"tool_name": tool_name, "scope": scope, "is_dangerous": is_dangerous},
                    headers=self._headers,
                )
                r.raise_for_status()
                self._registered_tools.add(tool_name)
        except Exception:
            pass  # Never crash the agent over a grant registration failure

    # ------------------------------------------------------------------
    # LangChain callbacks
    # ------------------------------------------------------------------

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        run_key = str(run_id)
        tool_name = serialized.get("name", "unknown_tool")
        self._tool_names[run_key] = tool_name
        self._tool_start_times[run_key] = time.monotonic()
        self._tool_inputs[run_key] = input_str
        self._add_grant(tool_name)

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        run_key = str(run_id)
        tool_name = self._tool_names.pop(run_key, "unknown_tool")
        start = self._tool_start_times.pop(run_key, None)
        input_str = self._tool_inputs.pop(run_key, "")
        duration_ms = int((time.monotonic() - start) * 1000) if start else None

        self._report_event(
            tool_name=tool_name,
            input_hash=_sha256(input_str),
            output_hash=_sha256(str(output)),
            duration_ms=duration_ms,
        )

    def on_tool_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        run_key = str(run_id)
        tool_name = self._tool_names.pop(run_key, "unknown_tool")
        start = self._tool_start_times.pop(run_key, None)
        input_str = self._tool_inputs.pop(run_key, "")
        duration_ms = int((time.monotonic() - start) * 1000) if start else None

        self._report_event(
            tool_name=tool_name,
            input_hash=_sha256(input_str),
            output_hash=_sha256(f"error:{type(error).__name__}:{error}"),
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # Event reporting
    # ------------------------------------------------------------------

    def _report_event(
        self,
        tool_name: str,
        input_hash: str,
        output_hash: str,
        duration_ms: Optional[int],
    ) -> None:
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.post(
                    f"{self.base_url}/api/v1/events",
                    json={
                        "agent_id": self.agent_id,
                        "tool_name": tool_name,
                        "input_hash": input_hash,
                        "output_hash": output_hash,
                        "duration_ms": duration_ms,
                        "session_id": self.session_id,
                    },
                    headers=self._headers,
                )
                r.raise_for_status()
                anomaly = r.json().get("anomaly_score")
                score_str = f"{anomaly:.3f}" if anomaly is not None else "n/a"
                flag = " ⚠️" if anomaly and anomaly >= 0.7 else ""
                print(f"[sentinel] tool={tool_name:<30} anomaly={score_str}{flag}")
        except Exception as exc:
            print(f"[sentinel] Warning: failed to report event for {tool_name}: {exc}")

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def get_trust_score(self) -> Optional[Dict[str, Any]]:
        """Fetch the current trust score for this agent."""
        try:
            with httpx.Client(timeout=10.0) as client:
                r = client.get(
                    f"{self.base_url}/api/v1/agents/{self.agent_id}/score",
                    headers=self._headers,
                )
                r.raise_for_status()
                return r.json()
        except Exception as exc:
            print(f"[sentinel] Warning: failed to fetch trust score: {exc}")
            return None
