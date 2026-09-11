from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    data_dir: str = "/config"
    default_poll_interval_seconds: int = 300
    http_timeout_seconds: float = 10.0
    app_secret_key: str | None = None
    auth_username: str | None = None
    auth_password: str | None = None
    log_level: str = "INFO"
    port: int = 8080
    public_dashboard_enabled: bool = True
    public_port: int = 8090

    model_config = {"env_prefix": "HC_"}

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def db_path(self) -> Path:
        return self.data_path / "healthchecker.db"

    @property
    def secret_key_path(self) -> Path:
        return self.data_path / "secret.key"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path.as_posix()}"


settings = Settings()
