from __future__ import annotations

from typing import List
from urllib.parse import parse_qs, urlparse

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
    console_logs: bool = False

    poll_interval_seconds: int = 30
    fast_poll_interval_seconds: int = 5
    max_retries: int = 3
    max_tickets: int = 2
    max_total_price: float | None = None
    max_total_usd: float = 2000.0
    price_currency: str = "BDT"
    top_offer_limit: int = 5
    availability_confidence_threshold: float = 0.75
    availability_confirmation_snapshots: int = 2
    preferred_operators: str = ""
    avoid_operators: str = ""
    preferred_departure_start: str | None = None
    preferred_departure_end: str | None = None
    avoid_night_buses: bool = False
    target_origin: str | None = None
    target_destination: str | None = None
    require_trip_setup: bool = False

    ui_enabled: bool = True
    ui_host: str = "127.0.0.1"
    ui_port: int = 8765
    ui_persist_after_run: bool = True

    mcp_server_url: str = "http://localhost:8931/mcp"
    mcp_command_timeout_seconds: int = 30

    target_event_url: str = "https://example.com/events/sample"
    monitor_targets_json: str | None = None
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

    @property
    def preferred_operators_list(self) -> List[str]:
        return [s.strip().lower() for s in self.preferred_operators.split(",") if s.strip()]

    @property
    def avoid_operators_list(self) -> List[str]:
        return [s.strip().lower() for s in self.avoid_operators.split(",") if s.strip()]

    @property
    def effective_max_total_price(self) -> float:
        return self.max_total_price if self.max_total_price is not None else self.max_total_usd

    @property
    def normalized_price_currency(self) -> str:
        return self.price_currency.strip().upper() or "PRICE"

    @property
    def effective_target_origin(self) -> str:
        return (self.target_origin or self._query_value("fromcity") or "").strip()

    @property
    def effective_target_destination(self) -> str:
        return (self.target_destination or self._query_value("tocity") or "").strip()

    def _query_value(self, key: str) -> str | None:
        parsed = urlparse(self.target_event_url)
        values = parse_qs(parsed.query).get(key)
        return values[0] if values else None


settings = Settings()
