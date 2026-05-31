"""Invalidate all API keys created before the HMAC-SHA256 hash upgrade.

BACKGROUND
----------
Prior to this migration, API key hashes were stored as plain SHA-256 digests:
    key_hash = sha256(plaintext_key)

The hash function was upgraded to HMAC-SHA256 using the server secret:
    key_hash = hmac_sha256(SECRET_KEY, plaintext_key)

All key_hash values in the database computed with the old algorithm will
NEVER match a lookup under the new algorithm. This means any key that existed
before the upgrade is permanently broken — it will always return 401.

Rather than leave these phantom keys silently failing, this migration
deactivates them all. The next application startup will bootstrap a new
admin key automatically.

OPERATOR ACTION REQUIRED
------------------------
1. Apply this migration: alembic upgrade head
2. Restart the API service.
3. On startup, a new bootstrap admin key will be generated and delivered
   via BOOTSTRAP_KEY_FILE (recommended) or stderr.
4. Update AGENTSENTINEL_API_KEY in all .env files and secrets stores.
5. Re-issue agent-scoped keys via POST /api/v1/keys for all integrated agents.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-31 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Deactivate all API keys with pre-HMAC SHA-256 hashes."""
    # All existing hashes were computed with plain SHA-256 and are now invalid.
    # Deactivating them triggers a clean bootstrap on next startup.
    op.execute("UPDATE api_keys SET is_active = false WHERE is_active = true")


def downgrade() -> None:
    """Re-activate all keys (restores phantom keys — manual re-hashing still required)."""
    op.execute("UPDATE api_keys SET is_active = true WHERE is_active = false")
