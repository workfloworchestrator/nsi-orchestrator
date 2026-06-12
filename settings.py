from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application-specific settings for the NSI orchestrator."""


settings = Settings()
