"""RFC 8628 device authorization grant, used by `aevrin login`."""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class DeviceCodeRequest(BaseModel):
    client_kind: str
    machine_id_hash: str | None = None

    @field_validator("client_kind")
    @classmethod
    def _valid_client_kind(cls, v: str) -> str:
        if v not in {"cli", "hook"}:
            raise ValueError("client_kind must be one of ['cli', 'hook']")
        return v


class DeviceCodeResponse(BaseModel):
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class DeviceTokenRequest(BaseModel):
    device_code: str


class DeviceTokenResponse(BaseModel):
    # RFC 8628 §3.5 error codes when not yet approved; on success, api_key is set.
    status: str  # "authorization_pending" | "slow_down" | "expired_token" | "access_denied" | "approved"
    api_key: str | None = None


class DeviceApproveRequest(BaseModel):
    user_code: str
    fingerprint: str | None = None
