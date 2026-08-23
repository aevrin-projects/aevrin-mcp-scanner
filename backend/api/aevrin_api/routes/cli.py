"""CLI endpoints: quota precheck and scan upload."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, status

from aevrin_api.config import Settings, get_settings
from aevrin_api.controllers import cli_controller
from aevrin_api.core.security import AuthenticatedUser
from aevrin_api.db import SupabaseRest
from aevrin_api.routes.deps import get_api_key_user, get_db
from aevrin_api.schemas import CliUploadRequest, ScanOut

router = APIRouter(prefix="/cli", tags=["cli"])

CliUser = Annotated[AuthenticatedUser, Depends(get_api_key_user)]
Db = Annotated[SupabaseRest, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]


@router.get("/precheck")
async def precheck(user: CliUser, db: Db, settings: Config) -> dict[str, bool]:
    """The CLI calls this *before* running its local scan (which can take
    minutes) so a quota-exhausted account fails fast instead of doing real
    work first. Read-only; does not consume quota; /cli/upload is still the
    actual gate, since that's the moment a scan is genuinely recorded."""
    return await cli_controller.precheck(user.id, db, settings)


@router.post("/upload", response_model=ScanOut, status_code=status.HTTP_201_CREATED)
async def upload_scan(
    body: CliUploadRequest,
    background: BackgroundTasks,
    user: CliUser,
    db: Db,
    settings: Config,
) -> ScanOut:
    """CLI already ran the full local scan (same scanner-core pipeline as
    the backend); this just persists the result to the user's account. It
    never re-runs the pipeline server-side, so the findings list itself is
    still self-reported; the score is not, though; see below.

    We never trust the client-submitted `score`; it's recomputed here from
    the submitted findings using the same shared `compute_score` the CLI
    itself used, and that recomputed value is what gets stored. This closes
    the cheapest tampering vector (a hand-crafted upload claiming a better
    score than its own findings justify) without requiring a full
    server-side re-scan, which isn't feasible for local/private targets.
    The findings list itself remains self-reported, a fuller integrity
    story (signed local attestation, spot-check re-scans of public repo
    targets) is a documented future improvement, not something this
    upload-and-trust-the-findings model can close on its own."""
    return await cli_controller.upload_scan(body, background, user.id, db, settings)
