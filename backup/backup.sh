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
# Both object stores are reached with mc. The GCS bucket is addressed through
# its S3-compatible endpoint using the HMAC key that already exists for the
# documents bucket — the same service account holds objectAdmin on the backups
# bucket, so no GCP service account key is needed anywhere in this path.
set -euo pipefail

: "${DATABASE_HOST:?}"
: "${DATABASE_USER:?}"
: "${DATABASE_NAME:?}"
: "${PGPASSWORD:?}"
: "${MINIO_ENDPOINT:?}"
: "${MINIO_USER:?}"
: "${MINIO_PASSWORD:?}"
: "${MINIO_BUCKET:?}"
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

echo "==> dumping ${DATABASE_NAME} from ${DATABASE_HOST}"
# Same flags the compose-era script used, so RESTORE.md stays accurate: a plain
# SQL script that restores as whoever runs psql.
pg_dump \
    --host="$DATABASE_HOST" \
    --username="$DATABASE_USER" \
    --dbname="$DATABASE_NAME" \
    --format=plain --no-owner --no-privileges \
    | brotli -q "$BROTLI_QUALITY" > "${work}/dump.sql.br"

echo "==> mirroring documents from ${MINIO_BUCKET}"
mc --quiet alias set minio "$MINIO_ENDPOINT" "$MINIO_USER" "$MINIO_PASSWORD"
mkdir -p "${work}/documents"
mc --quiet mirror "minio/${MINIO_BUCKET}" "${work}/documents"

echo "==> uploading ${ARCHIVE}"
mc --quiet alias set gcs "$GCS_ENDPOINT" "$GCS_ACCESS_KEY" "$GCS_SECRET_KEY"
# mc pipe consumes stdin, so the tar never lands on disk.
tar -cf - -C "$work" dump.sql.br documents \
    | mc pipe "gcs/${BACKUP_BUCKET}/${ARCHIVE}"

echo "==> verifying"
mc --quiet stat "gcs/${BACKUP_BUCKET}/${ARCHIVE}"

echo "backup ${ARCHIVE} complete"
