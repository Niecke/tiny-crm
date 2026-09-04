# Backup runner: pg_dump, mc and brotli in one place.
#
# Based on the CloudNativePG postgres image rather than a plain Debian, because
# pg_dump refuses to dump a server newer than itself — the major version here
# has to track the one the Cluster runs.
FROM ghcr.io/cloudnative-pg/postgresql:18.6-system-trixie

# mc from the official image, the same way the backend Dockerfile takes uv from
# the astral image. Pinned by digest; there is no other supported way to get a
# specific mc build.
COPY --from=docker.io/minio/mc:latest@sha256:a7fe349ef4bd8521fb8497f55c6042871b2ae640607cf99d9bede5e9bdf11727 /usr/bin/mc /usr/local/bin/mc

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
