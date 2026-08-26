from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import BinaryIO

import aioboto3
from aiobotocore.config import AioConfig
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
# AioConfig rather than botocore's Config: it is the subclass aiobotocore
# actually expects, and the one the client overloads are typed against.
_config = AioConfig(
    request_checksum_calculation="when_required",
    response_checksum_validation="when_required",
)


# Every call below opens the client the same way. endpoint_url=None is what
# "use AWS" means to botocore, so one spelling covers MinIO and real S3 — and
# passing the arguments explicitly instead of splatting a dict is what keeps
# the typed overloads in types-aioboto3 resolvable.


async def check_storage() -> None:
    """Called once at startup. Verifies bucket exists and versioning is enabled;
    logs a warning if not."""
    async with _session.client("s3", endpoint_url=settings.s3_endpoint_url, config=_config) as s3:
        try:
            await s3.head_bucket(Bucket=settings.s3_bucket)
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            logger.error(
                "S3 bucket '%s' is not accessible (code %s). Document uploads will fail.",
                settings.s3_bucket,
                code,
            )
            return
        try:
            resp = await s3.get_bucket_versioning(Bucket=settings.s3_bucket)
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
    async with _session.client("s3", endpoint_url=settings.s3_endpoint_url, config=_config) as s3:
        await s3.put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )


async def put_object_stream(key: str, fileobj: BinaryIO, content_type: str) -> None:
    """Upload straight from a file-like object.

    aioboto3 pulls the object in parts and switches to a multipart upload past
    8 MB, so the body never has to exist in memory as one blob the way
    put_object's `bytes` argument does. The caller keeps the file positioned at
    the start."""
    async with _session.client("s3", endpoint_url=settings.s3_endpoint_url, config=_config) as s3:
        await s3.upload_fileobj(
            fileobj,
            settings.s3_bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )


async def get_object_stream(key: str) -> AsyncIterator[bytes]:
    async with _session.client("s3", endpoint_url=settings.s3_endpoint_url, config=_config) as s3:
        response = await s3.get_object(Bucket=settings.s3_bucket, Key=key)
        async for chunk in response["Body"]:
            yield chunk


async def delete_object(key: str) -> None:
    async with _session.client("s3", endpoint_url=settings.s3_endpoint_url, config=_config) as s3:
        await s3.delete_object(Bucket=settings.s3_bucket, Key=key)
