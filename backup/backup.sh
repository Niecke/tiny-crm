#!/usr/bin/env bash
#
# One archive per run, written straight to the off-site bucket:
#
#   tiny-crm-<TS>.tar
#   ├── dump.sql.br     brotli — SQL is text and compresses about 10:1
#   └── documents/…     stored raw; they are already-compressed PDFs and images,
#                       so a second pass would burn CPU for nothing
#
# The archive is streamed into the upload rather than written to disk first,
# which keeps peak scratch usage at one copy of the document store instead of
# two.
#
# Both object stores are reached with rclone. The GCS bucket is addressed through
# its S3-compatible endpoint using an HMAC key on the tiny-crm-backup service
# account, which may add and read archives in the backups bucket but not delete
# or overwrite them — so no GCP service account key is needed anywhere in this
# path, and a leaked key cannot destroy existing backups.
set -euo pipefail

: "${DATABASE_HOST:?}"
: "${DATABASE_USER:?}"
: "${DATABASE_NAME:?}"
: "${PGPASSWORD:?}"
: "${S3_ENDPOINT_URL:?}"
: "${S3_REGION:?}"
: "${S3_ACCESS_KEY:?}"
: "${S3_SECRET_KEY:?}"
: "${S3_BUCKET:?}"
: "${GCS_ENDPOINT:?}"
: "${GCS_ACCESS_KEY:?}"
: "${GCS_SECRET_KEY:?}"
: "${BACKUP_BUCKET:?}"

WORK_DIR="${WORK_DIR:-/backup}"
# 5 rather than brotli's default of 11: on two shared vCPUs the top levels cost
# minutes for a few percent, and this runs while the app is serving.
BROTLI_QUALITY="${BROTLI_QUALITY:-5}"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="tiny-crm-${TS}.tar"

work="$(mktemp -d "${WORK_DIR}/run.XXXXXX")"
trap 'rm -rf "$work"' EXIT

# Both remotes are defined in the environment; the config file stays empty and
# only exists so rclone does not complain that it is missing.
export RCLONE_CONFIG="${work}/rclone.conf"
: > "$RCLONE_CONFIG"
# `docs` is the document store (Hetzner in production, the same settings the
# backend uses). `gcs` is the backups bucket; no_check_bucket because the HMAC
# key may not create buckets, and rclone would otherwise try.
export RCLONE_CONFIG_DOCS_TYPE=s3 RCLONE_CONFIG_DOCS_PROVIDER=Other \
    RCLONE_CONFIG_DOCS_ENDPOINT="$S3_ENDPOINT_URL" \
    RCLONE_CONFIG_DOCS_REGION="$S3_REGION" \
    RCLONE_CONFIG_DOCS_ACCESS_KEY_ID="$S3_ACCESS_KEY" \
    RCLONE_CONFIG_DOCS_SECRET_ACCESS_KEY="$S3_SECRET_KEY"
export RCLONE_CONFIG_GCS_TYPE=s3 RCLONE_CONFIG_GCS_PROVIDER=GCS \
    RCLONE_CONFIG_GCS_ENDPOINT="$GCS_ENDPOINT" \
    RCLONE_CONFIG_GCS_ACCESS_KEY_ID="$GCS_ACCESS_KEY" \
    RCLONE_CONFIG_GCS_SECRET_ACCESS_KEY="$GCS_SECRET_KEY" \
    RCLONE_CONFIG_GCS_NO_CHECK_BUCKET=true

echo "==> dumping ${DATABASE_NAME} from ${DATABASE_HOST}"
# Same flags the compose-era script used, so RESTORE.md stays accurate: a plain
# SQL script that restores as whoever runs psql.
pg_dump \
    --host="$DATABASE_HOST" \
    --username="$DATABASE_USER" \
    --dbname="$DATABASE_NAME" \
    --format=plain --no-owner --no-privileges \
    | brotli -q "$BROTLI_QUALITY" > "${work}/dump.sql.br"

echo "==> copying documents from ${S3_BUCKET}"
# Current versions only, as before: older versions stay in the versioned bucket.
mkdir -p "${work}/documents"
rclone copy --quiet "docs:${S3_BUCKET}" "${work}/documents"

echo "==> uploading ${ARCHIVE}"
# rclone rcat consumes stdin, so the tar never lands on disk.
tar -cf - -C "$work" dump.sql.br documents \
    | rclone rcat "gcs:${BACKUP_BUCKET}/${ARCHIVE}"

echo "==> verifying"
rclone lsl "gcs:${BACKUP_BUCKET}/${ARCHIVE}"

echo "backup ${ARCHIVE} complete"
