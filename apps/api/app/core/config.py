from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+asyncpg://ekitirun:ekitirun@localhost:5433/ekitirun"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me"
    qr_signing_secret: str = "change-me"
    paystack_secret_key: str = ""
    termii_api_key: str = ""
    termii_sender_id: str = "EkitiRun"
    # Shared secret the Traccar GPS gateway sends in X-Gateway-Secret (E13).
    gateway_secret: str = "change-me"
    # Development-only admin token, used until real admin auth lands in E3.
    # Send it as `Authorization: Bearer <token>`. Ignored in production.
    admin_dev_token: str = "dev-admin"
    # Public base URLs, used to build links returned by the API (QR images, Paystack redirect).
    public_api_url: str = "http://localhost:8000"
    public_web_url: str = "http://localhost:3000"
    # Comma-separated in env, e.g. CORS_ORIGINS=http://localhost:3000,https://ekitirun.ng
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


settings = Settings()
