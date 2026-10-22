from datetime import date
from typing import Annotated, Literal, Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Development-only default for every secret. Production refuses to start with it.
INSECURE_DEFAULT = "dev-only-insecure-secret-change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+asyncpg://ekitirun:ekitirun@localhost:5433/ekitirun"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = INSECURE_DEFAULT
    qr_signing_secret: str = INSECURE_DEFAULT
    paystack_secret_key: str = ""

    # SMS for phone verification (E3). "console" prints messages to the API log
    # instead of sending them; production must use "termii".
    sms_provider: Literal["console", "termii"] = "console"
    termii_api_key: str = ""
    termii_sender_id: str = "EkitiRun"
    termii_base_url: str = "https://api.ng.termii.com"
    # Development only: every OTP is this code, so frontend testing stays simple.
    # Leave empty to get random codes (printed in the API log with the console provider).
    otp_dev_code: str | None = "123456"

    # Race day, used for the minimum-age rule (age on race day). Until it is set,
    # ages are checked against today's date.
    race_date: date | None = None

    # Shared secret the Traccar GPS gateway sends in X-Gateway-Secret (E13).
    gateway_secret: str = INSECURE_DEFAULT
    # Development-only admin token, used until real admin auth exists.
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

    @field_validator("otp_dev_code", "race_date", mode="before")
    @classmethod
    def empty_is_none(cls, v):
        return v or None

    @model_validator(mode="after")
    def safe_for_production(self) -> Self:
        """Refuse to start in production with development shortcuts or default secrets."""
        if self.environment != "production":
            return self
        problems = [
            name.upper()
            for name in ("jwt_secret", "qr_signing_secret", "gateway_secret")
            if getattr(self, name) == INSECURE_DEFAULT or len(getattr(self, name)) < 32
        ]
        if self.otp_dev_code:
            problems.append("OTP_DEV_CODE must be empty")
        if self.sms_provider != "termii" or not self.termii_api_key:
            problems.append("SMS_PROVIDER=termii with TERMII_API_KEY")
        if problems:
            raise ValueError(
                "Unsafe production settings (secrets need 32+ random characters): "
                + ", ".join(problems)
            )
        return self


settings = Settings()
