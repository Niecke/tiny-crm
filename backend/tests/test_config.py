"""Unit tests for the production-defaults guard.

Settings are built with `_env_file=None` and the relevant variables cleared, so
these assert on the code's own defaults rather than on whatever the developer
happens to have in backend/.env.
"""

import pytest

from app.config import DEFAULT_S3_ACCESS_KEY, Settings

_ENV_VARS = ["JWT_SECRET", "CORS_ORIGINS", "S3_ACCESS_KEY", "S3_SECRET_KEY", "ENVIRONMENT"]


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_shipped_defaults_are_all_reported(clean_env: None) -> None:
    problems = Settings(_env_file=None).insecure_defaults()

    assert len(problems) == 4
    joined = " ".join(problems)
    assert "JWT_SECRET" in joined
    assert "CORS_ORIGINS" in joined
    assert "S3_ACCESS_KEY" in joined
    assert "S3_SECRET_KEY" in joined


def test_a_properly_configured_instance_has_nothing_to_report(clean_env: None) -> None:
    settings = Settings(
        _env_file=None,
        jwt_secret="9f2c" * 16,
        cors_origins=["https://crm.example.com"],
        s3_access_key="real-access-key",
        s3_secret_key="real-secret-key",
    )

    assert settings.insecure_defaults() == []


def test_each_default_is_reported_on_its_own(clean_env: None) -> None:
    settings = Settings(
        _env_file=None,
        jwt_secret="9f2c" * 16,
        cors_origins=["https://crm.example.com"],
        s3_access_key=DEFAULT_S3_ACCESS_KEY,
        s3_secret_key="real-secret-key",
    )

    problems = settings.insecure_defaults()

    assert len(problems) == 1
    assert "S3_ACCESS_KEY" in problems[0]


def test_a_wildcard_among_real_origins_still_counts(clean_env: None) -> None:
    settings = Settings(
        _env_file=None,
        jwt_secret="9f2c" * 16,
        cors_origins=["https://crm.example.com", "*"],
        s3_access_key="real-access-key",
        s3_secret_key="real-secret-key",
    )

    assert any("CORS_ORIGINS" in problem for problem in settings.insecure_defaults())
