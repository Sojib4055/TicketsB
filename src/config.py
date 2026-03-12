from __future__ import annotations

from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    app_env: str = "dev"
    dry_run: bool = True
    log_level: str = "INFO"

    poll_interval_seconds: int = 30
    fast_poll_interval_seconds: int = 5
    max_retries: int = 3
    max_tickets: int = 2
    max_total_usd: float = 200.0

    target_event_url: str = "https://example.com/events/sample"
    preferred_sections: str = "Lower Bowl,Floor"
    avoid_keywords: str = "resale,VIP,platinum,obstructed"

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    discord_webhook_url: str | None = None

    customer_name: str = "Sample User"
    customer_email: str = "user@example.com"
    customer_phone: str = "+10000000000"

    payment_method_alias: str = "visa_personal"
    card_last4: str = "1234"
    billing_zip: str = "10001"

    @property
    def preferred_sections_list(self) -> List[str]:
        return [s.strip() for s in self.preferred_sections.split(",") if s.strip()]

    @property
    def avoid_keywords_list(self) -> List[str]:
        return [s.strip().lower() for s in self.avoid_keywords.split(",") if s.strip()]


settings = Settings()
