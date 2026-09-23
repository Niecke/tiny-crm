# Backup runner: pg_dump, mc and brotli in one place.
#
# Based on the CloudNativePG postgres image rather than a plain Debian, because
# pg_dump refuses to dump a server newer than itself — the major version here
# has to track the one the Cluster runs.
FROM ghcr.io/cloudnative-pg/postgresql:18.6-system-trixie@sha256:172f3273cdd8d0214c5afaccdc4c1cfa3d4e2d67bc335d999c4fd1258ce54ebb

# mc from the official image, the same way the backend Dockerfile takes uv from
# the astral image. Pinned by digest; there is no other supported way to get a
# specific mc build.
#
# quay.io, not Docker Hub: MinIO withdrew minio/mc and minio/minio from Hub and
# archived the upstream repo, so the Hub pin stopped resolving mid-build. The
# digest is unchanged — quay serves the same artifact. Public builds are frozen,
# so this is a stopgap; see the issue on moving documents to Hetzner S3.
COPY --from=quay.io/minio/mc:RELEASE.2025-08-13T08-35-41Z@sha256:a7fe349ef4bd8521fb8497f55c6042871b2ae640607cf99d9bede5e9bdf11727 /usr/bin/mc /usr/local/bin/mc

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends brotli \
    && rm -rf /var/lib/apt/lists/*

COPY backup.sh /usr/local/bin/backup.sh
RUN chmod 0755 /usr/local/bin/backup.sh /usr/local/bin/mc

# Back to the image's unprivileged postgres user.
USER 26

ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=${GIT_COMMIT}

ENTRYPOINT ["/usr/local/bin/backup.sh"]
