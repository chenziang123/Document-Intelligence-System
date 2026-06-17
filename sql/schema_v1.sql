-- =============================================================================
-- 识墨文坊 · 数据库 DDL（基线）
-- 目标: PostgreSQL 14+ / Supabase
-- 契约: docs/contracts/integration-contract-v1.md
-- 执行: psql "$DATABASE_URL" -f sql/schema_v1.sql
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 用户与认证会话
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    display_name    TEXT,
    status          TEXT NOT NULL DEFAULT 'active',
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT users_status_check CHECK (status IN ('active', 'disabled', 'locked'))
);

CREATE INDEX IF NOT EXISTS idx_users_phone ON users (phone);
CREATE INDEX IF NOT EXISTS idx_users_status ON users (status);
CREATE INDEX IF NOT EXISTS idx_users_updated_at ON users (updated_at DESC);

CREATE TABLE IF NOT EXISTS auth_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL UNIQUE,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    user_agent      TEXT,
    ip_address      TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions (expires_at);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_revoked_at ON auth_sessions (revoked_at);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_last_used_at ON auth_sessions (last_used_at DESC);

-- ---------------------------------------------------------------------------
-- 对话会话 / 消息（应用前端）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(64) UNIQUE NOT NULL,
    title VARCHAR(255) NOT NULL DEFAULT '新会话',
    current_mode VARCHAR(50) NOT NULL DEFAULT 'default_conversation',
    user_id UUID REFERENCES users (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_session_id ON sessions(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user_updated_at ON sessions (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users (id) ON DELETE SET NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages (user_id);
CREATE INDEX IF NOT EXISTS idx_messages_session_created_at ON messages (session_id, created_at);

-- ---------------------------------------------------------------------------
-- 编排任务
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         TEXT NOT NULL UNIQUE,
    task_type       TEXT NOT NULL DEFAULT 'unknown',
    status          TEXT NOT NULL DEFAULT 'queued',
    error_code      TEXT,
    error_message   TEXT,
    parent_task_id  UUID REFERENCES tasks (id) ON DELETE SET NULL,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    user_id         UUID REFERENCES users (id) ON DELETE SET NULL,
    session_id      VARCHAR(64),
    source_mode     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    CONSTRAINT tasks_status_check CHECK (
        status IN (
            'queued',
            'running',
            'succeeded',
            'failed',
            'review',
            'cancelled'
        )
    )
);

COMMENT ON TABLE tasks IS '编排任务主表，状态机与契约第 2 节一致';
COMMENT ON COLUMN tasks.task_id IS '业务层 task_id，与抽取 JSON 中 task_id 对齐';
COMMENT ON COLUMN tasks.error_code IS '失败时填写，见契约第 3 节统一错误码';

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks (parent_task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks (user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_session_id ON tasks (session_id);

-- ---------------------------------------------------------------------------
-- 任务步骤
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS task_steps (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_uuid    UUID NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
    step_name    TEXT NOT NULL,
    step_order   INT NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'queued',
    detail       JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_code   TEXT,
    error_message TEXT,
    started_at   TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT task_steps_status_check CHECK (
        status IN ('queued', 'running', 'succeeded', 'failed', 'skipped')
    )
);

COMMENT ON TABLE task_steps IS '单任务内多步骤追踪，便于链路审计';

CREATE INDEX IF NOT EXISTS idx_task_steps_task ON task_steps (task_uuid);
CREATE INDEX IF NOT EXISTS idx_task_steps_name ON task_steps (step_name);

-- ---------------------------------------------------------------------------
-- 文档资产元数据
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_assets (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_uuid    UUID REFERENCES tasks (id) ON DELETE CASCADE,
    role         TEXT NOT NULL DEFAULT 'source',
    storage_key  TEXT,
    local_path   TEXT,
    file_name    TEXT,
    file_hash    TEXT,
    mime_type    TEXT,
    byte_size    BIGINT,
    page_count   INT,
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
    user_id      UUID REFERENCES users (id) ON DELETE SET NULL,
    session_id   VARCHAR(64),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT document_assets_role_check CHECK (
        role IN ('source', 'template', 'output', 'aux')
    )
);

COMMENT ON TABLE document_assets IS '文档元数据；storage_key 与 Supabase Storage 等对齐';

CREATE INDEX IF NOT EXISTS idx_document_assets_task ON document_assets (task_uuid);
CREATE INDEX IF NOT EXISTS idx_document_assets_user_id ON document_assets (user_id);
CREATE INDEX IF NOT EXISTS idx_document_assets_session_id ON document_assets (session_id);

-- ---------------------------------------------------------------------------
-- 抽取结果（JSONB + 版本）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS extraction_results (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_uuid        UUID NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
    schema_version   TEXT NOT NULL,
    payload          JSONB NOT NULL,
    result_version   INT NOT NULL DEFAULT 1,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT extraction_results_version_unique UNIQUE (task_uuid, result_version)
);

COMMENT ON TABLE extraction_results IS '抽取管线输出；payload 为完整 ExtractionResult JSON';
COMMENT ON COLUMN extraction_results.result_version IS '同任务多次抽取递增';

CREATE INDEX IF NOT EXISTS idx_extraction_task ON extraction_results (task_uuid);
CREATE INDEX IF NOT EXISTS idx_extraction_payload_gin ON extraction_results USING gin (payload jsonb_path_ops);

-- ---------------------------------------------------------------------------
-- 代理执行日志
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_execution_logs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_uuid     UUID NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
    logged_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    action        TEXT NOT NULL,
    summary       TEXT NOT NULL,
    ops_count     INT,
    rollback_id   TEXT,
    detail_ref    TEXT,
    extras        JSONB NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE agent_execution_logs IS '文档编辑/操作日志，契约「执行日志」一节';

CREATE INDEX IF NOT EXISTS idx_agent_exec_task ON agent_execution_logs (task_uuid);
CREATE INDEX IF NOT EXISTS idx_agent_exec_logged_at ON agent_execution_logs (logged_at DESC);

-- ---------------------------------------------------------------------------
-- 填表报告
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fill_reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_uuid       UUID NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
    schema_version  TEXT NOT NULL,
    template_id     TEXT,
    output_file     JSONB NOT NULL,
    filled_fields   JSONB NOT NULL DEFAULT '[]'::jsonb,
    skipped_fields  JSONB NOT NULL DEFAULT '[]'::jsonb,
    warnings        JSONB NOT NULL DEFAULT '[]'::jsonb,
    errors          JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE fill_reports IS '填表质检报告，契约「填表报告」一节';
COMMENT ON COLUMN fill_reports.output_file IS '含 storage_key / file_name / mime_type 或 local_path';

CREATE INDEX IF NOT EXISTS idx_fill_reports_task ON fill_reports (task_uuid);

-- ---------------------------------------------------------------------------
-- 审计日志
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor         TEXT,
    subject_type  TEXT NOT NULL,
    subject_id    TEXT NOT NULL,
    event         TEXT NOT NULL,
    payload       JSONB NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE audit_logs IS '通用审计：任务状态变更、人工复核、敏感操作等';

CREATE INDEX IF NOT EXISTS idx_audit_occurred ON audit_logs (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_subject ON audit_logs (subject_type, subject_id);

-- ---------------------------------------------------------------------------
-- 会话侧上传文件
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS session_files (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users (id) ON DELETE SET NULL,
    file_name VARCHAR(255) NOT NULL,
    file_type VARCHAR(20) NOT NULL CHECK (file_type IN ('data', 'template', 'generated')),
    file_path VARCHAR(1024) NOT NULL,
    file_size BIGINT NOT NULL DEFAULT 0,
    is_selected BOOLEAN NOT NULL DEFAULT FALSE,
    source TEXT NOT NULL DEFAULT 'upload',
    role TEXT NOT NULL DEFAULT 'source',
    task_uuid UUID REFERENCES tasks (id) ON DELETE SET NULL,
    origin_file_id INTEGER,
    storage_key TEXT,
    mime_type TEXT,
    file_hash TEXT,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_session_files_session_id ON session_files (session_id);
CREATE INDEX IF NOT EXISTS idx_session_files_file_type ON session_files (file_type);
CREATE INDEX IF NOT EXISTS idx_session_files_user_id ON session_files (user_id);
CREATE INDEX IF NOT EXISTS idx_session_files_session_created_at ON session_files (session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_files_task_uuid ON session_files (task_uuid);
CREATE INDEX IF NOT EXISTS idx_session_files_deleted_at ON session_files (deleted_at);
CREATE INDEX IF NOT EXISTS idx_session_files_source ON session_files (source);

-- ---------------------------------------------------------------------------
-- 文档库（空间 + 文档）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_spaces (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT,
    name            TEXT NOT NULL,
    icon            TEXT NOT NULL DEFAULT '📁',
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_doc_spaces_user ON document_spaces (user_id);
CREATE INDEX IF NOT EXISTS idx_doc_spaces_created ON document_spaces (created_at DESC);

CREATE TABLE IF NOT EXISTS library_documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    space_id        UUID NOT NULL REFERENCES document_spaces (id) ON DELETE CASCADE,
    user_id         TEXT,
    file_name       TEXT NOT NULL,
    file_size       BIGINT NOT NULL DEFAULT 0,
    mime_type       TEXT,
    file_extension  TEXT,
    storage_key     TEXT,
    blob_url        TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_library_docs_space ON library_documents (space_id);
CREATE INDEX IF NOT EXISTS idx_library_docs_user ON library_documents (user_id);
CREATE INDEX IF NOT EXISTS idx_library_docs_created ON library_documents (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_library_docs_deleted ON library_documents (deleted_at);

COMMIT;

-- =============================================================================
-- 可选：更新 updated_at 的触发器（应用层也可自行维护 tasks.updated_at）
-- =============================================================================
-- CREATE OR REPLACE FUNCTION set_updated_at()
-- RETURNS TRIGGER AS $$
-- BEGIN
--   NEW.updated_at = now();
--   RETURN NEW;
-- END;
-- $$ LANGUAGE plpgsql;
-- CREATE TRIGGER tr_tasks_updated_at
--   BEFORE UPDATE ON tasks
--   FOR EACH ROW EXECUTE FUNCTION set_updated_at();
