"""
MySQL 连接

使用方式：
  from db.connection import db_connection, health_check, build_conninfo

需在 .env 中设置 DB_ENABLED=true，并提供 DATABASE_URL（推荐）或 DB_HOST 等分段变量。
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator, Optional, Tuple
from urllib.parse import urlparse, unquote

import pymysql

from config import SystemConfig, get_config
from db.mysql_compat import MySQLConnection, build_mysql_kwargs

_pool = None


def _mask_conninfo(url: str) -> str:
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme or "mysql"
        host = parsed.hostname or "localhost"
        port = parsed.port or 3306
        user = unquote(parsed.username or "")
        database = (parsed.path or "").lstrip("/") or "doc_intel"
        return f"{scheme}://{user}:***@{host}:{port}/{database}"
    except Exception:
        return url


def build_conninfo(config: Optional[SystemConfig] = None) -> str:
    """生成可打印的连接信息（脱敏用）。"""
    cfg = (config or get_config()).database
    if cfg.url:
        return _mask_conninfo(cfg.url)
    return f"mysql://{cfg.username}:***@{cfg.host}:{cfg.port}/{cfg.database}"


def is_database_configured(config: Optional[SystemConfig] = None) -> bool:
    """数据库已启用且具备最小连接信息。"""
    cfg = (config or get_config()).database
    if not cfg.enabled:
        return False
    if cfg.url:
        return True
    return bool(cfg.host and cfg.database and cfg.username)


def get_pool(config: Optional[SystemConfig] = None):
    """兼容旧调用；本地开发改为每次直连，不再使用连接池。"""
    return None


def reset_pool() -> None:
    """兼容旧调用。"""
    global _pool
    _pool = None


@contextmanager
def db_connection(config: Optional[SystemConfig] = None) -> Generator:
    """每次请求建立一条 MySQL 连接，用完即关（避免连接池耗尽）。"""
    cfg = config or get_config()
    raw = pymysql.connect(**build_mysql_kwargs(cfg))
    try:
        yield MySQLConnection(raw)
    finally:
        try:
            raw.rollback()
        except Exception:
            pass
        raw.close()


def health_check(config: Optional[SystemConfig] = None) -> Tuple[bool, str]:
    """检查数据库是否可达。"""
    cfg = (config or get_config()).database
    if not cfg.enabled:
        return False, "数据库未启用（DB_ENABLED!=true）"
    if not is_database_configured(config):
        return False, "缺少 DATABASE_URL 或 DB_HOST/DB_NAME/DB_USER 等配置"
    try:
        with db_connection(config) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True, "连接正常"
    except Exception as e:
        return False, str(e)
