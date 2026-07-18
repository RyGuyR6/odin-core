#!/usr/bin/env bash
set -e

echo "==================================="
echo "Installing Database Layer"
echo "==================================="

mkdir -p backend/app/database
mkdir -p backend/app/models

#########################################
# database.py
#########################################

cat > backend/app/database/database.py <<'PYEOF'
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///./odin.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    autoflush=False,
    autocommit=False,
    bind=engine,
)

Base = declarative_base()
PYEOF

#########################################
# memory model
#########################################

cat > backend/app/models/memory.py <<'PYEOF'
from sqlalchemy import Column, Integer, String, Text

from app.database.database import Base


class Memory(Base):
    __tablename__ = "memory"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
PYEOF

#########################################
# init_db.py
#########################################

cat > backend/app/database/init_db.py <<'PYEOF'
from app.database.database import Base, engine

# Import models so SQLAlchemy knows about them.
from app.models.memory import Memory  # noqa: F401


def init_db():
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
PYEOF

echo
echo "==================================="
echo "Database layer installed."
echo "==================================="
echo
echo "Next:"
echo "1. pip install sqlalchemy"
echo "2. python -m app.database.init_db"
