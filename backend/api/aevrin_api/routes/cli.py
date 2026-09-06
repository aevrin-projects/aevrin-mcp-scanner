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
    """The CLI already ran the scan; this persists the result to the account.

    The pipeline is never re-run server-side, so an upload is a
    client-reported result end to end - findings, risk score and grade alike.
    Aevrin says so rather than implying otherwise: `invocation_channel`
    records that the result arrived from the CLI, and the scan detail view
    labels it. Re-deriving a grade here would mean either launching the
    server (which needs a sandbox and the exact package the CLI ran) or
    writing a second scoring algorithm beside the engine's, and two graders
    eventually disagree about one server. See ADR-033.

    Two things are still refused, because both compare the client's claims
    against the client's own evidence rather than recomputing anything:

    - a grade with no enumerated tools, since a grade is a claim about tools
      that were read;
    - a grade in the ALLOW band (A/B) alongside a Critical or High finding in
      the same payload, which is self-contradictory whatever produced it, and
      is the shape a tampered CLI takes to make a dangerous server install
      quietly.

    Closing the rest needs a signed local attestation or a server-side
    spot-check rescan; neither is implemented, and this model cannot close it
    alone."""
    return await cli_controller.upload_scan(body, background, user.id, db, settings)
