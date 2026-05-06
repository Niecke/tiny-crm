FROM ghcr.io/cirruslabs/flutter:stable AS builder
WORKDIR /app
COPY pubspec.* ./
RUN flutter pub get
COPY . .
RUN flutter build web --release

FROM caddy:alpine
COPY --from=builder /app/build/web /srv
COPY Caddyfile /etc/caddy/Caddyfile
