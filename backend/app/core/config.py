from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/allgonggo"
    SYNC_DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/allgonggo"
    ENVIRONMENT: str = "development"
    # 쉼표로 구분된 허용 오리진 목록 (Railway 환경변수로 주입)
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
