# 识墨文坊

文档库 + 智能对话 + 可视化工作流的 Web 系统。

## 环境要求

- Python 3.10 ~ 3.12（安装时勾选 Add to PATH）
- Node.js 18+
- MySQL（推荐 XAMPP，默认用户 `root`、密码为空）

---

## 首次运行（只需一次）

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
```

其中 `DATABASE_URL` 格式为 `mysql://用户名:密码@主机:端口/库名`，各段含义如下：

| 段 | 默认值 | 说明 |
|----|--------|------|
| 用户名 | `root` | XAMPP 默认管理员账号 |
| 密码 | （空） | XAMPP 默认无密码，故 `root:` 后留空 |
| 主机 | `localhost` | 本机 MySQL |
| 端口 | `3306` | MySQL 默认端口 |
| 库名 | `doc_intel` | 项目数据库，**第 5 步迁移时会自动创建** |

使用 XAMPP 且 MySQL 仍为默认账号（用户 `root`、无密码、端口 `3306`）时，**`.env` 里的 `DATABASE_URL` 不用改**。若需修改：

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

**终端 A — 后端**（需先激活虚拟环境，提示符前应出现 `(.venv)`）

```powershell
cd <项目根目录>
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "src"
cd src
python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8001
```

**终端 B — 前端**（不需要虚拟环境）

```powershell
cd <项目根目录>\extended-frontend
npm run dev
```

浏览器打开 **http://127.0.0.1:5174**，注册账号后即可使用。

自检：http://127.0.0.1:8001/health 应返回正常 JSON。

> 若启动后 PDF 报错缺少 `reportlab`，说明 `python` 仍指向系统环境。请在终端 A 改用完整路径：  
> `..\.venv\Scripts\python.exe -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8001`（工作目录仍为 `src`）

---

## 日常启动（之后每次）

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

---

## 常见问题

- **ECONNREFUSED**：后端未启动。先确认终端 A 里 uvicorn 在跑，再访问 http://127.0.0.1:8001/health。
- **端口被占用**（报错含 `Address already in use` 或 `only one usage of each socket`）：
  - 后端默认 **8001**，前端默认 **5174**
  - 先关掉之前没关的后端/前端终端窗口，再重新启动
  - 若仍报错，在 PowerShell 查占用进程并结束（把 `8001` 换成实际端口）：

```powershell
netstat -ano | findstr :8001
taskkill /PID <上一步最后一列的 PID> /F
```

- **缺少 reportlab**：后端未在虚拟环境中运行。先 `Activate.ps1`，或改用 `.venv\Scripts\python.exe` 启动（见第 7 步说明）。
- **AI 无响应**：检查 `.env` 里 `DEEPSEEK_API_KEY` 是否填写，改后重启后端。
