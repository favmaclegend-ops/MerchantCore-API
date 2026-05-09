from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    PROJECT_NAME: str = "Merchant Core API"
    VERSION: str = "0.1.0"
    DESCRIPTION: str = "Merchant Core API Service"

    DATABASE_URL: str = "sqlite:///./app.db"
    ALLOWED_HOSTS: list[str] = ["*"]

    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int =1440
    TOKEN_EXPIRE_MINUTES: int = 1440

    DEBUG: bool = False

    BCRYPT_ROUNDS: int = 10

    RESEND_API_KEY: str = ""
    SMTP_FROM_EMAIL: str = "onboarding@resend.dev"
    SMTP_FROM_NAME: str = "Merchant Core API"

    PUBLIC_URL: str | None = None

    @property
    def sqlalchemy_database_url(self) -> str:
        """Ensure correct driver and clean query params for MySQL."""
        url = self.DATABASE_URL
        # Replace mysql:// with mysql+pymysql:// if needed
        if url.startswith("mysql://") and "+pymysql" not in url:
            url = url.replace("mysql://", "mysql+pymysql://", 1)

        # Strip unsupported query params like ssl-mode
        parsed = urlparse(url)
        if parsed.query:
            query_params = parse_qs(parsed.query)
            query_params.pop("ssl-mode", None)
            new_query = urlencode(query_params, doseq=True)
            url = urlunparse((
                parsed.scheme, parsed.netloc, parsed.path,
                parsed.params, new_query, parsed.fragment
            ))
        return url


settings = Settings()
