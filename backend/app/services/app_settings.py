from sqlalchemy.orm import Session

from app.config import settings as env_settings
from app.models import AppSettings


class SettingsStore:
    _cache: AppSettings | None = None

    @classmethod
    def get(cls, db: Session) -> AppSettings:
        row = db.query(AppSettings).filter(AppSettings.id == 1).first()
        if not row:
            row = cls.seed(db)
        cls._cache = row
        return row

    @classmethod
    def cached(cls) -> AppSettings:
        if cls._cache is None:
            from app.database import SessionLocal

            db = SessionLocal()
            try:
                return cls.get(db)
            finally:
                db.close()
        return cls._cache

    @classmethod
    def invalidate(cls):
        cls._cache = None

    @classmethod
    def seed(cls, db: Session) -> AppSettings:
        row = AppSettings(
            id=1,
            comicvine_api_key=env_settings.comicvine_api_key,
            kapowarr_url=env_settings.kapowarr_url,
            kapowarr_api_key=env_settings.kapowarr_api_key,
            kapowarr_root_folder_id=env_settings.kapowarr_root_folder_id,
            komga_url=env_settings.komga_url,
            komga_api_key=env_settings.komga_api_key,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        cls._cache = row
        return row

    @classmethod
    def ensure_seeded(cls, db: Session):
        existing = db.query(AppSettings).filter(AppSettings.id == 1).first()
        if not existing:
            cls.seed(db)
        else:
            cls._cache = existing

    @classmethod
    def update(cls, db: Session, **fields) -> AppSettings:
        row = cls.get(db)
        for key, value in fields.items():
            if value is not None:
                setattr(row, key, value)
        db.commit()
        db.refresh(row)
        cls._cache = row
        return row
