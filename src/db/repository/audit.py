"""审计与 task_steps。"""
from __future__ import annotations

from typing import Any, Dict, Optional

import uuid

from db.mysql_compat import Json

from config import SystemConfig, get_config
from db.connection import db_connection

from .types import utc_now


def insert_audit_log_conn(
    conn,
    subject_type: str,
    subject_id: str,
    event: str,
    payload: Optional[Dict[str, Any]] = None,
    actor: str = "system",
) -> str:
    """在同一连接/事务内写入 audit_logs。"""
    pl = payload or {}
    log_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_logs (id, actor, subject_type, subject_id, event, payload)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (log_id, actor, subject_type, subject_id, event, Json(pl)),
        )
        return log_id


def insert_task_step(
    conn,
    task_uuid: str,
    step_name: str,
    *,
    step_order: int = 0,
    status: str = "succeeded",
    detail: Optional[Dict[str, Any]] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> str:
    """写入 task_steps。status: queued|running|succeeded|failed|skipped"""
    now = utc_now()
    if status == "running":
        started_at, completed_at = now, None
    else:
        started_at, completed_at = now, now
    step_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO task_steps (
                id, task_uuid, step_name, step_order, status, detail,
                error_code, error_message, started_at, completed_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            """,
            (
                step_id,
                task_uuid,
                step_name,
                step_order,
                status,
                Json(detail or {}),
                error_code,
                error_message,
                started_at,
                completed_at,
            ),
        )
        return step_id


def insert_audit_log(
    subject_type: str,
    subject_id: str,
    event: str,
    payload: Optional[Dict[str, Any]] = None,
    actor: Optional[str] = None,
    config: Optional[SystemConfig] = None,
) -> str:
    """独立事务写入 audit_logs。"""
    cfg = config or get_config()
    with db_connection(cfg) as conn:
        with conn.transaction():
            return insert_audit_log_conn(
                conn,
                subject_type,
                subject_id,
                event,
                payload,
                actor or "system",
            )
