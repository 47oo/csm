"""应用配置（环境变量）。

F012 只引入运行所需的配置项：运行环境与数据库连接。不引入认证 / 缓存 /
消息队列等未要求的基础设施配置。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["dev", "test", "prod"]


class Settings(BaseSettings):
    """从环境变量（前缀 ``CSM_``）读取的应用配置。"""

    model_config = SettingsConfigDict(
        env_prefix="CSM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Environment = "dev"

    # SQLAlchemy URL，驱动为 psycopg 3（postgresql+psycopg://）。
    database_url: str = "postgresql+psycopg://csm:csm@localhost:5432/csm"

    # 连接池配置。
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_echo: bool = False

    @property
    def foundation_enabled(self) -> bool:
        """非产品自检面 ``/_foundation/*`` 是否挂载。

        REQUIRED：生产配置下必须不可达。仅 dev / test 挂载。
        """
        return self.environment in ("dev", "test")


@lru_cache
def get_settings() -> Settings:
    return Settings()
