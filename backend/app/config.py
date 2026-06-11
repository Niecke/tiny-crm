from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://crm:crm@localhost:5432/crm"
    # Locked down to the real domain in prod via env var
    cors_origins: list[str] = ["*"]
    # Must be overridden in prod with a long random secret
    jwt_secret: str = "CHANGE_ME_IN_PROD"

    # S3-compatible storage — set S3_ENDPOINT_URL for MinIO/Hetzner; leave unset for AWS
    s3_endpoint_url: str | None = None
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "tinycrm-documents"
    s3_region: str = "us-east-1"


settings = Settings()
