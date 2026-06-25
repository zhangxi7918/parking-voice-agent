from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)
