# Backup runner: pg_dump, rclone and brotli in one place.
#
# Based on the CloudNativePG postgres image rather than a plain Debian, because
# pg_dump refuses to dump a server newer than itself — the major version here
# has to track the one the Cluster runs.
FROM ghcr.io/cloudnative-pg/postgresql:18.6-system-trixie@sha256:99bc64e413d59b017d169ce2ff25746f1d68c5d7210a19f12c0464a109216ee1

# rclone from the official image, the same way the backend Dockerfile takes uv
# from the astral image. Pinned by digest. The binary is statically linked, so
# lifting it out of the Alpine image into this Debian one is safe.
#
# rclone replaced mc once MinIO withdrew its images from Docker Hub and then
# quay.io (#112).
COPY --from=docker.io/rclone/rclone:1.75.1@sha256:45401ad7410db1d67ffdb58e19059ad20b0d8e0285a60e38bbec55cc1019c7a5 /usr/local/bin/rclone /usr/local/bin/rclone

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends brotli \
    && rm -rf /var/lib/apt/lists/*

COPY backup.sh /usr/local/bin/backup.sh
RUN chmod 0755 /usr/local/bin/backup.sh /usr/local/bin/rclone

# Back to the image's unprivileged postgres user.
USER 26

ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=${GIT_COMMIT}

ENTRYPOINT ["/usr/local/bin/backup.sh"]
