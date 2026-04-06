from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/ai_news_aggregator"
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    MY_EMAIL: str = ""
    MY_EMAIL_APP_PASSWORD: str = ""
    # Optional: Webshare rotating proxies for YouTube transcript fetching
    WEBSHARE_USERNAME: str = ""
    WEBSHARE_PASSWORD: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # drop stale connections before use
)
SessionLocal: sessionmaker[Session] = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db_session() -> Session:
    """Context-manager-style session factory for use outside request cycles."""
    return SessionLocal()
