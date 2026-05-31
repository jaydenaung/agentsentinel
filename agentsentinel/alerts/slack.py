"""Slack webhook alerting for CRITICAL findings."""

from urllib.parse import urlparse

import httpx
import structlog

from agentsentinel.config import settings
from agentsentinel.models.finding import Finding

log = structlog.get_logger(__name__)


def _is_safe_webhook_url(url: str) -> bool:
    """Defense-in-depth check: ensure the URL still targets hooks.slack.com over HTTPS.

    The config validator catches bad values at startup, but this guard prevents
    runtime exploitation if the URL is sourced from a mutable config store.
    """
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and (parsed.netloc == "hooks.slack.com" or parsed.netloc.endswith(".hooks.slack.com"))
    )


async def send_critical_alert(finding: Finding, agent_name: str) -> bool:
    """POST a Slack alert for a CRITICAL finding.

    Returns True if the webhook call succeeded, False otherwise.
    Does nothing (and returns False) when SLACK_WEBHOOK_URL is not configured.
    """
    if not settings.slack_webhook_url:
        log.debug("slack.no_webhook_configured")
        return False

    if not _is_safe_webhook_url(settings.slack_webhook_url):
        log.error("slack.webhook_url_blocked", reason="URL did not pass SSRF safety check")
        return False

    payload = {
        "text": f":rotating_light: *CRITICAL Finding — {agent_name}*",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f":rotating_light: *CRITICAL Security Finding*\n"
                        f"*Agent:* {agent_name}\n"
                        f"*Rule:* `{finding.rule_id}`\n"
                        f"*Message:* {finding.message}"
                    ),
                },
            }
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(settings.slack_webhook_url, json=payload)
            response.raise_for_status()
            log.info(
                "slack.alert_sent",
                rule_id=finding.rule_id,
                agent_name=agent_name,
            )
            return True
    except httpx.HTTPError as exc:
        log.warning("slack.alert_failed", error=str(exc), rule_id=finding.rule_id)
        return False
