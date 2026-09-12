"""Custom service icon uploads - stored under settings.icons_path and
served back at /custom-icons/<filename> (mounted in both main.py and
public.py, since a service's card can show up on either dashboard). Not
tied to a specific service id: the Add/Edit service modal uploads first,
then carries the returned filename along as part of the regular
create/update payload (models.Service.icon_type="upload") when the form
itself is saved - a service being added doesn't have an id yet to attach
an upload to.
"""

import secrets

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from .. import schemas
from ..config import settings
from ..security import require_auth

router = APIRouter(prefix="/api/icon-uploads", tags=["icon-uploads"], dependencies=[Depends(require_auth)])

# Keyed by the content-type the browser itself assigns based on the file's
# actual bytes (not just its name) - still not a full magic-byte sniff, but
# this is an authenticated admin-only route uploading their own icon, not
# untrusted public input.
_ALLOWED_CONTENT_TYPES = {
    "image/svg+xml": "svg",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
_MAX_BYTES = 1_000_000  # 1 MB - a logo, not a photo


@router.post("", response_model=schemas.IconUploadOut, status_code=201)
async def upload_icon(file: UploadFile = File(...)):
    ext = _ALLOWED_CONTENT_TYPES.get(file.content_type)
    if ext is None:
        raise HTTPException(400, "Only SVG, PNG, JPEG, or WebP images are accepted")
    data = await file.read(_MAX_BYTES + 1)
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > _MAX_BYTES:
        raise HTTPException(400, "Image must be 1 MB or smaller")

    # Random server-generated name, never the client's own filename - sidesteps
    # path traversal and collisions entirely rather than trying to sanitize one.
    filename = f"{secrets.token_hex(16)}.{ext}"
    (settings.icons_path / filename).write_bytes(data)
    return schemas.IconUploadOut(filename=filename, url=f"/custom-icons/{filename}")
