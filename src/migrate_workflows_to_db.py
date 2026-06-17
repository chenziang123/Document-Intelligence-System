"""
一次性迁移脚本：将 JSON 文件中的工作流迁移到 MySQL 数据库。
执行一次即可。
"""
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

from config import load_config, set_config

set_config(load_config())
from db.connection import db_connection, is_database_configured
from db.workflow_repository import _ensure_workflow_tables, is_db_enabled


def _migrate_json(conn, json_path: Path):
    if not json_path.exists():
        print("[迁移] JSON 文件不存在，跳过迁移")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        print("[迁移] JSON 数据格式异常，跳过")
        return

    count = 0
    for wf_id, wf in data.items():
        nodes_json = json.dumps(wf.get("nodes") or [], ensure_ascii=False)
        config_json = json.dumps(wf.get("config") or {}, ensure_ascii=False)
        created_at = wf.get("created_at")
        updated_at = wf.get("updated_at")

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_workflows
                    (workflow_id, name, icon, type, nodes, config, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()), COALESCE(%s, NOW()))
                ON DUPLICATE KEY UPDATE workflow_id = workflow_id
                """,
                (
                    wf_id,
                    wf.get("name", "未命名"),
                    wf.get("icon", "🔧"),
                    wf.get("type", "custom"),
                    nodes_json,
                    config_json,
                    created_at,
                    updated_at,
                ),
            )
            if cur.rowcount > 0:
                count += 1
    print(f"[迁移] 从 JSON 迁移了 {count} 条工作流到数据库")


def _verify(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM user_workflows")
        total = cur.fetchone()[0]
        cur.execute("SELECT workflow_id, name FROM user_workflows ORDER BY updated_at DESC LIMIT 5")
        rows = cur.fetchall()
    print(f"[验证] 数据库中共有 {total} 条工作流")
    for r in rows:
        print(f"  - {r[0]}: {r[1]}")


def main():
    from config import get_config

    cfg = get_config()

    print(f"数据库启用状态: {is_db_enabled(cfg)}")
    print(f"数据库: {cfg.database.database}")

    if not is_database_configured(cfg):
        print("[错误] 数据库未配置，请检查 .env 中的 DB_ENABLED 和连接信息")
        sys.exit(1)

    with db_connection(cfg) as conn:
        with conn.transaction():
            _ensure_workflow_tables(conn)
            print("[迁移] 表 user_workflows 已就绪")
            json_path = _ROOT / "workspace" / "workflows" / "user_workflows.json"
            _migrate_json(conn, json_path)
            _verify(conn)

    print("[完成] 迁移成功！")


if __name__ == "__main__":
    main()
