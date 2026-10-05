FROM node:24.21.0-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Git commit of this build, passed in from CI. Baked into the bundle (shown on
# the System page) and written to version.json, which the smoke test compares
# against the backend's and open tabs poll to reload after a deploy. The build
# time is baked in beside it, in the backend's format, and so is the product
# version CI works out ("v0.1.0" for a release, "v0.1.0-abc1234" otherwise).
ARG GIT_COMMIT=dev
ENV VITE_GIT_COMMIT=$GIT_COMMIT
ARG APP_VERSION=dev
ENV VITE_APP_VERSION=$APP_VERSION
RUN echo "{\"version\":\"$GIT_COMMIT\"}" > public/version.json && \
    VITE_BUILD_TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ") npm run build

# Static files only: Node exists in the build stage and nowhere after it.
FROM caddy:alpine@sha256:d44355d3c2149dc580ce2cac735955d1c08d3d00882c30489c241aa51a5c10d9
COPY --from=builder /app/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile

EXPOSE 8080
