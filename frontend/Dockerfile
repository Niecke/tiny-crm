FROM ghcr.io/cirruslabs/flutter:stable AS builder
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

FROM caddy:alpine
COPY --from=builder /app/build/web /srv
COPY Caddyfile /etc/caddy/Caddyfile

EXPOSE 8080