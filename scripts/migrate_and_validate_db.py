"""执行 `sql/schema_v1_mysql.sql` 并校验表结构（可选写读冒烟）。

用法：
  python scripts/migrate_and_validate_db.py --check-only
  python scripts/migrate_and_validate_db.py --apply --with-seed-check
"""
from __future__ import annotations

import argparse
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Tuple
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pymysql

from config import load_config
from db.connection import build_conninfo, db_connection, health_check, is_database_configured
from db.mysql_compat import Json, build_mysql_kwargs

MIGRATION_FILES = [
    ROOT / "sql" / "schema_v1_mysql.sql",
]

REQUIRED_TABLES = [
    "users",
    "auth_sessions",
    "sessions",
    "messages",
    "session_files",
    "tasks",
    "task_steps",
    "document_assets",
    "extraction_results",
    "agent_execution_logs",
    "fill_reports",
    "audit_logs",
    "document_spaces",
    "library_documents",
    "user_workflows",
    "workflow_executions",
]

REQUIRED_COLUMNS = {
    "sessions": ["user_id"],
    "messages": ["user_id"],
    "session_files": [
        "user_id",
        "source",
        "role",
        "task_uuid",
        "origin_file_id",
        "storage_key",
        "mime_type",
        "file_hash",
        "deleted_at",
    ],
    "tasks": ["user_id", "session_id", "source_mode"],
    "library_documents": ["space_id", "user_id"],
}


def _mask_conninfo(conninfo: str) -> str:
    if "://" in conninfo and "@" in conninfo:
        try:
            scheme, rest = conninfo.split("://", 1)
            auth, tail = rest.split("@", 1)
            if ":" in auth:
                user, _ = auth.split(":", 1)
                return f"{scheme}://{user}:***@{tail}"
        except Exception:
            return conninfo
    return conninfo


def _split_sql_statements(sql: str) -> List[str]:
    statements: List[str] = []
    buffer: List[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buffer.append(line)
        if stripped.endswith(";"):
            statement = "\n".join(buffer).strip()
            if statement:
                statements.append(statement[:-1].strip())
            buffer = []
    if buffer:
        tail = "\n".join(buffer).strip()
        if tail:
            statements.append(tail.rstrip(";"))
    return statements


def _read_sql(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"SQL 文件不存在: {path}")
    return path.read_text(encoding="utf-8")


def ensure_database_exists() -> None:
    cfg = load_config()
    kwargs = build_mysql_kwargs(cfg)
    database = kwargs.pop("database")
    conn = pymysql.connect(**kwargs)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
        print(f"[INFO] 数据库已就绪: {database}")
    finally:
        conn.close()


def apply_migrations() -> None:
    ensure_database_exists()
    cfg = load_config()
    for migration in MIGRATION_FILES:
        sql = _read_sql(migration)
        statements = _split_sql_statements(sql)
        print(f"[APPLY] {migration.name} ({len(statements)} statements)")
        with db_connection(cfg) as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    for statement in statements:
                        try:
                            cur.execute(statement)
                        except Exception as exc:
                            message = str(exc).lower()
                            if "duplicate key name" in message or "already exists" in message:
                                continue
                            raise


def validate_schema() -> List[str]:
    cfg = load_config()
    errors: List[str] = []
    with db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                """
            )
            existing_tables = {row[0] for row in cur.fetchall()}

            for table in REQUIRED_TABLES:
                if table not in existing_tables:
                    errors.append(f"缺少表: {table}")

            for table, columns in REQUIRED_COLUMNS.items():
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = DATABASE() AND table_name = %s
                    """,
                    (table,),
                )
                existing_columns = {row[0] for row in cur.fetchall()}
                for column in columns:
                    if column not in existing_columns:
                        errors.append(f"缺少列: {table}.{column}")

    return errors


def run_seed_check() -> Tuple[bool, str]:
    """在事务中做最小写读校验，最后回滚。"""
    cfg = load_config()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=1)
    user_id = str(uuid.uuid4())
    with db_connection(cfg) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        """
                        INSERT INTO users (id, phone, password_hash, display_name)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (user_id, "13900000000", "pbkdf2_sha256$1$dummy$dummy", "seed-check"),
                    )

                    cur.execute(
                        """
                        INSERT INTO sessions (session_id, title, current_mode, user_id)
                        VALUES (%s, %s, %s, %s)
                        """,
                        ("seed-check-session", "seed-check", "default_conversation", user_id),
                    )
                    session_pk = cur.lastrowid

                    cur.execute(
                        """
                        INSERT INTO messages (session_id, user_id, role, content, metadata)
                        VALUES (%s, %s, 'user', 'seed-check', %s)
                        """,
                        (session_pk, user_id, Json({})),
                    )

                    cur.execute(
                        """
                        INSERT INTO auth_sessions (id, user_id, token_hash, expires_at, metadata)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (str(uuid.uuid4()), user_id, "seed-check-token-hash", expires, Json({})),
                    )
                except Exception as exc:
                    conn._raw.rollback()
                    return False, str(exc)
            conn._raw.rollback()
    return True, "seed-check 通过（事务内回滚）"


def main() -> int:
    parser = argparse.ArgumentParser(description="应用 MySQL 基线 DDL 并校验数据库结构")
    parser.add_argument("--apply", action="store_true", help="执行 sql/schema_v1_mysql.sql")
    parser.add_argument("--check-only", action="store_true", help="仅校验结构，不执行 SQL")
    parser.add_argument("--with-seed-check", action="store_true", help="执行最小写读校验（事务内回滚）")
    args = parser.parse_args()

    cfg = load_config()
    if not cfg.database.enabled:
        print("[ERROR] DB_ENABLED 未开启")
        return 2
    if not is_database_configured(cfg):
        print("[ERROR] 数据库连接信息不完整")
        return 2

    conninfo = build_conninfo(cfg)
    print("[INFO] conninfo:", _mask_conninfo(conninfo))

    if args.apply and not args.check_only:
        try:
            ensure_database_exists()
        except Exception as exc:
            print("[ERROR] 无法创建/连接数据库:", exc)
            return 2

    ok, msg = health_check(cfg)
    if not ok:
        print("[ERROR] 数据库不可用:", msg)
        return 2
    print("[INFO] 数据库连通正常")

    if args.apply and not args.check_only:
        apply_migrations()
        print("[INFO] SQL 执行完成")

    schema_errors = validate_schema()
    if schema_errors:
        print("[ERROR] 结构校验失败:")
        for item in schema_errors:
            print(" -", item)
        return 1
    print("[INFO] 结构校验通过")

    if args.with_seed_check:
        seed_ok, seed_msg = run_seed_check()
        if not seed_ok:
            print("[ERROR] seed-check 失败:", seed_msg)
            return 1
        print("[INFO]", seed_msg)

    print("[DONE] 流程完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
