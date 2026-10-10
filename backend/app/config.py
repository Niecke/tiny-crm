from enum import StrEnum

from pydantic import BaseModel, Field
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


class WorkerPool(BaseModel):
    """One group of job slots in the worker: these queues, this many at once.

    A pool's slots are its own — a queue backed up in one pool never takes a
    slot from another. That is how mail keeps moving while a long job runs.
    """

    name: str
    queues: list[str] = Field(min_length=1)
    concurrency: int = Field(default=1, ge=1)


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
    # A login is a session (app/auth/sessions.py): a short-lived access token
    # the clients renew with a refresh token. The access token is what a leak
    # exposes, so it lives minutes. The refresh token's lifetime is idle time —
    # every refresh extends it — so the Android PWA stays signed in as long as
    # it is opened at least once in that window.
    access_token_lifetime_seconds: int = 60 * 15
    refresh_token_lifetime_seconds: int = 60 * 60 * 24 * 90

    # Login throttling, counted per client address over a sliding window.
    # Only failed logins count, so a legitimate mistype costs almost nothing.
    login_max_failures: int = 10
    login_failure_window_seconds: int = 300
    # Per-account backoff on top of it, kept in Postgres (app/auth/throttle.py).
    # After the free failures, each further one locks the account for 2, 4, 8, …
    # seconds up to the cap; a quiet decay window starts the count afresh.
    login_backoff_free_failures: int = 3
    login_backoff_max_seconds: int = 60 * 15
    login_backoff_decay_seconds: int = 60 * 60 * 24
    # At most one password-reset mail per account in this long.
    password_reset_cooldown_seconds: int = 60 * 5

    # Git commit of the running build, injected at image build time via the
    # GIT_COMMIT build arg (git isn't available inside the build container).
    git_commit: str = "unknown"
    # The product version of the running build, from the APP_VERSION build arg:
    # "v0.1.0" for a release, "v0.1.0-abc1234" for any other build (ci.yml).
    app_version: str = "dev"

    # S3-compatible storage — set S3_ENDPOINT_URL for MinIO/Hetzner; leave unset for AWS
    s3_endpoint_url: str | None = None
    s3_access_key: str = DEFAULT_S3_ACCESS_KEY
    s3_secret_key: str = DEFAULT_S3_SECRET_KEY
    s3_bucket: str = "tinycrm-documents"
    s3_region: str = "us-east-1"

    # Morning briefing to Slack (app/briefing.py, sent by scripts/send_briefing.py
    # from a CronJob). Unset means there is nowhere to send it, and the script
    # says so and exits non-zero rather than silently doing nothing.
    slack_webhook_url: str | None = None
    # What "today" means in the briefing. Task due dates are filed as 23:59
    # local time, which is the previous day in UTC for half the year, so the
    # day boundary has to be the operator's, not the server's.
    briefing_timezone: str = "Europe/Berlin"
    # Public origin of the frontend, for the "Open tinyCRM" link in the
    # message. Optional: without it the briefing simply has no link.
    app_url: str | None = None

    # Transactional mail through Brevo's API (app/mail.py): the invite a new
    # account gets and the password-reset link. Both links point at APP_URL, so
    # sending needs all three. Unset means no mail: a reset request is logged
    # and dropped, and the CLI refuses to invite. The API needs them to know
    # whether to queue a reset mail, the worker to send it.
    brevo_api_key: str | None = None
    # Must be a sender Brevo has verified, on a domain with its SPF/DKIM records.
    mail_from_address: str | None = None
    mail_from_name: str = "tinyCRM"
    # How long an invite or reset link stays usable. Either one is single-use
    # regardless: the token is bound to the password hash it was issued for.
    password_token_lifetime_seconds: int = 60 * 60 * 12

    # The background worker (app/worker.py, `python -m app.worker`): the pools
    # it runs, as JSON in WORKER_POOLS. Mail has a pool nothing else can
    # occupy. All pools share one process; running one Deployment per pool
    # later is this variable set differently on each, not a code change.
    worker_pools: list[WorkerPool] = [
        WorkerPool(name="mail", queues=["mail"], concurrency=2),
        WorkerPool(name="default", queues=["default"], concurrency=1),
    ]
    # On SIGTERM the worker takes no new jobs and gives the running ones this
    # long to finish before aborting them. Keep it below the pod's
    # terminationGracePeriodSeconds, or the kill comes first and the jobs are
    # left for the stalled-job sweep instead of being recorded as aborted.
    worker_shutdown_grace_seconds: int = 50
    # A queued mail older than this is dropped instead of sent: a reset link
    # arriving an hour after the click answers a question nobody is asking any
    # more. Above the retry schedule's total (app/jobs/mail.py), so a mail is
    # only ever dropped for a worker that was down, not for one that retried.
    mail_max_age_seconds: int = 60 * 30

    # Business card scanning (app/business_cards.py): the photos are read by
    # Claude through the Anthropic API. Unset means no scanning — the scan
    # endpoint answers 503 and says which variable to set.
    anthropic_api_key: str | None = None
    business_card_model: str = "claude-opus-5-5"

    def missing_mail_settings(self) -> list[str]:
        """Env vars that must be set before any mail can go out."""
        required = {
            "BREVO_API_KEY": self.brevo_api_key,
            "MAIL_FROM_ADDRESS": self.mail_from_address,
            "APP_URL": self.app_url,
        }
        return [name for name, value in required.items() if not value]

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
