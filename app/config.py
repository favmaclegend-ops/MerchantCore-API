from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    PROJECT_NAME: str = "Merchant Core API"
    VERSION: str = "0.1.0"
    DESCRIPTION: str = "Merchant Core API Service"

    DATABASE_URL: str = "sqlite:///./app.db"
    ALLOWED_HOSTS: list[str] = ["*"]

    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    TOKEN_EXPIRE_MINUTES: int = 30

    DEBUG: bool = False

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "Merchant Core API"

    @property
    def sqlalchemy_database_url(self) -> str:
        """Ensure correct driver is used for MySQL."""
        url = self.DATABASE_URL
        if url.startswith("mysql://") and "+pymysql" not in url:
            return url.replace("mysql://", "mysql+pymysql://", 1)
        return url


settings = Settings()
