-- =============================================================================
-- 识墨文坊 · 数据库 DDL（MySQL / MariaDB）
-- 目标: MySQL 8.0+ / MariaDB 10.4+（XAMPP）
-- 执行: python scripts/migrate_and_validate_db.py --apply
-- =============================================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ---------------------------------------------------------------------------
-- 用户与认证会话
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id              CHAR(36) PRIMARY KEY,
    phone           VARCHAR(32) NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    display_name    VARCHAR(255),
    status          VARCHAR(32) NOT NULL DEFAULT 'active',
    last_login_at   DATETIME(6),
    created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT users_status_check CHECK (status IN ('active', 'disabled', 'locked'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_users_phone ON users (phone);
CREATE INDEX idx_users_status ON users (status);
CREATE INDEX idx_users_updated_at ON users (updated_at DESC);

CREATE TABLE IF NOT EXISTS auth_sessions (
    id              CHAR(36) PRIMARY KEY,
    user_id         CHAR(36) NOT NULL,
    token_hash      VARCHAR(255) NOT NULL UNIQUE,
    expires_at      DATETIME(6) NOT NULL,
    revoked_at      DATETIME(6),
    user_agent      TEXT,
    ip_address      VARCHAR(64),
    metadata        JSON NOT NULL,
    created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    last_used_at    DATETIME(6),
    CONSTRAINT fk_auth_sessions_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_auth_sessions_user_id ON auth_sessions (user_id);
CREATE INDEX idx_auth_sessions_expires_at ON auth_sessions (expires_at);
CREATE INDEX idx_auth_sessions_revoked_at ON auth_sessions (revoked_at);
CREATE INDEX idx_auth_sessions_last_used_at ON auth_sessions (last_used_at DESC);

-- ---------------------------------------------------------------------------
-- 对话会话 / 消息
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL UNIQUE,
    title VARCHAR(255) NOT NULL DEFAULT '新会话',
    current_mode VARCHAR(50) NOT NULL DEFAULT 'default_conversation',
    user_id CHAR(36),
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_sessions_session_id ON sessions(session_id);
CREATE INDEX idx_sessions_updated_at ON sessions(updated_at DESC);
CREATE INDEX idx_sessions_user_id ON sessions (user_id);
CREATE INDEX idx_sessions_user_updated_at ON sessions (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    user_id CHAR(36),
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    metadata JSON,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT messages_role_check CHECK (role IN ('user', 'assistant', 'system')),
    CONSTRAINT fk_messages_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    CONSTRAINT fk_messages_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_messages_session_id ON messages(session_id);
CREATE INDEX idx_messages_created_at ON messages(created_at);
CREATE INDEX idx_messages_user_id ON messages (user_id);
CREATE INDEX idx_messages_session_created_at ON messages (session_id, created_at);

-- ---------------------------------------------------------------------------
-- 编排任务
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    id              CHAR(36) PRIMARY KEY,
    task_id         VARCHAR(255) NOT NULL UNIQUE,
    task_type       VARCHAR(64) NOT NULL DEFAULT 'unknown',
    status          VARCHAR(32) NOT NULL DEFAULT 'queued',
    error_code      VARCHAR(64),
    error_message   TEXT,
    parent_task_id  CHAR(36),
    metadata        JSON NOT NULL,
    user_id         CHAR(36),
    session_id      VARCHAR(64),
    source_mode     VARCHAR(64),
    created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    started_at      DATETIME(6),
    completed_at    DATETIME(6),
    CONSTRAINT tasks_status_check CHECK (
        status IN ('queued', 'running', 'succeeded', 'failed', 'review', 'cancelled')
    ),
    CONSTRAINT fk_tasks_parent FOREIGN KEY (parent_task_id) REFERENCES tasks (id) ON DELETE SET NULL,
    CONSTRAINT fk_tasks_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_tasks_status ON tasks (status);
CREATE INDEX idx_tasks_created_at ON tasks (created_at DESC);
CREATE INDEX idx_tasks_parent ON tasks (parent_task_id);
CREATE INDEX idx_tasks_user_id ON tasks (user_id);
CREATE INDEX idx_tasks_session_id ON tasks (session_id);

CREATE TABLE IF NOT EXISTS task_steps (
    id           CHAR(36) PRIMARY KEY,
    task_uuid    CHAR(36) NOT NULL,
    step_name    VARCHAR(255) NOT NULL,
    step_order   INT NOT NULL DEFAULT 0,
    status       VARCHAR(32) NOT NULL DEFAULT 'queued',
    detail       JSON NOT NULL,
    error_code   VARCHAR(64),
    error_message TEXT,
    started_at   DATETIME(6),
    completed_at DATETIME(6),
    created_at   DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT task_steps_status_check CHECK (
        status IN ('queued', 'running', 'succeeded', 'failed', 'skipped')
    ),
    CONSTRAINT fk_task_steps_task FOREIGN KEY (task_uuid) REFERENCES tasks (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_task_steps_task ON task_steps (task_uuid);
CREATE INDEX idx_task_steps_name ON task_steps (step_name);

CREATE TABLE IF NOT EXISTS document_assets (
    id           CHAR(36) PRIMARY KEY,
    task_uuid    CHAR(36),
    role         VARCHAR(32) NOT NULL DEFAULT 'source',
    storage_key  TEXT,
    local_path   TEXT,
    file_name    VARCHAR(512),
    file_hash    VARCHAR(128),
    mime_type    VARCHAR(128),
    byte_size    BIGINT,
    page_count   INT,
    metadata     JSON NOT NULL,
    user_id      CHAR(36),
    session_id   VARCHAR(64),
    created_at   DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT document_assets_role_check CHECK (
        role IN ('source', 'template', 'output', 'aux')
    ),
    CONSTRAINT fk_document_assets_task FOREIGN KEY (task_uuid) REFERENCES tasks (id) ON DELETE CASCADE,
    CONSTRAINT fk_document_assets_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_document_assets_task ON document_assets (task_uuid);
CREATE INDEX idx_document_assets_user_id ON document_assets (user_id);
CREATE INDEX idx_document_assets_session_id ON document_assets (session_id);

CREATE TABLE IF NOT EXISTS extraction_results (
    id               CHAR(36) PRIMARY KEY,
    task_uuid        CHAR(36) NOT NULL,
    schema_version   VARCHAR(64) NOT NULL,
    payload          JSON NOT NULL,
    result_version   INT NOT NULL DEFAULT 1,
    created_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT extraction_results_version_unique UNIQUE (task_uuid, result_version),
    CONSTRAINT fk_extraction_results_task FOREIGN KEY (task_uuid) REFERENCES tasks (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_extraction_task ON extraction_results (task_uuid);

CREATE TABLE IF NOT EXISTS agent_execution_logs (
    id            CHAR(36) PRIMARY KEY,
    task_uuid     CHAR(36) NOT NULL,
    logged_at     DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    action        VARCHAR(128) NOT NULL,
    summary       TEXT NOT NULL,
    ops_count     INT,
    rollback_id   VARCHAR(128),
    detail_ref    TEXT,
    extras        JSON NOT NULL,
    CONSTRAINT fk_agent_exec_task FOREIGN KEY (task_uuid) REFERENCES tasks (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_agent_exec_task ON agent_execution_logs (task_uuid);
CREATE INDEX idx_agent_exec_logged_at ON agent_execution_logs (logged_at DESC);

CREATE TABLE IF NOT EXISTS fill_reports (
    id              CHAR(36) PRIMARY KEY,
    task_uuid       CHAR(36) NOT NULL,
    schema_version  VARCHAR(64) NOT NULL,
    template_id     VARCHAR(128),
    output_file     JSON NOT NULL,
    filled_fields   JSON NOT NULL,
    skipped_fields  JSON NOT NULL,
    warnings        JSON NOT NULL,
    errors          JSON NOT NULL,
    created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_fill_reports_task FOREIGN KEY (task_uuid) REFERENCES tasks (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_fill_reports_task ON fill_reports (task_uuid);

CREATE TABLE IF NOT EXISTS audit_logs (
    id            CHAR(36) PRIMARY KEY,
    occurred_at   DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    actor         VARCHAR(128),
    subject_type  VARCHAR(64) NOT NULL,
    subject_id    VARCHAR(255) NOT NULL,
    event         VARCHAR(128) NOT NULL,
    payload       JSON NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_audit_occurred ON audit_logs (occurred_at DESC);
CREATE INDEX idx_audit_subject ON audit_logs (subject_type, subject_id);

CREATE TABLE IF NOT EXISTS session_files (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    user_id CHAR(36),
    file_name VARCHAR(255) NOT NULL,
    file_type VARCHAR(20) NOT NULL,
    file_path VARCHAR(1024) NOT NULL,
    file_size BIGINT NOT NULL DEFAULT 0,
    is_selected TINYINT(1) NOT NULL DEFAULT 0,
    source VARCHAR(32) NOT NULL DEFAULT 'upload',
    role VARCHAR(32) NOT NULL DEFAULT 'source',
    task_uuid CHAR(36),
    origin_file_id INT,
    storage_key TEXT,
    mime_type VARCHAR(128),
    file_hash VARCHAR(128),
    deleted_at DATETIME(6),
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT session_files_file_type_check CHECK (file_type IN ('data', 'template', 'generated')),
    CONSTRAINT fk_session_files_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    CONSTRAINT fk_session_files_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL,
    CONSTRAINT fk_session_files_task FOREIGN KEY (task_uuid) REFERENCES tasks (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_session_files_session_id ON session_files (session_id);
CREATE INDEX idx_session_files_file_type ON session_files (file_type);
CREATE INDEX idx_session_files_user_id ON session_files (user_id);
CREATE INDEX idx_session_files_session_created_at ON session_files (session_id, created_at DESC);
CREATE INDEX idx_session_files_task_uuid ON session_files (task_uuid);
CREATE INDEX idx_session_files_deleted_at ON session_files (deleted_at);
CREATE INDEX idx_session_files_source ON session_files (source);

CREATE TABLE IF NOT EXISTS document_spaces (
    id              CHAR(36) PRIMARY KEY,
    user_id         VARCHAR(64),
    name            VARCHAR(255) NOT NULL,
    icon            VARCHAR(32) NOT NULL DEFAULT '📁',
    description     TEXT,
    created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_doc_spaces_user ON document_spaces (user_id);
CREATE INDEX idx_doc_spaces_created ON document_spaces (created_at DESC);

CREATE TABLE IF NOT EXISTS library_documents (
    id              CHAR(36) PRIMARY KEY,
    space_id        CHAR(36) NOT NULL,
    user_id         VARCHAR(64),
    file_name       VARCHAR(512) NOT NULL,
    file_size       BIGINT NOT NULL DEFAULT 0,
    mime_type       VARCHAR(128),
    file_extension  VARCHAR(32),
    storage_key     TEXT,
    blob_url        TEXT,
    created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    deleted_at      DATETIME(6),
    CONSTRAINT fk_library_docs_space FOREIGN KEY (space_id) REFERENCES document_spaces (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_library_docs_space ON library_documents (space_id);
CREATE INDEX idx_library_docs_user ON library_documents (user_id);
CREATE INDEX idx_library_docs_created ON library_documents (created_at DESC);
CREATE INDEX idx_library_docs_deleted ON library_documents (deleted_at);

-- ---------------------------------------------------------------------------
-- 工作流（运行时也会 ensure，这里一并建表）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_workflows (
    workflow_id VARCHAR(64) PRIMARY KEY,
    name        VARCHAR(255) NOT NULL DEFAULT '未命名',
    icon        VARCHAR(32)  NOT NULL DEFAULT '🔧',
    type        VARCHAR(16)  NOT NULL DEFAULT 'custom',
    nodes       JSON         NOT NULL,
    config      JSON         NOT NULL,
    created_at  DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at  DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_user_workflows_updated ON user_workflows(updated_at DESC);
CREATE INDEX idx_user_workflows_type ON user_workflows(type);

CREATE TABLE IF NOT EXISTS workflow_executions (
    execution_id        VARCHAR(64) PRIMARY KEY,
    status              VARCHAR(32) NOT NULL DEFAULT 'running',
    error_code          VARCHAR(64),
    progress            INT         NOT NULL DEFAULT 0,
    current_file_index  INT         NOT NULL DEFAULT 0,
    total_files         INT         NOT NULL DEFAULT 0,
    current_file_name   TEXT        NOT NULL,
    logs                JSON        NOT NULL,
    output_files        JSON        NOT NULL,
    error               TEXT,
    created_at          DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at          DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_workflow_exec_updated ON workflow_executions(updated_at DESC);
CREATE INDEX idx_workflow_exec_status ON workflow_executions(status);

SET FOREIGN_KEY_CHECKS = 1;
