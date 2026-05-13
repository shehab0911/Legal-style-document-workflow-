"""Optional API authentication for production deployments."""

from __future__ import annotations

from typing import Annotated

from fastapi import Header, HTTPException

from app.config import settings


async def require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """
    When LEGAL_WORKFLOW_API_KEY is set, require the same value via
    X-API-Key header or Authorization: Bearer <token>.
    """
    expected = (settings.api_key or "").strip()
    if not expected:
        return
    token: str | None = None
    if x_api_key:
        token = x_api_key.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token or token != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API credentials")
