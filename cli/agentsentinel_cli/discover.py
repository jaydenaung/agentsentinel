"""
sentinel discover — finds AI agents across processes, network, files, and Docker containers.

Scan vectors:
  process   running Python/Node processes making LLM API calls
  network   open ports serving MCP SSE endpoints or agent APIs
  files     Python source files in a directory containing agent patterns
  docker    Docker containers with LLM API keys in their environment
"""

from __future__ import annotations

import dataclasses
import json
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from agentsentinel_cli.frameworks import (
    LLM_API_HOSTS,
    LLM_ENV_VARS,
    detect_framework,
    detect_model,
    detect_provider_from_env,
    extract_api_keys,
)

# ── Data model ────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class DiscoveredAgent:
    source: str            # process | network | file | docker
    name: str              # human-readable name
    framework: str         # LangChain | OpenAI Agents SDK | MCP | etc.
    provider: str          # Anthropic | OpenAI | Google | etc.
    model: str             # claude-sonnet | gpt-4o | etc.  (empty if unknown)
    location: str          # pid:1234 | port:8080 | /path/file.py | container:name
    api_keys: list[str]    # masked keys: ANTHROPIC_API_KEY=sk-ant-...5f3d
    live_connections: list[str]   # LLM API hosts this process is talking to
    risk: str              # CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN
    risk_reason: str       # one-line explanation of the risk level
    next_step: str         # suggested follow-up command


# ── Default port list for network scan ────────────────────────────────────────

_DEFAULT_PORTS = [
    3000, 3001, 4000, 5000,
    7860,                    # Gradio
    8000, 8001, 8002, 8003,
    8080, 8443, 8888,
    9000, 9001,
    11434,                   # Ollama
]

_MCP_INDICATOR_PATHS   = ["/sse", "/messages/"]
_OPENAI_COMPAT_PATHS   = ["/v1/models"]
_SENTINEL_PATHS        = ["/api/v1/agents", "/health"]
_AGENT_FRAMEWORK_PATHS = ["/api/agents", "/v1/runs", "/runs"]


# ── Process scanner ───────────────────────────────────────────────────────────

# IDE, language server, build tool, and OS helper processes that inherit shell
# env vars. They are not AI agents — flagging them creates noise.
_PROCESS_SKIP_FRAGMENTS = frozenset({
    "lsp-server", "lsp-runner", "lsp-worker",
    "server.bundle",
    "esbuild", "webpack", "rollup", "vite",
    "typescript-language-server", "tsserver",
    "pylsp", "pyright",
    "gopls", "rust-analyzer", "clangd",
    "code helper", "vmware fusion", "docker desktop",
    "safari", "firefox", "chrome helper",
})

# cmdline fragments that STRONGLY indicate an actual AI agent framework.
# Env-var inheritance alone (every shell child has the same vars) is insufficient.
_AGENT_CMDLINE_SIGNALS = frozenset({
    "langchain", "crewai", "autogen", "pyautogen",
    "openai.agents", "agents_sdk",
    "mcp_shim", "mcp-shim", "mcp.server",
    "sentinel_middleware", "agentsentinel",
    "llama_index", "llamaindex",
    "haystack", "pydantic_ai", "semantic_kernel",
    "agent.py", "agents.py",
})


def scan_processes() -> list[DiscoveredAgent]:
    """Scan running processes for AI agents using psutil.

    A process is only flagged when it shows STRONG evidence of being an agent:
      - Active TCP connection to a known LLM API host, OR
      - Agent framework keyword in its command line

    Processes that merely inherit LLM API keys from the shell (IDE helpers,
    language servers, build tools) are filtered to prevent noise.
    Duplicate process names with identical signals are deduplicated.
    """
    try:
        import psutil
    except ImportError:
        return []

    found: list[DiscoveredAgent] = []
    seen: set[tuple[str, str, str]] = set()  # (name, framework, first_key)

    for proc in psutil.process_iter(["pid", "name", "cmdline", "status"]):
        try:
            info = proc.as_dict(attrs=["pid", "name", "cmdline", "status"])
            cmdline = info.get("cmdline") or []
            proc_name = (info.get("name") or "").lower()

            if not cmdline:
                continue

            # Skip known non-agent processes
            if any(skip in proc_name for skip in _PROCESS_SKIP_FRAGMENTS):
                continue

            cmd_str = " ".join(str(c) for c in cmdline).lower()

            if not any(p in cmd_str for p in ("python", "node", "npx", "deno")):
                continue

            # ── Strong-signal gate ────────────────────────────────────────────
            has_framework_in_cmd = any(s in cmd_str for s in _AGENT_CMDLINE_SIGNALS)

            live_connections: list[str] = []
            try:
                for conn in proc.connections(kind="tcp"):
                    if conn.raddr and conn.raddr.ip:
                        try:
                            host = socket.gethostbyaddr(conn.raddr.ip)[0]
                            if any(h in host for h in LLM_API_HOSTS):
                                live_connections.append(host)
                        except (socket.herror, socket.gaierror):
                            pass
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass

            if not has_framework_in_cmd and not live_connections:
                continue  # env-var inheritance alone — skip

            # ── Gather details ────────────────────────────────────────────────
            try:
                env = proc.environ()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                env = {}

            framework, provider = detect_framework(cmd_str)
            if not provider:
                provider = detect_provider_from_env(env)

            api_keys = extract_api_keys(env)
            model = detect_model(cmd_str) or detect_model(" ".join(env.values()))
            name = _name_from_cmdline(cmdline)

            # Deduplicate: same agent name + same framework + same first key
            dedup_key = (name, framework, api_keys[0] if api_keys else "")
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            risk, risk_reason = _assess_process_risk(api_keys, live_connections, framework)

            found.append(DiscoveredAgent(
                source="process",
                name=name,
                framework=framework,
                provider=provider,
                model=model,
                location=f"pid:{info['pid']}",
                api_keys=api_keys,
                live_connections=live_connections,
                risk=risk,
                risk_reason=risk_reason,
                next_step=f"sentinel scan --pid {info['pid']}",
            ))

        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            continue

    return found


def _name_from_cmdline(cmdline: list[str]) -> str:
    """Extract a human-readable agent name from a process command line."""
    for part in reversed(cmdline):
        p = Path(part)
        if p.suffix in (".py", ".js", ".ts") and p.stem not in ("__main__", "-c"):
            return p.stem.replace("_", "-")
    # Fall back to the command itself
    for part in cmdline:
        if part and not part.startswith("-"):
            return Path(part).stem or part
    return "unknown-agent"


def _assess_process_risk(
    api_keys: list[str],
    live_connections: list[str],
    framework: str,
) -> tuple[str, str]:
    if api_keys:
        return (
            "CRITICAL",
            f"LLM API key{'s' if len(api_keys) > 1 else ''} exposed in process environment "
            f"({', '.join(k.split('=')[0] for k in api_keys)})",
        )
    if live_connections:
        return "HIGH", f"Active connection to LLM API: {', '.join(set(live_connections))}"
    if framework != "Unknown":
        return "MEDIUM", f"{framework} agent detected — run 'sentinel scan' for full analysis"
    return "UNKNOWN", "AI-related process detected — framework not identified"


# ── Network scanner ───────────────────────────────────────────────────────────

def scan_network(
    host: str = "127.0.0.1",
    ports: list[int] | None = None,
    timeout: float = 0.5,
) -> list[DiscoveredAgent]:
    """Probe local ports for AI agent endpoints (MCP, OpenAI-compat, AgentSentinel)."""
    if ports is None:
        ports = _DEFAULT_PORTS

    open_ports = _find_open_ports(host, ports, timeout)
    if not open_ports:
        return []

    found: list[DiscoveredAgent] = []
    for port in open_ports:
        agent = _probe_port(host, port, timeout * 4)
        if agent:
            found.append(agent)
    return found


def _find_open_ports(host: str, ports: list[int], timeout: float) -> list[int]:
    """Fast parallel TCP connect check."""
    open_ports: list[int] = []

    def check(port: int) -> int | None:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return port
        except (OSError, ConnectionRefusedError):
            return None

    with ThreadPoolExecutor(max_workers=50) as pool:
        for result in as_completed({pool.submit(check, p): p for p in ports}):
            r = result.result()
            if r is not None:
                open_ports.append(r)

    return sorted(open_ports)


def _probe_port(host: str, port: int, timeout: float) -> DiscoveredAgent | None:
    """Make HTTP requests to an open port and detect what kind of agent it is."""
    try:
        import httpx
    except ImportError:
        return None

    base = f"http://{host}:{port}"

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        # Try MCP SSE endpoint
        for path in _MCP_INDICATOR_PATHS:
            try:
                r = client.get(f"{base}{path}", headers={"Accept": "text/event-stream"})
                if r.status_code < 500 and (
                    "text/event-stream" in r.headers.get("content-type", "")
                    or "event-stream" in r.text[:200]
                    or r.status_code == 200
                ):
                    return DiscoveredAgent(
                        source="network",
                        name=f"mcp-server:{port}",
                        framework="MCP Server",
                        provider="",
                        model="",
                        location=f"port:{port}",
                        api_keys=[],
                        live_connections=[],
                        risk="UNKNOWN",
                        risk_reason="MCP server — run 'sentinel scan --url' to inspect tools",
                        next_step=f"sentinel scan --url {base}/sse",
                    )
            except httpx.RequestError:
                pass

        # Try OpenAI-compatible API
        for path in _OPENAI_COMPAT_PATHS:
            try:
                r = client.get(f"{base}{path}")
                if r.status_code in (200, 401) and _looks_like_openai_api(r):
                    return DiscoveredAgent(
                        source="network",
                        name=f"openai-compat-api:{port}",
                        framework="OpenAI-compatible API",
                        provider="",
                        model=_extract_model_from_response(r),
                        location=f"port:{port}",
                        api_keys=[],
                        live_connections=[],
                        risk="UNKNOWN",
                        risk_reason="OpenAI-compatible API — could be local model server or proxy",
                        next_step=f"sentinel scan --url {base}",
                    )
            except httpx.RequestError:
                pass

        # Try AgentSentinel platform
        try:
            r = client.get(f"{base}/health")
            if r.status_code == 200 and r.text.strip().startswith("{"):
                body = r.json()
                if "status" in body:
                    return DiscoveredAgent(
                        source="network",
                        name=f"agentsentinel:{port}",
                        framework="AgentSentinel",
                        provider="",
                        model="",
                        location=f"port:{port}",
                        api_keys=[],
                        live_connections=[],
                        risk="LOW",
                        risk_reason="AgentSentinel monitoring platform — already registered",
                        next_step=f"sentinel scan --connect http://{host}:{port}",
                    )
        except (httpx.RequestError, Exception):
            pass

    return None


def _looks_like_openai_api(response) -> bool:
    try:
        body = response.json()
        return "data" in body or "models" in body or "object" in body or "error" in body
    except Exception:
        return False


def _extract_model_from_response(response) -> str:
    try:
        data = response.json().get("data", [])
        if data:
            return data[0].get("id", "")
    except Exception:
        pass
    return ""


# ── File scanner ──────────────────────────────────────────────────────────────

def scan_files(path: Path) -> list[DiscoveredAgent]:
    """Find Python files in a directory that look like AI agents."""
    from agentsentinel_cli.scanner import scan_path as static_scan

    agents = static_scan(path)
    found: list[DiscoveredAgent] = []

    for agent in agents:
        framework, provider = detect_framework(agent.file.read_text(errors="ignore"))
        model = agent.model or detect_model(agent.file.read_text(errors="ignore"))
        tool_count = len(agent.tools)
        has_dangerous = any(t.is_dangerous for t in agent.tools)
        has_creds = bool(agent.hardcoded_creds)

        risk, risk_reason = _assess_file_risk(has_creds, has_dangerous, tool_count, framework)

        found.append(DiscoveredAgent(
            source="file",
            name=agent.file.stem.replace("_", "-"),
            framework=framework if framework != "Unknown" else _infer_framework_from_tools(agent),
            provider=provider,
            model=model,
            location=str(agent.file),
            api_keys=[f"HARDCODED: {c}" for c in agent.hardcoded_creds],
            live_connections=[],
            risk=risk,
            risk_reason=risk_reason,
            next_step=f"sentinel scan {agent.file}",
        ))

    return found


def _infer_framework_from_tools(agent) -> str:
    """Guess framework from tool detection source tags."""
    sources = {t.source for t in agent.tools}
    if "BaseTool subclass" in sources or "StructuredTool" in str(sources):
        return "LangChain"
    if "@tool decorator" in sources:
        return "LangChain / CrewAI"
    return "Python agent"


def _assess_file_risk(
    has_creds: bool,
    has_dangerous: bool,
    tool_count: int,
    framework: str,
) -> tuple[str, str]:
    if has_creds:
        return "CRITICAL", "Hardcoded credentials detected in source code — rotate immediately"
    if has_dangerous:
        return "HIGH", "Agent holds dangerous tool grants — run full scan"
    if tool_count > 10:
        return "MEDIUM", f"{tool_count} tool grants — excessive permissions, high blast radius"
    if tool_count > 0:
        return "LOW", f"{tool_count} tool grant{'s' if tool_count != 1 else ''} detected"
    return "UNKNOWN", "Agent file detected — run full scan for analysis"


# ── Docker scanner ────────────────────────────────────────────────────────────

def scan_docker() -> list[DiscoveredAgent]:
    """Find running Docker containers that look like AI agents."""
    if not _docker_available():
        return []

    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{json .}}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    found: list[DiscoveredAgent] = []

    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        try:
            container = json.loads(line)
            container_id = container.get("ID", "")
            container_name = container.get("Names", "unknown").lstrip("/")
            image = container.get("Image", "")

            # Inspect the container for environment variables
            env = _docker_inspect_env(container_id)
            if not env:
                continue

            has_llm_env = any(var in env for var in LLM_ENV_VARS)
            if not has_llm_env:
                # Check image name for agent signals
                framework, provider = detect_framework(image)
                if framework == "Unknown":
                    continue
            else:
                full_text = " ".join([image, container_name, " ".join(env.values())])
                framework, provider = detect_framework(full_text)

            api_keys = extract_api_keys(env)
            model = detect_model(" ".join(env.values()))
            provider = provider or detect_provider_from_env(env)
            risk, risk_reason = _assess_process_risk(api_keys, [], framework)

            found.append(DiscoveredAgent(
                source="docker",
                name=container_name,
                framework=framework,
                provider=provider,
                model=model,
                location=f"container:{container_name}",
                api_keys=api_keys,
                live_connections=[],
                risk=risk,
                risk_reason=risk_reason,
                next_step=f"docker exec {container_name} sentinel scan .",
            ))

        except (json.JSONDecodeError, KeyError):
            continue

    return found


def _docker_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _docker_inspect_env(container_id: str) -> dict[str, str]:
    """Return environment variables for a container as a dict."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format",
             "{{range .Config.Env}}{{.}}\n{{end}}", container_id],
            capture_output=True, text=True, timeout=10,
        )
        env: dict[str, str] = {}
        for line in result.stdout.strip().splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
        return env
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {}


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run_discovery(
    do_process: bool = True,
    do_network: bool = True,
    do_docker: bool = False,
    scan_path: Optional[Path] = None,
    ports: list[int] | None = None,
) -> list[DiscoveredAgent]:
    """Run all requested discovery scanners and return deduplicated results."""
    results: list[DiscoveredAgent] = []

    if do_process:
        results.extend(scan_processes())

    if do_network:
        results.extend(scan_network(ports=ports))

    if scan_path:
        results.extend(scan_files(scan_path))

    if do_docker:
        results.extend(scan_docker())

    return results


# ── JSON serialisation ────────────────────────────────────────────────────────

def as_json(agents: list[DiscoveredAgent]) -> str:
    return json.dumps(
        [dataclasses.asdict(a) for a in agents],
        indent=2,
    )
