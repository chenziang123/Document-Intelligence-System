# 工作流编排 · A → B 交接说明

> **约定**：小组决定**不再做任务⑤**（节点级执行进度的前后端联调展示）。本文档供 B 接手时了解 A 已交付内容、数据结构及 B 侧待办。  
> **文档日期**：以仓库当前实现为准，若代码有变请以 Git 为准。

---

## 一、A 已完成工作（给 B 看的摘要）

### 1. 节点配置面板（分工 ①）

- **位置**：右侧 `WorkflowConfig.vue` + `workflowStore.js` 中 `nodeSchemas`、`toolboxItems`。  
- **行为**：点击画布节点 → 右侧展示对应参数；支持 `conditionField`、`dependsOn`、`arrayIncludes`、`static` 说明文案。  
- **保存**：工作流保存 / 执行时，每个节点带 `schemaKey` 与 **`configValues`**（见下文「数据结构」）。  
- **对齐《待办》的补充**：在原有节点之外，新增 **7 个**节点的 Schema 与组件库入口（见第三节表）；**格式转换**为原节点 **增强**配置项。

### 2. 组件库 → 画布拖拽（分工 ②）

- **拖拽**：左侧组件库条目拖到中间画布落点 → 调用 `addNodeAt`，坐标落在 `canvas-inner` 内；落点水平位置会插入 `canvasNodes` 以兼顾连线顺序。  
- **`+` 按钮**：仍在列表末尾追加节点（`addNode`）。  
- **执行顺序**：前移/后移（`moveNodeEarlier` / `moveNodeLater`），在配置面板与节点卡片 **◀ ▶** 可操作；**仅改数组顺序**，与画布 `x/y` 无关。

### 3. 其它与编排相关的前端改动（便于 B 排障）

- **连线**：`WorkflowCanvas` 中路径由正交/三次贝塞尔生成，避免原先退化直线。  
- **文档库**：`LibraryView` 搜索绑定 `libraryStore.searchQuery`；`loadSpaces` 后清文档缓存并强制 `loadDocs`，避免「左侧数量与列表不一致」。  
- **不涉及**：任务⑤ 按节点展示进度 — **已决定不做**，后端若仍只有整次 `execution` 日志也无碍当前范围。

### 4. A **不负责**也 **未实现**的部分（避免误会）

- **`workflows_processors.py` 中对新增 7 个 `schemaKey` 的处理**：当前 **无**分支，执行时多为 **原文透传**。  
- **节点级进度 API / SSE**：未接；与任务⑤一并搁置。  
- **`docs/workflow-api-contract.md`**：仓库中若不存在或未更新，以实际 `POST /api/workflows/execute` 与 `nodes[].configValues` 为准。

---

## 二、数据结构（B 执行与校验时重点看）

### 1. 前端 → 执行接口

- 请求体含 **`nodes`**：`{ id, type, title, schemaKey, configValues }[]`（详见 `workflowStore.executeWorkflow`）。  
- **`configValues`**：纯 JSON 可序列化字段；具体 key 由各 `schemaKey` 的 `fields` 决定。

### 2. 后端当前入口

- **`src/api/routers/workflows.py`**：调度、输出配置、文档库入库（含 `targetSpaceId`、`_get_output_config` 优先 `schema-library-output`）、`user_id` 与空间主人对齐等。  
- **`src/api/routers/workflows_processors.py`**：`_process_node(content, …)` 按 **`schemaKey`** 分发；**未列出的 key 不会变换内容**。

### 3. 流水线输出文件

- **`src/core/orchestrator/executor.py`**：当前工作流产物格式白名单大致为 **`md` / `txt` / `pdf`**；**xlsx 等需 B 扩展** 若产品要「保存 Excel」真实落盘。

---

## 三、A 新增的 7 个节点（`schemaKey` 一览）

B 若要实现「按配置真跑」，需在 **`_process_node`**（及必要的表格/Excel 流水线）中 **逐 key 接入**：

| 界面名称 | `schemaKey` | 备注 |
|----------|-------------|------|
| 实体提取 | `schema-entity-extraction` | `entityFieldList`、`customEntityTypes`、`aliasMap`、`prompt` 等 |
| 数据处理 | `schema-data-process` | `processKind` 及各类依赖字段（排序/筛选/汇总…） |
| 数据清洗 | `schema-data-clean` | `cleanRules` 多选及日期/数字附加项 |
| 表格提取 | `schema-table-extract` | `tableStrategy`、`tableIndex`、`hasHeader` 等 |
| 数据汇总 | `schema-data-rollup` | `rollupDims`、`rollupMetrics`、`prompt` |
| 保存 Excel | `schema-save-excel` | `savePath`、`sheetName` 等 — **需与 executor 输出形态对齐** |
| 保存文本 | `schema-save-text` | 编码、换行、路径等 — **与现有 txt/md 分支协调** |

**格式转换**仍为 `schema-convert-format`，后端已有处理函数，A 侧扩展了表单项，B 可按需加深对 `configValues` 的消费。

---

## 四、B 建议承担的工作（交接清单）

### 必做 / 核心（对应分工 ③）

1. **执行链路**：按 `canvasNodes` **顺序**执行；输入节点 → 各处理节点 → 输出节点；中间产物在内存或临时文件中传递（与现有 `TaskExecutor.execute_workflow_pipeline` 一致或可重构）。  
2. **Processor 补全**：为上表 **7 个 `schemaKey`**（及你们约定的其它 key）在 **`workflows_processors.py`** 增加分支，**读取 `configValues`** 并调用现有能力（LLM、Excel、表格解析等）或新开服务。  
3. **输出节点**：`schema-save-excel` / `schema-save-text` 与 **`executor` 最终写盘格式** 对齐；避免前端选了 Excel 后端仍只写 md。  
4. **配置校验**：对非法 `configValues` 返回明确错误信息，便于前端展示（与分工「B 对配置项做校验」一致）。

### 批处理（分工 ④）

- 多文件时循环 / 任务模型与单次执行复用同一套核心；错误与结果汇总策略与《工作流编排-待办与用例》一致即可。

### 暂不做的范围（与小组决定一致）

- **任务⑤**：节点级进度 **服务端（原 B 的⑤）** 与 **前端展示** — **本次不做**；若日后恢复，再单独开文档约定字段与轮询/SSE。

### 环境与依赖

- 文档库、工作流持久化依赖 **PostgreSQL**；本地/Supabase 配好 `DB_ENABLED` 与 `DATABASE_URL` 等。  
- PDF 输出需 **`reportlab`**（已在 `requirements.txt`）。

---

## 五、联调时可快速自测

1. 前端搭一条 **PDF 输入 → AI 翻译 → 输出文件**（选 md/txt/pdf），确认整条仍通。  
2. 在 **Network** 里看 `execute` 的 `nodes[].configValues` 是否含 B 新消费字段。  
3. 加一条含 **新增节点** 的流，看日志是否进入 B 新写的分支、产物是否符合预期。

---

## 六、相关文件路径（便于 B 打开）

| 用途 | 路径 |
|------|------|
| 前端节点定义与默认配置 | `extended-frontend/src/stores/workflowStore.js` |
| 配置面板 | `extended-frontend/src/components/workflow/WorkflowConfig.vue` |
| 画布与拖拽 | `extended-frontend/src/components/workflow/WorkflowCanvas.vue`、`WorkflowSidebar.vue` |
| 执行调度与入库 | `src/api/routers/workflows.py` |
| 节点内容处理分发 | `src/api/routers/workflows_processors.py` |
| 流水线写文件 | `src/core/orchestrator/executor.py` |
| A 侧变更纪要（可选） | `项目工作总结-A侧与相关改动.md` |

---

*若 B 对齐接口时有增量字段，建议在 README 或小节「API 增量」写几行即可，无需强制恢复 `workflow-api-contract.md`。*
