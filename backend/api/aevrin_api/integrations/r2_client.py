from __future__ import annotations

from functools import lru_cache

import boto3
from botocore.client import Config as BotoConfig

from aevrin_api.config import Settings, get_settings


@lru_cache
def get_r2_client(settings: Settings | None = None):  # type: ignore[no-untyped-def]
    settings = settings or get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_s3_endpoint,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="auto",
    )


def upload_report(key: str, body: bytes, content_type: str, settings: Settings) -> None:
    get_r2_client(settings).put_object(
        Bucket=settings.r2_bucket, Key=key, Body=body, ContentType=content_type
    )


def presigned_report_url(key: str, settings: Settings, expires_in: int = 3600) -> str:
    url: str = get_r2_client(settings).generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.r2_bucket, "Key": key},
        ExpiresIn=expires_in,
    )
    return url
