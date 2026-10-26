from datetime import date
from typing import Annotated, Literal, Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Development-only default for every secret. Production refuses to start with it.
INSECURE_DEFAULT = "dev-only-insecure-secret-change-me-in-production"
DEV_KIT_PIN = "246810"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+asyncpg://ekitirun:ekitirun@localhost:5433/ekitirun"
    # Migrations only: a direct (non-pooled) connection, e.g. Neon's host without "-pooler".
    # Empty = use DATABASE_URL.
    migration_database_url: str | None = None
    # Connections per API process. Keep (pool + overflow) x processes under the database limit.
    db_pool_size: int = 10
    db_max_overflow: int = 10
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = INSECURE_DEFAULT
    qr_signing_secret: str = INSECURE_DEFAULT
    # Payments (E5). "fake" approves every checkout without Paystack, for local work;
    # "paystack" uses the real API (sk_test_ keys for test mode, sk_live_ in production).
    payment_provider: Literal["fake", "paystack"] = "fake"
    paystack_secret_key: str = ""
    paystack_base_url: str = "https://api.paystack.co"

    # SMS for phone verification (E3). "console" prints messages to the API log
    # instead of sending them; production must use "termii".
    sms_provider: Literal["console", "termii"] = "console"
    termii_api_key: str = ""
    termii_sender_id: str = "EkitiRun"
    termii_base_url: str = "https://api.ng.termii.com"
    # Development only: every OTP is this code, so frontend testing stays simple.
    # Leave empty to get random codes (printed in the API log with the console provider).
    otp_dev_code: str | None = "123456"

    # Shown on sponsor invoices and receipts (E6). Placeholders until the organisers confirm.
    organiser_name: str = "Ekiti Marathon Organising Committee"
    organiser_address: str = "Ado-Ekiti, Ekiti State, Nigeria"
    organiser_email: str = "sponsors@ekitirun.ng"
    bank_name: str = "Bank name (set BANK_NAME)"
    bank_account_name: str = "Account name (set BANK_ACCOUNT_NAME)"
    bank_account_number: str = "0000000000"
    invoice_due_days: int = 14

    # 6-digit PIN for the kit-collection and tracker-return desks (E15). Change it for the race.
    kit_pin: str = DEV_KIT_PIN

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

    @field_validator("otp_dev_code", "race_date", "migration_database_url", mode="before")
    @classmethod
    def empty_is_none(cls, v):
        return v or None

    @field_validator("kit_pin")
    @classmethod
    def six_digit_pin(cls, v: str) -> str:
        if not (len(v) == 6 and v.isdigit()):
            raise ValueError("KIT_PIN must be 6 digits")
        return v

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
        if self.kit_pin == DEV_KIT_PIN:
            problems.append("KIT_PIN (not the development PIN)")
        if self.sms_provider != "termii" or not self.termii_api_key:
            problems.append("SMS_PROVIDER=termii with TERMII_API_KEY")
        if self.payment_provider != "paystack" or not self.paystack_secret_key.startswith(
            "sk_live_"
        ):
            problems.append("PAYMENT_PROVIDER=paystack with a live PAYSTACK_SECRET_KEY")
        if problems:
            raise ValueError(
                "Unsafe production settings (secrets need 32+ random characters): "
                + ", ".join(problems)
            )
        return self


settings = Settings()
