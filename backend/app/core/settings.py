from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Odin Core"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"

    ODIN_GITHUB_TOKEN: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
