from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    comicvine_api_key: str = ""
    kapowarr_url: str = "http://localhost:5656"
    kapowarr_api_key: str = ""
    kapowarr_root_folder_id: int = 1
    komga_url: str = "http://localhost:25600"
    komga_api_key: str = ""
    data_dir: str = "/data"
    database_url: str = ""

    def model_post_init(self, __context) -> None:
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        if not self.database_url:
            db_path = Path(self.data_dir) / "app.db"
            self.database_url = f"sqlite:///{db_path.as_posix()}"

    @property
    def exports_dir(self) -> Path:
        path = Path(self.data_dir) / "exports"
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
