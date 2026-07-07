from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _run_migrations():
    inspector = inspect(engine)
    if inspector.has_table("read_list_items"):
        columns = {col["name"] for col in inspector.get_columns("read_list_items")}
        if "cover_image_url" not in columns:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE read_list_items "
                        "ADD COLUMN cover_image_url VARCHAR(512)"
                    )
                )

    if inspector.has_table("app_settings"):
        settings_columns = {
            col["name"] for col in inspector.get_columns("app_settings")
        }
        with engine.begin() as conn:
            if "komga_url" not in settings_columns:
                conn.execute(
                    text(
                        "ALTER TABLE app_settings "
                        "ADD COLUMN komga_url VARCHAR(512) "
                        "DEFAULT 'http://localhost:25600'"
                    )
                )
            if "komga_api_key" not in settings_columns:
                conn.execute(
                    text(
                        "ALTER TABLE app_settings "
                        "ADD COLUMN komga_api_key VARCHAR(255) DEFAULT ''"
                    )
                )

    if inspector.has_table("read_lists"):
        list_columns = {col["name"] for col in inspector.get_columns("read_lists")}
        with engine.begin() as conn:
            if "tags" not in list_columns:
                conn.execute(text("ALTER TABLE read_lists ADD COLUMN tags TEXT"))

    if inspector.has_table("read_list_items"):
        item_columns = {col["name"] for col in inspector.get_columns("read_list_items")}
        with engine.begin() as conn:
            if "notes" not in item_columns:
                conn.execute(text("ALTER TABLE read_list_items ADD COLUMN notes TEXT"))


def init_db():
    from app import models  # noqa: F401
    from app.services.app_settings import SettingsStore

    Base.metadata.create_all(bind=engine)
    _run_migrations()
    db = SessionLocal()
    try:
        SettingsStore.ensure_seeded(db)
    finally:
        db.close()
