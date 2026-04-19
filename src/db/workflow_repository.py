"""
工作流数据库持久化层
用户自定义工作流（custom）存 PostgreSQL，模板（template）仍从代码内置。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from psycopg.rows import dict_row

from config import SystemConfig, get_config
from db.connection import db_connection, is_database_configured
from utils.logger import get_logger

logger = get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 公共检查
# ---------------------------------------------------------------------------


def is_db_enabled(config: Optional[SystemConfig] = None) -> bool:
    cfg = config or get_config()
    return cfg.database.enabled and is_database_configured(cfg)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def db_list_workflows(config: Optional[SystemConfig] = None) -> List[Dict[str, Any]]:
    """
    获取所有用户自定义工作流摘要（不含完整 nodes），按更新时间倒序。
    """
    cfg = config or get_config()
    if not is_db_enabled(cfg):
        return []

    try:
        with db_connection(cfg) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT workflow_id, name, icon, type,
                           created_at, updated_at
                    FROM   user_workflows
                    WHERE  type = 'custom'
                    ORDER BY updated_at DESC
                    """,
                )
                rows = cur.fetchall()
                return [
                    {
                        "id": str(r["workflow_id"]),
                        "name": r["name"],
                        "icon": r["icon"],
                        "type": r["type"],
                        "created_at": r["created_at"].isoformat() if r["created_at"] else "",
                        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else "",
                    }
                    for r in rows
                ]
    except Exception as e:
        logger.error(f"[workflow_repo] db_list_workflows error: {e}")
        return []


def db_get_workflow(workflow_id: str, config: Optional[SystemConfig] = None) -> Optional[Dict[str, Any]]:
    """
    获取指定工作流的完整配置（含 nodes、config）。
    """
    cfg = config or get_config()
    if not is_db_enabled(cfg):
        return None

    try:
        with db_connection(cfg) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT workflow_id, name, icon, type, nodes, config,
                           created_at, updated_at
                    FROM   user_workflows
                    WHERE  workflow_id = %s AND type = 'custom'
                    """,
                    (workflow_id,),
                )
                r = cur.fetchone()
                if not r:
                    return None
                return {
                    "id": str(r["workflow_id"]),
                    "name": r["name"],
                    "icon": r["icon"],
                    "type": r["type"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else "",
                    "updated_at": r["updated_at"].isoformat() if r["updated_at"] else "",
                    "nodes": r["nodes"] if isinstance(r["nodes"], list) else json.loads(r["nodes"] or "[]"),
                    "config": r["config"] if isinstance(r["config"], dict) else json.loads(r["config"] or "{}"),
                }
    except Exception as e:
        logger.error(f"[workflow_repo] db_get_workflow({workflow_id}) error: {e}")
        return None


def db_save_workflow(
    workflow_id: str,
    name: str,
    icon: str = "🔧",
    nodes: Optional[List[Dict[str, Any]]] = None,
    config_data: Optional[Dict[str, Any]] = None,
    config: Optional[SystemConfig] = None,
) -> Dict[str, Any]:
    """
    新建或更新用户工作流。

    新建时 INSERT，返回 created_at。
    更新时 UPDATE，保留 created_at，更新 updated_at。
    """
    cfg = config or get_config()
    if not is_db_enabled(cfg):
        raise RuntimeError("数据库未启用，无法保存工作流")

    now = _utc_now()
    nodes_json = json.dumps(nodes or [], ensure_ascii=False)
    config_json = json.dumps(config_data or {}, ensure_ascii=False)

    with db_connection(cfg) as conn:
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                # 先查是否存在
                cur.execute(
                    "SELECT created_at FROM user_workflows WHERE workflow_id = %s",
                    (workflow_id,),
                )
                existing = cur.fetchone()
                created_at = existing["created_at"] if existing else now

            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO user_workflows
                        (workflow_id, name, icon, type, nodes, config, created_at, updated_at)
                    VALUES (%s, %s, %s, 'custom', %s, %s, %s, %s)
                    ON CONFLICT (workflow_id)
                    DO UPDATE SET
                        name       = EXCLUDED.name,
                        icon       = EXCLUDED.icon,
                        nodes      = EXCLUDED.nodes,
                        config     = EXCLUDED.config,
                        updated_at = EXCLUDED.updated_at
                    RETURNING workflow_id, name, icon, type, nodes, config, created_at, updated_at
                    """,
                    (workflow_id, name, icon, nodes_json, config_json, created_at, now),
                )
                r = cur.fetchone()
                logger.info(f"[workflow_repo] 工作流已保存: {workflow_id} ({name})")
                return {
                    "id": str(r["workflow_id"]),
                    "name": r["name"],
                    "icon": r["icon"],
                    "type": r["type"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else "",
                    "updated_at": r["updated_at"].isoformat() if r["updated_at"] else "",
                    "nodes": r["nodes"] if isinstance(r["nodes"], list) else json.loads(r["nodes"] or "[]"),
                    "config": r["config"] if isinstance(r["config"], dict) else json.loads(r["config"] or "{}"),
                }


def db_delete_workflow(workflow_id: str, config: Optional[SystemConfig] = None) -> bool:
    """
    删除指定工作流，返回 True 成功，False 不存在。
    """
    cfg = config or get_config()
    if not is_db_enabled(cfg):
        return False

    try:
        with db_connection(cfg) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM user_workflows WHERE workflow_id = %s AND type = 'custom'",
                    (workflow_id,),
                )
                deleted = cur.rowcount > 0
                if deleted:
                    logger.info(f"[workflow_repo] 工作流已删除: {workflow_id}")
                return deleted
    except Exception as e:
        logger.error(f"[workflow_repo] db_delete_workflow({workflow_id}) error: {e}")
        return False
