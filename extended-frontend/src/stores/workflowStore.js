import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import workflowApi from '../api/workflow'

export const useWorkflowStore = defineStore('workflow', () => {
  // ==================== 状态 ====================

  const currentWorkflowId = ref(null)
  const searchQuery = ref('')
  const workflowName = ref('新建工作流')

  // 选中的文档（来自文档库或本地上传）
  const selectedDocs = ref([])
  const localFiles = ref([])       // 本地上传的文件（File 对象）

  // 当前选中的节点 ID
  const selectedNodeId = ref(null)

  // 每个节点的配置值（key: nodeId, value: { paramKey: paramValue }）
  const nodeConfigs = ref({})

  // 画布节点列表
  const canvasNodes = ref([])

  /** 画布连线（第二阶段图结构）；空数组时按节点顺序渲染链式连线 */
  const workflowEdges = ref([])

  /** 是否处于「编辑连线」模式 */
  const isEdgeEditMode = ref(false)

  const hasCustomEdges = computed(() => workflowEdges.value.length > 0)

  /** 是否处于「编辑执行顺序」模式：拖拽节点会按位置重排列表顺序 */
  const isOrderEditMode = ref(false)
  /** 是否处于「多选清除」模式：点击多选节点后批量删除 */
  const isBulkDeleteMode = ref(false)
  const bulkSelectedNodeIds = ref([])

  // 画布默认间距（仅用于新节点默认位置与「自动对齐」）
  const CANVAS_NODE_W = 240
  const CANVAS_NODE_GAP = 88
  const CANVAS_SLOT_STEP = CANVAS_NODE_W + CANVAS_NODE_GAP
  const CANVAS_BASE_X = 30
  const CANVAS_BASE_Y = 160
  const TRANSLATION_TEMPLATE_ID = 'tpl_translation'
  const FORK_PARALLEL_TEMPLATE_ID = 'tpl_fork_parallel'
  const CONDITION_BRANCH_TEMPLATE_ID = 'tpl_condition_branch'
  const LOOP_TEMPLATE_ID = 'tpl_loop'
  const BUILTIN_TEMPLATE_IDS = [
    TRANSLATION_TEMPLATE_ID,
    FORK_PARALLEL_TEMPLATE_ID,
    CONDITION_BRANCH_TEMPLATE_ID,
    LOOP_TEMPLATE_ID,
  ]

  const DEFAULT_RUN_SETTINGS = {
    concurrentLimit: 3,
    continueOnError: true,
    notifyOnError: true,
  }
  const runSettings = ref({ ...DEFAULT_RUN_SETTINGS })

  // ==================== 动态数据（从 API 加载） ====================

  const workflows = ref({})
  const templates = ref([])
  const availableModels = ref([])
  const availableLanguages = ref([])
  const outputFormats = ref([])
  const unsupportedFieldHints = ref({
    hasHeader: '暂不支持（当前自动识别表头）',
  })

  // ==================== 节点 Schema（无硬编码值，所有选项由 API 决定） ====================

  /** 旧版分格式输入节点 → 统一文档输入（兼容已保存工作流） */
  const INPUT_SCHEMA_ALIASES = {
    'schema-pdf-input': 'schema-document-input',
    'schema-md-input': 'schema-document-input',
    'schema-txt-input': 'schema-document-input',
    'schema-docx-input': 'schema-document-input',
    'schema-xlsx-input': 'schema-document-input',
  }

  function resolveSchemaKey(schemaKey) {
    return INPUT_SCHEMA_ALIASES[schemaKey] || schemaKey
  }

  const nodeSchemas = ref({
    'schema-document-input': {
      icon: '', iconClass: 'input',
      title: '文档输入', subtitle: '输入节点',
      fields: [
        { key: '_hint_input_formats', type: 'static', text: '支持 PDF、Markdown、TXT、Word (DOCX)、Excel (XLSX) 等格式；实际解析按上传文件类型自动识别。' },
        { key: 'skipExisting', label: '跳过已处理文档', type: 'toggle' },
      ]
    },
    'schema-translate': {
      icon: '', iconClass: 'ai',
      title: 'AI 翻译', subtitle: '翻译节点',
      fields: [
        { key: 'targetLanguage', label: '目标语言', type: 'language-selector' },
        { key: 'prompt', label: '翻译提示词', type: 'textarea' }
      ]
    },
    'schema-extract-summary': {
      icon: '', iconClass: 'ai',
      title: '内容提取', subtitle: '提取节点',
      fields: [
        { key: 'extractType', label: '提取类型', type: 'select',
          options: [{ value: 'summary', label: '生成摘要' }, { value: 'keypoints', label: '提取要点' }, { value: 'both', label: '摘要+要点' }] },
        { key: 'summaryLength', label: '摘要长度', type: 'select',
          options: [{ value: 'short', label: '简短' }, { value: 'medium', label: '适中' }, { value: 'detailed', label: '详细' }] },
        { key: 'prompt', label: '自定义提示词', type: 'textarea' }
      ]
    },
    'schema-extract-data': {
      icon: '', iconClass: 'ai',
      title: '数据抽取', subtitle: '抽取节点',
      fields: [
        { key: 'dataFormat', label: '输出格式', type: 'select',
          options: [{ value: 'json', label: 'JSON' }, { value: 'csv', label: 'CSV' }, { value: 'table', label: '表格' }] },
        { key: 'extractFields', label: '要提取的字段', type: 'textarea', placeholder: '例: 名称,日期,金额（逗号分隔）' },
        { key: 'prompt', label: '提取规则描述', type: 'textarea' }
      ]
    },
    'schema-analyze-content': {
      icon: '', iconClass: 'ai',
      title: '内容分析', subtitle: '分析节点',
      fields: [
        { key: 'analysisType', label: '分析类型', type: 'select',
          options: [{ value: 'keywords', label: '关键词提取' }, { value: 'entities', label: '实体识别' }, { value: 'all', label: '全面分析' }] },
        { key: 'entityTypes', label: '实体类型', type: 'select-multiple',
          options: [{ value: 'person', label: '人名' }, { value: 'location', label: '地名' }, { value: 'org', label: '机构' }, { value: 'date', label: '日期' }],
          dependsOn: { field: 'analysisType', values: ['entities', 'all'] } },
        { key: 'topK', label: '关键词数量', type: 'input', placeholder: '默认10',
          dependsOn: { field: 'analysisType', values: ['keywords', 'all'] } },
        { key: 'prompt', label: '自定义分析要求', type: 'textarea' }
      ]
    },
    'schema-enhance-text': {
      icon: '', iconClass: 'ai',
      title: '文本增强', subtitle: '增强节点',
      fields: [
        { key: 'enhanceType', label: '增强类型', type: 'select',
          options: [{ value: 'grammar', label: '语法检查' }, { value: 'polish', label: '文本润色' }, { value: 'rephrase', label: '改写' }, { value: 'all', label: '全面优化' }] },
        { key: 'style', label: '文本风格', type: 'select',
          options: [{ value: 'concise', label: '简洁' }, { value: 'formal', label: '学术' }, { value: 'casual', label: '口语' }, { value: 'professional', label: '专业' }] },
        { key: 'prompt', label: '自定义要求', type: 'textarea' }
      ]
    },
    'schema-convert-format': {
      icon: '', iconClass: 'ai',
      title: '格式转换', subtitle: '转换节点',
      fields: [
        { key: '_hint_cf', type: 'static', text: '选择目标格式及转换选项；配置将保存在节点 config 供执行端解析。' },
        { key: 'targetFormat', label: '目标格式', type: 'select',
          options: [
            { value: 'markdown', label: 'Markdown' },
            { value: 'html', label: 'HTML' },
            { value: 'plaintext', label: '纯文本' },
            { value: 'pdf', label: 'PDF' },
            { value: 'docx', label: 'Word (DOCX)' },
            { value: 'json', label: 'JSON' }
          ] },
        { key: 'conversionOptions', label: '转换选项', type: 'select-multiple',
          options: [
            { value: 'keep_layout', label: '尽量保留版面' },
            { value: 'extract_tables', label: '优先提取表格' },
            { value: 'embed_images', label: '保留内嵌图片' },
            { value: 'code_as_text', label: '代码块转纯文本' },
            { value: 'sanitize_html', label: 'HTML 安全清洗' }
          ] },
        { key: 'preserveFormatting', label: '保留原格式标记', type: 'toggle' },
        { key: 'preserveStructure', label: '保留文档结构', type: 'toggle' },
        { key: 'prompt', label: '自定义转换规则', type: 'textarea' }
      ]
    },
    'schema-split-document': {
      icon: '', iconClass: 'ai',
      title: '文档分割', subtitle: '分割节点',
      fields: [
        { key: 'splitMethod', label: '分割方式', type: 'select',
          options: [{ value: 'section', label: '按章节' }, { value: 'paragraph', label: '按段落' }, { value: 'size', label: '按大小' }, { value: 'page', label: '按页数' }] },
        { key: '_hint_split_section', type: 'static', text: '按章节/标题切分，识别「一、」「第一章」等结构。',
          dependsOn: { field: 'splitMethod', value: 'section' } },
        { key: '_hint_split_paragraph', type: 'static', text: '按空行与自然段切分，每段前会加序号。',
          dependsOn: { field: 'splitMethod', value: 'paragraph' } },
        { key: 'splitSize', type: 'input', dynamicBy: 'splitMethod',
          labelMap: { size: '每段字符数', page: '逻辑页大小' },
          placeholderMap: { size: '默认 500', page: '默认「一页」，可填：半页、800字一页' },
          hintMap: {
            size: '大约每多少字切成一段，段与段之间会插入【分割】标记。',
            page: '按逻辑页切分（非真实 PDF 页码），段间会插入【新页面】标记。'
          },
          dependsOn: { field: 'splitMethod', values: ['size', 'page'] } },
        { key: 'preserveContext', label: '保留上下文', type: 'toggle',
          hint: '开启后相邻片段会保留少量重叠内容，避免句子在分界处被截断。' },
        { key: 'prompt', label: '自定义分割规则', type: 'textarea', placeholder: '可选：用自然语言描述分段要求' }
      ]
    },
    'schema-keyword-highlight': {
      icon: '', iconClass: 'ai',
      title: '关键词高亮', subtitle: '增强节点',
      fields: [
        { key: 'topK', label: '关键词数量', type: 'input', placeholder: '默认 10' },
        { key: 'marker', label: '高亮标记符', type: 'input', placeholder: '默认 **' },
        { key: 'prompt', label: '自定义规则', type: 'textarea' }
      ]
    },
    'schema-sensitive-masking': {
      icon: '', iconClass: 'ai',
      title: '敏感信息脱敏', subtitle: '安全节点',
      fields: [
        { key: 'maskToken', label: '掩码符号', type: 'input', placeholder: '默认 *' },
        { key: 'prompt', label: '自定义脱敏规则', type: 'textarea' }
      ]
    },
    'schema-term-normalize': {
      icon: '', iconClass: 'ai',
      title: '术语统一替换', subtitle: '规范节点',
      fields: [
        { key: 'termDictionary', label: '术语词典', type: 'textarea', placeholder: '示例：A=>标准术语A; B=>标准术语B' },
        { key: 'prompt', label: '自定义规则', type: 'textarea' }
      ]
    },
    'schema-outline-generate': {
      icon: '', iconClass: 'ai',
      title: '结构化提纲生成', subtitle: '分析节点',
      fields: [
        { key: 'maxDepth', label: '最大层级', type: 'input', placeholder: '默认 3' },
        { key: 'prompt', label: '自定义规则', type: 'textarea' }
      ]
    },
    'schema-sentiment-enhanced': {
      icon: '', iconClass: 'ai',
      title: '情感倾向分析', subtitle: '分析节点',
      fields: [
        { key: 'prompt', label: '自定义分析规则', type: 'textarea' }
      ]
    },
    'schema-timeline-extract': {
      icon: '', iconClass: 'ai',
      title: '时间线抽取', subtitle: '抽取节点',
      fields: [
        { key: 'prompt', label: '自定义抽取规则', type: 'textarea' }
      ]
    },
    'schema-save': {
      icon: '', iconClass: 'output',
      title: '保存文件', subtitle: '输出节点',
      fields: [
        { key: 'savePath', label: '保存路径', type: 'input' },
        { key: 'outputFormat', label: '输出格式', type: 'format-selector' }
      ]
    },
    'schema-library-output': {
      icon: '', iconClass: 'output',
      title: '输出文件', subtitle: '输出节点',
      fields: [
        { key: 'outputMode', label: '输出模式', type: 'output-mode-select' },
        { key: 'targetSpaceId', label: '目标文档库', type: 'library-selector', conditionField: 'outputMode', conditionValue: 'library' },
        { key: 'namingRule', label: '文件命名规则', type: 'input', placeholder: '{original_file}_out' },
        { key: 'outputFormat', label: '输出格式', type: 'format-selector' },
        { key: 'sheetName', label: '工作表名称', type: 'input', placeholder: '默认 Sheet1',
          dependsOn: { field: 'outputFormat', values: ['xlsx', 'excel'] } },
        { key: 'outputEncoding', label: '文本编码', type: 'select',
          options: [{ value: 'utf-8', label: 'UTF-8' }, { value: 'gbk', label: 'GBK' }],
          dependsOn: { field: 'outputFormat', values: ['txt', 'md'] } },
        { key: 'lineEnding', label: '换行符', type: 'select',
          options: [{ value: 'lf', label: 'LF (Unix)' }, { value: 'crlf', label: 'CRLF (Windows)' }],
          dependsOn: { field: 'outputFormat', values: ['txt', 'md'] } }
      ]
    },
    // —— 以下为《工作流编排-待办与用例》「节点配置」对齐的专项 schema ——
    'schema-entity-extraction': {
      icon: '', iconClass: 'ai',
      title: '实体提取', subtitle: '实体与结构化字段',
      fields: [
        { key: '_hint_entity', type: 'static', text: '从上游文档中抽取结构化实体；字段名与类型将随工作流保存到 config。' },
        { key: 'entityFieldList', label: '提取字段列表', type: 'textarea', placeholder: '每行一个字段，或逗号分隔，例：姓名\n日期\n金额' },
        { key: 'customEntityTypes', label: '自定义实体类型', type: 'textarea', placeholder: '可选：描述需识别的自定义类型，如「合同条款」「项目阶段」' },
        { key: 'aliasMap', label: '字段别名映射', type: 'textarea', placeholder: '可选：买方=甲方; 卖方=乙方（分号或换行分隔）' },
        { key: 'prompt', label: '补充抽取规则', type: 'textarea', placeholder: '对模型或规则的额外说明' }
      ]
    },
    'schema-data-process': {
      icon: '', iconClass: 'ai',
      title: '数据处理', subtitle: '表格类操作',
      fields: [
        { key: '_hint_dp', type: 'static', text: '针对表格数据：先选择处理类型，再填写对应参数（与《节点处理》数据处理章节一致）。' },
        { key: 'processKind', label: '处理类型', type: 'select',
          options: [
            { value: 'sort', label: '排序' },
            { value: 'filter', label: '筛选' },
            { value: 'aggregate', label: '汇总' },
            { value: 'dedupe', label: '去重' },
            { value: 'fill_null', label: '填充空值' },
            { value: 'computed_column', label: '新增计算列' },
            { value: 'merge_columns', label: '合并列' },
            { value: 'split_column', label: '拆分列' }
          ] },
        { key: 'sortColumn', label: '排序列（列名）', type: 'input', placeholder: '例如：金额 或 D', dependsOn: { field: 'processKind', value: 'sort' } },
        { key: 'sortOrder', label: '升降序', type: 'select',
          options: [{ value: 'asc', label: '升序' }, { value: 'desc', label: '降序' }],
          dependsOn: { field: 'processKind', value: 'sort' } },
        { key: 'filterExpr', label: '筛选条件', type: 'textarea', placeholder: '例：列「状态」= 已完成；或简短表达式说明', dependsOn: { field: 'processKind', value: 'filter' } },
        { key: 'aggregateColumn', label: '汇总列', type: 'input', placeholder: '要汇总的列名', dependsOn: { field: 'processKind', value: 'aggregate' } },
        { key: 'aggregateOp', label: '汇总方式', type: 'select',
          options: [
            { value: 'sum', label: '求和' },
            { value: 'count', label: '计数' },
            { value: 'avg', label: '平均值' },
            { value: 'min', label: '最小' },
            { value: 'max', label: '最大' }
          ],
          dependsOn: { field: 'processKind', value: 'aggregate' } },
        { key: 'groupByColumns', label: '分组列（可选）', type: 'input', placeholder: '逗号分隔，留空表示全文一条汇总', dependsOn: { field: 'processKind', value: 'aggregate' } },
        { key: 'dedupeColumns', label: '去重依据列', type: 'input', placeholder: '逗号分隔列名，留空表示整行去重', dependsOn: { field: 'processKind', value: 'dedupe' } },
        { key: 'fillColumns', label: '填充列', type: 'input', placeholder: '要填充的列，逗号分隔', dependsOn: { field: 'processKind', value: 'fill_null' } },
        { key: 'fillValue', label: '填充值', type: 'input', placeholder: '例如：0 或 N/A', dependsOn: { field: 'processKind', value: 'fill_null' } },
        { key: 'computedFormula', label: '计算表达式', type: 'textarea', placeholder: '例：=[金额]*[数量] 或列运算说明', dependsOn: { field: 'processKind', value: 'computed_column' } },
        { key: 'computedColumnName', label: '新列名', type: 'input', placeholder: '结果写入的列标题', dependsOn: { field: 'processKind', value: 'computed_column' } },
        { key: 'mergeSourceColumns', label: '待合并列', type: 'input', placeholder: '逗号分隔', dependsOn: { field: 'processKind', value: 'merge_columns' } },
        { key: 'mergeSeparator', label: '连接符', type: 'input', placeholder: '默认空格', dependsOn: { field: 'processKind', value: 'merge_columns' } },
        { key: 'mergeTargetColumn', label: '目标列名', type: 'input', dependsOn: { field: 'processKind', value: 'merge_columns' } },
        { key: 'splitSourceColumn', label: '待拆分列', type: 'input', dependsOn: { field: 'processKind', value: 'split_column' } },
        { key: 'splitDelimiter', label: '分隔符', type: 'input', placeholder: '如：,、;、|', dependsOn: { field: 'processKind', value: 'split_column' } },
        { key: 'splitIntoColumns', label: '拆成列名', type: 'input', placeholder: '逗号分隔多列标题', dependsOn: { field: 'processKind', value: 'split_column' } },
        { key: 'prompt', label: '补充说明', type: 'textarea' }
      ]
    },
    'schema-data-clean': {
      icon: '', iconClass: 'ai',
      title: '数据清洗', subtitle: '规则与规范化',
      fields: [
        { key: '_hint_dc', type: 'static', text: '可多选下方规则；实际清洗与预览在执行阶段由服务端/执行引擎应用（可先保存配置再联调）。' },
        { key: 'cleanRules', label: '清洗规则', type: 'select-multiple',
          options: [
            { value: 'trim_spaces', label: '去除首尾空格' },
            { value: 'normalize_date', label: '统一日期格式' },
            { value: 'normalize_number', label: '统一数字格式' },
            { value: 'handle_outliers', label: '处理异常值' },
            { value: 'expand_merged_cells', label: '合并单元格展开' },
            { value: 'fix_format_errors', label: '修正格式错误' }
          ] },
        { key: 'dateFormatPattern', label: '目标日期格式', type: 'input', placeholder: '例：YYYY-MM-DD（勾选「统一日期格式」后可填）',
          dependsOn: { field: 'cleanRules', arrayIncludes: 'normalize_date' } },
        { key: 'numberDecimalPlaces', label: '小数位数', type: 'input', placeholder: '可选，如：2',
          dependsOn: { field: 'cleanRules', arrayIncludes: 'normalize_number' } },
        { key: 'prompt', label: '补充规则说明', type: 'textarea' },
        { key: '_preview_note', type: 'static', text: '「预览清洗结果」需执行流水线支持后由后端推送或轮询刷新；此处仅保存规则配置。' }
      ]
    },
    'schema-table-extract': {
      icon: '', iconClass: 'ai',
      title: '表格提取', subtitle: '从文档中抽取表格',
      fields: [
        { key: 'tableStrategy', label: '提取策略', type: 'select',
          options: [
            { value: 'first', label: '第一个表格' },
            { value: 'all', label: '全部表格' },
            { value: 'by_index', label: '按序号' }
          ] },
        { key: 'tableIndex', label: '表格序号（从 1 开始）', type: 'input', placeholder: '当策略为「按序号」',
          dependsOn: { field: 'tableStrategy', value: 'by_index' } },
        { key: 'hasHeader', label: '首行为表头', type: 'toggle' },
        { key: 'prompt', label: '补充说明', type: 'textarea' }
      ]
    },
    'schema-data-rollup': {
      icon: '', iconClass: 'ai',
      title: '数据汇总', subtitle: '统计汇总',
      fields: [
        { key: 'rollupDims', label: '分类维度（列）', type: 'textarea', placeholder: '逗号或换行分隔' },
        { key: 'rollupMetrics', label: '指标与聚合', type: 'textarea', placeholder: '例：销售额:sum; 数量:count' },
        { key: 'prompt', label: '补充说明', type: 'textarea' }
      ]
    },
    'schema-save-excel': {
      icon: '', iconClass: 'output',
      title: '保存 Excel', subtitle: '输出节点',
      fields: [
        { key: 'savePath', label: '相对路径或文件名前缀', type: 'input', placeholder: '可选' },
        { key: 'sheetName', label: '工作表名称', type: 'input', placeholder: '默认 Sheet1' },
        { key: 'prompt', label: '备注', type: 'textarea' }
      ]
    },
    'schema-save-text': {
      icon: '', iconClass: 'output',
      title: '保存文本', subtitle: '输出节点',
      fields: [
        { key: 'outputEncoding', label: '编码', type: 'select',
          options: [{ value: 'utf-8', label: 'UTF-8' }, { value: 'gbk', label: 'GBK' }] },
        { key: 'lineEnding', label: '换行符', type: 'select',
          options: [{ value: 'lf', label: 'LF (Unix)' }, { value: 'crlf', label: 'CRLF (Windows)' }] },
        { key: 'savePath', label: '文件名或前缀', type: 'input' },
        { key: 'prompt', label: '备注', type: 'textarea' }
      ]
    },
    'schema-loop': {
      icon: '', iconClass: 'control',
      title: '循环处理', subtitle: '流程控制',
      fields: [
        { key: '_hint_loop', type: 'static', text: '按顺序重复执行循环体内的节点，直到满足退出条件或达到最大次数。循环体内的节点不会在顺序流中重复运行。' },
        { key: 'bodyNodeIds', label: '循环体节点（按顺序）', type: 'node-multiselect' },
        { key: 'maxIterations', label: '最大循环次数', type: 'input', placeholder: '默认 5，上限 50' },
        { key: 'exitCondition', label: '退出条件', type: 'select',
          options: [
            { value: 'unchanged', label: '输出与上一轮相同' },
            { value: 'empty', label: '输出为空' },
            { value: 'contains', label: '输出包含指定文本' },
            { value: 'max_only', label: '仅达到最大次数' },
          ] },
        { key: 'exitContainsText', label: '退出匹配文本', type: 'input', placeholder: '退出条件为「包含指定文本」时填写',
          dependsOn: { field: 'exitCondition', value: 'contains' } },
      ]
    },
    'schema-condition': {
      icon: '', iconClass: 'control',
      title: '条件分支', subtitle: '流程控制',
      fields: [
        { key: '_hint_condition', type: 'static', text: '根据当前文档内容判断走向。请在「编辑连线」模式下为 true / false 两条出口分别连线。' },
        { key: 'conditionType', label: '条件类型', type: 'select',
          options: [
            { value: 'contains', label: '包含文本' },
            { value: 'not_contains', label: '不包含文本' },
            { value: 'empty', label: '内容为空' },
            { value: 'not_empty', label: '内容非空' },
            { value: 'length_gt', label: '长度大于' },
            { value: 'length_lt', label: '长度小于' },
          ] },
        { key: 'matchText', label: '匹配文本', type: 'input', placeholder: '条件为包含/不包含时填写',
          dependsOn: { field: 'conditionType', values: ['contains', 'not_contains'] } },
        { key: 'minLength', label: '长度阈值', type: 'input', placeholder: '默认 0',
          dependsOn: { field: 'conditionType', values: ['length_gt', 'length_lt'] } },
      ]
    },
    'schema-fork': {
      icon: '', iconClass: 'control',
      title: '分叉网关', subtitle: '流程控制',
      fields: [
        { key: '_hint_fork', type: 'static', text: '从本节点引出多条连线到各分支首节点，各分支并行执行至汇合节点（每路可包含多个串联节点）。' },
        { key: 'joinNodeId', label: '汇合节点', type: 'node-select', hint: '选择画布上的「汇合网关」节点' },
        { key: 'mergeStrategy', label: '合并策略', type: 'select',
          options: [
            { value: 'concat', label: '拼接（分隔线连接）' },
            { value: 'first', label: '取第一路结果' },
            { value: 'last', label: '取最后一路结果' },
            { value: 'longest', label: '取最长结果' },
          ] },
      ]
    },
    'schema-join': {
      icon: '', iconClass: 'control',
      title: '汇合网关', subtitle: '流程控制',
      fields: [
        { key: '_hint_join', type: 'static', text: '标记分叉分支的汇合点；分叉网关需指定本节点。连线从汇合节点继续向后执行。' },
      ]
    }
  })

  // ==================== 工具箱（无硬编码值） ====================

  const toolboxItems = ref([
    {
      section: '输入',
      items: [
        {
          icon: '', name: '文档输入', type: 'input', title: '文档输入',
          body: '从文档库或本地上传 PDF / MD / TXT / DOCX / XLSX 等文件',
          schemaKey: 'schema-document-input',
          schema: null
        }
      ]
    },
    {
      section: '处理',
      items: [
        {
          icon: '', name: 'AI 翻译', type: 'ai', title: 'AI 翻译', body: '使用大模型进行智能翻译处理',
          schemaKey: 'schema-translate',
          schema: null
        },
        {
          icon: '', name: '内容提取', type: 'ai', title: '内容提取', body: '生成摘要和提取关键要点',
          schemaKey: 'schema-extract-summary',
          schema: null
        },
        {
          icon: '', name: '数据抽取', type: 'ai', title: '数据抽取', body: '从文档中提取结构化数据',
          schemaKey: 'schema-extract-data',
          schema: null
        },
        {
          icon: '', name: '实体提取', type: 'ai', title: '实体提取', body: '按字段与自定义实体类型抽取结构化信息',
          schemaKey: 'schema-entity-extraction',
          schema: null
        },
        {
          icon: '', name: '数据处理', type: 'ai', title: '数据处理', body: '表格排序、筛选、汇总、去重与列变换',
          schemaKey: 'schema-data-process',
          schema: null
        },
        {
          icon: '', name: '数据清洗', type: 'ai', title: '数据清洗', body: '去空格、格式统一与脏数据规范化',
          schemaKey: 'schema-data-clean',
          schema: null
        },
        {
          icon: '', name: '表格提取', type: 'ai', title: '表格提取', body: '从 PDF/Word 等文档中提取表格结构',
          schemaKey: 'schema-table-extract',
          schema: null
        },
        {
          icon: '', name: '数据汇总', type: 'ai', title: '数据汇总', body: '按维度统计汇总指标',
          schemaKey: 'schema-data-rollup',
          schema: null
        },
        {
          icon: '', name: '内容分析', type: 'ai', title: '内容分析', body: '关键词提取和实体识别',
          schemaKey: 'schema-analyze-content',
          schema: null
        },
        {
          icon: '', name: '文本增强', type: 'ai', title: '文本增强', body: '语法检查、润色和改写',
          schemaKey: 'schema-enhance-text',
          schema: null
        },
        {
          icon: '', name: '文档分割', type: 'ai', title: '文档分割', body: '智能分割文档为多个部分',
          schemaKey: 'schema-split-document',
          schema: null
        },
        {
          icon: '', name: '关键词高亮', type: 'ai', title: '关键词高亮', body: '提取关键词并在结果中标注高亮',
          schemaKey: 'schema-keyword-highlight',
          schema: null
        },
        {
          icon: '', name: '敏感信息脱敏', type: 'ai', title: '敏感信息脱敏', body: '手机号/身份证/邮箱等自动掩码',
          schemaKey: 'schema-sensitive-masking',
          schema: null
        },
        {
          icon: '', name: '术语统一替换', type: 'ai', title: '术语统一替换', body: '按词典规范化术语表达',
          schemaKey: 'schema-term-normalize',
          schema: null
        }
      ]
    },
    {
      section: '流程控制',
      items: [
        {
          icon: '', name: '循环处理', type: 'control', title: '循环处理', body: '重复执行一组节点直到满足退出条件',
          schemaKey: 'schema-loop',
          schema: null
        },
        {
          icon: '', name: '条件分支', type: 'control', title: '条件分支', body: '按文档内容走 true / false 不同路径',
          schemaKey: 'schema-condition',
          schema: null
        },
        {
          icon: '', name: '分叉网关', type: 'control', title: '分叉网关', body: '多路并行分叉，在汇合节点合并',
          schemaKey: 'schema-fork',
          schema: null
        },
        {
          icon: '', name: '汇合网关', type: 'control', title: '汇合网关', body: '标记分叉分支汇合后继续执行',
          schemaKey: 'schema-join',
          schema: null
        }
      ]
    },
    {
      section: '输出',
      items: [
        {
          icon: '', name: '输出文件', type: 'output', title: '输出文件', body: '下载或入库，支持 PDF / MD / TXT / Excel',
          schemaKey: 'schema-library-output',
          schema: null
        }
      ]
    }
  ])

  // ==================== 执行状态 ====================

  const isExecuting = ref(false)
  const executionProgress = ref(0)
  const executionLogs = ref([])
  const outputFiles = ref([])
  const nodeProgress = ref([])
  const currentNodeId = ref('')
  const currentNodeName = ref('')
  /** running | completed | failed（与后端 status 对齐，idle 表示未在执行） */
  const executionStatus = ref('idle')
  const executionCurrentFileIndex = ref(0)
  const executionTotalFiles = ref(0)
  const executionCurrentFileName = ref('')

  // ==================== 计算属性 ====================

  const currentWorkflow = computed(() =>
    currentWorkflowId.value ? workflows.value[currentWorkflowId.value] : null
  )

  const customWorkflows = computed(() =>
    Object.values(workflows.value)
      .filter(w => w.type === 'custom' && !BUILTIN_TEMPLATE_IDS.includes(w.id))
      .sort((a, b) => _workflowRecencyKey(b) - _workflowRecencyKey(a))
  )

  const templateWorkflows = computed(() =>
    BUILTIN_TEMPLATE_IDS
      .map(id => workflows.value[id])
      .filter(w => w && w.type === 'template')
  )

  function _workflowMatchesSearch(wf, query) {
    if (!query || !wf) return true
    const parts = [
      wf.name,
      wf.description,
      wf.time,
      wf.id,
      ...(wf.nodes || []).flatMap(n => [n.title, n.body, n.schemaKey, n.type]),
    ]
    return parts.some(part => String(part || '').toLowerCase().includes(query))
  }

  const filteredCustomWorkflows = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return customWorkflows.value
    return customWorkflows.value.filter(w => _workflowMatchesSearch(w, q))
  })

  const filteredTemplateWorkflows = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return templateWorkflows.value
    return templateWorkflows.value.filter(w => _workflowMatchesSearch(w, q))
  })

  const hasActiveWorkflowSearch = computed(() => searchQuery.value.trim().length > 0)

  const selectedNode = computed(() =>
    canvasNodes.value.find(n => n.id === selectedNodeId.value)
  )

  // 文档总数（库选 + 本地）
  const totalDocCount = computed(() =>
    selectedDocs.value.length + localFiles.value.length
  )

  // ==================== 画布缓存（切换模块时保留未保存编辑） ====================

  let _workflowsHydrated = false
  let _selectWorkflowSeq = 0

  function _mapNodesToCanvas(nodes) {
    return (nodes || []).map((n, i) => ({
      ...n,
      x: n.x ?? (CANVAS_BASE_X + i * CANVAS_SLOT_STEP),
      y: n.y ?? CANVAS_BASE_Y,
      configValues: n.configValues || {},
      schema: n.schema || nodeSchemas.value[resolveSchemaKey(n.schemaKey)] || null,
    }))
  }

  function _serializeCanvasNodes() {
    return canvasNodes.value.map(({ schema, ...rest }) => rest)
  }

  /** 将当前画布节点与配置写回 workflows 缓存，避免切 Tab 后被服务端空数据覆盖 */
  function _normalizeRunSettings(raw) {
    const rs = raw || {}
    const limit = Number(rs.concurrentLimit)
    return {
      concurrentLimit: Number.isFinite(limit) ? Math.min(10, Math.max(1, Math.round(limit))) : DEFAULT_RUN_SETTINGS.concurrentLimit,
      continueOnError: rs.continueOnError !== false,
      notifyOnError: rs.notifyOnError !== false,
    }
  }

  function _loadRunSettingsFromWorkflow(wf) {
    runSettings.value = _normalizeRunSettings(wf?.config?.runSettings)
  }

  function _normalizeWorkflowEdges(raw) {
    if (!Array.isArray(raw)) return []
    return raw
      .map(e => ({
        id: String(e?.id || `edge_${e?.from}_${e?.to}_${Date.now()}`),
        from: String(e?.from || ''),
        to: String(e?.to || ''),
        label: String(e?.label || ''),
      }))
      .filter(e => e.from && e.to)
  }

  function _loadEdgesFromWorkflow(wf) {
    workflowEdges.value = _normalizeWorkflowEdges(wf?.config?.graph?.edges)
  }

  function _syncEdgesToWorkflowCache() {
    const id = currentWorkflowId.value
    if (!id) return
    const existing = workflows.value[id]
    if (!existing) return
    existing.config = {
      ...(existing.config || {}),
      graph: {
        ...(existing.config?.graph || {}),
        edges: workflowEdges.value.map(e => ({ ...e })),
      },
    }
  }

  function syncRunSettingsToWorkflowCache() {
    const id = currentWorkflowId.value
    if (!id) return
    const existing = workflows.value[id]
    if (!existing) return
    existing.config = {
      ...(existing.config || {}),
      runSettings: { ...runSettings.value },
    }
  }

  function updateRunSettings(key, value) {
    if (key === 'concurrentLimit') {
      const n = Number(value)
      runSettings.value.concurrentLimit = Number.isFinite(n)
        ? Math.min(10, Math.max(1, Math.round(n)))
        : DEFAULT_RUN_SETTINGS.concurrentLimit
    } else {
      runSettings.value[key] = !!value
    }
    syncRunSettingsToWorkflowCache()
  }

  function syncCanvasToWorkflowCache() {
    const id = currentWorkflowId.value
    if (!id) return
    const existing = workflows.value[id]
    if (!existing) return
    const nodes = _serializeCanvasNodes()
    existing.nodes = nodes
    existing.name = workflowName.value
    existing.config = {
      ...(existing.config || {}),
      runSettings: { ...runSettings.value },
      graph: {
        ...(existing.config?.graph || {}),
        edges: workflowEdges.value.map(e => ({ ...e })),
      },
    }
  }

  async function ensureWorkflowsLoaded({ force = false } = {}) {
    if (_workflowsHydrated && !force) return
    syncCanvasToWorkflowCache()
    await loadWorkflows()
    await loadTemplates()
    _cleanupGhostWorkflows()
    _workflowsHydrated = true
    const id = currentWorkflowId.value
    if (id && canvasNodes.value.length === 0) {
      const wf = workflows.value[id]
      if (wf?.nodes?.length) {
        workflowName.value = wf.name || workflowName.value
        canvasNodes.value = _mapNodesToCanvas(wf.nodes)
      }
    }
  }

  // ==================== API 加载 ====================

  async function loadWorkflows() {
    syncCanvasToWorkflowCache()
    const preserved = {}
    Object.entries(workflows.value).forEach(([id, wf]) => {
      if (BUILTIN_TEMPLATE_IDS.includes(id)) {
        if (wf.type === 'template') {
          preserved[id] = { ...wf, nodes: [...(wf.nodes || [])] }
        }
        return
      }
      if (id === currentWorkflowId.value) {
        preserved[id] = { ...wf, nodes: [...(wf.nodes || [])] }
      }
    })

    try {
      const res = await workflowApi.getWorkflows()
      const list = res?.workflows || []
      const next = {}
      list.forEach(w => {
        // 内置预设仅在前端维护，忽略后端误存的 tpl_* 记录
        if (BUILTIN_TEMPLATE_IDS.includes(w.id)) return
        next[w.id] = {
          id: w.id,
          name: w.name,
          icon: w.icon || '',
          time: _formatTime(w.updated_at || w.created_at),
          type: w.type || 'custom',
          nodes: w.nodes || [],
          config: w.config || {},
          created_at: w.created_at || '',
          updated_at: w.updated_at || '',
        }
      })
      Object.entries(preserved).forEach(([id, wf]) => {
        if (!next[id]) {
          next[id] = wf
          return
        }
        if (id === currentWorkflowId.value && (wf.nodes?.length || canvasNodes.value.length)) {
          next[id] = {
            ...next[id],
            nodes: canvasNodes.value.length ? _serializeCanvasNodes() : wf.nodes,
          }
        }
      })
      workflows.value = next
    } catch (e) {
      console.error('loadWorkflows error:', e)
    }
  }

  async function loadTemplates() {
    try {
      const res = await workflowApi.getTemplates()
      const list = res?.templates || []
      templates.value = list.map(t => ({
        id: t.id,
        name: t.name,
        icon: t.icon || '',
        description: t.description || '',
        type: 'template',
        time: '系统预设',
        nodes: t.nodes || [],
        config: t.config || {}
      }))
      // 合并 API 模板（当前为空）并注册前端内置「文档翻译流」
      templates.value.forEach(t => {
        workflows.value[t.id] = t
      })
      _cleanupGhostWorkflows()
      delete workflows.value['translate-pdf']
      delete workflows.value['translate-docx']
    } catch (e) {
      console.error('loadTemplates error:', e)
      _cleanupGhostWorkflows()
    }
  }

  async function loadModels() {
    try {
      const res = await workflowApi.getModels()
      availableModels.value = Array.isArray(res) ? res : (res?.models || [])
    } catch (e) {
      console.error('loadModels error:', e)
    }
  }

  async function loadLanguages() {
    try {
      const res = await workflowApi.getLanguages()
      availableLanguages.value = (Array.isArray(res) ? res : []).map(item => ({
        code: item.code,
        label: item.name || item.code
      }))
    } catch (e) {
      console.error('loadLanguages error:', e)
    }
  }

  async function loadOutputFormats() {
    try {
      const res = await workflowApi.getOutputFormats()
      outputFormats.value = (Array.isArray(res) ? res : []).map(item => ({
        code: item.code,
        label: item.name || item.code
      }))
    } catch (e) {
      console.error('loadOutputFormats error:', e)
    }
  }

  // ==================== 工作流操作 ====================

  function selectWorkflow(workflowId) {
    const prevId = currentWorkflowId.value
    if (prevId && workflows.value[prevId]) {
      syncCanvasToWorkflowCache()
    }

    const seq = ++_selectWorkflowSeq
    currentWorkflowId.value = workflowId
    const wf = workflows.value[workflowId]

    if (!wf) {
      workflowName.value = '未命名'
      if (canvasNodes.value.length === 0) {
        canvasNodes.value = []
      }
      runSettings.value = { ...DEFAULT_RUN_SETTINGS }
      workflowEdges.value = []
      selectedNodeId.value = null
      return
    }

    workflowName.value = wf.name
    _loadRunSettingsFromWorkflow(wf)
    _loadEdgesFromWorkflow(wf)

    // 模板工作流：优先使用缓存中的 nodes（含用户未保存的编辑）
    if (wf.type === 'template') {
      canvasNodes.value = _mapNodesToCanvas(wf.nodes)
      selectedNodeId.value = null
      return
    }

    // 自定义工作流：先用本地缓存渲染，避免等待 API 期间画布空白
    if (wf.nodes?.length) {
      canvasNodes.value = _mapNodesToCanvas(wf.nodes)
    }
    selectedNodeId.value = null

    workflowApi.getWorkflow(workflowId).then(res => {
      if (seq !== _selectWorkflowSeq || currentWorkflowId.value !== workflowId) return
      const wfData = res || {}
      workflowName.value = wfData.name || wf.name || '未命名'
      const serverNodes = wfData.nodes || []
      if (serverNodes.length > 0) {
        canvasNodes.value = _mapNodesToCanvas(serverNodes)
        if (workflows.value[workflowId]) {
          workflows.value[workflowId].nodes = _serializeCanvasNodes()
        }
      } else if (canvasNodes.value.length === 0) {
        canvasNodes.value = []
      }
      if (wfData.config) {
        workflows.value[workflowId] = {
          ...workflows.value[workflowId],
          config: wfData.config,
        }
        _loadRunSettingsFromWorkflow(workflows.value[workflowId])
        _loadEdgesFromWorkflow(workflows.value[workflowId])
      } else {
        workflowEdges.value = []
      }
      selectedNodeId.value = null
    }).catch(() => {
      if (seq !== _selectWorkflowSeq || currentWorkflowId.value !== workflowId) return
      workflowName.value = wf.name || '未命名'
      if (canvasNodes.value.length === 0) {
        canvasNodes.value = wf.nodes?.length ? _mapNodesToCanvas(wf.nodes) : []
      }
    })
  }

  async function createNewWorkflow() {
    const now = new Date().toISOString()
    const id = 'wf_' + Date.now()
    const name = '新建工作流'
    workflows.value[id] = {
      id,
      name,
      icon: '',
      time: '刚刚',
      type: 'custom',
      nodes: [],
      config: { runSettings: { ...DEFAULT_RUN_SETTINGS }, graph: { edges: [] } },
      created_at: now,
      updated_at: now,
    }
    currentWorkflowId.value = id
    workflowName.value = name
    runSettings.value = { ...DEFAULT_RUN_SETTINGS }
    workflowEdges.value = []
    canvasNodes.value = []
    selectedNodeId.value = null
    // 立即保存到后端
    try {
      await workflowApi.saveWorkflow({
        id,
        name,
        icon: '',
        type: 'custom',
        nodes: [],
        config: { runSettings: { ...DEFAULT_RUN_SETTINGS }, graph: { edges: [] } },
      })
    } catch (e) {
      console.error('createNewWorkflow save error:', e)
    }
  }

  async function saveCurrentWorkflow() {
    if (!currentWorkflowId.value) return
    const wf = workflows.value[currentWorkflowId.value]
    if (!wf) return

    const nodes = _serializeCanvasNodes()
    const config = {
      ...(wf.config || {}),
      runSettings: { ...runSettings.value },
      graph: {
        ...(wf.config?.graph || {}),
        edges: workflowEdges.value.map(e => ({ ...e })),
      },
    }
    const name = workflowName.value || wf.name || '未命名工作流'

    // 保存系统预设：另存为「我的工作流」，并恢复预设模板为出厂状态
    if (BUILTIN_TEMPLATE_IDS.includes(wf.id) && wf.type === 'template') {
      const templateId = wf.id
      const newId = 'wf_' + Date.now()
      const now = new Date().toISOString()
      const newWf = {
        id: newId,
        name,
        icon: wf.icon || '',
        time: '刚刚',
        type: 'custom',
        nodes,
        config,
        created_at: now,
        updated_at: now,
      }
      try {
        await workflowApi.saveWorkflow({
          id: newId,
          name,
          icon: newWf.icon,
          type: 'custom',
          nodes,
          config,
        })
        workflows.value[newId] = newWf
        currentWorkflowId.value = newId
        _resetBuiltinTemplate(templateId)
      } catch (e) {
        console.error('saveCurrentWorkflow (from template) error:', e)
      }
      return
    }

    wf.nodes = nodes
    wf.name = name
    wf.config = config
    try {
      await workflowApi.saveWorkflow({
        id: wf.id,
        name,
        icon: wf.icon || '',
        type: 'custom',
        nodes: wf.nodes,
        config: wf.config || {},
      })
      wf.time = '刚刚'
      wf.updated_at = new Date().toISOString()
    } catch (e) {
      console.error('saveCurrentWorkflow error:', e)
    }
  }

  function _workflowRecencyKey(w) {
    if (!w) return 0
    const updated = Date.parse(w.updated_at || '')
    if (Number.isFinite(updated)) return updated
    const created = Date.parse(w.created_at || '')
    if (Number.isFinite(created)) return created
    const m = String(w.id || '').match(/^wf_(\d+)$/)
    if (m) return Number(m[1]) || 0
    return 0
  }

  function _listSelectableCustomWorkflows() {
    return Object.values(workflows.value)
      .filter(w => w.type === 'custom' && !BUILTIN_TEMPLATE_IDS.includes(w.id))
      .sort((a, b) => _workflowRecencyKey(b) - _workflowRecencyKey(a))
  }

  function _omitWorkflowFromState(workflowId) {
    const next = { ...workflows.value }
    delete next[workflowId]
    workflows.value = next
  }

  async function _selectWorkflowAfterRemoval() {
    currentWorkflowId.value = null
    selectedNodeId.value = null

    const remaining = _listSelectableCustomWorkflows()
    if (remaining.length > 0) {
      selectWorkflow(remaining[0].id)
      return
    }
    const templates = BUILTIN_TEMPLATE_IDS.map(id => workflows.value[id]).filter(Boolean)
    if (templates.length > 0) {
      selectWorkflow(templates[0].id)
      return
    }
    await createNewWorkflow()
  }

  async function _removeWorkflowFromState(workflowId) {
    const wasCurrent = currentWorkflowId.value === workflowId
    _omitWorkflowFromState(workflowId)
    if (!wasCurrent) return
    await _selectWorkflowAfterRemoval()
  }

  async function _deleteOneWorkflow(workflowId, { navigate = true } = {}) {
    const wf = workflows.value[workflowId]
    if (!wf) return false

    if (wf.type === 'template' && BUILTIN_TEMPLATE_IDS.includes(workflowId)) {
      throw new Error('无法删除系统模板工作流')
    }

    const wasCurrent = currentWorkflowId.value === workflowId

    if (BUILTIN_TEMPLATE_IDS.includes(workflowId)) {
      _omitWorkflowFromState(workflowId)
      _resetBuiltinTemplate(workflowId)
      if (navigate && wasCurrent) {
        await _selectWorkflowAfterRemoval()
      }
      return true
    }

    if (wf.type === 'template') {
      throw new Error('无法删除系统模板工作流')
    }

    try {
      await workflowApi.deleteWorkflow(workflowId)
    } catch (e) {
      const msg = String(e?.message || '')
      if (/不存在|模板工作流|not found|404/i.test(msg)) {
        _omitWorkflowFromState(workflowId)
        if (navigate && wasCurrent) {
          await _selectWorkflowAfterRemoval()
        }
        return true
      }
      throw e
    }

    _omitWorkflowFromState(workflowId)
    if (navigate && wasCurrent) {
      await _selectWorkflowAfterRemoval()
    }
    return true
  }

  async function deleteWorkflow(workflowId) {
    await _deleteOneWorkflow(workflowId, { navigate: true })
  }

  async function deleteWorkflows(workflowIds) {
    const ids = [...new Set((workflowIds || []).map(id => String(id).trim()).filter(Boolean))]
    if (!ids.length) return { deleted: 0, failed: 0 }

    const needNavigate = ids.includes(currentWorkflowId.value)
    let deleted = 0
    let failed = 0
    let lastError = null

    for (const id of ids) {
      try {
        const ok = await _deleteOneWorkflow(id, { navigate: false })
        if (ok) deleted += 1
      } catch (e) {
        failed += 1
        lastError = e
      }
    }

    const currentMissing = !currentWorkflowId.value || !workflows.value[currentWorkflowId.value]
    if (needNavigate || currentMissing) {
      await _selectWorkflowAfterRemoval()
    }

    if (failed > 0 && deleted === 0 && lastError) {
      throw lastError
    }
    return { deleted, failed }
  }

  // ==================== 节点操作 ====================

  function selectNode(nodeId) {
    selectedNodeId.value = nodeId
  }

  function updateNodePosition(nodeId, x, y) {
    const node = canvasNodes.value.find(n => n.id === nodeId)
    if (node) {
      node.x = x
      node.y = y
      syncCanvasToWorkflowCache()
    }
  }

  /** 执行顺序前移一格（仅调整列表顺序，不改变画布坐标） */
  function moveNodeEarlier(nodeId) {
    const idx = canvasNodes.value.findIndex(n => n.id === nodeId)
    if (idx <= 0) return
    const list = canvasNodes.value
    const item = list[idx]
    list.splice(idx, 1)
    list.splice(idx - 1, 0, item)
    syncCanvasToWorkflowCache()
  }

  /** 执行顺序后移一格 */
  function moveNodeLater(nodeId) {
    const idx = canvasNodes.value.findIndex(n => n.id === nodeId)
    if (idx < 0 || idx >= canvasNodes.value.length - 1) return
    const list = canvasNodes.value
    const item = list[idx]
    list.splice(idx, 1)
    list.splice(idx + 1, 0, item)
    syncCanvasToWorkflowCache()
  }

  function enterOrderEditMode() {
    if (isBulkDeleteMode.value) exitBulkDeleteMode()
    if (isEdgeEditMode.value) exitEdgeEditMode()
    isOrderEditMode.value = true
  }

  function exitOrderEditMode() {
    isOrderEditMode.value = false
    syncCanvasToWorkflowCache()
  }

  function toggleOrderEditMode() {
    if (isOrderEditMode.value) {
      exitOrderEditMode()
    } else {
      enterOrderEditMode()
    }
  }

  function enterBulkDeleteMode() {
    if (isOrderEditMode.value) exitOrderEditMode()
    if (isEdgeEditMode.value) exitEdgeEditMode()
    isBulkDeleteMode.value = true
    bulkSelectedNodeIds.value = []
    selectedNodeId.value = null
  }

  function exitBulkDeleteMode() {
    isBulkDeleteMode.value = false
    bulkSelectedNodeIds.value = []
  }

  function toggleBulkDeleteMode() {
    if (isBulkDeleteMode.value) {
      exitBulkDeleteMode()
    } else {
      enterBulkDeleteMode()
    }
  }

  function _removeEdgesForNode(nodeId) {
    const id = String(nodeId)
    workflowEdges.value = workflowEdges.value.filter(e => e.from !== id && e.to !== id)
    _syncEdgesToWorkflowCache()
  }

  function _newEdgeId(from, to) {
    return `edge_${from}_${to}_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`
  }

  function addWorkflowEdge(fromId, toId, label = '') {
    const from = String(fromId || '')
    const to = String(toId || '')
    if (!from || !to || from === to) return null
    const exists = workflowEdges.value.some(
      e => e.from === from && e.to === to && String(e.label || '') === String(label || '')
    )
    if (exists) return null
    const edge = {
      id: _newEdgeId(from, to),
      from,
      to,
      label: String(label || ''),
    }
    workflowEdges.value.push(edge)
    _syncEdgesToWorkflowCache()
    return edge
  }

  function removeWorkflowEdge(edgeId) {
    const id = String(edgeId || '')
    if (!id) return
    workflowEdges.value = workflowEdges.value.filter(e => e.id !== id)
    _syncEdgesToWorkflowCache()
  }

  function clearWorkflowEdges() {
    workflowEdges.value = []
    _syncEdgesToWorkflowCache()
  }

  function enterEdgeEditMode() {
    if (isOrderEditMode.value) exitOrderEditMode()
    if (isBulkDeleteMode.value) exitBulkDeleteMode()
    isEdgeEditMode.value = true
    selectedNodeId.value = null
  }

  function exitEdgeEditMode() {
    isEdgeEditMode.value = false
    syncCanvasToWorkflowCache()
  }

  function toggleEdgeEditMode() {
    if (isEdgeEditMode.value) {
      exitEdgeEditMode()
    } else {
      enterEdgeEditMode()
    }
  }

  function toggleBulkSelectNode(nodeId) {
    if (!isBulkDeleteMode.value) return
    const ids = bulkSelectedNodeIds.value
    const idx = ids.indexOf(nodeId)
    if (idx >= 0) ids.splice(idx, 1)
    else ids.push(nodeId)
  }

  function clearBulkSelection() {
    bulkSelectedNodeIds.value = []
  }

  function selectAllBulkNodes() {
    if (!isBulkDeleteMode.value) return
    bulkSelectedNodeIds.value = canvasNodes.value.map(n => n.id)
  }

  function deleteBulkSelectedNodes() {
    if (!bulkSelectedNodeIds.value.length) return
    const toDelete = new Set(bulkSelectedNodeIds.value)
    canvasNodes.value = canvasNodes.value.filter(n => !toDelete.has(n.id))
    workflowEdges.value = workflowEdges.value.filter(e => !toDelete.has(e.from) && !toDelete.has(e.to))
    bulkSelectedNodeIds.value = []
    if (selectedNodeId.value && toDelete.has(selectedNodeId.value)) {
      selectedNodeId.value = canvasNodes.value[0]?.id ?? null
    }
    syncCanvasToWorkflowCache()
    if (canvasNodes.value.length === 0) exitBulkDeleteMode()
  }

  /** 编辑顺序模式下：按画布位置（先 X 后 Y）重排执行列表，不改变坐标 */
  function reorderNodesByCanvasPosition() {
    if (canvasNodes.value.length < 2) return
    const sorted = [...canvasNodes.value].sort((a, b) => {
      const ax = a.x + CANVAS_NODE_W / 2
      const bx = b.x + CANVAS_NODE_W / 2
      if (ax !== bx) return ax - bx
      return a.y - b.y
    })
    canvasNodes.value = sorted
    syncCanvasToWorkflowCache()
  }

  /** 按当前执行顺序将节点整理为一行水平流水线 */
  function alignCanvasNodes() {
    canvasNodes.value.forEach((n, i) => {
      n.x = CANVAS_BASE_X + i * CANVAS_SLOT_STEP
      n.y = CANVAS_BASE_Y
    })
    syncCanvasToWorkflowCache()
  }

  function updateNodeConfig(nodeId, key, value) {
    const node = canvasNodes.value.find(n => n.id === nodeId)
    if (node) {
      if (!node.configValues) node.configValues = {}
      node.configValues[key] = value

      // 特殊处理：inputSource 变化时清空对应数据
      if (key === 'inputSource') {
        if (value === 'library') {
          localFiles.value = []
        } else {
          node.configValues.spaceId = null
          selectedDocs.value = []
        }
      }
      syncCanvasToWorkflowCache()
    }
  }

  function addNode(toolboxItem) {
    const schema = nodeSchemas.value[toolboxItem.schemaKey] || null
    const id = 'n_' + Date.now()
    const lastNode = canvasNodes.value[canvasNodes.value.length - 1]
    const x = lastNode ? lastNode.x + CANVAS_SLOT_STEP : CANVAS_BASE_X
    const y = lastNode ? lastNode.y : CANVAS_BASE_Y
    const configValues = _defaultConfigForSchemaKey(toolboxItem.schemaKey)
    const newNode = {
      id,
      type: toolboxItem.type,
      icon: toolboxItem.icon,
      title: toolboxItem.title,
      body: toolboxItem.body,
      x,
      y,
      configValues,
      schemaKey: toolboxItem.schemaKey,
      schema
    }
    canvasNodes.value.push(newNode)
    selectedNodeId.value = id
    syncCanvasToWorkflowCache()
    return id
  }

  /** 在画布指定坐标放置节点（拖拽落点）；坐标相对于 canvas-inner 左上角 */
  function addNodeAt(toolboxItem, x, y) {
    const schema = nodeSchemas.value[toolboxItem.schemaKey] || null
    const id = 'n_' + Date.now()
    const INNER = 3000
    const NODE_PLACEHOLDER_W = CANVAS_NODE_W
    const NODE_PLACEHOLDER_H = 100
    const cx = Math.round(Math.min(Math.max(8, x), INNER - NODE_PLACEHOLDER_W - 8))
    const cy = Math.round(Math.min(Math.max(8, y), INNER - NODE_PLACEHOLDER_H - 8))
    const configValues = _defaultConfigForSchemaKey(toolboxItem.schemaKey)
    const newNode = {
      id,
      type: toolboxItem.type,
      icon: toolboxItem.icon,
      title: toolboxItem.title,
      body: toolboxItem.body,
      x: cx,
      y: cy,
      configValues,
      schemaKey: toolboxItem.schemaKey,
      schema
    }
    canvasNodes.value.push(newNode)
    reorderNodesByCanvasPosition()
    selectedNodeId.value = id
    syncCanvasToWorkflowCache()
    return id
  }

  /** 新节点拖入画布时的默认配置，避免「处理类型」等依赖字段全空导致面板无内容 */
  function _defaultConfigForSchemaKey(schemaKey) {
    switch (schemaKey) {
      case 'schema-document-input':
      case 'schema-pdf-input':
      case 'schema-md-input':
      case 'schema-txt-input':
      case 'schema-docx-input':
      case 'schema-xlsx-input':
        return { inputSource: 'library', spaceId: null, skipExisting: false }
      case 'schema-data-process':
        return { processKind: 'sort', sortOrder: 'asc' }
      case 'schema-data-clean':
        return { cleanRules: ['trim_spaces'] }
      case 'schema-table-extract':
        return { tableStrategy: 'first', hasHeader: true }
      case 'schema-library-output':
        return { outputMode: 'download', namingRule: '{original_file}_out', outputFormat: 'md' }
      case 'schema-save-text':
        return { outputEncoding: 'utf-8', lineEnding: 'lf' }
      case 'schema-convert-format':
        return { targetFormat: 'markdown', conversionOptions: [] }
      case 'schema-loop':
        return { bodyNodeIds: [], maxIterations: 5, exitCondition: 'unchanged', exitContainsText: '' }
      case 'schema-condition':
        return { conditionType: 'contains', matchText: '', minLength: 0 }
      case 'schema-fork':
        return { mergeStrategy: 'concat', joinNodeId: '' }
      case 'schema-join':
        return {}
      default:
        return {}
    }
  }

  function deleteNode(nodeId) {
    const idx = canvasNodes.value.findIndex(n => n.id === nodeId)
    if (idx === -1) return
    canvasNodes.value.splice(idx, 1)
    _removeEdgesForNode(nodeId)
    if (selectedNodeId.value === nodeId) {
      selectedNodeId.value = canvasNodes.value.length > 0
        ? canvasNodes.value[Math.min(idx, canvasNodes.value.length - 1)].id
        : null
    }
    syncCanvasToWorkflowCache()
  }

  function clearCanvas() {
    canvasNodes.value = []
    workflowEdges.value = []
    selectedNodeId.value = null
  }

  // ==================== 文档操作（从文档库） ====================

  function setSelectedDocs(docs) {
    selectedDocs.value = docs
  }

  function addSelectedDoc(doc) {
    if (!selectedDocs.value.find(d => d.id === doc.id)) {
      selectedDocs.value.push(doc)
    }
  }

  function removeSelectedDoc(docId) {
    selectedDocs.value = selectedDocs.value.filter(d => d.id !== docId)
  }

  function clearSelectedDocs() {
    selectedDocs.value = []
  }

  // ==================== 本地文件操作 ====================

  function addLocalFiles(files) {
    files.forEach(file => {
      if (!localFiles.value.find(f => f.name === file.name && f.size === file.size)) {
        localFiles.value.push({
          id: 'local_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6),
          name: file.name,
          size: file.size,
          file: file,
          type: file.type
        })
      }
    })
  }

  function removeLocalFile(fileId) {
    localFiles.value = localFiles.value.filter(f => f.id !== fileId)
  }

  function clearLocalFiles() {
    localFiles.value = []
  }

  // ==================== 工作流执行 ====================

  function _sanitizeConfigValue(value) {
    if (Array.isArray(value)) {
      return value
        .map(v => _sanitizeConfigValue(v))
        .filter(v => v !== null && v !== undefined)
    }

    if (value && typeof value === 'object') {
      if (Object.prototype.hasOwnProperty.call(value, 'value')) {
        return value.value
      }
      return value
    }

    if (value === '[object Object]') {
      return null
    }

    return value
  }

  function _sanitizeNodeConfigValues(configValues) {
    const src = configValues || {}
    const out = {}
    Object.keys(src).forEach(k => {
      out[k] = _sanitizeConfigValue(src[k])
    })
    return out
  }

  function _normalizeExecutionLog(log) {
    if (log == null) return { type: 'info', message: '' }
    if (typeof log === 'string') return { type: 'info', message: log }
    const rawType = String(log.type || 'info').toLowerCase()
    const type =
      rawType === 'success' || rawType === 'complete' ? 'done' : rawType === 'warning' ? 'warn' : rawType
    const allowed = ['info', 'done', 'warn', 'error']
    const t = allowed.includes(type) ? type : 'info'
    const msg =
      log.message != null
        ? String(log.message)
        : log.msg != null
          ? String(log.msg)
          : ''
    return { type: t, message: msg || JSON.stringify(log) }
  }

  /** 将服务端返回的完整 logs 中尚未追加的部分写入 executionLogs，返回新的游标 */
  function _appendNewLogsFromResponse(res, lastCount) {
    const raw = res?.logs
    if (!Array.isArray(raw) || raw.length <= lastCount) return lastCount
    for (let i = lastCount; i < raw.length; i++) {
      executionLogs.value.push(_normalizeExecutionLog(raw[i]))
    }
    return raw.length
  }

  function _applyExecutionSnapshot(res) {
    const idx = res?.current_file_index ?? res?.currentFileIndex ?? 0
    const total = res?.total_files ?? res?.totalFiles ?? 0
    const name = res?.current_file_name ?? res?.currentFileName ?? ''
    executionCurrentFileIndex.value = Number(idx) || 0
    executionTotalFiles.value = Number(total) || 0
    executionCurrentFileName.value = String(name || '')
    if (res?.progress != null && res.progress !== '') {
      const p = Number(res.progress)
      if (!Number.isNaN(p)) executionProgress.value = Math.min(100, Math.max(0, p))
    }
    nodeProgress.value = Array.isArray(res?.node_progress) ? res.node_progress : nodeProgress.value
    currentNodeId.value = res?.current_node_id ?? res?.currentNodeId ?? ''
    currentNodeName.value = res?.current_node_name ?? res?.currentNodeName ?? ''
  }

  async function executeWorkflow() {
    if (isExecuting.value) return
    if (isOrderEditMode.value) {
      exitOrderEditMode()
    }
    if (isBulkDeleteMode.value) {
      exitBulkDeleteMode()
    }
    if (isEdgeEditMode.value) {
      exitEdgeEditMode()
    }
    isExecuting.value = true
    executionProgress.value = 0
    executionLogs.value = []
    outputFiles.value = []
    executionStatus.value = 'running'
    executionCurrentFileIndex.value = 0
    executionTotalFiles.value = 0
    executionCurrentFileName.value = ''
    nodeProgress.value = canvasNodes.value.map((n, idx) => ({
      id: n.id,
      title: n.title,
      type: n.type,
      schemaKey: n.schemaKey,
      index: idx + 1,
      status: 'pending',
      progress: 0,
      message: ''
    }))
    currentNodeId.value = ''
    currentNodeName.value = ''

    try {
      // 将本地文件转为 base64 发送（逐字节避免栈溢出）
      const localFilePayloads = await Promise.all(
        localFiles.value.map(async f => {
          if (f.file && f.file.arrayBuffer) {
            const buffer = await f.file.arrayBuffer()
            const bytes = new Uint8Array(buffer)
            let binary = ''
            for (let i = 0; i < bytes.length; i++) {
              binary += String.fromCharCode(bytes[i])
            }
            const base64 = btoa(binary)
            return { name: f.name, size: f.size, content: base64 }
          }
          return { name: f.name, size: f.size }
        })
      )

      // 收集执行参数
      const params = {
        workflowId: currentWorkflowId.value,
        nodes: canvasNodes.value.map(n => ({
          id: n.id,
          type: n.type,
          title: n.title,
          schemaKey: n.schemaKey,
          configValues: _sanitizeNodeConfigValues(n.configValues)
        })),
        docs: selectedDocs.value.map(d => d.id),
        localFiles: localFilePayloads,
        runSettings: { ...runSettings.value },
        workflowEdges: workflowEdges.value.map(e => ({
          id: e.id,
          from: e.from,
          to: e.to,
          label: e.label || '',
        })),
      }

      const res = await workflowApi.execute(params)
      const executionId = res?.execution_id
      if (!executionId) {
        executionLogs.value.push({ type: 'error', message: '未返回 execution_id，无法轮询状态' })
        executionStatus.value = 'failed'
        return
      }

      // 轮询执行状态
      await pollExecution(executionId)
    } catch (e) {
      executionLogs.value.push({ type: 'error', message: e.message })
      executionStatus.value = 'failed'
    } finally {
      isExecuting.value = false
    }
  }

  async function pollExecution(executionId) {
    const maxPolls = 120
    let polls = 0
    let lastLogCount = 0
    while (polls < maxPolls) {
      try {
        const res = await workflowApi.getExecutionStatus(executionId)
        const status = res?.status
        _applyExecutionSnapshot(res)
        lastLogCount = _appendNewLogsFromResponse(res, lastLogCount)

        if (status === 'completed') {
          executionProgress.value = 100
          executionStatus.value = 'completed'
          if (Array.isArray(res.output_files) && res.output_files.length > 0) {
            outputFiles.value = res.output_files
          }
          break
        }
        if (status === 'failed') {
          executionStatus.value = 'failed'
          break
        }

        // running / pending 等：进度条优先用服务端 progress，否则按文件序号估算
        const tf = executionTotalFiles.value || 0
        const ci = executionCurrentFileIndex.value || 0
        if (res?.progress == null || res.progress === '') {
          if (tf > 0 && ci > 0) {
            executionProgress.value = Math.min(99, Math.max(0, Math.round((ci / tf) * 100)))
          }
        }
      } catch (e) {
        executionLogs.value.push({ type: 'error', message: e.message })
        executionStatus.value = 'failed'
        break
      }
      await new Promise(r => setTimeout(r, 2000))
      polls++
    }
    if (polls >= maxPolls) {
      executionLogs.value.push({ type: 'error', message: '执行超时' })
      executionStatus.value = 'failed'
    }
  }

  // ==================== 辅助方法 ====================

  function setSearchQuery(query) {
    searchQuery.value = query
  }

  function clearSearchQuery() {
    searchQuery.value = ''
  }

  async function ensureInitialWorkflowSelection() {
    const custom = _listSelectableCustomWorkflows()
    if (custom.length > 0) {
      selectWorkflow(custom[0].id)
      return
    }
    const templates = BUILTIN_TEMPLATE_IDS.map(id => workflows.value[id]).filter(Boolean)
    if (templates.length > 0) {
      selectWorkflow(templates[0].id)
      return
    }
    await createNewWorkflow()
  }

  function updateWorkflowName(name) {
    workflowName.value = name
    const wf = workflows.value[currentWorkflowId.value]
    if (wf) {
      wf.name = name
    }
  }

  // 根据 schemaKey 获取 schema（用于配置面板动态渲染）
  function getSchemaByKey(schemaKey) {
    return nodeSchemas.value[resolveSchemaKey(schemaKey)] || null
  }

  function _tplEdge(id, from, to, label = '') {
    return { id, from, to, label }
  }

  function _buildBuiltinTemplateById(id) {
    const builders = {
      [TRANSLATION_TEMPLATE_ID]: _buildTranslationTemplateWorkflow,
      [FORK_PARALLEL_TEMPLATE_ID]: _buildForkParallelTemplateWorkflow,
      [CONDITION_BRANCH_TEMPLATE_ID]: _buildConditionBranchTemplateWorkflow,
      [LOOP_TEMPLATE_ID]: _buildLoopTemplateWorkflow,
    }
    const build = builders[id]
    return build ? build() : null
  }

  function _resetBuiltinTemplate(id) {
    const built = _buildBuiltinTemplateById(id)
    if (!built) return
    workflows.value[id] = built
    _rebuildTemplatesList()
  }

  /** 清除误写入「我的工作流」的内置预设副本（tpl_* + type=custom） */
  function _cleanupGhostWorkflows() {
    const next = { ...workflows.value }
    let changed = false
    for (const id of BUILTIN_TEMPLATE_IDS) {
      const wf = next[id]
      if (wf && wf.type !== 'template') {
        delete next[id]
        changed = true
      }
    }
    if (changed) {
      workflows.value = next
    }
    seedBuiltinTemplates()
  }

  function _seedBuiltinTemplate(built) {
    const existing = workflows.value[built.id]
    const merged = existing?.type === 'template'
      ? {
          ...built,
          ...existing,
          type: 'template',
          nodes: existing.nodes?.length ? existing.nodes : built.nodes,
          config: {
            ...built.config,
            ...(existing.config || {}),
            runSettings: {
              ...DEFAULT_RUN_SETTINGS,
              ...(built.config?.runSettings || {}),
              ...(existing.config?.runSettings || {}),
            },
            graph: {
              ...(built.config?.graph || {}),
              ...(existing.config?.graph || {}),
              edges: (existing.config?.graph?.edges?.length
                ? existing.config.graph.edges
                : built.config?.graph?.edges) || [],
            },
          },
        }
      : built
    workflows.value[built.id] = merged
    return merged
  }

  function _rebuildTemplatesList() {
    templates.value = BUILTIN_TEMPLATE_IDS.map(id => workflows.value[id]).filter(Boolean)
  }

  function seedBuiltinTemplates() {
    _seedBuiltinTemplate(_buildTranslationTemplateWorkflow())
    _seedBuiltinTemplate(_buildForkParallelTemplateWorkflow())
    _seedBuiltinTemplate(_buildConditionBranchTemplateWorkflow())
    _seedBuiltinTemplate(_buildLoopTemplateWorkflow())
    _rebuildTemplatesList()
  }

  function _buildTranslationTemplateWorkflow() {
    return {
      id: TRANSLATION_TEMPLATE_ID,
      name: '文档翻译流',
      icon: '',
      time: '系统预设',
      type: 'template',
      nodes: [
        {
          id: 'n_input',
          type: 'input',
          icon: '',
          title: '文档输入',
          body: '从文档库或本地上传 PDF / MD / TXT / DOCX / XLSX 等文件',
          x: CANVAS_BASE_X,
          y: CANVAS_BASE_Y,
          configValues: {
            inputSource: 'library',
            spaceId: null,
            skipExisting: false
          },
          schemaKey: 'schema-document-input',
          schema: nodeSchemas.value['schema-document-input']
        },
        {
          id: 'n_translate',
          type: 'ai',
          icon: '',
          title: 'AI 翻译',
          body: '使用大模型进行智能翻译处理',
          x: CANVAS_BASE_X + CANVAS_SLOT_STEP,
          y: CANVAS_BASE_Y,
          configValues: {
            targetLanguage: 'en',
            prompt: '请将此文档翻译为指定语言，保持原文格式和专业术语的准确性。'
          },
          schemaKey: 'schema-translate',
          schema: nodeSchemas.value['schema-translate']
        },
        {
          id: 'n_output',
          type: 'output',
          icon: '',
          title: '输出文件',
          body: '保存结果到文档库或直接下载',
          x: CANVAS_BASE_X + CANVAS_SLOT_STEP * 2,
          y: CANVAS_BASE_Y,
          configValues: {
            outputMode: 'download',
            targetSpaceId: null,
            namingRule: '{original_file}_translated',
            outputFormat: 'pdf'
          },
          schemaKey: 'schema-library-output',
          schema: nodeSchemas.value['schema-library-output']
        }
      ],
      config: { runSettings: { ...DEFAULT_RUN_SETTINGS } }
    }
  }

  /** 分叉 + 汇合：每路 2 个处理节点并行，再合并输出 */
  function _buildForkParallelTemplateWorkflow() {
    const y = CANVAS_BASE_Y
    const yTop = y - 72
    const yBot = y + 72
    return {
      id: FORK_PARALLEL_TEMPLATE_ID,
      name: '分叉并行示例',
      icon: '',
      time: '系统预设',
      type: 'template',
      nodes: [
        {
          id: 'fp_input',
          type: 'input',
          icon: '',
          title: '文档输入',
          body: '从文档库或本地上传 PDF / MD / TXT / DOCX / XLSX 等文件',
          x: CANVAS_BASE_X,
          y,
          configValues: { inputSource: 'library', spaceId: null, skipExisting: false },
          schemaKey: 'schema-document-input',
        },
        {
          id: 'fp_fork',
          type: 'control',
          icon: '',
          title: '分叉网关',
          body: '多路并行分叉，在汇合节点合并',
          x: CANVAS_BASE_X + CANVAS_SLOT_STEP,
          y,
          configValues: { mergeStrategy: 'concat', joinNodeId: 'fp_join' },
          schemaKey: 'schema-fork',
        },
        {
          id: 'fp_translate',
          type: 'ai',
          icon: '',
          title: 'AI 翻译',
          body: '使用大模型进行智能翻译处理',
          x: CANVAS_BASE_X + CANVAS_SLOT_STEP * 2,
          y: yTop,
          configValues: { targetLanguage: '中文', prompt: '' },
          schemaKey: 'schema-translate',
        },
        {
          id: 'fp_enhance',
          type: 'ai',
          icon: '',
          title: '文本增强',
          body: '语法检查、润色和改写',
          x: CANVAS_BASE_X + CANVAS_SLOT_STEP * 3,
          y: yTop,
          configValues: { enhanceType: 'polish', style: 'formal', prompt: '' },
          schemaKey: 'schema-enhance-text',
        },
        {
          id: 'fp_summary',
          type: 'ai',
          icon: '',
          title: '内容提取',
          body: '生成摘要和提取关键要点',
          x: CANVAS_BASE_X + CANVAS_SLOT_STEP * 2,
          y: yBot,
          configValues: { extractType: 'summary', summaryLength: 'medium', prompt: '' },
          schemaKey: 'schema-extract-summary',
        },
        {
          id: 'fp_keyword',
          type: 'ai',
          icon: '',
          title: '关键词高亮',
          body: '提取关键词并在结果中标注高亮',
          x: CANVAS_BASE_X + CANVAS_SLOT_STEP * 3,
          y: yBot,
          configValues: { topK: '10', marker: '**', prompt: '' },
          schemaKey: 'schema-keyword-highlight',
        },
        {
          id: 'fp_join',
          type: 'control',
          icon: '',
          title: '汇合网关',
          body: '标记分叉分支汇合后继续执行',
          x: CANVAS_BASE_X + CANVAS_SLOT_STEP * 4,
          y,
          configValues: {},
          schemaKey: 'schema-join',
        },
        {
          id: 'fp_output',
          type: 'output',
          icon: '',
          title: '输出文件',
          body: '保存结果到文档库或直接下载',
          x: CANVAS_BASE_X + CANVAS_SLOT_STEP * 5,
          y,
          configValues: {
            outputMode: 'download',
            targetSpaceId: null,
            namingRule: '{original_file}_fork_out',
            outputFormat: 'md',
          },
          schemaKey: 'schema-library-output',
        },
      ],
      config: {
        runSettings: { ...DEFAULT_RUN_SETTINGS },
        graph: {
          edges: [
            _tplEdge('fp_e1', 'fp_input', 'fp_fork'),
            _tplEdge('fp_e2', 'fp_fork', 'fp_translate'),
            _tplEdge('fp_e3', 'fp_fork', 'fp_summary'),
            _tplEdge('fp_e4', 'fp_translate', 'fp_enhance'),
            _tplEdge('fp_e5', 'fp_enhance', 'fp_join'),
            _tplEdge('fp_e6', 'fp_summary', 'fp_keyword'),
            _tplEdge('fp_e7', 'fp_keyword', 'fp_join'),
            _tplEdge('fp_e8', 'fp_join', 'fp_output'),
          ],
        },
      },
    }
  }

  /** 条件分支：true / false 各 2 个处理节点 */
  function _buildConditionBranchTemplateWorkflow() {
    const y = CANVAS_BASE_Y
    const yTop = y - 72
    const yBot = y + 72
    return {
      id: CONDITION_BRANCH_TEMPLATE_ID,
      name: '条件分支示例',
      icon: '',
      time: '系统预设',
      type: 'template',
      nodes: [
        {
          id: 'cb_input',
          type: 'input',
          icon: '',
          title: '文档输入',
          body: '从文档库或本地上传 PDF / MD / TXT / DOCX / XLSX 等文件',
          x: CANVAS_BASE_X,
          y,
          configValues: { inputSource: 'library', spaceId: null, skipExisting: false },
          schemaKey: 'schema-document-input',
        },
        {
          id: 'cb_cond',
          type: 'control',
          icon: '',
          title: '条件分支',
          body: '按文档内容走 true / false 不同路径',
          x: CANVAS_BASE_X + CANVAS_SLOT_STEP,
          y,
          configValues: {
            conditionType: 'contains',
            matchText: '的',
            minLength: 0,
          },
          schemaKey: 'schema-condition',
        },
        {
          id: 'cb_translate',
          type: 'ai',
          icon: '',
          title: 'AI 翻译',
          body: '使用大模型进行智能翻译处理',
          x: CANVAS_BASE_X + CANVAS_SLOT_STEP * 2,
          y: yTop,
          configValues: { targetLanguage: '中文', prompt: '' },
          schemaKey: 'schema-translate',
        },
        {
          id: 'cb_enhance',
          type: 'ai',
          icon: '',
          title: '文本增强',
          body: '语法检查、润色和改写',
          x: CANVAS_BASE_X + CANVAS_SLOT_STEP * 3,
          y: yTop,
          configValues: { enhanceType: 'polish', style: 'formal', prompt: '' },
          schemaKey: 'schema-enhance-text',
        },
        {
          id: 'cb_summary',
          type: 'ai',
          icon: '',
          title: '内容提取',
          body: '生成摘要和提取关键要点',
          x: CANVAS_BASE_X + CANVAS_SLOT_STEP * 2,
          y: yBot,
          configValues: { extractType: 'summary', summaryLength: 'short', prompt: '' },
          schemaKey: 'schema-extract-summary',
        },
        {
          id: 'cb_keyword',
          type: 'ai',
          icon: '',
          title: '关键词高亮',
          body: '提取关键词并在结果中标注高亮',
          x: CANVAS_BASE_X + CANVAS_SLOT_STEP * 3,
          y: yBot,
          configValues: { topK: '8', marker: '**', prompt: '' },
          schemaKey: 'schema-keyword-highlight',
        },
        {
          id: 'cb_output',
          type: 'output',
          icon: '',
          title: '输出文件',
          body: '保存结果到文档库或直接下载',
          x: CANVAS_BASE_X + CANVAS_SLOT_STEP * 4,
          y,
          configValues: {
            outputMode: 'download',
            targetSpaceId: null,
            namingRule: '{original_file}_branch_out',
            outputFormat: 'md',
          },
          schemaKey: 'schema-library-output',
        },
      ],
      config: {
        runSettings: { ...DEFAULT_RUN_SETTINGS },
        graph: {
          edges: [
            _tplEdge('cb_e1', 'cb_input', 'cb_cond'),
            _tplEdge('cb_e2', 'cb_cond', 'cb_translate', 'true'),
            _tplEdge('cb_e3', 'cb_cond', 'cb_summary', 'false'),
            _tplEdge('cb_e4', 'cb_translate', 'cb_enhance'),
            _tplEdge('cb_e5', 'cb_enhance', 'cb_output'),
            _tplEdge('cb_e6', 'cb_summary', 'cb_keyword'),
            _tplEdge('cb_e7', 'cb_keyword', 'cb_output'),
          ],
        },
      },
    }
  }

  /** 循环处理：循环体内 2 个处理节点，按配置重复执行直至退出 */
  function _buildLoopTemplateWorkflow() {
    const y = CANVAS_BASE_Y
    const yBody = y + 120
    return {
      id: LOOP_TEMPLATE_ID,
      name: '循环处理示例',
      icon: '',
      time: '系统预设',
      type: 'template',
      nodes: [
        {
          id: 'lp_input',
          type: 'input',
          icon: '',
          title: '文档输入',
          body: '从文档库或本地上传 PDF / MD / TXT / DOCX / XLSX 等文件',
          x: CANVAS_BASE_X,
          y,
          configValues: { inputSource: 'library', spaceId: null, skipExisting: false },
          schemaKey: 'schema-document-input',
        },
        {
          id: 'lp_loop',
          type: 'control',
          icon: '',
          title: '循环处理',
          body: '重复执行循环体，直至满足退出条件',
          x: CANVAS_BASE_X + CANVAS_SLOT_STEP,
          y,
          configValues: {
            bodyNodeIds: ['lp_enhance', 'lp_keyword'],
            maxIterations: 5,
            exitCondition: 'unchanged',
            exitContainsText: '',
          },
          schemaKey: 'schema-loop',
        },
        {
          id: 'lp_enhance',
          type: 'ai',
          icon: '',
          title: '文本增强',
          body: '语法检查、润色和改写',
          x: CANVAS_BASE_X + CANVAS_SLOT_STEP,
          y: yBody,
          configValues: { enhanceType: 'polish', style: 'formal', prompt: '' },
          schemaKey: 'schema-enhance-text',
        },
        {
          id: 'lp_keyword',
          type: 'ai',
          icon: '',
          title: '关键词高亮',
          body: '提取关键词并在结果中标注高亮',
          x: CANVAS_BASE_X + CANVAS_SLOT_STEP * 2,
          y: yBody,
          configValues: { topK: '10', marker: '**', prompt: '' },
          schemaKey: 'schema-keyword-highlight',
        },
        {
          id: 'lp_output',
          type: 'output',
          icon: '',
          title: '输出文件',
          body: '保存结果到文档库或直接下载',
          x: CANVAS_BASE_X + CANVAS_SLOT_STEP * 2,
          y,
          configValues: {
            outputMode: 'download',
            targetSpaceId: null,
            namingRule: '{original_file}_loop_out',
            outputFormat: 'md',
          },
          schemaKey: 'schema-library-output',
        },
      ],
      config: {
        runSettings: { ...DEFAULT_RUN_SETTINGS },
        graph: {
          edges: [
            _tplEdge('lp_e1', 'lp_input', 'lp_loop'),
            _tplEdge('lp_e2', 'lp_loop', 'lp_output'),
          ],
        },
      },
    }
  }

  /** @deprecated 使用 seedBuiltinTemplates */
  function seedTranslationTemplate() {
    _seedBuiltinTemplate(_buildTranslationTemplateWorkflow())
    _rebuildTemplatesList()
  }

  // 加载翻译模板（预置文档翻译专用模板）
  function loadTranslationTemplate() {
    seedBuiltinTemplates()
    currentWorkflowId.value = TRANSLATION_TEMPLATE_ID
    workflowName.value = '文档翻译流'
    const wf = workflows.value[TRANSLATION_TEMPLATE_ID]
    _loadRunSettingsFromWorkflow(wf)
    _loadEdgesFromWorkflow(wf)
    canvasNodes.value = _mapNodesToCanvas(wf.nodes)
    selectedNodeId.value = null
    syncCanvasToWorkflowCache()
  }

  function _formatTime(dateStr) {
    if (!dateStr) return ''
    const date = new Date(dateStr)
    const now = new Date()
    const diff = now - date
    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(diff / 3600000)
    const days = Math.floor(diff / 86400000)
    if (minutes < 1) return '刚刚'
    if (minutes < 60) return `${minutes}分钟前`
    if (hours < 24) return `${hours}小时前`
    if (days === 1) return '昨天'
    if (days < 7) return `${days}天前`
    return date.toLocaleDateString('zh-CN')
  }

  // ==================== 导出 ====================

  return {
    // 状态
    currentWorkflowId,
    searchQuery,
    workflowName,
    selectedDocs,
    localFiles,
    selectedNodeId,
    selectedNode,
    nodeConfigs,
    nodeSchemas,
    workflows,
    templates,
    toolboxItems,
    canvasNodes,
    workflowEdges,
    hasCustomEdges,
    isEdgeEditMode,
    runSettings,
    isOrderEditMode,
    isBulkDeleteMode,
    bulkSelectedNodeIds,
    availableModels,
    availableLanguages,
    outputFormats,
    unsupportedFieldHints,
    isExecuting,
    executionProgress,
    executionLogs,
    outputFiles,
    nodeProgress,
    currentNodeId,
    currentNodeName,
    executionStatus,
    executionCurrentFileIndex,
    executionTotalFiles,
    executionCurrentFileName,
    // 计算属性
    currentWorkflow,
    customWorkflows,
    templateWorkflows,
    filteredCustomWorkflows,
    filteredTemplateWorkflows,
    hasActiveWorkflowSearch,
    totalDocCount,
    // API 加载
    loadWorkflows,
    loadTemplates,
    ensureWorkflowsLoaded,
    ensureInitialWorkflowSelection,
    loadModels,
    loadLanguages,
    loadOutputFormats,
    // 工作流操作
    selectWorkflow,
    createNewWorkflow,
    saveCurrentWorkflow,
    syncCanvasToWorkflowCache,
    deleteWorkflow,
    deleteWorkflows,
    setSearchQuery,
    clearSearchQuery,
    updateWorkflowName,
    updateRunSettings,
    loadTranslationTemplate,
    // 节点操作
    selectNode,
    updateNodePosition,
    moveNodeEarlier,
    moveNodeLater,
    enterOrderEditMode,
    exitOrderEditMode,
    toggleOrderEditMode,
    enterBulkDeleteMode,
    exitBulkDeleteMode,
    toggleBulkDeleteMode,
    addWorkflowEdge,
    removeWorkflowEdge,
    clearWorkflowEdges,
    enterEdgeEditMode,
    exitEdgeEditMode,
    toggleEdgeEditMode,
    toggleBulkSelectNode,
    clearBulkSelection,
    selectAllBulkNodes,
    deleteBulkSelectedNodes,
    reorderNodesByCanvasPosition,
    alignCanvasNodes,
    updateNodeConfig,
    addNode,
    addNodeAt,
    deleteNode,
    clearCanvas,
    getSchemaByKey,
    // 文档操作
    setSelectedDocs,
    addSelectedDoc,
    removeSelectedDoc,
    clearSelectedDocs,
    // 本地文件
    addLocalFiles,
    removeLocalFile,
    clearLocalFiles,
    // 执行
    executeWorkflow
  }
})
