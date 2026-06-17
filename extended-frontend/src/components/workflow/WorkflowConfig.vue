<script setup>
import { ref, computed, onMounted } from 'vue'
import { MousePointerClick } from 'lucide-vue-next'
import { useWorkflowStore } from '../../stores/workflowStore'
import { useLibraryStore } from '../../stores/libraryStore'

const emit = defineEmits(['openBatchModal'])
const workflowStore = useWorkflowStore()
const libraryStore = useLibraryStore()

const activeTab = ref('node') // 'node' | 'wf'
const fileInputRef = ref(null)
const isLoadingLibrary = ref(false)
const newSpaceName = ref('')
const isSaving = ref(false)

// 加载文档库空间
onMounted(async () => {
  try {
    await Promise.all([
      libraryStore.loadSpaces(),
      workflowStore.loadModels(),
      workflowStore.loadLanguages(),
      workflowStore.loadOutputFormats(),
    ])
  } catch (e) {
    console.error('initial load error:', e)
  }
})

function openBatchModal() {
  emit('openBatchModal')
}

// ==================== Tab 切换 ====================
function switchTab(tab) {
  activeTab.value = tab
}

// ==================== 节点配置更新 ====================
function updateConfig(key, value) {
  const nodeId = workflowStore.selectedNodeId
  if (nodeId) {
    workflowStore.updateNodeConfig(nodeId, key, value)
  }
}

function toggleMulti(key, option, checked) {
  const nodeId = workflowStore.selectedNodeId
  if (!nodeId) return
  const cfg = workflowStore.selectedNode?.configValues
  if (!cfg) return
  const current = Array.isArray(cfg[key]) ? [...cfg[key]] : []
  if (checked) {
    if (!current.includes(option)) current.push(option)
  } else {
    const idx = current.indexOf(option)
    if (idx > -1) current.splice(idx, 1)
  }
  updateConfig(key, current)
}

// ==================== 获取字段值 ====================
function getFieldValue(field, node) {
  if (!node || !node.configValues) return null
  return node.configValues[field.key] ?? null
}

function optionValue(opt) {
  if (opt && typeof opt === 'object') return opt.value ?? opt.label ?? ''
  return opt
}

function optionLabel(opt) {
  if (opt && typeof opt === 'object') return opt.label ?? opt.value ?? ''
  return opt
}

function normalizeFieldValue(value) {
  if (value && typeof value === 'object') return value.value ?? value.label ?? null
  return value
}

function getMultiFieldValues(field, node) {
  const raw = getFieldValue(field, node)
  if (!Array.isArray(raw)) return []
  return raw.map(v => normalizeFieldValue(v))
}

function getNodeMultiFieldValues(field, node) {
  const raw = getFieldValue(field, node)
  return Array.isArray(raw) ? raw.map(String) : []
}

function toggleNodeMulti(fieldKey, targetNodeId, checked) {
  const nodeId = workflowStore.selectedNodeId
  if (!nodeId) return
  const cfg = workflowStore.selectedNode?.configValues
  const current = Array.isArray(cfg?.[fieldKey]) ? [...cfg[fieldKey]] : []
  if (checked) {
    if (!current.includes(targetNodeId)) current.push(targetNodeId)
  } else {
    const idx = current.indexOf(targetNodeId)
    if (idx > -1) current.splice(idx, 1)
  }
  updateConfig(fieldKey, current)
}

/** 循环节点可引用的处理节点 */
const selectableProcessNodes = computed(() => {
  const excludeId = workflowStore.selectedNodeId
  return workflowStore.canvasNodes.filter(
    n => n.id !== excludeId && n.type !== 'input' && n.type !== 'output' && n.type !== 'control'
  )
})

/** 分叉网关可选择的汇合节点 */
const selectableJoinNodes = computed(() => {
  const excludeId = workflowStore.selectedNodeId
  return workflowStore.canvasNodes.filter(
    n => n.id !== excludeId && n.schemaKey === 'schema-join'
  )
})

function selectSingleNodeField(fieldKey, targetNodeId) {
  updateConfig(fieldKey, targetNodeId || '')
}

// ==================== Schema 获取 ====================
function getNodeSchema(node) {
  if (!node) return null
  return node.schema || workflowStore.getSchemaByKey(node.schemaKey) || null
}

function getFieldUnsupportedHint(field) {
  if (!field?.key) return ''
  return workflowStore.unsupportedFieldHints?.[field.key] || ''
}

// ==================== 文档库选择相关 ====================

// 切换输出模式
function handleOutputModeChange(value) {
  updateConfig('outputMode', value)
  if (value === 'download') {
    // 切到下载模式时，清空文档库相关配置
    updateConfig('targetSpaceId', null)
    updateConfig('namingRule', '')
  }
}

async function handleCreateNewSpace() {
  const name = newSpaceName.value.trim()
  if (!name) return
  try {
    const space = await libraryStore.createSpace(name)
    updateConfig('targetSpaceId', space.id)
    newSpaceName.value = ''
  } catch (e) {
    console.error('createSpace error:', e)
  }
}

// 切换输入来源
function handleInputSourceChange(value) {
  updateConfig('inputSource', value)
  if (value === 'local') {
    updateConfig('spaceId', null)
    workflowStore.clearSelectedDocs()
  } else {
    workflowStore.clearLocalFiles()
  }
}

// 下载输出文件
function downloadFile(file) {
  let url
  if (file.blob_name) {
    url = `/api/files/download-by-blob?blob_name=${encodeURIComponent(file.blob_name)}`
  } else {
    url = `/api/files/download?path=${encodeURIComponent(file.path)}`
  }
  const a = document.createElement('a')
  a.href = url
  a.download = file.name
  a.click()
}

// 选择文档库空间
function handleSpaceChange(spaceId) {
  updateConfig('spaceId', spaceId)
  if (spaceId) {
    loadDocsForSpace(spaceId)
  } else {
    workflowStore.clearSelectedDocs()
  }
}

async function loadDocsForSpace(spaceId) {
  isLoadingLibrary.value = true
  try {
    await libraryStore.loadDocs(spaceId)
    // 自动选中所有文档
    const allDocIds = libraryStore.currentDocs.map(d => d.id)
    workflowStore.setSelectedDocs([...libraryStore.currentDocs])
  } finally {
    isLoadingLibrary.value = false
  }
}

// 切换文档选中
function handleDocToggle(docId) {
  const doc = libraryStore.currentDocs.find(d => d.id === docId)
  if (!doc) return
  if (workflowStore.selectedDocs.find(d => d.id === docId)) {
    workflowStore.removeSelectedDoc(docId)
  } else {
    workflowStore.addSelectedDoc(doc)
  }
}

// ==================== 本地上传 ====================
function handleFileSelect(event) {
  const files = Array.from(event.target.files || [])
  if (files.length > 0) {
    workflowStore.addLocalFiles(files)
  }
  // 清空 input 以便重复选择同一文件
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

function handleDrop(event) {
  event.preventDefault()
  const files = Array.from(event.dataTransfer?.files || [])
  const allowed = files.filter(f =>
    ['application/pdf', 'text/markdown', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
     'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
     'text/plain'].includes(f.type) ||
    f.name.endsWith('.md') || f.name.endsWith('.txt')
  )
  if (allowed.length > 0) {
    workflowStore.addLocalFiles(allowed)
  }
}

function handleDragOver(event) {
  event.preventDefault()
}

// ==================== 语言/格式选择 ====================
function handleLanguageChange(langCode) {
  updateConfig('targetLanguage', langCode)
}

function handleFormatChange(formatCode) {
  updateConfig('outputFormat', formatCode)
}

function _formatSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

// ==================== 目标文档库选择 ====================
function handleTargetSpaceChange(spaceId) {
  if (spaceId === '__new__') {
    // 显示新建表单，清空选择
    updateConfig('targetSpaceId', null)
    return
  }
  updateConfig('targetSpaceId', spaceId)
}

// ==================== 执行工作流 ====================
async function handleExecute() {
  await workflowStore.executeWorkflow()
}

// ==================== 全局设置 ====================
async function handleSaveWorkflow() {
  if (isSaving.value) return
  isSaving.value = true
  try {
    await workflowStore.saveCurrentWorkflow()
  } finally {
    isSaving.value = false
  }
}

function handleGlobalInputSource(value) {
  // 全局设置也写入第一个输入节点的配置
  const firstInputNode = workflowStore.canvasNodes.find(n => n.type === 'input')
  if (firstInputNode) {
    workflowStore.updateNodeConfig(firstInputNode.id, 'inputSource', value)
  }
}

// 当前选中的文档（来自 store）
const displayedDocs = computed(() => workflowStore.selectedDocs)
const displayedLocalFiles = computed(() => workflowStore.localFiles)
const currentInputSource = computed(() => {
  const node = workflowStore.selectedNode
  if (!node) return null
  return getFieldValue({ key: 'inputSource' }, node) || 'library'
})

const currentSpaceId = computed(() => {
  const node = workflowStore.selectedNode
  if (!node) return null
  return getFieldValue({ key: 'spaceId' }, node) || null
})

const inputDocCount = computed(() => {
  if (currentInputSource.value === 'local') {
    return displayedLocalFiles.value.length
  }
  return displayedDocs.value.length
})

const isInputNode = computed(() => workflowStore.selectedNode?.type === 'input')
const isOutputNode = computed(() => workflowStore.selectedNode?.type === 'output')

const hasSelectedInputSummary = computed(() =>
  displayedDocs.value.length > 0 || displayedLocalFiles.value.length > 0
)

const currentOutputMode = computed(() => {
  const node = workflowStore.selectedNode
  if (!node) return 'download'
  return getFieldValue({ key: 'outputMode' }, node) || 'download'
})

const currentTargetSpaceId = computed(() => {
  const node = workflowStore.selectedNode
  if (!node) return null
  return getFieldValue({ key: 'targetSpaceId' }, node) || null
})

const currentLanguage = computed(() => {
  const node = workflowStore.selectedNode
  if (!node) return null
  return getFieldValue({ key: 'targetLanguage' }, node) || null
})

const currentFormat = computed(() => {
  const node = workflowStore.selectedNode
  if (!node) return null
  return getFieldValue({ key: 'outputFormat' }, node) || workflowStore.outputFormats[0]?.code
})

/** 是否显示该 schema 字段（支持 conditionField、dependsOn、arrayIncludes） */
function isFieldVisible(field, node) {
  if (!node) return false
  if (field.conditionField != null && field.conditionValue !== undefined) {
    const actual = getFieldValue({ key: field.conditionField }, node)
    if (actual !== field.conditionValue) return false
  }
  const raw = field.dependsOn
  if (!raw) return true
  const deps = Array.isArray(raw) ? raw : [raw]
  for (const dep of deps) {
    const val = getFieldValue({ key: dep.field }, node)
    if (dep.arrayIncludes != null) {
      const arr = Array.isArray(val) ? val : val != null ? [val] : []
      if (!arr.includes(dep.arrayIncludes)) return false
    } else if (dep.values !== undefined && Array.isArray(dep.values)) {
      if (!dep.values.includes(val)) return false
    } else if (dep.value !== undefined && val !== dep.value) {
      return false
    }
  }
  return true
}

/** 根据 dynamicBy 字段解析标签、占位符、说明（用于分割参数等联动文案） */
function getFieldDynamicKey(field, node) {
  const by = field.dynamicBy
  if (!by || !node) return null
  return getFieldValue({ key: by }, node)
}

function getFieldLabel(field, node) {
  const key = getFieldDynamicKey(field, node)
  if (key != null && field.labelMap?.[key]) return field.labelMap[key]
  return field.label || ''
}

function getFieldPlaceholder(field, node) {
  const key = getFieldDynamicKey(field, node)
  if (key != null && field.placeholderMap?.[key]) return field.placeholderMap[key]
  return field.placeholder || ''
}

function getFieldHint(field, node) {
  const key = getFieldDynamicKey(field, node)
  if (key != null && field.hintMap?.[key]) return field.hintMap[key]
  return field.hint || ''
}

const filteredFields = computed(() => {
  const schema = getNodeSchema(workflowStore.selectedNode)
  if (!schema?.fields) return []
  return schema.fields.filter(f => isFieldVisible(f, workflowStore.selectedNode))
})

/** 当前选中节点在执行顺序（canvasNodes 序列）中的索引 */
const selectedStepOrderIndex = computed(() => {
  const id = workflowStore.selectedNodeId
  if (!id) return -1
  return workflowStore.canvasNodes.findIndex(n => n.id === id)
})

const executionButtonText = computed(() => {
  const node = workflowStore.selectedNode
  if (!node) return '执行'
  
  const title = node.title || node.type
  
  // 根据节点标题生成对应的按钮文本
  const verbMap = {
    'AI 翻译': '翻译',
    '内容提取': '提取',
    '数据抽取': '抽取',
    '实体提取': '提取',
    '数据处理': '处理',
    '数据清洗': '清洗',
    '表格提取': '提取',
    '数据汇总': '汇总',
    '内容分析': '分析',
    '文本增强': '增强',
    '格式转换': '转换',
    '文档分割': '分割',
    '保存 Excel': '导出',
    '保存文本': '保存'
  }
  
  const verb = verbMap[title] || '处理'
  return `开始${verb}`
})

function nodeStatusText(status) {
  const map = {
    pending: '等待中',
    running: '执行中',
    completed: '已完成',
    failed: '失败'
  }
  return map[status] || '未开始'
}
</script>

<template>
  <div class="workflow-config-panel">

    <!-- Tab Bar -->
    <div class="config-tabs">
      <button
        class="config-tab"
        :class="{ active: activeTab === 'node' }"
        @click="switchTab('node')"
      >
        节点配置
      </button>
      <button
        class="config-tab"
        :class="{ active: activeTab === 'wf' }"
        @click="switchTab('wf')"
      >
        全局设置
      </button>
    </div>

    <!-- Panel Content -->
    <div class="config-content">

      <!-- ======== 全局设置 ======== -->
      <div v-if="activeTab === 'wf'" class="config-section">
        <div class="node-config-header">
          <div class="node-config-icon-wrap wf-settings-icon" aria-hidden="true" />
          <div>
            <div class="node-config-title">{{ workflowStore.workflowName }}</div>
            <div class="node-config-subtitle">全局配置 · {{ workflowStore.canvasNodes.length }} 个节点</div>
          </div>
        </div>

        <div class="config-group">
          <div class="config-group-label">基础信息</div>
          <div class="field-row">
            <div class="field">
              <label class="field-label">工作流名称</label>
              <input
                class="config-input"
                :value="workflowStore.workflowName"
                @input="workflowStore.updateWorkflowName($event.target.value)"
              />
            </div>
          </div>
          <div class="field-row">
            <div class="field">
              <label class="field-label">输入文档库</label>
              <select
                class="config-select"
                :value="libraryStore.currentSpaceId || ''"
                @change="handleSpaceChange($event.target.value)"
              >
                <option value="">-- 选择文档库 --</option>
                <option
                  v-for="space in libraryStore.spaces"
                  :key="space.id"
                  :value="space.id"
                >{{ space.name }}</option>
              </select>
            </div>
            <div class="field">
              <label class="field-label">输出文档库</label>
              <select
                class="config-select"
                :value="currentTargetSpaceId || ''"
                @change="handleTargetSpaceChange($event.target.value)"
              >
                <option value="">-- 选择目标库 --</option>
                <option
                  v-for="space in libraryStore.spaces"
                  :key="space.id"
                  :value="space.id"
                >{{ space.name }}</option>
              </select>
            </div>
          </div>
        </div>

        <div class="config-group">
          <div class="config-group-label">运行设置</div>
          <p class="run-settings-hint">
            多文件批量处理已支持。并发数量大于 1 时将并行处理多个文件；设为 1 则逐个串行处理。
          </p>
          <div class="field">
            <label class="field-label">并发数量</label>
            <div class="range-row">
              <input
                type="range"
                min="1"
                max="10"
                class="range-input"
                :value="workflowStore.runSettings.concurrentLimit"
                @input="workflowStore.updateRunSettings('concurrentLimit', Number($event.target.value))"
              />
              <span class="range-val">{{ workflowStore.runSettings.concurrentLimit }} 个文档/批</span>
            </div>
          </div>
          <div class="field field-toggle-row">
            <label class="field-label">出错时继续</label>
            <p class="field-desc">关闭后，任一批次中有文件失败将停止后续处理。</p>
            <div
              class="toggle-switch"
              :class="{ on: workflowStore.runSettings.continueOnError }"
              @click="workflowStore.updateRunSettings('continueOnError', !workflowStore.runSettings.continueOnError)"
            ></div>
          </div>
          <div class="field field-toggle-row">
            <label class="field-label">出错通知</label>
            <p class="field-desc">开启后，文件处理失败时会在执行日志中突出提示。</p>
            <div
              class="toggle-switch"
              :class="{ on: workflowStore.runSettings.notifyOnError }"
              @click="workflowStore.updateRunSettings('notifyOnError', !workflowStore.runSettings.notifyOnError)"
            ></div>
          </div>
        </div>

        <!-- 保存按钮 -->
        <button
          class="save-wf-btn"
          :class="{ saving: isSaving }"
          :disabled="isSaving"
          @click="handleSaveWorkflow"
        >
          <span v-if="isSaving" class="save-spinner"></span>
          <span>{{ isSaving ? '保存中...' : '保存工作流' }}</span>
        </button>
      </div>

      <!-- ======== 节点配置 ======== -->
      <div v-else-if="activeTab === 'node' && workflowStore.selectedNode" class="config-section node-config-anim">

        <!-- Step Indicator -->
        <div class="step-indicator">
          <div
            v-for="(node, i) in workflowStore.canvasNodes"
            :key="node.id"
            class="step-dot-wrap"
          >
            <div
              class="step-dot"
              :class="{
                ['type-' + node.type]: true,
                'step-done': i < workflowStore.canvasNodes.findIndex(n => n.id === workflowStore.selectedNodeId),
                'step-active': workflowStore.selectedNodeId === node.id
              }"
            ></div>
            <div v-if="i < workflowStore.canvasNodes.length - 1" class="step-connector"></div>
          </div>
        </div>

        <!-- Node Header -->
        <div class="node-config-header">
          <div class="node-config-icon-wrap" :class="workflowStore.selectedNode.type" aria-hidden="true" />
          <div>
            <div class="node-config-title">{{ workflowStore.selectedNode.title }}</div>
            <div class="node-config-subtitle">{{ getNodeSchema(workflowStore.selectedNode)?.subtitle }}</div>
            <p v-if="workflowStore.selectedNode.body" class="node-config-desc">{{ workflowStore.selectedNode.body }}</p>
          </div>
        </div>

        <!-- 执行顺序（与画布坐标独立，决定上下游与运行步骤） -->
        <div v-if="workflowStore.canvasNodes.length > 1" class="config-group step-order-group">
          <div class="config-group-label">执行顺序</div>
          <p class="step-order-hint">
            平时可自由拖拽摆放节点。需快速调整执行顺序时，点击画布上方「编辑顺序」，拖拽后松手即可；画布太乱可点「自动对齐」整理。
          </p>
          <div class="step-order-row">
            <button
              type="button"
              class="step-order-btn"
              :disabled="selectedStepOrderIndex <= 0"
              title="前移：更早执行"
              @click="workflowStore.moveNodeEarlier(workflowStore.selectedNodeId)"
            >前移</button>
            <span class="step-order-pos">第 {{ selectedStepOrderIndex + 1 }} / {{ workflowStore.canvasNodes.length }} 步</span>
            <button
              type="button"
              class="step-order-btn"
              :disabled="selectedStepOrderIndex < 0 || selectedStepOrderIndex >= workflowStore.canvasNodes.length - 1"
              title="后移：更晚执行"
              @click="workflowStore.moveNodeLater(workflowStore.selectedNodeId)"
            >后移</button>
          </div>
        </div>

        <!-- ===== 输入文件（仅输入节点，来源与选文件合一） ===== -->
        <div v-if="isInputNode" class="config-group doc-input-group">
          <div class="config-group-label">
            输入文件
            <span class="doc-count-badge">{{ inputDocCount }} 个</span>
          </div>

          <div class="doc-input-card">
            <div class="source-tabs doc-source-tabs">
              <button
                type="button"
                class="source-tab"
                :class="{ active: currentInputSource === 'library' }"
                @click="handleInputSourceChange('library')"
              >从文档库选择</button>
              <button
                type="button"
                class="source-tab"
                :class="{ active: currentInputSource === 'local' }"
                @click="handleInputSourceChange('local')"
              >本地上传</button>
            </div>

            <div v-if="currentInputSource === 'library'" class="doc-panel">
              <div class="doc-panel-field">
                <label class="field-label">文档库</label>
                <select
                  class="config-select"
                  :value="currentSpaceId || ''"
                  @change="handleSpaceChange($event.target.value)"
                >
                  <option value="">请选择文档库</option>
                  <option
                    v-for="space in libraryStore.spaces"
                    :key="space.id"
                    :value="space.id"
                  >{{ space.name }}</option>
                </select>
              </div>

              <div v-if="isLoadingLibrary" class="doc-loading">
                <span class="loading-dots-sm"><span></span><span></span><span></span></span> 加载文档...
              </div>
              <div v-else-if="!currentSpaceId" class="doc-empty-hint">
                请先选择文档库，再勾选要处理的文件
              </div>
              <div v-else-if="libraryStore.currentDocs.length === 0" class="doc-empty-hint">
                该文档库暂无文档，请先在文档库页面上传
              </div>
              <div v-else class="doc-list">
                <div
                  v-for="doc in libraryStore.currentDocs"
                  :key="doc.id"
                  class="doc-list-item"
                  :class="{ selected: workflowStore.selectedDocs.find(d => d.id === doc.id) }"
                  @click="handleDocToggle(doc.id)"
                >
                  <div class="doc-list-check">
                    <span v-if="workflowStore.selectedDocs.find(d => d.id === doc.id)" class="check-mark" />
                  </div>
                  <span class="doc-list-icon" aria-hidden="true" />
                  <span class="doc-list-name">{{ doc.name }}</span>
                  <span class="doc-list-size">{{ doc.size }}</span>
                </div>
              </div>
            </div>

            <div v-else class="doc-panel">
              <div
                class="upload-zone"
                @click="fileInputRef?.click()"
                @drop="handleDrop"
                @dragover="handleDragOver"
              >
                <input
                  ref="fileInputRef"
                  type="file"
                  accept=".pdf,.md,.docx,.doc,.xlsx,.txt"
                  multiple
                  style="display:none"
                  @change="handleFileSelect"
                />
                <div class="upload-zone-icon" aria-hidden="true" />
                <div class="upload-zone-text">点击或拖拽文件到此处</div>
                <div class="upload-zone-hint">支持 PDF、Markdown、Word、Excel、TXT</div>
              </div>

              <div v-if="displayedLocalFiles.length > 0" class="local-files-list">
                <div
                  v-for="file in displayedLocalFiles"
                  :key="file.id"
                  class="local-file-item"
                >
                  <span class="local-file-icon" aria-hidden="true" />
                  <span class="local-file-name">{{ file.name }}</span>
                  <span class="local-file-size">{{ _formatSize(file.size) }}</span>
                  <button
                    type="button"
                    class="local-file-remove"
                    @click="workflowStore.removeLocalFile(file.id)"
                  >×</button>
                </div>
              </div>
              <div v-else class="doc-empty-hint doc-empty-inline">
                尚未添加文件
              </div>
            </div>
          </div>
        </div>

        <!-- 已选文档（输出节点：置于输出配置上方，避免挤占按钮邻近区域） -->
        <div v-if="isOutputNode && hasSelectedInputSummary" class="config-group">
          <div class="config-group-label">
            已选文档 <span class="doc-count-badge">{{ displayedDocs.length + displayedLocalFiles.length }} 个</span>
          </div>
          <div class="selected-docs-list">
            <div
              v-for="doc in displayedDocs"
              :key="doc.id"
              class="selected-doc-item"
            >
              <span class="selected-doc-icon" aria-hidden="true" />
              <span class="selected-doc-name">{{ doc.name }}</span>
              <span class="selected-doc-size">{{ doc.size }}</span>
            </div>
            <div
              v-for="file in displayedLocalFiles"
              :key="file.id"
              class="selected-doc-item"
            >
              <span class="selected-doc-icon" aria-hidden="true" />
              <span class="selected-doc-name">{{ file.name }}</span>
              <span class="selected-doc-size">{{ _formatSize(file.size) }}</span>
            </div>
          </div>
        </div>

        <!-- Fields -->
        <div v-if="filteredFields.length > 0" class="config-group" :class="{ 'output-config-group': isOutputNode }">
          <div class="config-group-label">{{ isOutputNode ? '输出文件' : '参数配置' }}</div>

          <template v-for="(field, fIdx) in filteredFields" :key="field.key || ('static-' + fIdx)">

            <!-- ===== 静态说明 ===== -->
            <div v-if="field.type === 'static'" class="field field-static-row">
              <p class="field-static-text">{{ field.text }}</p>
            </div>

            <!-- ===== 输出模式选择 ===== -->
            <div v-else-if="field.type === 'output-mode-select'" class="field">
              <label class="field-label">{{ field.label }}</label>
              <div class="source-tabs">
                <button
                  class="source-tab"
                  :class="{ active: currentOutputMode === 'download' }"
                  @click="handleOutputModeChange('download')"
                >仅输出（可下载）</button>
                <button
                  class="source-tab"
                  :class="{ active: currentOutputMode === 'library' }"
                  @click="handleOutputModeChange('library')"
                >保存到文档库</button>
              </div>
            </div>

            <!-- ===== 输入来源选择 ===== -->
            <div v-else-if="field.type === 'select-source'" class="field">
              <label class="field-label">{{ field.label }}</label>
              <div class="source-tabs">
                <button
                  v-for="opt in field.options"
                  :key="opt.value"
                  class="source-tab"
                  :class="{ active: currentInputSource === opt.value }"
                  @click="handleInputSourceChange(opt.value)"
                >{{ opt.label }}</button>
              </div>
            </div>

            <!-- ===== 文档库选择器 ===== -->
            <div v-else-if="field.type === 'library-selector'" class="field">
              <label class="field-label">{{ field.label }}</label>
              <select
                class="config-select"
                :value="field.key === 'targetSpaceId' ? currentTargetSpaceId : currentSpaceId"
                @change="field.key === 'targetSpaceId' ? handleTargetSpaceChange($event.target.value) : handleSpaceChange($event.target.value)"
              >
                <option value="">-- 选择文档库 --</option>
                <option
                  v-for="space in libraryStore.spaces"
                  :key="space.id"
                  :value="space.id"
                >{{ space.name }}</option>
                <option value="__new__">新建文档库…</option>
              </select>
              <div v-if="field.key === 'targetSpaceId' && currentTargetSpaceId === '__new__'" class="new-space-form">
                <input
                  v-model="newSpaceName"
                  class="config-input"
                  placeholder="输入新文档库名称"
                  style="margin-top: 8px;"
                />
                <button
                  class="btn-sm btn-primary"
                  style="margin-top: 6px;"
                  @click="handleCreateNewSpace"
                >确认创建</button>
              </div>
            </div>

            <!-- ===== 语言选择器 ===== -->
            <div v-else-if="field.type === 'language-selector'" class="field">
              <label class="field-label">{{ field.label }}</label>
              <div class="language-grid">
                <button
                  v-for="lang in workflowStore.availableLanguages"
                  :key="lang.code"
                  class="lang-chip"
                  :class="{ active: currentLanguage === lang.code }"
                  @click="handleLanguageChange(lang.code)"
                >{{ lang.label }}</button>
              </div>
            </div>

            <!-- ===== 格式选择器 ===== -->
            <div v-else-if="field.type === 'format-selector'" class="field">
              <label class="field-label">{{ field.label }}</label>
              <div class="format-grid">
                <button
                  v-for="fmt in workflowStore.outputFormats"
                  :key="fmt.code"
                  class="format-chip"
                  :class="{ active: currentFormat === fmt.code }"
                  @click="handleFormatChange(fmt.code)"
                >{{ fmt.label }}</button>
              </div>
            </div>

            <!-- ===== Select ===== -->
            <div v-else-if="field.type === 'select'" class="field">
              <label class="field-label">{{ field.label }}</label>
              <div v-if="getFieldUnsupportedHint(field)" class="field-badge field-badge-warning">{{ getFieldUnsupportedHint(field) }}</div>
              <select
                class="config-select"
                :value="normalizeFieldValue(getFieldValue(field, workflowStore.selectedNode))"
                @change="updateConfig(field.key, $event.target.value)"
                :disabled="Boolean(getFieldUnsupportedHint(field))"
              >
                <option
                  v-for="opt in (field.options || [])"
                  :key="optionValue(opt)"
                  :value="optionValue(opt)"
                >{{ optionLabel(opt) }}</option>
              </select>
            </div>

            <!-- ===== Input ===== -->
            <div v-else-if="field.type === 'input'" class="field">
              <label class="field-label">{{ getFieldLabel(field, workflowStore.selectedNode) }}</label>
              <p v-if="getFieldHint(field, workflowStore.selectedNode)" class="field-hint-text">{{ getFieldHint(field, workflowStore.selectedNode) }}</p>
              <div v-if="getFieldUnsupportedHint(field)" class="field-badge field-badge-warning">{{ getFieldUnsupportedHint(field) }}</div>
              <input
                class="config-input"
                type="text"
                :placeholder="getFieldPlaceholder(field, workflowStore.selectedNode)"
                :value="getFieldValue(field, workflowStore.selectedNode)"
                @input="updateConfig(field.key, $event.target.value)"
                :disabled="Boolean(getFieldUnsupportedHint(field))"
              />
            </div>

            <!-- ===== Textarea ===== -->
            <div v-else-if="field.type === 'textarea'" class="field">
              <label class="field-label">{{ getFieldLabel(field, workflowStore.selectedNode) }}</label>
              <p v-if="getFieldHint(field, workflowStore.selectedNode)" class="field-hint-text">{{ getFieldHint(field, workflowStore.selectedNode) }}</p>
              <div v-if="getFieldUnsupportedHint(field)" class="field-badge field-badge-warning">{{ getFieldUnsupportedHint(field) }}</div>
              <textarea
                class="config-textarea"
                :placeholder="getFieldPlaceholder(field, workflowStore.selectedNode)"
                :value="getFieldValue(field, workflowStore.selectedNode)"
                @input="updateConfig(field.key, $event.target.value)"
                :disabled="Boolean(getFieldUnsupportedHint(field))"
              ></textarea>
            </div>

            <!-- ===== Range ===== -->
            <div v-else-if="field.type === 'range'" class="field">
              <label class="field-label">{{ field.label }}</label>
              <div v-if="getFieldUnsupportedHint(field)" class="field-badge field-badge-warning">{{ getFieldUnsupportedHint(field) }}</div>
              <div class="range-row">
                <input
                  type="range"
                  class="range-input"
                  :min="field.min"
                  :max="field.max"
                  :value="getFieldValue(field, workflowStore.selectedNode)"
                  @input="updateConfig(field.key, Number($event.target.value))"
                  :disabled="Boolean(getFieldUnsupportedHint(field))"
                />
                <span class="range-val">{{ getFieldValue(field, workflowStore.selectedNode) || field.min }} {{ field.unit }}</span>
              </div>
            </div>

            <!-- ===== Toggle ===== -->
            <div v-else-if="field.type === 'toggle'" class="field field-toggle-row">
              <div class="field-toggle-copy">
                <label class="field-label">{{ field.label }}</label>
                <p v-if="getFieldHint(field, workflowStore.selectedNode)" class="field-hint-text">{{ getFieldHint(field, workflowStore.selectedNode) }}</p>
              </div>
              <div v-if="getFieldUnsupportedHint(field)" class="field-badge field-badge-warning">{{ getFieldUnsupportedHint(field) }}</div>
              <div
                class="toggle-switch"
                :class="{ on: getFieldValue(field, workflowStore.selectedNode) }"
                @click="!getFieldUnsupportedHint(field) && (updateConfig(field.key, !getFieldValue(field, workflowStore.selectedNode)), $event.target.classList.toggle('on'))"
              ></div>
            </div>

            <!-- ===== 画布节点多选（循环体） ===== -->
            <div v-else-if="field.type === 'node-multiselect'" class="field">
              <label class="field-label">{{ field.label }}</label>
              <p v-if="getFieldHint(field, workflowStore.selectedNode)" class="field-hint-text">{{ getFieldHint(field, workflowStore.selectedNode) }}</p>
              <div v-if="selectableProcessNodes.length === 0" class="node-multiselect-empty">画布上暂无可选的处理节点</div>
              <div v-else class="node-multiselect-list">
                <label
                  v-for="pn in selectableProcessNodes"
                  :key="pn.id"
                  class="node-multiselect-item"
                  :class="{ active: getNodeMultiFieldValues(field, workflowStore.selectedNode).includes(pn.id) }"
                >
                  <input
                    type="checkbox"
                    :checked="getNodeMultiFieldValues(field, workflowStore.selectedNode).includes(pn.id)"
                    @change="toggleNodeMulti(field.key, pn.id, $event.target.checked)"
                  />
                  <span class="node-multiselect-title">{{ pn.title }}</span>
                  <span class="node-multiselect-id">{{ pn.id }}</span>
                </label>
              </div>
            </div>

            <!-- ===== 画布节点单选（汇合节点等） ===== -->
            <div v-else-if="field.type === 'node-select'" class="field">
              <label class="field-label">{{ field.label }}</label>
              <p v-if="getFieldHint(field, workflowStore.selectedNode)" class="field-hint-text">{{ getFieldHint(field, workflowStore.selectedNode) }}</p>
              <div v-if="selectableJoinNodes.length === 0" class="node-multiselect-empty">画布上暂无汇合网关节点</div>
              <div v-else class="node-multiselect-list">
                <label
                  v-for="pn in selectableJoinNodes"
                  :key="pn.id"
                  class="node-multiselect-item"
                  :class="{ active: getFieldValue(field, workflowStore.selectedNode) === pn.id }"
                >
                  <input
                    type="radio"
                    :name="'node-select-' + field.key"
                    :checked="getFieldValue(field, workflowStore.selectedNode) === pn.id"
                    @change="selectSingleNodeField(field.key, pn.id)"
                  />
                  <span class="node-multiselect-title">{{ pn.title }}</span>
                  <span class="node-multiselect-id">{{ pn.id }}</span>
                </label>
              </div>
            </div>

            <!-- ===== Multi-select tags ===== -->
            <div v-else-if="field.type === 'multiselect' || field.type === 'select-multiple'" class="field">
              <label class="field-label">{{ field.label }}</label>
              <div v-if="getFieldUnsupportedHint(field)" class="field-badge field-badge-warning">{{ getFieldUnsupportedHint(field) }}</div>
              <div class="tag-grid">
                <div
                  v-for="opt in (field.options || [])"
                  :key="optionValue(opt)"
                  class="tag-chip"
                  :class="{ active: getMultiFieldValues(field, workflowStore.selectedNode).includes(optionValue(opt)) }"
                  @click="!getFieldUnsupportedHint(field) && toggleMulti(field.key, optionValue(opt), !getMultiFieldValues(field, workflowStore.selectedNode).includes(optionValue(opt)))"
                >{{ optionLabel(opt) }}</div>
              </div>
            </div>

          </template>
        </div>

        <!-- Selected Docs Summary (for non-input, non-output nodes) -->
        <div v-if="!isOutputNode && workflowStore.selectedNode.type !== 'input' && hasSelectedInputSummary" class="config-group">
          <div class="config-group-label">
            已选文档 <span class="doc-count-badge">{{ displayedDocs.length + displayedLocalFiles.length }} 个</span>
          </div>
          <div class="selected-docs-list">
            <div
              v-for="doc in displayedDocs"
              :key="doc.id"
              class="selected-doc-item"
            >
              <span class="selected-doc-icon" aria-hidden="true" />
              <span class="selected-doc-name">{{ doc.name }}</span>
              <span class="selected-doc-size">{{ doc.size }}</span>
            </div>
            <div
              v-for="file in displayedLocalFiles"
              :key="file.id"
              class="selected-doc-item"
            >
              <span class="selected-doc-icon" aria-hidden="true" />
              <span class="selected-doc-name">{{ file.name }}</span>
              <span class="selected-doc-size">{{ _formatSize(file.size) }}</span>
            </div>
          </div>
        </div>

        <!-- Output Files Download（紧贴开始处理按钮上方） -->
        <div v-if="workflowStore.outputFiles.length > 0 && !workflowStore.isExecuting" class="output-files-section">
          <div class="output-files-title">处理结果</div>
          <div
            v-for="f in workflowStore.outputFiles"
            :key="f.path"
            class="output-file-item"
          >
            <span class="output-file-name">{{ f.name }}</span>
            <span class="output-file-size">{{ (f.size / 1024).toFixed(1) }} KB</span>
            <button class="output-download-btn" @click="downloadFile(f)">下载</button>
          </div>
        </div>

        <!-- Action Button -->
        <button
          class="config-btn"
          :class="{ executing: workflowStore.isExecuting }"
          @click="handleExecute"
          :disabled="workflowStore.isExecuting"
        >
          <span v-if="workflowStore.isExecuting" class="btn-spinner"></span>
          <span v-else>▶</span>
          <span>{{ workflowStore.isExecuting ? `处理中 ${workflowStore.executionProgress}%` : executionButtonText }}</span>
        </button>

        <!-- Execution Progress -->
        <div v-if="workflowStore.isExecuting || workflowStore.executionLogs.length > 0" class="execution-status">
          <div class="exec-progress-bar">
            <div class="exec-progress-fill" :style="{ width: workflowStore.executionProgress + '%' }"></div>
          </div>
          <div v-if="workflowStore.nodeProgress.length > 0" class="node-progress-list">
            <div
              v-for="item in workflowStore.nodeProgress"
              :key="item.id"
              class="node-progress-item"
              :class="[
                'node-progress-' + item.status,
                item.type ? 'node-progress-type-' + item.type : '',
              ]"
            >
              <div class="node-progress-main">
                <span class="node-progress-index">{{ item.index }}</span>
                <span class="node-progress-title">{{ item.title }}</span>
                <span class="node-progress-state">{{ nodeStatusText(item.status) }}</span>
              </div>
              <div class="node-progress-track">
                <div class="node-progress-fill" :style="{ width: (item.progress || 0) + '%' }"></div>
              </div>
            </div>
          </div>
          <div class="exec-logs">
            <div
              v-for="(log, i) in workflowStore.executionLogs"
              :key="i"
              class="exec-log-item"
              :class="'log-' + log.type"
            >{{ log.message }}</div>
          </div>
        </div>
      </div>

      <!-- ======== 无选中节点 — 空状态 ======== -->
      <div v-else class="config-empty-state">
        <div class="empty-icon empty-icon-shape" aria-hidden="true">
          <MousePointerClick :size="28" :stroke-width="1.75" />
        </div>
        <div class="empty-title">点击节点以配置</div>
        <div class="empty-desc">在画布上点击任意节点<br/>右侧将切换显示该节点的专属配置</div>
        <div class="empty-nodes-hint" v-if="workflowStore.canvasNodes.length > 0">
          <div class="empty-nodes-title">工作流节点</div>
          <div
            v-for="(node, i) in workflowStore.canvasNodes"
            :key="node.id"
            class="empty-node-item"
            :class="{ done: workflowStore.selectedNodeId && i < workflowStore.canvasNodes.findIndex(n => n.id === workflowStore.selectedNodeId) }"
            @click="workflowStore.selectNode(node.id)"
          >
            <span class="empty-node-icon" :class="node.type" aria-hidden="true" />
            <span>{{ node.title }}</span>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
.source-tabs {
  display: flex;
  gap: 4px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  padding: 3px;
}

.source-tab {
  flex: 1;
  padding: 8px 12px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.source-tab:hover {
  background: var(--bg-hover);
  color: var(--text-secondary);
}

.source-tab.active {
  background: var(--bg-card);
  border-color: rgba(37, 99, 235, 0.3);
  color: var(--accent-primary);
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.12);
}

.doc-input-group {
  margin-bottom: 4px;
}

.doc-input-card {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-card);
  overflow: hidden;
}

.doc-source-tabs {
  margin: 0;
  border-radius: 0;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-secondary);
  padding: 6px;
}

.doc-panel {
  padding: 14px;
}

.doc-panel-field {
  margin-bottom: 12px;
}

.doc-panel-field .field-label {
  display: block;
  margin-bottom: 6px;
}

.doc-empty-inline {
  padding: 12px 0 4px;
  text-align: center;
}

.doc-count-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent-primary);
  background: rgba(37, 99, 235, 0.12);
  padding: 2px 8px;
  border-radius: 0;
  margin-left: 8px;
}

.doc-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px;
  color: var(--text-muted);
  font-size: 13px;
}

.loading-dots-sm {
  display: flex;
  gap: 4px;
}

.loading-dots-sm span {
  width: 6px;
  height: 6px;
  background: var(--accent-primary);
  border-radius: 0;
  animation: pulse-dot 1.4s ease-in-out infinite;
}

.loading-dots-sm span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots-sm span:nth-child(3) { animation-delay: 0.4s; }

@keyframes pulse-dot {
  0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1); }
}

.doc-empty-hint {
  padding: 20px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}

.doc-list {
  max-height: 220px;
  overflow-y: auto;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-tertiary);
}

.doc-list-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.15s;
  font-size: 13px;
  border-bottom: 1px solid var(--border-color);
}

.doc-list-item:last-child {
  border-bottom: none;
}

.doc-list-item:hover {
  background: var(--bg-hover);
}

.doc-list-item.selected {
  background: rgba(37, 99, 235, 0.08);
}

.doc-list-check {
  width: 18px;
  height: 18px;
  border: 2px solid var(--border-color);
  border-radius: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.15s;
}

.doc-list-item.selected .doc-list-check {
  background: var(--accent-primary);
  border-color: var(--accent-primary);
}

.doc-list-item.selected .check-mark {
  border-color: #fff;
}

.check-mark {
  display: block;
  width: 5px;
  height: 9px;
  border: solid transparent;
  border-width: 0 2px 2px 0;
  border-color: var(--accent-primary);
  transform: rotate(45deg);
  margin-bottom: 2px;
}

.doc-list-icon {
  width: 3px;
  height: 22px;
  border-radius: 0;
  background: rgba(37, 99, 235, 0.22);
  flex-shrink: 0;
}

.doc-list-name {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-primary);
}

.doc-list-size {
  color: var(--text-muted);
  font-size: 12px;
  flex-shrink: 0;
}

/* Local upload section */
.doc-local-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.upload-zone {
  border: 2px dashed var(--border-color);
  border-radius: var(--radius-md);
  padding: 24px 16px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--bg-tertiary);
}

.upload-zone:hover {
  border-color: rgba(37, 99, 235, 0.45);
  background: rgba(37, 99, 235, 0.04);
}

.upload-zone-icon {
  width: 40px;
  height: 40px;
  margin: 0 auto 8px;
  border-radius: 0;
  border: 2px dashed rgba(37, 99, 235, 0.28);
  background: rgba(37, 99, 235, 0.05);
}

.upload-zone-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.upload-zone-hint {
  font-size: 12px;
  color: var(--text-muted);
}

.local-files-list {
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
  overflow: hidden;
}

.local-file-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  font-size: 13px;
  border-bottom: 1px solid var(--border-color);
}

.local-file-item:last-child {
  border-bottom: none;
}

.local-file-icon {
  width: 3px;
  height: 22px;
  border-radius: 0;
  background: rgba(37, 99, 235, 0.22);
  flex-shrink: 0;
}

.local-file-name {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-primary);
}

.local-file-size {
  color: var(--text-muted);
  font-size: 12px;
  flex-shrink: 0;
}

.local-file-remove {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 0;
  font-size: 16px;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}

.local-file-remove:hover {
  background: rgba(239, 68, 68, 0.15);
  color: var(--accent-danger);
}

/* Language grid */
.language-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.lang-chip {
  padding: 6px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.lang-chip:hover {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}

.lang-chip.active {
  background: rgba(6, 182, 212, 0.15);
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
  font-weight: 600;
}

/* Format grid */
.format-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.format-chip {
  padding: 6px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.format-chip:hover {
  border-color: var(--accent-warning);
  color: var(--accent-warning);
}

.format-chip.active {
  background: rgba(245, 158, 11, 0.15);
  border-color: var(--accent-warning);
  color: var(--accent-warning);
  font-weight: 600;
}

.field-hint {
  margin-top: 6px;
}

.field-static-row {
  margin: 0 0 10px;
}

.field-static-text {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-muted);
  padding: 10px 12px;
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
}

.field-hint-text {
  margin: 4px 0 8px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-muted);
}

.field-toggle-copy {
  flex: 1;
  min-width: 0;
}

.step-order-group {
  margin-bottom: 4px;
}

.step-order-hint {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.45;
}

.step-order-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.step-order-btn {
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 500;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}

.step-order-btn:hover:not(:disabled) {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}

.step-order-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.step-order-pos {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.field-badge {
  display: inline-block;
  margin: 4px 0 8px;
  padding: 2px 8px;
  border-radius: 0;
  font-size: 11px;
  font-weight: 600;
}

.field-badge-warning {
  color: #f59e0b;
  background: rgba(245, 158, 11, 0.12);
  border: 1px solid rgba(245, 158, 11, 0.28);
}

.field-badge-info {
  color: #059669;
  background: rgba(5, 150, 105, 0.1);
  border: 1px solid rgba(5, 150, 105, 0.28);
}

.run-settings-hint,
.field-desc {
  margin: 0 0 8px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-muted);
}

.range-row--disabled {
  opacity: 0.45;
  pointer-events: none;
}

.node-multiselect-empty {
  font-size: 12px;
  color: var(--text-muted);
  padding: 8px 0;
}

.node-multiselect-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 200px;
  overflow-y: auto;
}

.node-multiselect-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.15s;
}

.node-multiselect-item:hover,
.node-multiselect-item.active {
  border-color: rgba(124, 58, 237, 0.45);
  background: rgba(124, 58, 237, 0.06);
}

.node-multiselect-title {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.node-multiselect-id {
  font-size: 10px;
  color: var(--text-muted);
  font-family: ui-monospace, monospace;
}

.hint-loading {
  font-size: 12px;
  color: var(--text-muted);
}

/* Execute button */
.config-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px;
  background: var(--gradient-success);
  border: none;
  border-radius: var(--radius-md);
  font-size: 15px;
  font-weight: 600;
  color: white;
  cursor: pointer;
  transition: all 0.2s;
  margin-top: 8px;
}

.config-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(16, 185, 129, 0.4);
}

.config-btn.executing {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  cursor: default;
}

.config-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.btn-spinner {
  display: inline-block;
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 0;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Execution status */
.execution-status {
  margin-top: 16px;
  padding: 14px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
}

.exec-progress-bar {
  height: 6px;
  background: var(--bg-secondary);
  border-radius: 0;
  overflow: hidden;
  margin-bottom: 12px;
}

.exec-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent-success), var(--accent-cyan));
  border-radius: 0;
  transition: width 0.5s ease;
}

.node-progress-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.node-progress-item {
  padding: 8px 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
}

.node-progress-type-input {
  --np-accent: #eab308;
  --np-accent-soft: rgba(234, 179, 8, 0.45);
  --np-accent-bg: rgba(234, 179, 8, 0.16);
  --np-accent-text: #a16207;
  border-color: rgba(234, 179, 8, 0.35);
}

.node-progress-type-ai {
  --np-accent: #2563eb;
  --np-accent-soft: rgba(37, 99, 235, 0.55);
  --np-accent-bg: rgba(37, 99, 235, 0.14);
  --np-accent-text: #1d4ed8;
  border-color: rgba(37, 99, 235, 0.28);
}

.node-progress-type-output {
  --np-accent: #1e40af;
  --np-accent-soft: rgba(30, 64, 175, 0.55);
  --np-accent-bg: rgba(30, 64, 175, 0.14);
  --np-accent-text: #1e3a8a;
  border-color: rgba(30, 64, 175, 0.28);
}

.node-progress-type-control {
  --np-accent: #7c3aed;
  --np-accent-soft: rgba(124, 58, 237, 0.5);
  --np-accent-bg: rgba(124, 58, 237, 0.14);
  --np-accent-text: #6d28d9;
  border-color: rgba(124, 58, 237, 0.28);
}

.node-progress-main {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.node-progress-index {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 0;
  background: var(--bg-tertiary);
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 700;
}

.node-progress-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.node-progress-state {
  color: var(--text-muted);
  font-size: 11px;
}

.node-progress-track {
  height: 4px;
  overflow: hidden;
  border-radius: 0;
  background: var(--bg-tertiary);
}

.node-progress-fill {
  height: 100%;
  width: 0;
  border-radius: 0;
  background: var(--np-accent-soft, var(--text-muted));
  transition: width 0.35s ease;
}

.node-progress-type-input .node-progress-index,
.node-progress-type-ai .node-progress-index,
.node-progress-type-output .node-progress-index,
.node-progress-type-control .node-progress-index {
  background: var(--np-accent-bg);
  color: var(--np-accent-text);
}

.node-progress-type-input .node-progress-fill,
.node-progress-type-ai .node-progress-fill,
.node-progress-type-output .node-progress-fill,
.node-progress-type-control .node-progress-fill {
  background: var(--np-accent-soft);
}

.node-progress-running .node-progress-index,
.node-progress-running .node-progress-fill {
  background: var(--np-accent, var(--accent-cyan));
  color: white;
}

.node-progress-type-input.node-progress-running .node-progress-index {
  color: #ffffff;
}

.node-progress-completed .node-progress-index,
.node-progress-completed .node-progress-fill {
  background: var(--np-accent, var(--accent-success));
  color: white;
}

.node-progress-type-input.node-progress-completed .node-progress-index {
  color: #ffffff;
}

.node-progress-failed .node-progress-index,
.node-progress-failed .node-progress-fill {
  background: #ef4444;
  color: white;
}

.exec-logs {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 120px;
  overflow-y: auto;
}

.output-files-section {
  margin-top: 8px;
  margin-bottom: 12px;
  border-top: 1px solid var(--border-color);
  padding-top: 12px;
}

.output-config-group {
  margin-bottom: 8px;
}

.output-files-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.output-file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 0;
  background: var(--bg-tertiary);
  margin-bottom: 6px;
}

.output-file-name {
  flex: 1;
  font-size: 13px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.output-file-size {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
}

.output-download-btn {
  padding: 4px 12px;
  border-radius: 0;
  background: var(--accent-primary);
  color: #fff;
  border: none;
  font-size: 12px;
  cursor: pointer;
  transition: opacity 0.2s;
  white-space: nowrap;
}

.output-download-btn:hover {
  opacity: 0.85;
}

.exec-log-item {
  font-size: 12px;
  color: var(--text-muted);
  padding: 4px 0;
  border-bottom: 1px solid var(--border-color);
}

.exec-log-item:last-child {
  border-bottom: none;
}

.exec-log-item.log-done {
  color: var(--accent-success);
}

.exec-log-item.log-error {
  color: var(--accent-danger);
}

/* Save workflow button */
.save-wf-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 16px;
  margin-top: 20px;
  background: var(--gradient-primary);
  border: none;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 600;
  color: white;
  cursor: pointer;
  transition: all 0.2s;
}

.save-wf-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.4);
}

.save-wf-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.save-wf-btn.saving {
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.save-spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: white;
  border-radius: 0;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
