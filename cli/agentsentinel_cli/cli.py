"""AgentSentinel CLI — one-command security scanner and discovery tool for AI agents."""

import sys
from pathlib import Path

import click

from agentsentinel_cli.scanner import scan_path
from agentsentinel_cli.rules import run_rules, posture_score
from agentsentinel_cli.report import print_scan_result, as_json, console


@click.group()
@click.version_option(package_name="agentsentinel-cli")
def main() -> None:
    """AgentSentinel — AI agent security scanner and discovery tool.

    \b
    Commands:
      discover   Find AI agents running in your environment
      scan       Deep-scan an agent file, process, or URL for security issues
    """


# ── sentinel scan ─────────────────────────────────────────────────────────────

@main.command()
@click.argument("target", default=".", type=click.Path(exists=True, path_type=Path))
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text",
              help="Output format.")
@click.option("--fail-on", type=click.Choice(["CRITICAL", "HIGH", "MEDIUM", "LOW"]),
              default=None, help="Exit with code 1 if findings at or above this severity exist.")
@click.option("--connect", metavar="URL", default=None,
              help="AgentSentinel API URL for live behavior data (e.g. http://localhost:9000).")
@click.option("--api-key", envvar="AGENTSENTINEL_API_KEY", default=None,
              help="API key for --connect. Defaults to $AGENTSENTINEL_API_KEY.")
def scan(
    target: Path,
    fmt: str,
    fail_on: str | None,
    connect: str | None,
    api_key: str | None,
) -> None:
    """Scan a Python file or directory for AI agent security issues.

    TARGET can be a single .py file or a directory (scanned recursively).

    \b
    Examples:
        sentinel scan my_agent.py
        sentinel scan ./agents/
        sentinel scan my_agent.py --fail-on CRITICAL
        sentinel scan my_agent.py --format json
        sentinel scan my_agent.py --connect http://localhost:9000
    """
    agents = scan_path(target)

    findings_map = {a.file: run_rules(a) for a in agents}
    scores_map = {a.file: posture_score(findings_map[a.file]) for a in agents}

    if connect and api_key and agents:
        _enrich_from_platform(agents, scores_map, connect, api_key)

    if fmt == "json":
        click.echo(as_json(agents, findings_map, scores_map))
    else:
        print_scan_result(agents, findings_map, scores_map, target, connect_url=connect)

    if fail_on:
        _severity_rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        threshold = _severity_rank.get(fail_on, 0)
        breach = any(
            _severity_rank.get(f.severity, 0) >= threshold
            for fl in findings_map.values()
            for f in fl
        )
        if breach:
            sys.exit(1)


def _enrich_from_platform(agents, scores_map, connect_url, api_key):
    try:
        import httpx
        headers = {"X-API-Key": api_key}
        base = connect_url.rstrip("/")
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{base}/api/v1/agents", headers=headers)
            resp.raise_for_status()
            platform_agents = {a["name"]: a for a in resp.json()}
        for agent in agents:
            candidate_name = agent.file.stem.replace("_", "-")
            for name, data in platform_agents.items():
                if candidate_name in name or name in candidate_name:
                    platform_score = data.get("trust_score", scores_map[agent.file])
                    scores_map[agent.file] = int(platform_score)
                    break
    except Exception as exc:
        console.print(f"  [dim yellow]Warning: could not connect to AgentSentinel: {exc}[/dim yellow]")


# ── sentinel discover ─────────────────────────────────────────────────────────

@main.command()
@click.option("--process/--no-process", default=True, show_default=True,
              help="Scan running processes for LLM API usage.")
@click.option("--network/--no-network", default=True, show_default=True,
              help="Probe local ports for MCP servers and agent APIs.")
@click.option("--docker/--no-docker", default=False, show_default=True,
              help="Inspect running Docker containers.")
@click.option("--path", "scan_path", default=None, type=click.Path(exists=True, path_type=Path),
              metavar="DIR", help="Scan a directory for agent source files.")
@click.option("--subnet", default=None, metavar="CIDR",
              help="Scan a CIDR subnet for AI agent endpoints, e.g. 10.0.0.0/24.")
@click.option("--ports", default=None, metavar="RANGE",
              help="Custom port range for network scan, e.g. 8000-9001. Defaults to common agent ports.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text",
              help="Output format.")
@click.option("--verbose", "-v", is_flag=True, default=False,
              help="Show full details per discovered agent.")
def discover(
    process: bool,
    network: bool,
    docker: bool,
    scan_path: Path | None,
    subnet: str | None,
    ports: str | None,
    fmt: str,
    verbose: bool,
) -> None:
    """Find AI agents running in your environment.

    Scans running processes, local network ports, source files, and Docker
    containers to surface AI agents — including unmonitored ones.

    \b
    Examples:
        sentinel discover                        scan processes + network
        sentinel discover --docker               include Docker containers
        sentinel discover --path ./agents        scan a source directory
        sentinel discover --subnet 10.0.0.0/24   scan internal subnet
        sentinel discover --no-process           network scan only
        sentinel discover --ports 8000-9001      custom port range
        sentinel discover --format json          machine-readable output
    """
    from agentsentinel_cli.discover import run_discovery, as_json as discover_json
    from agentsentinel_cli.discover_report import print_discover_result, print_subnet_progress

    # Parse port range
    port_list = _parse_ports(ports) if ports else None

    # Collect active scan vectors for the header
    vectors = []
    if process:
        vectors.append("processes")
    if network:
        vectors.append("network")
    if subnet:
        vectors.append(f"subnet ({subnet})")
    if scan_path:
        vectors.append(f"files ({scan_path})")
    if docker:
        vectors.append("docker")

    if not vectors:
        console.print("[yellow]No scan vectors selected — use at least one of: "
                      "--process, --network, --subnet, --path, --docker[/yellow]")
        sys.exit(1)

    if fmt == "text":
        _warn_missing_deps(process, network)

    # Progress callback for subnet scan — only in text mode
    progress_cb = print_subnet_progress if (subnet and fmt == "text") else None

    agents, subnet_stats = run_discovery(
        do_process=process,
        do_network=network,
        do_docker=docker,
        scan_path=scan_path,
        ports=port_list,
        subnet=subnet,
        subnet_progress_cb=progress_cb,
    )

    if fmt == "json":
        click.echo(discover_json(agents))
        return

    print_discover_result(agents, vectors=vectors, verbose=verbose, subnet_stats=subnet_stats)

    # Exit 1 if any CRITICAL agents found (useful for CI)
    if any(a.risk == "CRITICAL" for a in agents):
        sys.exit(1)


def _parse_ports(ports_str: str) -> list[int]:
    """Parse '8000-9001' or '8000,8080,9000' into a list of ints."""
    ports: list[int] = []
    for part in ports_str.split(","):
        part = part.strip()
        if "-" in part:
            lo, _, hi = part.partition("-")
            try:
                ports.extend(range(int(lo), int(hi) + 1))
            except ValueError:
                pass
        else:
            try:
                ports.append(int(part))
            except ValueError:
                pass
    return ports


def _warn_missing_deps(do_process: bool, do_network: bool) -> None:
    if do_process:
        try:
            import psutil  # noqa: F401
        except ImportError:
            console.print(
                "[dim yellow]  ⚠  psutil not installed — process scan disabled.[/dim yellow]\n"
                "[dim]  Install with: pip install agentsentinel-cli\\[discover][/dim]\n"
            )
    if do_network:
        try:
            import httpx  # noqa: F401
        except ImportError:
            console.print(
                "[dim yellow]  ⚠  httpx not installed — network probe disabled.[/dim yellow]\n"
                "[dim]  Install with: pip install agentsentinel-cli\\[discover][/dim]\n"
            )
