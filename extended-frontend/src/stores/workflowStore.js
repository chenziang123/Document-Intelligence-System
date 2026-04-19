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

  // ==================== 动态数据（从 API 加载） ====================

  const workflows = ref({})
  const templates = ref([])
  const availableModels = ref([])
  const availableLanguages = ref([
    { code: 'en', label: '英语' },
    { code: 'zh', label: '中文' },
    { code: 'ja', label: '日语' },
    { code: 'ko', label: '韩语' },
    { code: 'fr', label: '法语' },
    { code: 'de', label: '德语' },
    { code: 'es', label: '西班牙语' },
    { code: 'ru', label: '俄语' },
    { code: 'ar', label: '阿拉伯语' },
    { code: 'pt', label: '葡萄牙语' },
    { code: 'it', label: '意大利语' },
  ])
  const outputFormats = ref([
    { code: 'pdf', label: 'PDF' },
    { code: 'md', label: 'Markdown' },
    { code: 'txt', label: 'TXT' },
  ])

  // ==================== 节点 Schema（无硬编码值，所有选项由 API 决定） ====================

  const nodeSchemas = ref({
    'schema-pdf-input': {
      icon: '📕', iconClass: 'input',
      title: 'PDF 输入', subtitle: '输入节点',
      fields: [
        { key: 'inputSource', label: '文档来源', type: 'select-source',
          options: [{ value: 'library', label: '从文档库选择' }, { value: 'local', label: '本地上传' }] },
        { key: 'spaceId', label: '选择文档库', type: 'library-selector' },
        { key: 'skipExisting', label: '跳过已处理文档', type: 'toggle' }
      ]
    },
    'schema-md-input': {
      icon: '📝', iconClass: 'input',
      title: 'MD 输入', subtitle: '输入节点',
      fields: [
        { key: 'inputSource', label: '文档来源', type: 'select-source',
          options: [{ value: 'library', label: '从文档库选择' }, { value: 'local', label: '本地上传' }] },
        { key: 'spaceId', label: '选择文档库', type: 'library-selector' }
      ]
    },
    'schema-docx-input': {
      icon: '📘', iconClass: 'input',
      title: 'DOCX 输入', subtitle: '输入节点',
      fields: [
        { key: 'inputSource', label: '文档来源', type: 'select-source',
          options: [{ value: 'library', label: '从文档库选择' }, { value: 'local', label: '本地上传' }] },
        { key: 'spaceId', label: '选择文档库', type: 'library-selector' }
      ]
    },
    'schema-xlsx-input': {
      icon: '📊', iconClass: 'input',
      title: 'XLSX 输入', subtitle: '输入节点',
      fields: [
        { key: 'inputSource', label: '文档来源', type: 'select-source',
          options: [{ value: 'library', label: '从文档库选择' }, { value: 'local', label: '本地上传' }] },
        { key: 'spaceId', label: '选择文档库', type: 'library-selector' },
        { key: 'sheetIndex', label: '工作表索引', type: 'input' },
        { key: 'hasHeader', label: '首行为表头', type: 'toggle' }
      ]
    },
    'schema-translate': {
      icon: '🌍', iconClass: 'ai',
      title: 'AI 翻译', subtitle: '翻译节点',
      fields: [
        { key: 'targetLanguage', label: '目标语言', type: 'language-selector' },
        { key: 'prompt', label: '翻译提示词', type: 'textarea' }
      ]
    },
    'schema-save': {
      icon: '💾', iconClass: 'output',
      title: '保存文件', subtitle: '输出节点',
      fields: [
        { key: 'savePath', label: '保存路径', type: 'input' },
        { key: 'outputFormat', label: '输出格式', type: 'format-selector' }
      ]
    },
    'schema-library-output': {
      icon: '📁', iconClass: 'output',
      title: '输出文件', subtitle: '输出节点',
      fields: [
        { key: 'outputMode', label: '输出模式', type: 'output-mode-select' },
        { key: 'targetSpaceId', label: '目标文档库', type: 'library-selector', conditionField: 'outputMode', conditionValue: 'library' },
        { key: 'namingRule', label: '文件命名规则', type: 'input', conditionField: 'outputMode', conditionValue: 'library' },
        { key: 'outputFormat', label: '输出格式', type: 'format-selector' },
        { key: 'notifyOnComplete', label: '完成通知', type: 'toggle' }
      ]
    }
  })

  // ==================== 工具箱（无硬编码值） ====================

  const toolboxItems = ref([
    {
      section: '输入',
      items: [
        {
          icon: '📕', name: 'PDF 输入', type: 'input', title: 'PDF 输入', body: '导入 PDF 文件',
          schemaKey: 'schema-pdf-input',
          schema: null // 动态从 nodeSchemas 获取
        },
        {
          icon: '📝', name: 'MD 输入', type: 'input', title: 'MD 输入', body: '导入 Markdown 文件',
          schemaKey: 'schema-md-input',
          schema: null
        },
        {
          icon: '📘', name: 'DOCX 输入', type: 'input', title: 'DOCX 输入', body: '导入 Word 文档',
          schemaKey: 'schema-docx-input',
          schema: null
        },
        {
          icon: '📊', name: 'XLSX 输入', type: 'input', title: 'XLSX 输入', body: '导入 Excel 表格数据',
          schemaKey: 'schema-xlsx-input',
          schema: null
        }
      ]
    },
    {
      section: '处理',
      items: [
        {
          icon: '🌍', name: 'AI 翻译', type: 'ai', title: 'AI 翻译', body: '使用大模型进行智能翻译处理',
          schemaKey: 'schema-translate',
          schema: null
        }
      ]
    },
    {
      section: '输出',
      items: [
        {
          icon: '💾', name: '保存文件', type: 'output', title: '保存文件', body: '保存处理结果到本地文件',
          schemaKey: 'schema-save',
          schema: null
        },
        {
          icon: '📁', name: '输出文件', type: 'output', title: '输出文件', body: '保存结果到文档库或直接下载',
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

  // ==================== 计算属性 ====================

  const currentWorkflow = computed(() =>
    currentWorkflowId.value ? workflows.value[currentWorkflowId.value] : null
  )

  const customWorkflows = computed(() =>
    Object.values(workflows.value).filter(w => w.type === 'custom')
  )

  const templateWorkflows = computed(() =>
    Object.values(workflows.value).filter(w => w.type === 'template')
  )

  const selectedNode = computed(() =>
    canvasNodes.value.find(n => n.id === selectedNodeId.value)
  )

  // 文档总数（库选 + 本地）
  const totalDocCount = computed(() =>
    selectedDocs.value.length + localFiles.value.length
  )

  // ==================== API 加载 ====================

  async function loadWorkflows() {
    try {
      const res = await workflowApi.getWorkflows()
      const list = res?.workflows || []
      workflows.value = {}
      list.forEach(w => {
        workflows.value[w.id] = {
          id: w.id,
          name: w.name,
          icon: w.icon || '🔧',
          time: _formatTime(w.updated_at || w.created_at),
          type: w.type || 'custom',
          nodes: w.nodes || [],           // 完整节点列表（含 configValues、schemaKey）
          config: w.config || {},
          created_at: w.created_at || '',
          updated_at: w.updated_at || '',
        }
      })
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
        icon: t.icon || '📄',
        description: t.description || '',
        type: 'template',
        time: '系统预设',
        nodes: t.nodes || [],
        config: t.config || {}
      }))
      // 合并到 workflows
      templates.value.forEach(t => {
        workflows.value[t.id] = t
      })
    } catch (e) {
      console.error('loadTemplates error:', e)
    }
  }

  async function loadModels() {
    try {
      const res = await workflowApi.getModels()
      availableModels.value = res?.models || []
    } catch (e) {
      console.error('loadModels error:', e)
    }
  }

  // ==================== 工作流操作 ====================

  function selectWorkflow(workflowId) {
    currentWorkflowId.value = workflowId
    const wf = workflows.value[workflowId]

    if (!wf) {
      workflowName.value = '未命名'
      canvasNodes.value = []
      selectedNodeId.value = null
      return
    }

    // 模板工作流（type=template）：nodes 已随 loadTemplates 完整加载，无需调 API
    if (wf.type === 'template') {
      workflowName.value = wf.name
      canvasNodes.value = (wf.nodes || []).map((n, i) => ({
        ...n,
        x: n.x ?? (30 + i * 260),
        y: n.y ?? 160,
        configValues: n.configValues || {},
        schema: n.schema || nodeSchemas.value[n.schemaKey] || null,
      }))
      selectedNodeId.value = null
      return
    }

    // 用户自定义工作流：从数据库获取完整节点
    workflowApi.getWorkflow(workflowId).then(res => {
      const wfData = res || {}
      workflowName.value = wfData.name || wf.name || '未命名'
      canvasNodes.value = (wfData.nodes || []).map((n, i) => ({
        ...n,
        x: n.x ?? (30 + i * 260),
        y: n.y ?? 160,
        configValues: n.configValues || {},
        schema: n.schema || nodeSchemas.value[n.schemaKey] || null,
      }))
      selectedNodeId.value = null
    }).catch(() => {
      workflowName.value = wf.name || '未命名'
      canvasNodes.value = []
    })
  }

  async function createNewWorkflow() {
    const id = 'wf_' + Date.now()
    const name = '新建工作流'
    workflows.value[id] = {
      id,
      name,
      icon: '🔧',
      time: '刚刚',
      type: 'custom',
      nodes: [],
      config: {},
    }
    currentWorkflowId.value = id
    workflowName.value = name
    canvasNodes.value = []
    selectedNodeId.value = null
    // 立即保存到后端
    try {
      await workflowApi.saveWorkflow({
        id,
        name,
        icon: '🔧',
        type: 'custom',
        nodes: [],
        config: {},
      })
    } catch (e) {
      console.error('createNewWorkflow save error:', e)
    }
  }

  async function saveCurrentWorkflow() {
    if (!currentWorkflowId.value) return
    const wf = workflows.value[currentWorkflowId.value]
    if (!wf) return
    // 节点要保存完整配置：id, type, title, icon, body, schemaKey, configValues
    wf.nodes = canvasNodes.value.map(({ x, y, schema, ...rest }) => rest)
    try {
      await workflowApi.saveWorkflow({
        id: wf.id,
        name: wf.name,
        icon: wf.icon || '🔧',
        type: 'custom',
        nodes: wf.nodes,
        config: wf.config || {},
      })
      wf.time = '刚刚'
    } catch (e) {
      console.error('saveCurrentWorkflow error:', e)
    }
  }

  async function deleteWorkflow(workflowId) {
    try {
      await workflowApi.deleteWorkflow(workflowId)
    } catch (e) {
      console.error('deleteWorkflow error:', e)
    }
    delete workflows.value[workflowId]
    if (currentWorkflowId.value === workflowId) {
      const keys = Object.keys(workflows.value)
      currentWorkflowId.value = keys.length > 0 ? keys[0] : null
      if (currentWorkflowId.value) {
        selectWorkflow(currentWorkflowId.value)
      } else {
        createNewWorkflow()
      }
    }
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
    }
  }

  function updateNodeConfig(nodeId, key, value) {
    const node = canvasNodes.value.find(n => n.id === nodeId)
    if (node) {
      if (!node.configValues) node.configValues = {}
      node.configValues[key] = value

      // 特殊处理：inputSource 变化时清空对应数据
      if (key === 'inputSource') {
        if (value === 'library') {
          node.configValues.localFiles = []
        } else {
          node.configValues.spaceId = null
          selectedDocs.value = []
        }
      }
    }
  }

  function addNode(toolboxItem) {
    const schema = nodeSchemas.value[toolboxItem.schemaKey] || null
    const id = 'n_' + Date.now()
    const lastNode = canvasNodes.value[canvasNodes.value.length - 1]
    const x = lastNode ? lastNode.x + 260 : 30
    const y = lastNode ? lastNode.y : 160
    const newNode = {
      id,
      type: toolboxItem.type,
      icon: toolboxItem.icon,
      title: toolboxItem.title,
      body: toolboxItem.body,
      x,
      y,
      configValues: {},
      schemaKey: toolboxItem.schemaKey,
      schema
    }
    canvasNodes.value.push(newNode)
    selectedNodeId.value = id
    return id
  }

  function deleteNode(nodeId) {
    const idx = canvasNodes.value.findIndex(n => n.id === nodeId)
    if (idx === -1) return
    canvasNodes.value.splice(idx, 1)
    if (selectedNodeId.value === nodeId) {
      selectedNodeId.value = canvasNodes.value.length > 0
        ? canvasNodes.value[Math.min(idx, canvasNodes.value.length - 1)].id
        : null
    }
  }

  function clearCanvas() {
    canvasNodes.value = []
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

  async function executeWorkflow() {
    if (isExecuting.value) return
    isExecuting.value = true
    executionProgress.value = 0
    executionLogs.value = []

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
          configValues: n.configValues
        })),
        docs: selectedDocs.value.map(d => d.id),
        localFiles: localFilePayloads
      }

      const res = await workflowApi.execute(params)
      const executionId = res?.execution_id

      // 轮询执行状态
      await pollExecution(executionId)
    } catch (e) {
      executionLogs.value.push({ type: 'error', message: e.message })
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
        if (status === 'completed') {
          executionProgress.value = 100
          // 追加 output_files
          if (res.output_files && res.output_files.length > 0) {
            res.output_files.forEach(f => {
              executionLogs.value.push({ type: 'done', message: `📥 ${f.name}` })
            })
            outputFiles.value = res.output_files
          }
          executionLogs.value.push({ type: 'done', message: `全部完成，共 ${res.output_files?.length || 0} 个输出文件` })
          break
        } else if (status === 'failed') {
          executionLogs.value.push({ type: 'error', message: res?.error || '执行失败' })
          break
        } else {
          executionProgress.value = res.progress || Math.round((res.current_file_index / Math.max(res.total_files, 1)) * 100)
          // 只追加新日志（服务器返回完整历史）
          if (res.logs && res.logs.length > lastLogCount) {
            const newLogs = res.logs.slice(lastLogCount)
            newLogs.forEach(log => executionLogs.value.push(log))
            lastLogCount = res.logs.length
          }
        }
      } catch (e) {
        executionLogs.value.push({ type: 'error', message: e.message })
        break
      }
      await new Promise(r => setTimeout(r, 2000))
      polls++
    }
    if (polls >= maxPolls) {
      executionLogs.value.push({ type: 'error', message: '执行超时' })
    }
  }

  // ==================== 辅助方法 ====================

  function setSearchQuery(query) {
    searchQuery.value = query
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
    return nodeSchemas.value[schemaKey] || null
  }

  // 加载翻译模板（预置文档翻译专用模板）
  function loadTranslationTemplate() {
    const templateId = 'tpl_translation'
    workflows.value[templateId] = {
      id: templateId,
      name: '文档翻译流',
      icon: '🌍',
      time: '系统预设',
      type: 'template',
      nodes: [
        {
          id: 'n_pdf',
          type: 'input',
          icon: '📕',
          title: 'PDF 输入',
          body: '导入 PDF 文件',
          configValues: {
            inputSource: 'library',
            spaceId: null,
            skipExisting: false
          },
          schemaKey: 'schema-pdf-input',
          schema: nodeSchemas.value['schema-pdf-input']
        },
        {
          id: 'n_translate',
          type: 'ai',
          icon: '🌍',
          title: 'AI 翻译',
          body: '使用大模型进行智能翻译处理',
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
          icon: '📁',
          title: '输出文件',
          body: '保存结果到文档库或直接下载',
          configValues: {
            outputMode: 'download',
            targetSpaceId: null,
            namingRule: '{original_name}_translated',
            outputFormat: 'pdf',
            notifyOnComplete: true
          },
          schemaKey: 'schema-library-output',
          schema: nodeSchemas.value['schema-library-output']
        }
      ],
      config: {}
    }
    currentWorkflowId.value = templateId
    workflowName.value = '文档翻译流'
    canvasNodes.value = [
      {
        ...workflows.value[templateId].nodes[0], x: 30, y: 160
      },
      {
        ...workflows.value[templateId].nodes[1], x: 290, y: 160
      },
      {
        ...workflows.value[templateId].nodes[2], x: 550, y: 160
      }
    ]
    selectedNodeId.value = null
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
    availableModels,
    availableLanguages,
    outputFormats,
    isExecuting,
    executionProgress,
    executionLogs,
    outputFiles,
    // 计算属性
    currentWorkflow,
    customWorkflows,
    templateWorkflows,
    totalDocCount,
    // API 加载
    loadWorkflows,
    loadTemplates,
    loadModels,
    // 工作流操作
    selectWorkflow,
    createNewWorkflow,
    saveCurrentWorkflow,
    deleteWorkflow,
    setSearchQuery,
    updateWorkflowName,
    loadTranslationTemplate,
    // 节点操作
    selectNode,
    updateNodePosition,
    updateNodeConfig,
    addNode,
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
