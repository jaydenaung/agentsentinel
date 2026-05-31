"""API key authentication — dependencies and key generation utilities."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentsentinel.config import settings
from agentsentinel.database import get_db
from agentsentinel.models.api_key import ApiKey

log = structlog.get_logger(__name__)

_VALID_SCOPES = {"admin", "agent", "readonly"}
_SCOPE_PREFIX = {"admin": "adm", "agent": "agt", "readonly": "ro"}

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# ── Key generation ────────────────────────────────────────────────────────────

def generate_raw_key(scope: str) -> str:
    """Return a new plaintext key: as_<scope_abbr>_<32 random hex chars>."""
    prefix = _SCOPE_PREFIX[scope]
    return f"as_{prefix}_{secrets.token_hex(32)}"


def hash_key(raw: str) -> str:
    """HMAC-SHA256 of the plaintext key using the server secret.

    Using HMAC with a server-side secret prevents rainbow-table attacks against
    the key_hash column even if the database is compromised.
    """
    return hmac.new(
        settings.secret_key.encode(),
        raw.encode(),
        hashlib.sha256,
    ).hexdigest()


def key_prefix(raw: str) -> str:
    """First 12 characters of the key — safe to store and display."""
    return raw[:12]


# ── Core lookup ───────────────────────────────────────────────────────────────

async def _resolve_key(raw: str, db: AsyncSession) -> ApiKey:
    """Look up an active key by its hash. Raises 401 if not found."""
    digest = hash_key(raw)
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == digest, ApiKey.is_active == True)  # noqa: E712
    )
    key = result.scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")
    key.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    return key


# ── Dependency factory ────────────────────────────────────────────────────────

def require_scope(*allowed: str):
    """Return a FastAPI dependency that validates the key and enforces scope.

    Usage:
        @router.get("/...", dependencies=[Depends(require_scope("admin", "readonly"))])
    Or to get the key object:
        async def handler(key: Annotated[ApiKey, Depends(require_scope("admin"))]):
    """
    async def _dep(
        raw: Annotated[str | None, Security(_api_key_header)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> ApiKey:
        if not raw:
            raise HTTPException(status_code=401, detail="X-API-Key header required")
        key = await _resolve_key(raw, db)
        if key.scope not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Scope '{key.scope}' not permitted. Required: {sorted(allowed)}",
            )
        return key

    return _dep


# Convenience aliases used in route definitions
require_admin = require_scope("admin")
require_agent = require_scope("admin", "agent")    # agents reporting events
require_read  = require_scope("admin", "readonly")  # dashboards / monitoring


# ── Bootstrap ─────────────────────────────────────────────────────────────────

async def bootstrap_admin_key(db: AsyncSession) -> None:
    """Create an initial admin key if none exist.

    Called once at application startup. The full plaintext key is printed to
    stdout — copy it immediately, it will never be shown again.
    """
    result = await db.execute(
        select(ApiKey).where(ApiKey.scope == "admin", ApiKey.is_active == True)  # noqa: E712
    )
    existing = result.scalar_one_or_none()
    if existing:
        return

    raw = generate_raw_key("admin")
    key = ApiKey(
        id=uuid.uuid4(),
        name="bootstrap-admin",
        key_prefix=key_prefix(raw),
        key_hash=hash_key(raw),
        scope="admin",
        is_active=True,
    )
    db.add(key)
    await db.commit()

    # Log only non-sensitive metadata — the plaintext key must never appear in logs
    log.info(
        "bootstrap.admin_key_created",
        message="No admin key found — created bootstrap key.",
        key_prefix=key_prefix(raw),
    )
    # Print to stdout so it's visible at container startup; not stored in log aggregators
    print("\n" + "=" * 70)
    print("  AGENTSENTINEL BOOTSTRAP ADMIN KEY")
    print("  Copy this now — it will not be shown again.")
    print(f"\n  {raw}\n")
    print("  Set it as AGENTSENTINEL_API_KEY in your environment or .env file.")
    print("=" * 70 + "\n", flush=True)
