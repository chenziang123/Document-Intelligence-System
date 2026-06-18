# 识墨文坊

文档库 + 智能对话 + 可视化工作流的 Web 系统。

---

## 老师 / 评审快速上手

| 方式 | 适用场景 | 怎么做 |
|------|----------|--------|
| **线上访问** | 远程体验、无需安装环境 | 浏览器打开 **http://20.205.19.180** → 注册账号即可 |
| **本地运行** | 本机答辩演示、查看源码 | 按下方「本地首次运行」→「本地日常启动」 |

**线上地址说明：** 若打不开，可能是演示服务器已关机，请联系项目维护同学启动后再访问。

**功能入口：** 登录后左侧导航可进入 **文档库**、**智能对话**、**工作流编排**。

---

## 环境要求（仅本地运行需要）

- Python 3.10 ~ 3.12（安装时勾选 Add to PATH）
- Node.js 18+
- MySQL（推荐 XAMPP，默认用户 `root`、密码为空）

---

## 本地首次运行（只需一次）

### 1. 进入项目目录

```powershell
cd <项目根目录>
# 例：cd D:\Document-Intelligence-System
```

### 2. 创建并激活 Python 虚拟环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

若无法执行 Activate，先运行：`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### 3. 安装 Python 依赖

```powershell
pip install -r requirements.txt
```

### 4. 配置环境变量

```powershell
copy .env.example .env
```

用记事本打开 `.env`，至少填写以下三项：

```ini
DEEPSEEK_API_KEY=你的密钥
DB_ENABLED=true
DATABASE_URL=mysql://root:@localhost:3306/doc_intel
AUTH_SECRET_KEY=任意随机字符串
```

其中 `DATABASE_URL` 格式为 `mysql://用户名:密码@主机:端口/库名`：

| 段 | 默认值 | 说明 |
|----|--------|------|
| 用户名 | `root` | XAMPP 默认管理员账号 |
| 密码 | （空） | XAMPP 默认无密码，故 `root:` 后留空 |
| 主机 | `localhost` | 本机 MySQL |
| 端口 | `3306` | MySQL 默认端口 |
| 库名 | `doc_intel` | 项目数据库，**第 5 步迁移时会自动创建** |

使用 XAMPP 且 MySQL 仍为默认账号时，**`DATABASE_URL` 一般不用改**。若需修改：

- **root 有密码**：`DATABASE_URL=mysql://root:你的密码@localhost:3306/doc_intel`
- **端口不是 3306**：将 URL 中的 `3306` 改为实际端口

### 5. 启动 MySQL 并初始化数据库

1. 打开 XAMPP，启动 **MySQL**
2. 在项目根目录、已激活 `(.venv)` 的终端执行：

```powershell
python scripts\migrate_and_validate_db.py --apply
```

看到 `数据库已就绪` 即成功。

### 6. 安装前端依赖

```powershell
cd extended-frontend
npm install
cd ..
```

### 7. 首次启动并验证

**终端 A — 后端**（提示符前应出现 `(.venv)`）

```powershell
cd <项目根目录>
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "src"
cd src
python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8001
```

**终端 B — 前端**

```powershell
cd <项目根目录>\extended-frontend
npm run dev
```

浏览器打开 **http://127.0.0.1:5174**，注册账号后即可使用。

自检：http://127.0.0.1:8001/health 应返回 `database_ok: true`。

> 若 PDF 报错缺少 `reportlab`，说明未使用虚拟环境。终端 A 改用：  
> `..\.venv\Scripts\python.exe -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8001`（工作目录仍为 `src`）

---

## 本地日常启动（之后每次）

1. 打开 XAMPP，启动 **MySQL**
2. 开两个 PowerShell：

**终端 A — 后端**

```powershell
cd <项目根目录>
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "src"
cd src
python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8001
```

**终端 B — 前端**

```powershell
cd <项目根目录>\extended-frontend
npm run dev
```

浏览器访问 http://127.0.0.1:5174

更短的备忘见项目根目录 `二次.md`（若已克隆）。

---

## 智能对话模式说明

| 模式 | 用途 | 附件要求 |
|------|------|----------|
| 默认对话 | 通用问答 | 可选 |
| 文档理解 | 阅读并回答文档内容 | 数据文件（pdf/docx/txt/md） |
| 文档编辑 | 按指令修改 Word 等 | 数据文件，**仅 docx/md/txt/xlsx** |
| 提取与填表 | 从文档抽字段或 Excel 筛数填表 | 数据文件 + **xlsx 模板**（docx 提取时模板必传） |

**提取与填表** 需上传 **xlsx 模板**（第 1 行为列名），模板放在「模板文件」区，源文档放在「数据文件」区。

---

## 常见问题

- **ECONNREFUSED / 前端连不上**：后端未启动。先确认终端 A 里 uvicorn 在跑，再访问 http://127.0.0.1:8001/health。
- **端口被占用**：后端默认 **8001**，前端 **5174**。关掉旧终端后重试；或 `netstat -ano | findstr :8001` → `taskkill /PID <PID> /F`。
- **缺少 reportlab**：后端未在虚拟环境中运行，见上文「首次启动」备用命令。
- **AI 无响应**：检查 `.env` 里 `DEEPSEEK_API_KEY`，改后重启后端。
- **工作流「文档路径未找到」**：文档库记录存在但文件已删，删除后重新上传即可。
- **提取与填表无结果**：确认已上传 xlsx 模板；从 Word 提取时模板为必填。
- **线上地址打不开**：演示服务器可能已关机，请联系维护同学。

---

## 源码

https://github.com/chenziang123/Document-Intelligence-System
