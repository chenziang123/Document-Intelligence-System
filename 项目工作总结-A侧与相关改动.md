# 项目工作总结（工作流编排与周边）

本文档汇总本次在 **Document-Intelligence-System** 上与工作流编排、文档库及运行相关的实现与问题解决，便于交付与接续开发。（对应分工中同学 A 侧任务及部分联调问题。）

---

## 一、前端：工作流编排

### 1. 任务①｜节点配置面板

**目标：** 选中节点后可在右侧配置参数，对齐《工作流编排-待办与用例》中「节点配置」方向。

**主要改动文件：**

- `extended-frontend/src/stores/workflowStore.js`  
  - 新增 Schema 与左侧组件库条目：实体提取、数据处理、数据清洗、表格提取、数据汇总、保存 Excel、保存文本等。  
  - 强化「格式转换」节点（目标格式、转换选项等）。  
  - `addNode` / `addNodeAt` 时为部分节点写入默认 `configValues`，避免面板空白。  
- `extended-frontend/src/components/workflow/WorkflowConfig.vue`  
  - 字段可见性：`conditionField` + `dependsOn` + `arrayIncludes`（如清洗规则多选后显示日期/数字相关表单项）。  
  - 新增 `type: 'static'` 说明文案。  
  - 执行按钮动词映射扩展。  

### 2. 任务②｜从组件库拖入画布

**目标：** 从组件库拖到画布指定位置落点，并与 Pinia 中的 `canvasNodes` 一致。

**主要改动：**

- `workflowStore.js`：`addNodeAt(toolboxItem, x, y)`，按水平落点插入数组以兼顾连线顺序。  
- `WorkflowSidebar.vue`：组件项 `dragstart` 写入 `application/x-workflow-node` / `text/plain`；`+` 仍为末尾添加；组件库搜索过滤。  
- `WorkflowCanvas.vue`：`canvas-area` 上 `dragenter` / `dragover` / `drop` 解析载荷并调用 `addNodeAt`。  
- `extended-frontend/src/styles/main.css`：拖拽经过画布时高亮 `.canvas-area--drop-target`。  

### 3. 画布连线视觉

**问题：** 原二次贝塞尔控制点与端点共线，退化为僵硬水平线。

**改动：** `WorkflowCanvas.vue` 中 `buildConnectionPath`：  
- 纵向差小：直线；  
- 纵向差明显：正交折线；  
- 其余：三次贝塞尔平滑。  
`main.css` 中为 `.conn-path` 增加 `stroke-linecap` / `stroke-linejoin: round`。  

### 4. 执行顺序（Pipeline 顺序）

**问题：** 仅拖动节点不改变 `canvasNodes` 数组顺序，与执行/连线不一致。

**改动：**  

- `workflowStore.js`：`moveNodeEarlier` / `moveNodeLater`。  
- `WorkflowConfig.vue`：「执行顺序」前移/后移与步骤提示。  
- `WorkflowCanvas.vue`：节点标题栏 ◀ / ▶（多节点时）。  
- `main.css`：`.node-seq-actions` / `.node-seq-btn` 等样式。  

### 5. 文档库页面告警修复

**问题：** `LibraryView.vue` 使用未定义的 `searchInput`。

**改动：** 改为绑定 `libraryStore.searchQuery` + `clearSearch()`，消除 Vue 告警。  

### 6. 文档库列表与左侧数量一致

**问题：** `loadSpaces` 后仍使用旧的 `docsCache`，工作流入库后出现「左侧数字变了、网格未更新」。

**改动：** `libraryStore.js` 中 `loadSpaces` 成功后清空 `docsCache` 并对当前空间 `loadDocs(..., true)` 强制刷新。  

---

## 二、后端：工作流与文档库

### 1. 工作流输出写入文档库

**问题：**  
- 未选目标库或 DB 不可用时缺少明确日志；失败仍可能误报「已保存到文档库」。  
- 多输出节点时始终取第一个 `output` 节点，可能拿不到「输出文件（文档库）」配置。

**改动文件：** `src/api/routers/workflows.py`

- `_get_output_config`：优先 `schema-library-output`。  
- 任务开始：「文档库」模式但未选 `targetSpaceId`、或未启用/未配置数据库时写入 **warn**。  
- `_save_output_to_library`：  
  - 返回 `(成功, 错误信息)`；  
  - 入库前校验文件存在；  
  - **`user_id` 使用 `document_spaces` 的所属用户**（避免已登录列表带 `user_id` 条件时看不到 `user_id` 为空的记录）；  
  - 本地文件路径统一到 `Path(config.work_dir) / "library" / space_id`；  
- 仅在真正入库成功时记录「已保存到文档库」；失败写入 **error**。  

### 2. PDF 依赖

**问题：** 工作流输出 PDF 报错 `No module named 'reportlab'`。

**改动：** `requirements.txt` 增加 `reportlab>=4.0.0`（需在可访问 PyPI 或镜像的环境下 `pip install`）。  

---

## 三、运行与运维文档

已存在 **`运行说明.md`**（项目根目录）：后端虚拟环境、`uvicorn`、前端 `npm run dev`、`.env` 与停止方式等。**数据库**需自行配置：`DB_ENABLED` + `DATABASE_URL`（或 `DB_*`），并执行 **`python scripts/migrate_and_validate_db.py --apply`** 建表。  

---

## 四、使用与验收提示

| 能力 | 建议自测要点 |
|------|----------------|
| 节点配置 | 选中各类型节点，参数与联动是否正常；保存工作流后再打开是否保留 |
| 拖拽加节点 | 从左侧拖到画布、`+` 添加、执行顺序前移/后移 |
| 输出 PDF | 已安装 `reportlab` |
| 输出到文档库 | `.env` 数据库可用 + 迁移已执行；输出节点必选目标空间；入库记录 `user_id` 与空间一致 |
| 文档库列表 | `loadSpaces` 后网格与左侧数量一致 |

---

## 五、未完成 / 交由他人（参考分工）

以下仍属原《分工》或其它同学职责示例，本文档所列改动**不宣称**已实现：

- 节点执行逻辑全链路（B）、批处理（B）、执行进度服务端与深度联调（A 展示侧 + B）。  
- 所有新前端 Schema 在后端处理器中的逐项落地与校验。  

---

*文档根据会话内实现整理；若你与队友另有线下提交，可自行补充条目与日期。*
