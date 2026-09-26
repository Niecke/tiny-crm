FROM node:24.21.0-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Git commit of this build, passed in from CI. Baked into the bundle (shown on
# the System page) and written to version.json, which the smoke test compares
# against the backend's — the same contract the Flutter image keeps. The build
# time is baked in beside it, in the backend's format, and so is the product
# version CI works out ("v0.1.0" for a release, "v0.1.0-abc1234" otherwise).
ARG GIT_COMMIT=dev
ENV VITE_GIT_COMMIT=$GIT_COMMIT
ARG APP_VERSION=dev
ENV VITE_APP_VERSION=$APP_VERSION
RUN echo "{\"version\":\"$GIT_COMMIT\"}" > public/version.json && \
    VITE_BUILD_TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ") npm run build

# Static files only: Node exists in the build stage and nowhere after it. The
# same Caddy digest as the Flutter image, so the two stay on one server version
# until the cutover.
FROM caddy:alpine@sha256:6aeddd44c3078b0f9a35206472a11420648a79c184603ef95957d0a20044cb2b
# Under /srv/next because that is the path the app is served at: requests
# arrive with the /next prefix intact, and the file layout matches them.
COPY --from=builder /app/dist /srv/next
COPY Caddyfile /etc/caddy/Caddyfile

EXPOSE 8080
