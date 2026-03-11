from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    product_name: str = "get-put.io"
    host: str = "0.0.0.0"
    port: int = 8000
    storage_path: Path = Path("/media")
    state_path: Path = ROOT_DIR / "data" / "app" / "state.json"
    rclone_binary: str = Field(default="rclone", alias="RCLONE_BINARY")
    schedule_timezone: str = "UTC"
    scheduler_poll_seconds: int = 30

    putio_app_id: str | None = Field(default=None, alias="PUTIO_APP_ID")
    putio_client_secret: str | None = Field(default=None, alias="PUTIO_CLIENT_SECRET")
    putio_redirect_uri: str = Field(
        default="http://localhost:8787/api/auth/putio/callback",
        alias="PUTIO_REDIRECT_URI",
    )
    putio_access_token: str | None = Field(default=None, alias="PUTIO_ACCESS_TOKEN")

    jellyfin_base_url: str | None = Field(default=None, alias="JELLYFIN_BASE_URL")
    jellyfin_api_key: str | None = Field(default=None, alias="JELLYFIN_API_KEY")

    model_config = SettingsConfigDict(
        env_prefix="GET_PUTIO_",
        env_file=(ROOT_DIR / ".env", ROOT_DIR / "backend" / ".env"),
        extra="ignore",
    )

    @property
    def frontend_dist(self) -> Path:
        return Path(__file__).resolve().parent / "static"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
