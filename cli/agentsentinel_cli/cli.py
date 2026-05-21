"""AgentSentinel CLI — one-command security scanner for AI agents."""

import sys
from pathlib import Path

import click

from agentsentinel_cli.scanner import scan_path
from agentsentinel_cli.rules import run_rules, posture_score
from agentsentinel_cli.report import print_scan_result, as_json, console


@click.group()
@click.version_option(package_name="agentsentinel-cli")
def main() -> None:
    """AgentSentinel — AI agent security scanner."""


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

    Examples:

    \b
        sentinel scan my_agent.py
        sentinel scan ./agents/
        sentinel scan my_agent.py --fail-on CRITICAL
        sentinel scan my_agent.py --format json
        sentinel scan my_agent.py --connect http://localhost:9000
    """
    agents = scan_path(target)

    findings_map = {a.file: run_rules(a) for a in agents}
    scores_map = {a.file: posture_score(findings_map[a.file]) for a in agents}

    # Optional: enrich with live behavior score from running AgentSentinel
    if connect and api_key and agents:
        _enrich_from_platform(agents, scores_map, connect, api_key)

    if fmt == "json":
        click.echo(as_json(agents, findings_map, scores_map))
    else:
        print_scan_result(agents, findings_map, scores_map, target, connect_url=connect)

    # Exit code for CI gating
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
    """Fetch live behavior scores from a running AgentSentinel instance."""
    try:
        import httpx
        headers = {"X-API-Key": api_key}
        base = connect_url.rstrip("/")

        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{base}/api/v1/agents", headers=headers)
            resp.raise_for_status()
            platform_agents = {a["name"]: a for a in resp.json()}

        for agent in agents:
            # Match by agent name derived from filename
            candidate_name = agent.file.stem.replace("_", "-")
            for name, data in platform_agents.items():
                if candidate_name in name or name in candidate_name:
                    # Blend platform trust score with static posture score
                    platform_score = data.get("trust_score", scores_map[agent.file])
                    scores_map[agent.file] = int(platform_score)
                    break
    except Exception as exc:
        console.print(f"  [dim yellow]Warning: could not connect to AgentSentinel: {exc}[/dim yellow]")
