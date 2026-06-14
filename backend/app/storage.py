from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)

_session = aioboto3.Session(
    aws_access_key_id=settings.s3_access_key,
    aws_secret_access_key=settings.s3_secret_key,
    region_name=settings.s3_region,
)

# botocore >=1.36 sends a CRC32 checksum with aws-chunked trailers on every
# request by default. Non-AWS S3 (Hetzner/MinIO/Ceph) reject the new headers
# and return SignatureDoesNotMatch, so only send checksums when required.
_config = Config(
    request_checksum_calculation="when_required",
    response_checksum_validation="when_required",
)


def _client_kwargs() -> dict[str, object]:
    kwargs: dict[str, object] = {"config": _config}
    if settings.s3_endpoint_url:
        kwargs["endpoint_url"] = settings.s3_endpoint_url
    return kwargs


async def check_storage() -> None:
    """Called once at startup. Verifies bucket exists and versioning is enabled;
    logs a warning if not."""
    async with _session.client("s3", **_client_kwargs()) as s3:  # type: ignore[arg-type]
        try:
            await s3.head_bucket(Bucket=settings.s3_bucket)  # type: ignore[attr-defined]
        except ClientError as exc:
            code = exc.response["Error"]["Code"]  # type: ignore[attr-defined]
            logger.error(
                "S3 bucket '%s' is not accessible (code %s). Document uploads will fail.",
                settings.s3_bucket,
                code,
            )
            return
        try:
            resp = await s3.get_bucket_versioning(Bucket=settings.s3_bucket)  # type: ignore[attr-defined]
            status = resp.get("Status", "")
            if status != "Enabled":
                logger.warning(
                    "S3 bucket '%s' does not have versioning enabled (status: '%s'). "
                    "Old document versions will not be preserved on content replacement.",
                    settings.s3_bucket,
                    status or "Suspended/Off",
                )
        except ClientError as exc:
            logger.warning(
                "Could not check versioning for bucket '%s': %s",
                settings.s3_bucket,
                exc,
            )


async def put_object(key: str, data: bytes, content_type: str) -> None:
    async with _session.client("s3", **_client_kwargs()) as s3:  # type: ignore[arg-type]
        await s3.put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )


async def get_object_stream(key: str) -> AsyncIterator[bytes]:
    async with _session.client("s3", **_client_kwargs()) as s3:  # type: ignore[arg-type]
        response = await s3.get_object(Bucket=settings.s3_bucket, Key=key)
        async for chunk in response["Body"]:
            yield chunk


async def delete_object(key: str) -> None:
    async with _session.client("s3", **_client_kwargs()) as s3:  # type: ignore[arg-type]
        await s3.delete_object(Bucket=settings.s3_bucket, Key=key)
