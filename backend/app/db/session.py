from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    database_url = get_settings().database_url
    if not database_url:
        raise RuntimeError("ABEL_DATABASE_URL nao foi configurada")
    return create_engine(database_url, pool_pre_ping=True, pool_recycle=1800)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db_session():
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
