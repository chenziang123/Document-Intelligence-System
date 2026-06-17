"""PyMySQL 兼容层，提供与 psycopg 相近的连接 / 游标 API。"""
from __future__ import annotations

import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple, Union
from urllib.parse import unquote, urlparse

import pymysql
from dbutils.pooled_db import PooledDB
from pymysql.cursors import DictCursor

dict_row = DictCursor


class Json:
    """将 dict/list 序列化为 JSON 字符串供 MySQL JSON 列使用。"""

    def __init__(self, obj: Any):
        self.obj = obj

    def __str__(self) -> str:
        return json.dumps(self.obj, ensure_ascii=False)


def parse_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        stripped = value.strip()
        # 仅解析 JSON 对象/数组，避免把昵称 "111" 误转成 int
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value
    return value


def normalize_datetime(value: Any) -> Any:
    """MySQL DATETIME 无时区，统一视为 UTC 以便与代码内 aware datetime 比较。"""
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def normalize_row_value(value: Any) -> Any:
    return normalize_datetime(parse_json_value(value))


def _prepare_params(params: Optional[Union[Sequence[Any], Dict[str, Any]]]) -> Optional[Union[Tuple[Any, ...], Dict[str, Any]]]:
    if params is None:
        return None
    if isinstance(params, dict):
        return {k: (str(v) if isinstance(v, Json) else v) for k, v in params.items()}

    prepared = []
    for item in params:
        if isinstance(item, Json):
            prepared.append(str(item))
        else:
            prepared.append(item)
    return tuple(prepared)


_CAST_RE = re.compile(
    r"::(?:uuid|jsonb|text|bigint|int)\b",
    re.IGNORECASE,
)


def adapt_sql(sql: str) -> str:
    """将常见 PostgreSQL 方言转换为 MySQL 可执行 SQL。"""
    adapted = _CAST_RE.sub("", sql)
    adapted = re.sub(
        r"ON CONFLICT \(([^)]+)\)\s+DO UPDATE SET",
        r"ON DUPLICATE KEY UPDATE",
        adapted,
        flags=re.IGNORECASE,
    )
    adapted = re.sub(r"\bEXCLUDED\.(\w+)", r"VALUES(\1)", adapted, flags=re.IGNORECASE)
    adapted = adapted.replace("FALSE", "0").replace("false", "0")
    adapted = re.sub(r"\bnow\(\)", "NOW()", adapted, flags=re.IGNORECASE)
    adapted = re.sub(
        r"ADD COLUMN IF NOT EXISTS (\w+)",
        r"ADD COLUMN \1",
        adapted,
        flags=re.IGNORECASE,
    )
    return adapted


_RETURNING_RE = re.compile(r"\bRETURNING\b", re.IGNORECASE)


class MySQLCursor:
    def __init__(self, conn: pymysql.connections.Connection, row_factory=None):
        self._conn = conn
        self._row_factory = row_factory
        self._cursor = conn.cursor(DictCursor if row_factory else pymysql.cursors.Cursor)
        self.rowcount = 0
        self.lastrowid = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def execute(self, sql: str, params: Optional[Union[Sequence[Any], Dict[str, Any]]] = None):
        sql = adapt_sql(sql)
        prepared = _prepare_params(params)

        if _RETURNING_RE.search(sql):
            return self._execute_with_returning(sql, prepared)

        self._cursor.execute(sql, prepared)
        self.rowcount = self._cursor.rowcount
        self.lastrowid = self._cursor.lastrowid
        return self

    def _execute_with_returning(self, sql: str, params):
        match = _RETURNING_RE.search(sql)
        base_sql = sql[: match.start()].strip()
        returning_cols = sql[match.end() :].strip()

        self._cursor.execute(base_sql, params)
        self.rowcount = self._cursor.rowcount
        self.lastrowid = self._cursor.lastrowid

        select_sql, select_params = self._build_followup_select(base_sql, returning_cols, params)
        if not select_sql:
            return self

        self._cursor.execute(select_sql, select_params)
        return self

    def _build_followup_select(self, base_sql: str, returning_cols: str, params) -> Tuple[Optional[str], Tuple[Any, ...]]:
        upper = base_sql.upper()

        if upper.startswith("INSERT INTO"):
            table_match = re.search(r"INSERT\s+INTO\s+(\w+)", base_sql, re.IGNORECASE)
            if not table_match:
                return None, ()
            table = table_match.group(1)

            cols_match = re.search(r"\(([^)]+)\)\s*VALUES", base_sql, re.IGNORECASE | re.DOTALL)
            if cols_match and params:
                cols = [c.strip() for c in cols_match.group(1).split(",")]
                if "id" in cols:
                    idx = cols.index("id")
                    if isinstance(params, tuple) and idx < len(params):
                        return (
                            f"SELECT {returning_cols} FROM {table} WHERE id = %s",
                            (params[idx],),
                        )

            if self.lastrowid:
                return (
                    f"SELECT {returning_cols} FROM {table} WHERE id = %s",
                    (self.lastrowid,),
                )

            if isinstance(params, tuple) and params:
                if table == "sessions":
                    return (
                        f"SELECT {returning_cols} FROM {table} WHERE session_id = %s",
                        (params[0],),
                    )
                if table == "users":
                    return (
                        f"SELECT {returning_cols} FROM {table} WHERE phone = %s",
                        (params[0],),
                    )
                if table == "auth_sessions":
                    return (
                        f"SELECT {returning_cols} FROM {table} WHERE token_hash = %s",
                        (params[1] if len(params) > 1 else params[0],),
                    )
                if table == "user_workflows":
                    return (
                        f"SELECT {returning_cols} FROM {table} WHERE workflow_id = %s",
                        (params[0],),
                    )

        if upper.startswith("UPDATE"):
            table_match = re.search(r"UPDATE\s+(\w+)", base_sql, re.IGNORECASE)
            where_match = re.search(r"\bWHERE\b(.+)$", base_sql, re.IGNORECASE | re.DOTALL)
            if table_match and where_match and params:
                table = table_match.group(1)
                where_clause = where_match.group(1).strip()
                where_param_count = where_clause.count("%s")
                if isinstance(params, tuple) and where_param_count:
                    where_params = params[-where_param_count:]
                    return (
                        f"SELECT {returning_cols} FROM {table} WHERE {where_clause}",
                        where_params,
                    )

        return None, ()

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        if isinstance(row, dict):
            return {k: normalize_row_value(v) for k, v in row.items()}
        return row

    def fetchall(self):
        rows = self._cursor.fetchall()
        if not rows:
            return []
        if isinstance(rows[0], dict):
            return [{k: normalize_row_value(v) for k, v in row.items()} for row in rows]
        return rows

    def close(self):
        self._cursor.close()


class TransactionContext:
    def __init__(self, conn: "MySQLConnection"):
        self._conn = conn

    def __enter__(self):
        self._conn._raw.begin()
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self._conn._raw.rollback()
        else:
            self._conn._raw.commit()
        return False


class MySQLConnection:
    def __init__(self, raw_conn: pymysql.connections.Connection):
        self._raw = raw_conn

    def transaction(self):
        return TransactionContext(self)

    def cursor(self, row_factory=None):
        return MySQLCursor(self._raw, row_factory=row_factory)

    def close(self):
        self._raw.close()


def build_mysql_kwargs(config) -> Dict[str, Any]:
    db = config.database
    if db.url:
        parsed = urlparse(db.url)
        database = parsed.path.lstrip("/") or db.database
        return {
            "host": parsed.hostname or db.host,
            "port": parsed.port or db.port,
            "user": unquote(parsed.username or db.username or ""),
            "password": unquote(parsed.password or db.password or ""),
            "database": database,
            "charset": "utf8mb4",
            "cursorclass": pymysql.cursors.Cursor,
            "autocommit": False,
            "connect_timeout": 10,
            "read_timeout": 30,
            "write_timeout": 30,
        }

    return {
        "host": db.host,
        "port": db.port,
        "user": db.username,
        "password": db.password,
        "database": db.database,
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.Cursor,
        "autocommit": False,
        "connect_timeout": 10,
        "read_timeout": 30,
        "write_timeout": 30,
    }


_pool: Optional[PooledDB] = None


def create_pool(config) -> PooledDB:
    kwargs = build_mysql_kwargs(config)
    max_conn = max(2, config.database.pool_max_size)
    return PooledDB(
        creator=pymysql,
        maxconnections=max_conn,
        mincached=1,
        maxcached=max_conn,
        blocking=True,
        maxusage=0,
        ping=1,
        **kwargs,
    )


def get_raw_connection(pool: PooledDB) -> pymysql.connections.Connection:
    return pool.connection()


@contextmanager
def pooled_connection(pool: PooledDB):
    raw = get_raw_connection(pool)
    try:
        yield MySQLConnection(raw)
    finally:
        try:
            raw.rollback()
        except Exception:
            pass
        raw.close()
