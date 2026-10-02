from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from bot.database.models import Base, Package


async def create_database(
    database_url: str,
) -> tuple[async_sessionmaker[AsyncSession], AsyncEngine]:
    url = make_url(database_url)
    if url.drivername.startswith("sqlite") and url.database and url.database != ":memory:":
        Path(url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        if await session.get(Package, 1) is None:
            session.add_all(
                [
                    Package(name="60 UC", uc_amount=60, price=12000, is_active=True),
                    Package(name="325 UC", uc_amount=325, price=60000, is_active=True),
                    Package(name="660 UC", uc_amount=660, price=120000, is_active=True),
                    Package(name="1800 UC", uc_amount=1800, price=300000, is_active=True),
                ]
            )
    return sessions, engine
