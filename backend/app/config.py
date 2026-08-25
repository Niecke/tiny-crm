from enum import StrEnum

from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder values shipped in the defaults so a fresh checkout runs against
# the local compose stack. check_secure_defaults() warns about every one that
# survives into a running instance, and refuses to start in production.
DEFAULT_JWT_SECRET = "CHANGE_ME_IN_PROD"
DEFAULT_S3_ACCESS_KEY = "minioadmin"
DEFAULT_S3_SECRET_KEY = "minioadmin"


class Environment(StrEnum):
    development = "development"
    production = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Production tightens the development defaults below from warnings into a
    # hard startup failure. Set ENVIRONMENT=production on the deployed instance.
    environment: Environment = Environment.development

    database_url: str = "postgresql+asyncpg://crm:crm@localhost:5432/crm"
    # SQLAlchemy statement logging. Off by default: echo prints every statement
    # together with its bound parameters, i.e. contact and document data.
    db_echo: bool = False
    # Locked down to the real domain in prod via env var
    cors_origins: list[str] = ["*"]
    # Must be overridden in prod with a long random secret
    jwt_secret: str = DEFAULT_JWT_SECRET
    # How long a login stays valid. There is no refresh token, so this is also
    # the hard re-login interval. ~9 months keeps the Android PWA logged in.
    jwt_lifetime_seconds: int = 60 * 60 * 24 * 270

    # Git commit of the running build, injected at image build time via the
    # GIT_COMMIT build arg (git isn't available inside the build container).
    git_commit: str = "unknown"

    # S3-compatible storage — set S3_ENDPOINT_URL for MinIO/Hetzner; leave unset for AWS
    s3_endpoint_url: str | None = None
    s3_access_key: str = DEFAULT_S3_ACCESS_KEY
    s3_secret_key: str = DEFAULT_S3_SECRET_KEY
    s3_bucket: str = "tinycrm-documents"
    s3_region: str = "us-east-1"

    def insecure_defaults(self) -> list[str]:
        """Env vars still sitting on a built-in default that is unsafe to deploy.

        Each entry names the variable and says what to set it to, so the startup
        log is enough to fix the deployment without reading this file.
        """
        problems: list[str] = []
        if self.jwt_secret == DEFAULT_JWT_SECRET:
            problems.append(
                "JWT_SECRET is the built-in placeholder — anyone who knows it can mint "
                "valid tokens for this instance. Generate one with `openssl rand -hex 32`."
            )
        if "*" in self.cors_origins:
            problems.append(
                "CORS_ORIGINS allows any origin ('*') — set it to the frontend's real "
                'origin, e.g. CORS_ORIGINS=["https://crm.example.com"].'
            )
        if self.s3_access_key == DEFAULT_S3_ACCESS_KEY:
            problems.append("S3_ACCESS_KEY is the MinIO demo credential 'minioadmin'.")
        if self.s3_secret_key == DEFAULT_S3_SECRET_KEY:
            problems.append("S3_SECRET_KEY is the MinIO demo credential 'minioadmin'.")
        return problems


settings = Settings()
