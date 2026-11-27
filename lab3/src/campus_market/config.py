"""Load explicit local settings without embedding authentication secrets."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """Configuration shared by HTTP, command line, and database services."""

    database_url: str
    secret: str
    asset_dir: Path
    secure_cookie: bool = False
    testing: bool = False

    @classmethod
    def from_env(cls, *, testing: bool = False) -> "Settings":
        """Read .env from the launch directory; fail closed on missing secrets."""
        load_dotenv(override=False)
        key = "TEST_DATABASE_URL" if testing else "DATABASE_URL"
        url = os.environ.get(key, "")
        secret = os.environ.get("APP_SECRET", "")
        if not url.startswith("postgresql+psycopg://"):
            raise ValueError(f"{key} must specify a PostgreSQL psycopg connection")
        if len(secret) < 32 or secret.startswith("CHANGE_"):
            raise ValueError("APP_SECRET must contain at least 32 random characters")
        return cls(
            database_url=url,
            secret=secret,
            asset_dir=Path(os.environ.get("ASSET_DIR", "var/images")).resolve(),
            secure_cookie=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
            testing=testing,
        )
