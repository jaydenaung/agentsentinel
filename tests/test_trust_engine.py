"""Tests for the trust score engine — score computation and status derivation."""

import pytest

from agentsentinel.trust.engine import derive_status


# ── Status derivation ─────────────────────────────────────────────────────────

class TestDeriveStatus:
    def test_trusted_at_80(self):
        assert derive_status(80.0) == "TRUSTED"

    def test_trusted_at_100(self):
        assert derive_status(100.0) == "TRUSTED"

    def test_watch_at_60(self):
        assert derive_status(60.0) == "WATCH"

    def test_watch_at_79(self):
        assert derive_status(79.9) == "WATCH"

    def test_alert_at_40(self):
        assert derive_status(40.0) == "ALERT"

    def test_alert_at_59(self):
        assert derive_status(59.9) == "ALERT"

    def test_critical_at_39(self):
        assert derive_status(39.9) == "CRITICAL"

    def test_critical_at_0(self):
        assert derive_status(0.0) == "CRITICAL"


# ── Trust score formula ──────────────────────────────────────────────────────

class TestTrustScoreFormula:
    """Verify the composite formula: (posture * 0.45) + (behavior * 0.45) + recency."""

    def _composite(self, posture: float, behavior: float, recency: float = 0.0) -> float:
        return (posture * 0.45) + (behavior * 0.45) + recency

    def test_critical_agent_below_40(self):
        score = self._composite(posture=20.0, behavior=30.0)
        assert score < 40.0
        assert derive_status(score) == "CRITICAL"

    def test_trusted_agent_above_80(self):
        score = self._composite(posture=95.0, behavior=90.0)
        assert score >= 80.0
        assert derive_status(score) == "TRUSTED"

    def test_watch_band(self):
        score = self._composite(posture=70.0, behavior=65.0)
        assert 60.0 <= score < 80.0
        assert derive_status(score) == "WATCH"

    def test_alert_band(self):
        score = self._composite(posture=50.0, behavior=45.0)
        assert 40.0 <= score < 60.0
        assert derive_status(score) == "ALERT"

    def test_recency_bonus_lifts_score(self):
        without = self._composite(posture=75.0, behavior=70.0, recency=0.0)
        with_recency = self._composite(posture=75.0, behavior=70.0, recency=10.0)
        assert with_recency - without == pytest.approx(10.0)

    def test_floor_at_zero(self):
        score = self._composite(posture=0.0, behavior=0.0)
        assert score == pytest.approx(0.0)

    def test_ceiling_at_100(self):
        raw = self._composite(posture=100.0, behavior=100.0, recency=10.0)
        capped = min(100.0, raw)
        assert capped == pytest.approx(100.0)
