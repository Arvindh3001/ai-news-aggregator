"""Run once to create all tables. Safe to re-run — create_all is idempotent."""
from app.database.connection import engine
from app.database.models import Base


def init_db() -> None:
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print("Done.")


if __name__ == "__main__":
    init_db()
