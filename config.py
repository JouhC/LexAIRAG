from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from urllib.parse import quote_plus


class Settings(BaseSettings):
    # --- config for pydantic-settings v2 ---
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow",
    )

    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: int = 5432
    @property
    def DATABASE_URL(self) -> str:
        # URL-encode user/pass to handle special characters safely
        user = quote_plus(self.DB_USER)
        password = quote_plus(self.DB_PASSWORD)
        host = self.DB_HOST
        return f"postgresql://postgres.fpneuorcexvaxdweztdc:{password}@aws-1-ap-southeast-2.pooler.supabase.com:5432/postgres"
        #return f"postgresql://{user}:{password}@{host}:{self.DB_PORT}/{self.DB_NAME}?sslmode=require"

settings = Settings()