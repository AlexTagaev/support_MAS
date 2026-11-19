"""Inactive Jivo webhook placeholder until its protocol is implemented."""

from fastapi import APIRouter, HTTPException, status

router = APIRouter()


@router.post("/api/jivo/webhook")
async def jivo_webhook():
    """Reject requests until event authentication and processing are ready."""
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Jivo webhook handling is not enabled yet",
    )
