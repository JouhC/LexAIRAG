from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from urllib.parse import quote_plus
from typing import List, Optional, Any
from pydantic import AnyHttpUrl, field_validator
import json

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
    DEFAULT_API_URL: str = "http://localhost:8000"
    TEST: str = ""

    @field_validator("TEST", mode="after")
    @classmethod
    def parse_origins(cls, v: Any) -> Any:
        if v is None or v == "":
            return []

        if isinstance(v, str):
            v = v.strip()
            print([item.strip() for item in v.split(",") if item.strip()])
            # If JSON string, load it
            if v.startswith("["):
                return json.loads(v)
            # If comma-separated
            return [item.strip() for item in v.split(",") if item.strip()]

        return v

    @property
    def DATABASE_URL(self) -> str:
        # URL-encode user/pass to handle special characters safely
        user = quote_plus(self.DB_USER)
        password = quote_plus(self.DB_PASSWORD)
        host = self.DB_HOST
        return f"postgresql://{user}:{password}@{host}:{self.DB_PORT}/{self.DB_NAME}?sslmode=require"

settings = Settings()