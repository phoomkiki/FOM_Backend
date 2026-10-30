from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"

    # Optional: only needed for direct SQLAlchemy/Alembic operations.
    # Runtime API data access uses Supabase Data API (SUPABASE_URL).
    database_url: str | None = None

    secret_key: str = Field(
        default="CHANGE_THIS_TO_A_LONG_RANDOM_SECRET",
        validation_alias=AliasChoices("JWT_SECRET", "SECRET_KEY"),
    )
    access_token_expire_minutes: int = 60

    supabase_url: str | None = None
    supabase_service_role_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "SUPABASE_SECRET_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
        ),
    )

    line_channel_id: str | None = None
    frontend_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()
