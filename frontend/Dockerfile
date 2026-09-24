FROM ghcr.io/adrianjagielak/flutter:3.47.2@sha256:083e197fd1382da5d8da14a0f9dfef7ae11b44e00f26e977ddd30d5897c81d51 AS builder
WORKDIR /app
RUN flutter precache --web
COPY pubspec.* ./
RUN flutter pub get
COPY . .
# Git commit of this build, passed in from CI (git isn't available in-container).
# It's the single version identifier: baked into the app via --dart-define
# (shown in the footer) and written to version.json, which already-open clients
# poll so they reload themselves whenever a new commit is shipped.
ARG GIT_COMMIT=dev
RUN echo "{\"version\":\"$GIT_COMMIT\"}" > web/version.json && \
    flutter build web --release \
      --dart-define=GIT_COMMIT=$GIT_COMMIT \
      --wasm

FROM caddy:alpine@sha256:6aeddd44c3078b0f9a35206472a11420648a79c184603ef95957d0a20044cb2b
COPY --from=builder /app/build/web /srv
COPY Caddyfile /etc/caddy/Caddyfile

EXPOSE 8080