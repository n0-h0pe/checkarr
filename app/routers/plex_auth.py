"""Backs the "Sign in to Plex" button: the standard PIN-based OAuth-ish flow
third-party Plex apps use to get a token without ever seeing the user's
Plex password. See app/plex_client.py for the shared client identity.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from .. import schemas
from ..plex_client import PLEX_CLIENT_IDENTIFIER, PLEX_PRODUCT, plex_tv_headers
from ..security import require_auth

router = APIRouter(prefix="/api/plex-auth", tags=["plex-auth"], dependencies=[Depends(require_auth)])

PLEX_PINS_URL = "https://plex.tv/api/v2/pins"


@router.post("/start", response_model=schemas.PlexAuthStartResponse)
async def start():
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(PLEX_PINS_URL, params={"strong": "true"}, headers=plex_tv_headers())
        except httpx.RequestError as exc:
            raise HTTPException(502, f"Could not reach plex.tv: {exc}")

    if resp.status_code not in (200, 201):
        raise HTTPException(502, f"plex.tv returned HTTP {resp.status_code} creating a sign-in PIN")

    data = resp.json()
    auth_url = (
        "https://app.plex.tv/auth#?"
        f"clientID={PLEX_CLIENT_IDENTIFIER}"
        f"&code={data['code']}"
        f"&context%5Bdevice%5D%5Bproduct%5D={PLEX_PRODUCT.replace(' ', '%20')}"
    )
    return schemas.PlexAuthStartResponse(pin_id=data["id"], code=data["code"], auth_url=auth_url)


@router.get("/poll", response_model=schemas.PlexAuthPollResponse)
async def poll(pin_id: int = Query(...)):
    url = f"{PLEX_PINS_URL}/{pin_id}"
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(url, headers=plex_tv_headers())
        except httpx.RequestError as exc:
            raise HTTPException(502, f"Could not reach plex.tv: {exc}")

    if resp.status_code != 200:
        raise HTTPException(502, f"plex.tv returned HTTP {resp.status_code} checking the sign-in PIN")

    data = resp.json()
    return schemas.PlexAuthPollResponse(token=data.get("authToken"))
