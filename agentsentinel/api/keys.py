"""API key management endpoints (admin only)."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentsentinel.auth import (
    generate_raw_key,
    hash_key,
    key_prefix,
    require_admin,
)
from agentsentinel.database import get_db
from agentsentinel.models.api_key import ApiKey
from agentsentinel.schemas.api_key import ApiKeyCreate, ApiKeyCreatedResponse, ApiKeyResponse

router = APIRouter(prefix="/keys", tags=["keys"])
log = structlog.get_logger(__name__)

_VALID_SCOPES = {"admin", "agent", "readonly"}


@router.post("", response_model=ApiKeyCreatedResponse, status_code=201)
async def create_key(
    body: ApiKeyCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[ApiKey, Depends(require_admin)],
) -> ApiKeyCreatedResponse:
    """Create a new API key. Returns the plaintext key once — store it securely."""
    if body.scope not in _VALID_SCOPES:
        raise HTTPException(status_code=422, detail=f"scope must be one of {sorted(_VALID_SCOPES)}")

    raw = generate_raw_key(body.scope)
    key = ApiKey(
        id=uuid.uuid4(),
        name=body.name,
        key_prefix=key_prefix(raw),
        key_hash=hash_key(raw),
        scope=body.scope,
        is_active=True,
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)

    log.info("key.created", key_id=str(key.id), scope=key.scope, name=key.name)
    return ApiKeyCreatedResponse(
        id=key.id,
        name=key.name,
        key_prefix=key.key_prefix,
        scope=key.scope,
        is_active=key.is_active,
        last_used_at=key.last_used_at,
        created_at=key.created_at,
        key=raw,
    )


@router.get("", response_model=list[ApiKeyResponse])
async def list_keys(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[ApiKey, Depends(require_admin)],
) -> list[ApiKey]:
    """List all API keys (prefix only — plaintext keys are never stored)."""
    result = await db.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))
    return list(result.scalars().all())


@router.delete("/{key_id}", status_code=204)
async def revoke_key(
    key_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    caller: Annotated[ApiKey, Depends(require_admin)],
) -> None:
    """Revoke an API key by ID. The key is deactivated, not deleted."""
    key = await db.get(ApiKey, key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="Key not found")
    if key.id == caller.id:
        raise HTTPException(status_code=400, detail="Cannot revoke the key you are currently using")
    key.is_active = False
    await db.commit()
    log.info("key.revoked", key_id=str(key_id))
