#!/usr/bin/env bash
set -e

mkdir -p backend/app/database
mkdir -p backend/app/models

touch backend/app/database/__init__.py
touch backend/app/models/__init__.py

cat > backend/app/database/database.py <<'PY'
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///./odin.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)

Base = declarative_base()
PY

cat > backend/app/models/memory.py <<'PY'
from sqlalchemy import Column, Integer, String, Text

from app.database.database import Base


class Memory(Base):
    __tablename__ = "memory"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
PY

cat > backend/app/database/init_db.py <<'PY'
from app.database.database import Base, engine
from app.models.memory import Memory  # noqa: F401


def init_db():
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
PY

echo "Database files created."
