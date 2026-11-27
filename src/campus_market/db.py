"""Session ownership: business commands own one complete database transaction."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from campus_market.config import Settings


class Database:
    """A process-local pool; sessions must never be shared between requests."""

    def __init__(self, settings: Settings):
        self.engine = create_engine(
            settings.database_url, pool_size=10, max_overflow=20,
            pool_pre_ping=True, connect_args={"connect_timeout": 5},
        )
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def close(self):
        """Release pool connections during graceful application shutdown."""
        self.engine.dispose()
