"""AgentSentinel CLI — one-command security scanner and discovery tool for AI agents."""

import sys
from pathlib import Path

import click

from agentsentinel_cli.scanner import scan_path
from agentsentinel_cli.rules import run_rules, posture_score
from rich.panel import Panel
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


# ── sentinel mcp ──────────────────────────────────────────────────────────────

@main.group(name="mcp")
def mcp_group() -> None:
    """MCP server security commands.

    \b
    Commands:
      scan   Enumerate an MCP server's tools and audit for security issues
    """


@mcp_group.command("scan")
@click.argument("target", default=None, required=False, metavar="URL")
@click.option("--stdio", "stdio_cmd", default=None, metavar="CMD",
              help="Audit a stdio-transport server. Provide the launch command, e.g. 'python server.py'.")
@click.option("--auth-header", "auth_header", default=None, metavar="HEADER",
              help="HTTP header to include, e.g. 'Authorization: Bearer token123'.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text",
              help="Output format.")
@click.option("--timeout", default=10.0, show_default=True, metavar="SECONDS",
              help="Connection timeout in seconds.")
@click.option("--fail-on", type=click.Choice(["CRITICAL", "HIGH", "MEDIUM", "LOW"]), default=None,
              help="Exit with code 1 if findings at or above this severity exist.")
def mcp_scan(
    target: str | None,
    stdio_cmd: str | None,
    auth_header: str | None,
    fmt: str,
    timeout: float,
    fail_on: str | None,
) -> None:
    """Enumerate an MCP server's tools and audit for security issues.

    Connects to the server, lists all exposed tools, and checks for
    authentication gaps, exfiltration paths, code execution exposure,
    and input validation weaknesses.

    \b
    Examples:
        sentinel mcp scan http://localhost:3000
        sentinel mcp scan http://localhost:3000 --auth-header "Authorization: Bearer token"
        sentinel mcp scan --stdio "python my_mcp_server.py"
        sentinel mcp scan http://localhost:3000 --format json
        sentinel mcp scan http://localhost:3000 --fail-on CRITICAL
    """
    from agentsentinel_cli.mcp_client import scan_http, scan_stdio, McpError, McpAuthRequired
    from agentsentinel_cli.mcp_rules import McpContext, run_mcp_rules, mcp_posture_score
    from agentsentinel_cli.mcp_report import print_mcp_result, as_mcp_json

    if not target and not stdio_cmd:
        console.print("[red]Error:[/red] provide a URL target or --stdio CMD.")
        console.print("  Example: [dim]sentinel mcp scan http://localhost:3000[/dim]")
        console.print("  Example: [dim]sentinel mcp scan --stdio 'python server.py'[/dim]")
        sys.exit(1)
    if target and stdio_cmd:
        console.print("[red]Error:[/red] --stdio and a URL target are mutually exclusive.")
        sys.exit(1)

    display_target = stdio_cmd if stdio_cmd else target

    extra_headers: dict[str, str] = {}
    if auth_header:
        if ":" not in auth_header:
            console.print("[red]Error:[/red] --auth-header must be in 'Header-Name: value' format.")
            sys.exit(1)
        key, _, val = auth_header.partition(":")
        extra_headers[key.strip()] = val.strip()

    auth_required = bool(auth_header)

    try:
        if stdio_cmd:
            server = scan_stdio(stdio_cmd, timeout=timeout)
            auth_required = False  # stdio has no network auth concept
        else:
            server = scan_http(target, extra_headers=extra_headers or None, timeout=timeout)
    except McpAuthRequired as exc:
        console.print(f"\n[bold yellow]Authentication required[/bold yellow] (HTTP {exc.status_code})")
        console.print(
            "  Provide credentials with: "
            "[bold]--auth-header 'Authorization: Bearer <token>'[/bold]"
        )
        sys.exit(1)
    except McpError as exc:
        console.print(f"\n[red]MCP connection failed:[/red] {exc}")
        sys.exit(1)
    except Exception as exc:
        console.print(f"\n[red]Unexpected error:[/red] {exc}")
        sys.exit(1)

    ctx = McpContext(server=server, auth_required=auth_required)
    findings = run_mcp_rules(ctx)
    score = mcp_posture_score(findings)

    if fmt == "json":
        click.echo(as_mcp_json(ctx, findings, score, display_target))
    else:
        print_mcp_result(ctx, findings, score, display_target)

    if fail_on:
        _severity_rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        threshold = _severity_rank.get(fail_on, 0)
        if any(_severity_rank.get(f.severity, 0) >= threshold for f in findings):
            sys.exit(1)


# ── sentinel probe ────────────────────────────────────────────────────────────

@main.command()
@click.argument("target_url")
@click.option("--input-field",  "input_field",  default=None, metavar="FIELD",
              help="JSON field name for the message (auto-detected if omitted).")
@click.option("--output-field", "output_field", default=None, metavar="FIELD",
              help="JSON field name for the response (auto-detected if omitted).")
@click.option("--auth-header",  "auth_header",  default=None, metavar="HEADER",
              help="HTTP auth header, e.g. 'Authorization: Bearer token'.")
@click.option("--attacks", "attack_cats", default=None, metavar="CATS",
              help="Comma-separated categories: injection,jailbreak,extraction,encoding,context. Default: all.")
@click.option("--timeout", default=15.0, show_default=True, metavar="SECONDS",
              help="Per-probe timeout in seconds.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
@click.option("--fail-on", type=click.Choice(["CRITICAL", "HIGH", "MEDIUM", "LOW"]),
              default=None, help="Exit 1 if any finding at or above this severity.")
def probe(
    target_url: str,
    input_field: str | None,
    output_field: str | None,
    auth_header: str | None,
    attack_cats: str | None,
    timeout: float,
    fmt: str,
    fail_on: str | None,
) -> None:
    """Run a static attack battery against a live agent endpoint.

    Sends 50 adversarial payloads across 5 categories and detects success via
    response pattern matching. No API key required.

    \b
    Examples:
        sentinel probe http://my-agent.com/chat
        sentinel probe http://my-agent.com/chat --attacks injection,jailbreak
        sentinel probe http://my-agent.com/chat --input-field message --output-field response
        sentinel probe http://my-agent.com/chat --auth-header "Authorization: Bearer token"
        sentinel probe http://my-agent.com/chat --format json --fail-on HIGH
    """
    from agentsentinel_cli.target import TargetConfig, TargetError
    from agentsentinel_cli.probe import run_probe
    from agentsentinel_cli.probe_report import print_probe_result, as_probe_json

    categories = [c.strip() for c in attack_cats.split(",")] if attack_cats else None

    config = TargetConfig(
        url=target_url,
        input_field=input_field,
        output_field=output_field,
        auth_header=auth_header,
        timeout=timeout,
    )

    total_attacks = len(__import__("agentsentinel_cli.attacks", fromlist=["get_attacks"]).get_attacks(categories))
    _counter: list[int] = [0]

    def _progress(current: int, total: int, attack_id: str, name: str) -> None:
        _counter[0] = current
        if fmt == "text":
            console.print(
                f"  [dim][{current:>2}/{total}][/dim] "
                f"[dim cyan]{attack_id}[/dim cyan] {name[:50]}",
                end="\r",
            )

    if fmt == "text":
        console.print()
        console.print(
            f"  Running [bold white]{total_attacks}[/bold white] probes against "
            f"[bold white]{target_url}[/bold white] …\n"
        )

    try:
        report = run_probe(config, categories=categories, progress_cb=_progress)
    except TargetError as exc:
        console.print(f"\n[red]Target error:[/red] {exc}")
        sys.exit(1)
    except Exception as exc:
        console.print(f"\n[red]Unexpected error:[/red] {exc}")
        sys.exit(1)

    if fmt == "text":
        console.print()  # clear progress line
        print_probe_result(report)
    else:
        click.echo(as_probe_json(report))

    if fail_on:
        _rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        threshold = _rank.get(fail_on, 0)
        if any(_rank.get(r.severity, 0) >= threshold for r in report.findings):
            sys.exit(1)


# ── sentinel ai-probe ─────────────────────────────────────────────────────────

@main.command(name="ai-probe")
@click.argument("target_url")
@click.option("--input-field",  "input_field",  default=None, metavar="FIELD",
              help="JSON field name for the message (auto-detected if omitted).")
@click.option("--output-field", "output_field", default=None, metavar="FIELD",
              help="JSON field name for the response (auto-detected if omitted).")
@click.option("--auth-header",  "auth_header",  default=None, metavar="HEADER",
              help="HTTP auth header, e.g. 'Authorization: Bearer token'.")
@click.option("--context", "ctx", default="", metavar="TEXT",
              help="Optional context about the agent, e.g. 'customer service bot for a bank'.")
@click.option("--max-probes", default=20, show_default=True,
              help="Maximum number of probes Claude can send.")
@click.option("--model", default="claude-opus-4-8", show_default=True,
              help="Claude model to use as the probe agent.")
@click.option("--timeout", default=15.0, show_default=True, metavar="SECONDS",
              help="Per-probe timeout in seconds.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
@click.option("--fail-on", type=click.Choice(["CRITICAL", "HIGH", "MEDIUM", "LOW"]),
              default=None, help="Exit 1 if any finding at or above this severity.")
def ai_probe(
    target_url: str,
    input_field: str | None,
    output_field: str | None,
    auth_header: str | None,
    ctx: str,
    max_probes: int,
    model: str,
    timeout: float,
    fmt: str,
    fail_on: str | None,
) -> None:
    """Run Claude as an autonomous red-team agent against a live endpoint.

    Claude decides what to test, interprets responses intelligently, escalates
    on partial success, and records findings with evidence. Requires ANTHROPIC_API_KEY.

    \b
    Examples:
        sentinel ai-probe http://my-agent.com/chat
        sentinel ai-probe http://my-agent.com/chat --context "customer service bot for a bank"
        sentinel ai-probe http://my-agent.com/chat --max-probes 30
        sentinel ai-probe http://my-agent.com/chat --format json --fail-on CRITICAL
    """
    import os
    from agentsentinel_cli.target import TargetConfig, TargetError
    from agentsentinel_cli.ai_probe import run_ai_probe, DEFAULT_MODEL
    from agentsentinel_cli.probe_report import print_ai_probe_result, as_ai_probe_json

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        console.print("[red]Error:[/red] ANTHROPIC_API_KEY environment variable is not set.")
        console.print("  Export it with: [bold]export ANTHROPIC_API_KEY=sk-ant-...[/bold]")
        sys.exit(1)

    config = TargetConfig(
        url=target_url,
        input_field=input_field,
        output_field=output_field,
        auth_header=auth_header,
        timeout=timeout,
    )

    if fmt == "text":
        console.print()
        console.print(Panel.fit(
            f"[bold white]AgentSentinel AI Probe[/bold white]  [dim](Claude {model})[/dim]\n"
            f"[dim]Target: {target_url}[/dim]",
            border_style="bright_blue",
            padding=(0, 2),
        ))
        console.print(
            f"\n  Probe agent initialised. Budget: [bold white]{max_probes}[/bold white] probes.\n"
        )

    def _progress(probe_num: int, total: int, category: str, rationale: str) -> None:
        if fmt == "text":
            console.print(
                f"  [dim][{probe_num:>2}/{total}][/dim] "
                f"[dim cyan]{category:<12}[/dim cyan] "
                f"[dim]{rationale[:60]}[/dim]"
            )

    try:
        report = run_ai_probe(
            config,
            api_key=api_key,
            max_probes=max_probes,
            context=ctx,
            model=model,
            progress_cb=_progress,
        )
    except ImportError as exc:
        console.print(f"\n[red]Missing dependency:[/red] {exc}")
        sys.exit(1)
    except TargetError as exc:
        console.print(f"\n[red]Target error:[/red] {exc}")
        sys.exit(1)
    except Exception as exc:
        console.print(f"\n[red]Unexpected error:[/red] {exc}")
        sys.exit(1)

    if fmt == "text":
        console.print()
        print_ai_probe_result(report)
    else:
        click.echo(as_ai_probe_json(report))

    if fail_on:
        _rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        threshold = _rank.get(fail_on, 0)
        if any(_rank.get(f.severity, 0) >= threshold for f in report.findings):
            sys.exit(1)


# ── sentinel inspect ──────────────────────────────────────────────────────────

@main.command()
@click.argument("target")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text",
              help="Output format.")
@click.option("--no-ai", "skip_ai", is_flag=True, default=False,
              help="Skip Claude AI summary even if ANTHROPIC_API_KEY is set.")
@click.option("--model", default="claude-haiku-4-5-20251001", show_default=True,
              help="Claude model used for AI summary generation.")
@click.option("--auth-header", "auth_header", default=None, metavar="HEADER",
              help="HTTP auth header for live endpoint inspection, e.g. 'Authorization: Bearer token'.")
@click.option("--fail-on", type=click.Choice(["CRITICAL", "HIGH", "MEDIUM", "LOW"]),
              default=None, help="Exit with code 1 if findings at or above this severity exist.")
def inspect(
    target: str,
    fmt: str,
    skip_ai: bool,
    model: str,
    auth_header: str | None,
    fail_on: str | None,
) -> None:
    """Generate an intelligence report for an AI agent.

    TARGET can be a Python file, a directory, or a live HTTP endpoint URL.
    Shows framework, model, deployment, capabilities, data flows, and trust score.
    With ANTHROPIC_API_KEY set, adds a plain English summary of what the agent does.

    \b
    Examples:
        sentinel inspect my_agent.py
        sentinel inspect ./agents/
        sentinel inspect http://localhost:3000
        sentinel inspect my_agent.py --format json
        sentinel inspect my_agent.py --no-ai
    """
    import os
    from agentsentinel_cli.inspect import inspect_file, inspect_live
    from agentsentinel_cli.inspect_report import print_inspect_result, as_inspect_json

    api_key = "" if skip_ai else os.environ.get("ANTHROPIC_API_KEY", "")

    if target.startswith("http://") or target.startswith("https://"):
        extra_headers: dict[str, str] = {}
        if auth_header:
            if ":" not in auth_header:
                console.print("[red]Error:[/red] --auth-header must be 'Header-Name: value' format.")
                sys.exit(1)
            k, _, v = auth_header.partition(":")
            extra_headers[k.strip()] = v.strip()

        report = inspect_live(
            target,
            extra_headers=extra_headers or None,
            api_key=api_key,
            summary_model=model,
        )
    else:
        path = Path(target)
        if not path.exists():
            console.print(f"[red]Error:[/red] path does not exist: {target}")
            sys.exit(1)

        if path.is_dir():
            # Inspect all agent files in directory, report each
            from agentsentinel_cli.inspect import inspect_file as _inspect
            from agentsentinel_cli.scanner import scan_path as _scan
            agents = _scan(path)
            if not agents:
                console.print(f"[yellow]No agent files detected in:[/yellow] {target}")
                sys.exit(0)
            reports = []
            for agent in agents:
                r = _inspect(agent.file, api_key=api_key, summary_model=model)
                if r:
                    reports.append(r)
            if fmt == "json":
                import json as _json
                click.echo(_json.dumps([_json.loads(as_inspect_json(r)) for r in reports], indent=2))
            else:
                for r in reports:
                    print_inspect_result(r)
            if fail_on:
                _rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
                threshold = _rank.get(fail_on, 0)
                if any(_rank.get(f.severity, 0) >= threshold for r in reports for f in r.findings):
                    sys.exit(1)
            return

        report = inspect_file(path, api_key=api_key, summary_model=model)
        if report is None:
            console.print(f"[yellow]No agent signals detected in:[/yellow] {target}")
            console.print("  Is this an agent file with @tool decorators, Tool() definitions, or known framework imports?")
            sys.exit(0)

    if fmt == "json":
        click.echo(as_inspect_json(report))
    else:
        print_inspect_result(report)

    if fail_on:
        _rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        threshold = _rank.get(fail_on, 0)
        if any(_rank.get(f.severity, 0) >= threshold for f in report.findings):
            sys.exit(1)


# ── sentinel secrets ─────────────────────────────────────────────────────────

@main.command()
@click.argument("target", default=".", type=click.Path(exists=True, path_type=Path))
@click.option("--scope", type=click.Choice(["all", "memory", "config"]), default="all",
              show_default=True,
              help="Scan scope: all files, memory files only, or config/env files only.")
@click.option("--severity", type=click.Choice(["CRITICAL", "HIGH", "MEDIUM", "LOW"]),
              default="MEDIUM", show_default=True,
              help="Minimum severity level to display.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text",
              help="Output format.")
@click.option("--fail-on", type=click.Choice(["CRITICAL", "HIGH", "MEDIUM", "LOW"]),
              default=None,
              help="Exit with code 1 if findings at or above this severity exist.")
@click.option("--no-redact", is_flag=True, default=False,
              help="Show full matched values instead of redacting them.")
def secrets(
    target: Path,
    scope: str,
    severity: str,
    fmt: str,
    fail_on: str | None,
    no_redact: bool,
) -> None:
    """Scan for exposed secrets, API keys, and PII in agent files and memory.

    Detects credentials (Anthropic, OpenAI, AWS, GitHub, Stripe, Google, HuggingFace),
    global PII (email, credit card, US SSN), Singapore PII (NRIC/FIN with checksum
    validation, passport, mobile, landline, UEN, postal code), and memory contamination
    patterns (customer PII clusters leaked from tool call results, system prompt leakage).

    \b
    Examples:
        sentinel secrets .                       scan current directory
        sentinel secrets ~/.claude/projects/     scan Claude Code agent memory
        sentinel secrets . --scope memory        memory files only
        sentinel secrets . --scope config        config/env files only
        sentinel secrets . --severity HIGH       show HIGH and CRITICAL only
        sentinel secrets . --format json         machine-readable output
        sentinel secrets . --fail-on HIGH        exit 1 if any HIGH+ findings
        sentinel secrets . --no-redact           show full matched values
    """
    from agentsentinel_cli.secrets import scan_secrets
    from agentsentinel_cli.secrets_report import print_secrets_result, as_secrets_json

    report = scan_secrets(target, scope=scope, redact=not no_redact)

    if fmt == "json":
        click.echo(as_secrets_json(report))
    else:
        print_secrets_result(report, min_severity=severity)

    if fail_on:
        _rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        threshold = _rank.get(fail_on, 0)
        if any(_rank.get(f.severity, 0) >= threshold for f in report.findings):
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
