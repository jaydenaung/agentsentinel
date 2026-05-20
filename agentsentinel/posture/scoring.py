"""Posture score calculator — translates findings into a 0–100 score."""

from agentsentinel.models.finding import Finding

_DEDUCTIONS: dict[str, int] = {
    "CRITICAL": 40,
    "HIGH": 20,
    "MEDIUM": 10,
    "LOW": 5,
}


def calculate_posture_score(findings: list[Finding]) -> int:
    """Compute posture score starting at 100 and deducting per finding severity.

    Returns an integer in the range [0, 100].
    """
    score = 100
    for finding in findings:
        score -= _DEDUCTIONS.get(finding.severity, 0)
    return max(0, score)
