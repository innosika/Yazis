"""SQLite through SQLAlchemy 2. One file, WAL mode, schema created on start-up.

Only user data lives here (documents, settings, pronunciations, command overrides and
custom commands). The built-in command catalog and the CS lexicon are code, versioned
with the application, so an upgrade never needs a data migration for them.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None


def init_db(path: Path) -> Engine:
    global _engine, _Session
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn: Any, _record: Any) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    from app.db import models  # noqa: F401  (register tables)

    Base.metadata.create_all(engine)
    _engine = engine
    _Session = sessionmaker(engine, expire_on_commit=False)
    return engine


@contextmanager
def session() -> Iterator[Session]:
    if _Session is None:
        raise RuntimeError("database not initialised")
    s = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
