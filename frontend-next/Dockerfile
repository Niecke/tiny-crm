FROM node:24.22.1-alpine@sha256:06d7adf3e0ef61a13f1d28682726366f97a15aa1888c934d3ecec86c33918b53 AS builder
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
FROM caddy:alpine@sha256:eb4d35b7452d1ab6171fbdbe8d9275b2301dad6dad92115d91e19fb9b24d510f

RUN addgroup -g 10001 -S caddy && adduser -u 10001 -D -S -G caddy caddy

ENV XDG_CONFIG_HOME=/tmp/config \
    XDG_DATA_HOME=/tmp/data

COPY --from=builder /app/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile

USER 10001

EXPOSE 8080
