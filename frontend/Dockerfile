FROM ghcr.io/cirruslabs/flutter:stable AS builder
WORKDIR /app
RUN flutter precache --web
COPY pubspec.* ./
RUN flutter pub get
COPY . .
RUN export APP_VERSION=$(date -u +%Y%m%d%H%M%S) && \
    echo "{\"version\":\"$APP_VERSION\"}" > web/version.json && \
    flutter build web --release --dart-define=APP_VERSION=$APP_VERSION

FROM caddy:alpine
COPY --from=builder /app/build/web /srv
COPY Caddyfile /etc/caddy/Caddyfile

EXPOSE 8080