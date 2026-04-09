from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings


settings = get_settings()

engine_kwargs: dict[str, object] = {
    "echo": False,
    # The app currently runs in local/dev-style lifecycles where repeated startup
    # and CLI/test access can cross event loops. Disabling pooling avoids
    # asyncpg loop-affinity issues until a production-specific DB strategy lands.
    "poolclass": NullPool,
}

engine = create_async_engine(settings.database_url, **engine_kwargs)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
