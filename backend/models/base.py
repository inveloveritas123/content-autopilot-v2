from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import settings


class Base(DeclarativeBase):
    pass


async_engine = create_async_engine(settings.database_url, echo=False)
async_session_factory = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

sync_engine = create_engine(settings.sync_database_url, echo=False)
sync_session_factory = sessionmaker(sync_engine, expire_on_commit=False)
