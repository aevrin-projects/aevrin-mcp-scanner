"""HTTP layer: one module per resource, each a thin shell over services/.

`ROUTERS` is the single registration list so adding an endpoint file never means
remembering to edit main.py as well.
"""

from fastapi import APIRouter

from aevrin_api.routes import (
    account,
    admin,
    admin_marketplace,
    agents,
    ai,
    api_keys,
    auth_lookup,
    billing,
    cli,
    device,
    events,
    export,
    findings,
    github,
    hook,
    marketplace,
    orgs,
    scans,
    scheduler,
)

ROUTERS: list[APIRouter] = [
    scans.router,
    findings.router,
    hook.router,
    cli.router,
    api_keys.router,
    export.router,
    device.router,
    events.router,
    account.router,
    billing.router,
    auth_lookup.router,
    github.router,
    admin.router,
    agents.router,
    orgs.router,
    marketplace.router,
    ai.router,
    admin_marketplace.router,
    scheduler.router,
]

__all__ = ["ROUTERS"]
