from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://ekitirun:ekitirun@localhost:5432/ekitirun"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me"
    qr_signing_secret: str = "change-me"
    paystack_secret_key: str = ""
    termii_api_key: str = ""
    termii_sender_id: str = "EkitiRun"
    # Comma-separated in env, e.g. CORS_ORIGINS=http://localhost:3000,https://ekitirun.ng
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


settings = Settings()
