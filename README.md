# 文档智能系统

个人项目：文档解析与理解、工作流编排、大模型调用与 PostgreSQL 持久化的一体化实现。

## 运行方式

前端：

```text
cd extended-frontend
npm install
npm run dev
```

后端：

```text
cd src
python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8001
```

## 阿里云 OSS（可选）

在根目录 `.env` 中配置（勿提交密钥），示例见 `.env.example`：

- `STORAGE_PROVIDER=aliyun_oss`
- `STORAGE_ENABLED=true`
- `OSS_ENDPOINT=https://oss-cn-shanghai.aliyuncs.com`（按 Bucket 地域调整）
- `OSS_ACCESS_KEY_ID`、`OSS_ACCESS_KEY_SECRET`、`OSS_BUCKET`
- `OSS_PREFIX=sessions`（对象键前缀，可选）

依赖：`pip install -r requirements.txt`（已包含 `oss2`）。
