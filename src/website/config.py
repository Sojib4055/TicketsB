from pathlib import Path
from typing import Literal

from pydantic import Field, PrivateAttr
from pydantic_settings import BaseSettings, SettingsConfigDict


class WebSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    booking_mode: Literal['demo', 'live'] = 'demo'
    website_host: str = '127.0.0.1'
    website_port: int = 8765
    website_public_url: str = 'http://127.0.0.1:8765'
    website_database: Path = Path('data/tickets.sqlite3')
    website_secure_cookies: bool = False
    browser_executable: str = ''
    website_poll_seconds: int = Field(default=60, ge=15, le=600)
    website_worker_concurrency: int = Field(default=2, ge=1, le=8)
    website_browser_limit: int = Field(default=4, ge=2, le=12)
    website_provider_timeout: int = Field(default=90, ge=10, le=180)
    website_session_idle_minutes: int = Field(default=20, ge=5, le=120)
    website_departure_buffer_minutes: int = Field(default=5, ge=0, le=60)
    website_backup_hours: int = Field(default=24, ge=1, le=168)
    website_backup_keep: int = Field(default=7, ge=1, le=30)
    _browser_budget: object = PrivateAttr(default=None)
    whatsapp_access_token: str = ''
    whatsapp_phone_number_id: str = ''
    whatsapp_api_version: str = ''
    whatsapp_template_name: str = 'ticket_booking_update'
    whatsapp_template_language: str = 'en_US'
    whatsapp_verify_token: str = ''
    whatsapp_app_secret: str = ''

    @property
    def whatsapp_ready(self) -> bool:
        return all((self.whatsapp_access_token, self.whatsapp_phone_number_id,
                    self.whatsapp_api_version, self.whatsapp_template_name))


web_settings = WebSettings()
