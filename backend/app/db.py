from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .models import Base

engine = None
SessionLocal = None


def init_db(url: str) -> None:
    """(Re)initialise the engine and create tables. Called by create_app()."""
    global engine, SessionLocal
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True}
    engine = create_engine(url, **kwargs)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    try:
        from .auth import init_default_users
        with SessionLocal() as s:
            init_default_users(s)
    except Exception:
        pass


def get_session():
    with SessionLocal() as session:
        yield session
