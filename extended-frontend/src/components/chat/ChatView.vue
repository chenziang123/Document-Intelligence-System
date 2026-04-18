<script setup>
defineOptions({ name: 'ChatView' })

import { ref, onMounted, onUnmounted, nextTick, watch, computed } from 'vue'
import { marked } from 'marked'
import { useSessionStore } from '../../stores/sessionStore'
import { useFileStore } from '../../stores/fileStore'
import ChatSidebar from './ChatSidebar.vue'

// 配置 marked
marked.setOptions({
  breaks: true,
  gfm: true,
})

const sessionStore = useSessionStore()
const fileStore = useFileStore()

const messagesContainer = ref(null)
const inputText = ref('')
const textareaRef = ref(null)
const isDragover = ref(false)
const previewEntities = ref({})

const showProgress = computed(() => sessionStore.showProgressBar)
const progressVal = computed(() => sessionStore.progressValue)
const progressMsg = computed(() => sessionStore.progressMessage)

const chatModes = ['default_conversation', 'document_understanding', 'document_editing', 'mixed']
const modeLabels = {
  default_conversation: '默认对话',
  document_understanding: '文档理解',
  document_editing: '文档编辑',
  mixed: '混合模式'
}

function switchChatMode(mode) {
  sessionStore.switchMode(mode)
}

const quickActions = [
  { icon: '📖', text: '分析文档', prompt: '分析这份文档的核心内容' },
  { icon: '🎯', text: '提取信息', prompt: '提取文档中的关键信息' },
  { icon: '🌍', text: '翻译内容', prompt: '帮我翻译这篇论文' },
  { icon: '🔄', text: '使用工作流', action: 'workflow' }
]

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

watch(() => sessionStore.currentSessionId, () => {
  scrollToBottom()
})

watch(() => sessionStore.messages.length, () => {
  scrollToBottom()
})

watch(() => sessionStore.isStreaming, (streaming) => {
  if (streaming) scrollToBottom()
})

onMounted(() => {
  sessionStore.connectWebSocket()
  scrollToBottom()
})

onUnmounted(() => {
  sessionStore.disconnectWebSocket()
})

function insertPrompt(prompt) {
  if (prompt.action) {
    const tabStore = window.__tabStore__
    if (tabStore) tabStore.switchTab(prompt.action)
  }
}

function formatTime(isoString) {
  if (!isoString) return ''
  const dt = new Date(isoString)
  if (Number.isNaN(dt.getTime())) return ''
  return dt.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function copyMessage(content) {
  navigator.clipboard.writeText(content)
}

function renderMarkdown(content) {
  if (!content) return ''
  return marked.parse(content)
}

function autoResize() {
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
    textareaRef.value.style.height = Math.min(textareaRef.value.scrollHeight, 200) + 'px'
  }
}

function handleKeyDown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text) return

  await sessionStore.sendMessage(text, sessionStore.currentMode)
  inputText.value = ''
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
  }
}

function handleDragOver(e) {
  e.preventDefault()
  isDragover.value = true
}

function handleDragLeave() {
  isDragover.value = false
}

function handleDrop(e) {
  e.preventDefault()
  isDragover.value = false
  const files = Array.from(e.dataTransfer.files)
  if (files.length > 0) {
    files.forEach(file => fileStore.addFile(fileStore.currentFileType, file))
  }
}

function handleFileInput(e) {
  const files = Array.from(e.target.files)
  if (files.length > 0) {
    files.forEach(file => fileStore.addFile(fileStore.currentFileType, file))
  }
}

function triggerFileInput() {
  const input = document.createElement('input')
  input.type = 'file'
  input.multiple = true
  input.accept = '.pdf,.doc,.docx,.xlsx,.xls,.txt'
  input.onchange = handleFileInput
  input.click()
}

function switchFileType(type) {
  fileStore.switchFileType(type)
}

function removeFile(id, type) {
  fileStore.removeFile(id, type)
}

function formatFileSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function getFileExt(fileName) {
  if (!fileName || typeof fileName !== 'string') return 'FILE'
  const ext = fileName.split('.').pop()
  return ext ? ext.toUpperCase() : 'FILE'
}

function downloadResultFile(fileInfo) {
  const sid = sessionStore.currentSessionId
  if (fileInfo?.file_id && sid) {
    const url = `/api/sessions/${encodeURIComponent(sid)}/files/${encodeURIComponent(fileInfo.file_id)}/download`
    window.open(url, '_blank', 'noopener,noreferrer')
    return
  }
  if (!fileInfo?.file_path) return
  const url = `/api/files/download?path=${encodeURIComponent(fileInfo.file_path)}`
  const a = document.createElement('a')
  a.href = url
  a.download = fileInfo.file_name
  a.click()
}

// ============ 实体提取表格预览 ============
function getPreviewEntities(msg) {
  if (!msg) return []
  if (previewEntities.value[msg.id]) return previewEntities.value[msg.id]
  const entities = msg.entitiesData || []
  if (entities.length > 0) {
    previewEntities.value[msg.id] = entities
  }
  return entities
}

function getEntityHeaders(msg) {
  const entities = getPreviewEntities(msg)
  if (!entities || entities.length === 0) return []
  return Object.keys(entities[0])
}

function getEntityCells(entity, header) {
  const val = entity[header]
  if (val === undefined || val === null) return ''
  if (Array.isArray(val)) return val[0] ?? ''
  return String(val)
}

function downloadEntitiesJson(msg) {
  const entities = getPreviewEntities(msg)
  if (!entities.length) return
  const json = JSON.stringify(entities, null, 2)
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'extraction_result.json'
  a.click()
  URL.revokeObjectURL(url)
}

/** WebSocket 写在根上；历史消息可能在 metadata.tableFillingData */
function getTableFillingData(msg) {
  if (!msg || msg.role !== 'assistant') return null
  return msg.tableFillingData ?? msg.metadata?.tableFillingData ?? null
}

function getTableFillDownloadFiles(msg) {
  const tf = getTableFillingData(msg)
  if (Array.isArray(tf?.generated_files) && tf.generated_files.length) return tf.generated_files
  if (Array.isArray(msg?.generated_files) && msg.generated_files.length) return msg.generated_files
  return []
}

const TABLE_PREVIEW_MAX_ROWS = 50

function tablePreviewRows(tf) {
  if (!tf || typeof tf !== 'object') return []
  const a = tf.previewData
  const b = tf.filtered_rows
  if (Array.isArray(a) && a.length) return a
  if (Array.isArray(b) && b.length) return b
  return []
}

function tablePreviewDisplayRows(tf) {
  return tablePreviewRows(tf).slice(0, TABLE_PREVIEW_MAX_ROWS)
}

function tablePreviewExtraCount(tf) {
  const n = tablePreviewRows(tf).length
  return n > TABLE_PREVIEW_MAX_ROWS ? n - TABLE_PREVIEW_MAX_ROWS : 0
}

function tablePreviewColumns(rows) {
  if (!Array.isArray(rows) || rows.length === 0) return []
  const ordered = []
  const seen = new Set()
  const first = rows[0]
  if (first && typeof first === 'object' && !Array.isArray(first)) {
    for (const k of Object.keys(first)) {
      ordered.push(k)
      seen.add(k)
    }
  }
  for (const row of rows) {
    if (!row || typeof row !== 'object' || Array.isArray(row)) continue
    for (const k of Object.keys(row)) {
      if (!seen.has(k)) {
        seen.add(k)
        ordered.push(k)
      }
    }
  }
  return ordered
}

function formatTablePreviewCell(val) {
  if (val === null || val === undefined || val === '') return '—'
  if (typeof val === 'object') {
    try {
      return JSON.stringify(val)
    } catch {
      return String(val)
    }
  }
  return String(val)
}

/** 每条助手消息最多算一次预览结构，避免模板里对每格重复 tablePreviewColumns */
function buildTableFillPreviewBundle(msg) {
  const tf = getTableFillingData(msg)
  if (!tf || tf.success === undefined) return null
  const rows = tablePreviewRows(tf)
  if (!rows.length) return null
  const columns = tablePreviewColumns(rows)
  const displayRows = rows.slice(0, TABLE_PREVIEW_MAX_ROWS)
  const extra = Math.max(0, rows.length - TABLE_PREVIEW_MAX_ROWS)
  return { tf, columns, displayRows, totalRows: rows.length, extra }
}

const tableFillPreviewByMessageKey = computed(() => {
  const list = sessionStore.messages
  const out = {}
  for (let i = 0; i < list.length; i++) {
    const msg = list[i]
    if (msg.role !== 'assistant') continue
    const key = msg.id != null && msg.id !== '' ? String(msg.id) : `_i_${i}`
    const b = buildTableFillPreviewBundle(msg)
    if (b) out[key] = b
  }
  return out
})

function tablePreviewBundleFor(msg, index) {
  const key = msg.id != null && msg.id !== '' ? String(msg.id) : `_i_${index}`
  return tableFillPreviewByMessageKey.value[key] || null
}

function tablePreviewBundleList(msg, index) {
  const b = tablePreviewBundleFor(msg, index)
  return b ? [b] : []
}

function getFileStyle(fileName) {
  const ext = (fileName || '').split('.').pop().toLowerCase()
  const map = {
    pdf:  { bg: 'rgba(239, 68, 68, 0.15)', text: '#ef4444', icon: '📄' },
    doc:  { bg: 'rgba(59, 130, 246, 0.15)', text: '#3b82f6', icon: '📝' },
    docx: { bg: 'rgba(59, 130, 246, 0.15)', text: '#3b82f6', icon: '📝' },
    xls:  { bg: 'rgba(16, 185, 129, 0.15)', text: '#10b981', icon: '📊' },
    xlsx: { bg: 'rgba(16, 185, 129, 0.15)', text: '#10b981', icon: '📊' },
    txt:  { bg: 'rgba(161, 161, 170, 0.15)', text: '#a1a1aa', icon: '📃' },
    md:   { bg: 'rgba(161, 161, 170, 0.15)', text: '#a1a1aa', icon: '📃' },
  }
  return map[ext] || { bg: 'rgba(161, 161, 170, 0.15)', text: '#a1a1aa', icon: '📎' }
}

function userMessageAttachments(msg) {
  const m = msg.metadata || {}
  const data = (m.files || []).map((f) => ({ ...f, _kind: 'data' }))
  const tpl = (m.template_files || []).map((f) => ({ ...f, _kind: 'template' }))
  return [...data, ...tpl]
}
</script>

<template>
  <div class="chat-view">
    <ChatSidebar :collapsed="sessionStore.sidebarCollapsed" />
    <div class="chat-main" :class="{ 'sidebar-collapsed': sessionStore.sidebarCollapsed }">
      <!-- 展开按钮 - 在右侧始终可见 -->
      <button v-if="sessionStore.sidebarCollapsed" class="sidebar-toggle collapsed-toggle" @click="sessionStore.toggleSidebar" title="展开侧边栏">
        →
      </button>

      <!-- 处理模式气泡容器 -->
      <div class="mode-selector">
        <span class="mode-label">处理模式:</span>
        <div class="mode-tabs">
          <button
            v-for="mode in chatModes"
            :key="mode"
            class="mode-tab"
            :class="{ active: sessionStore.currentMode === mode }"
            @click="switchChatMode(mode)"
          >
            {{ modeLabels[mode] }}
          </button>
        </div>
      </div>

      <div class="chat-messages" ref="messagesContainer">
        <div v-if="sessionStore.isInitializing" class="welcome-state">
          <div class="welcome-icon">💬</div>
          <h1 class="welcome-title">加载中...</h1>
        </div>

        <div v-else-if="sessionStore.messages.length === 0" class="welcome-state">
          <div class="welcome-icon">💬</div>
          <h1 class="welcome-title">智能对话</h1>
          <p class="welcome-subtitle">
            通过自然语言与系统交互，完成文档分析，信息提取，内容生成等任务
          </p>
          <div class="quick-actions">
            <button
              v-for="action in quickActions"
              :key="action.text"
              class="quick-action"
              @click="insertPrompt(action)"
            >
              <span>{{ action.icon }}</span>
              <span>{{ action.text }}</span>
            </button>
          </div>
        </div>

        <div
          v-for="(msg, index) in sessionStore.messages"
          :key="msg.id != null ? msg.id : `m-${index}`"
          class="message"
          :class="msg.role"
        >
          <div class="message-avatar">
            {{ msg.role === 'user' ? '👤' : msg.role === 'system' ? 'ℹ️' : '🤖' }}
          </div>
          <div class="message-content">
            <!-- 用户消息：带附件时显示文件卡片 -->
            <template v-if="msg.role === 'user' && userMessageAttachments(msg).length > 0">
              <div class="user-attachments">
                <div
                  v-for="(att, idx) in userMessageAttachments(msg)"
                  :key="`${att.id ?? att.file_id ?? idx}-${att.file_name}`"
                  class="attachment-card"
                  :class="{ 'attachment-uploading': att.pending }"
                >
                  <div
                    class="attachment-icon"
                    :style="{ background: getFileStyle(att.file_name).bg, color: getFileStyle(att.file_name).text }"
                  >
                    <span v-if="att.pending" class="attachment-spinner">⏳</span>
                    <span v-else>{{ getFileStyle(att.file_name).icon }}</span>
                  </div>
                  <div class="attachment-info">
                    <div class="attachment-name" :title="att.file_name">{{ att.file_name }}</div>
                    <div class="attachment-meta">
                      <span v-if="att.pending" class="upload-status">上传中...</span>
                      <template v-else>
                        {{ getFileExt(att.file_name) }}
                        <span v-if="formatFileSize(att.file_size)"> | {{ formatFileSize(att.file_size) }}</span>
                      </template>
                      <span v-if="att._kind === 'template'" class="template-badge">· 模板</span>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="msg.content" class="message-bubble">
                <span>{{ msg.content }}</span>
              </div>
            </template>
            <!-- 用户消息：无附件 -->
            <div v-else-if="msg.role === 'user'" class="message-bubble">
              <span>{{ msg.content }}</span>
            </div>
            <!-- 系统消息 -->
            <div v-else-if="msg.role === 'system'" class="message-bubble system">
              <span>{{ msg.content }}</span>
            </div>
            <!-- 助手消息 -->
            <div v-else class="message-bubble" :class="{ 'md-content': msg.role === 'assistant' }">
              <div v-if="msg.role === 'assistant'" v-html="renderMarkdown(msg.content)"></div>
              <!-- 表格填表预览：每条消息只取一次 bundle（computed 预聚合 + 单次 list 迭代） -->
              <template v-for="tb in tablePreviewBundleList(msg, index)" :key="(msg.id != null ? msg.id : index) + '-tbl'">
                <div class="entity-preview table-fill-preview">
                  <div class="entity-preview-header">
                    <div>
                      <span class="entity-preview-title">
                        📋 表格结果预览（{{ tb.totalRows }} 行）
                      </span>
                      <span v-if="tb.tf.matched_rows != null" class="table-fill-stats table-fill-stats-inline">
                        命中 {{ tb.tf.matched_rows }}/{{ tb.tf.total_rows ?? '—' }} 行
                      </span>
                    </div>
                    <div v-if="getTableFillDownloadFiles(msg).length" class="entity-preview-actions">
                      <button
                        v-for="f in getTableFillDownloadFiles(msg)"
                        :key="f.file_id ?? f.file_path"
                        class="entity-action-btn"
                        type="button"
                        @click="downloadResultFile(f)"
                      >
                        {{ getFileExt(f.file_name) }} ↓
                      </button>
                    </div>
                  </div>
                  <div class="entity-table-wrapper">
                    <table class="entity-table">
                      <thead>
                        <tr>
                          <th v-for="col in tb.columns" :key="col">
                            {{ col }}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(row, ri) in tb.displayRows" :key="ri">
                          <td
                            v-for="col in tb.columns"
                            :key="col"
                            :title="formatTablePreviewCell(row && row[col] !== undefined ? row[col] : '')"
                          >
                            {{ formatTablePreviewCell(row && row[col] !== undefined ? row[col] : '') }}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <div v-if="tb.extra > 0" class="entity-preview-more">
                    还有 {{ tb.extra }} 行未展示，请下载生成文件查看全部
                  </div>
                </div>
              </template>
              <!-- 仅表格填表：无 previewData 时仍要下载；勿用 getTableFillDownloadFiles 单独判断，否则无 tableFillingData 时会误用 msg.generated_files 与实体提取重复 -->
              <div
                v-if="getTableFillingData(msg) && getTableFillDownloadFiles(msg).length && !tablePreviewBundleFor(msg, index)"
                class="entity-preview table-fill-preview table-fill-downloads-only"
              >
                <div class="entity-preview-header">
                  <span class="entity-preview-title">📋 生成结果</span>
                  <div class="entity-preview-actions">
                    <button
                      v-for="f in getTableFillDownloadFiles(msg)"
                      :key="f.file_id ?? f.file_path"
                      class="entity-action-btn"
                      type="button"
                      @click="downloadResultFile(f)"
                    >
                      {{ getFileExt(f.file_name) }} ↓
                    </button>
                  </div>
                </div>
              </div>
              <!-- 实体提取结果：表格预览（与表格填表共用 table-fill-preview 表头/表体样式） -->
              <div v-if="msg.entitiesData?.length" class="entity-preview table-fill-preview">
                <div class="entity-preview-header">
                  <span class="entity-preview-title">📊 提取结果预览（共 {{ msg.entitiesData.length }} 条）</span>
                  <div class="entity-preview-actions">
                    <button v-for="f in msg.generated_files" :key="f.file_id" class="entity-action-btn" @click="downloadResultFile(f)">
                      {{ getFileExt(f.file_name) }} ↓
                    </button>
                  </div>
                </div>
                <div class="entity-table-wrapper">
                  <table class="entity-table">
                    <thead>
                      <tr>
                        <th v-for="h in getEntityHeaders(msg)" :key="h">{{ h }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(entity, rowIdx) in msg.entitiesData.slice(0, 20)" :key="rowIdx">
                        <td v-for="h in getEntityHeaders(msg)" :key="h" :title="entity[h] != null ? String(entity[h]) : ''">
                          {{ getEntityCells(entity, h) }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div v-if="msg.entitiesData.length > 20" class="entity-preview-more">
                  还有 {{ msg.entitiesData.length - 20 }} 条数据，下载完整文件查看全部
                </div>
              </div>
              <!-- 仅文件下载：实体提取等场景；表格填表已在上方标题栏处理，勿与 msg.generated_files 再渲一排 -->
              <div
                v-else-if="msg.generated_files?.length && !getTableFillingData(msg)"
                class="entity-preview table-fill-preview table-fill-downloads-only"
              >
                <div class="entity-preview-header">
                  <span class="entity-preview-title">📊 生成结果</span>
                  <div class="entity-preview-actions">
                    <button v-for="f in msg.generated_files" :key="f.file_id" class="entity-action-btn" @click="downloadResultFile(f)">
                      {{ getFileExt(f.file_name) }} ↓
                    </button>
                  </div>
                </div>
              </div>
            </div>
            <div class="message-time">{{ formatTime(msg.created_at) }}</div>
          </div>
        </div>

        <!-- 上传文件进度 -->
        <div v-if="sessionStore.isUploadingFiles" class="message system">
          <div class="message-avatar">⏳</div>
          <div class="message-content">
            <div class="message-bubble upload-progress">
              <span class="upload-icon">📤</span>
              <span class="upload-text">{{ sessionStore.uploadProgress || '正在上传文件...' }}</span>
            </div>
          </div>
        </div>

        <!-- 进度条（实体提取/表格填表） -->
        <div v-if="showProgress && (sessionStore.currentMode === 'entity_extraction' || sessionStore.currentMode === 'table_filling' || sessionStore.currentMode === 'mixed')" class="message assistant">
          <div class="message-avatar">⚙️</div>
          <div class="message-content">
            <div class="progress-card">
              <div class="progress-header">
                <span class="progress-title">任务处理中</span>
                <span class="progress-msg">{{ progressMsg }}</span>
                <span v-if="progressVal < 100" class="progress-indicator">●</span>
                <span v-else class="progress-done">完成</span>
              </div>
              <div class="progress-bar-container">
                <div class="progress-bar" :style="{ width: progressVal + '%' }"></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="chat-input-area">
        <div class="chat-input-row">
          <div
            class="file-drop-zone"
            :class="{ dragover: isDragover }"
            @dragover="handleDragOver"
            @dragleave="handleDragLeave"
            @drop="handleDrop"
            @click="triggerFileInput"
          >
            <span class="file-drop-zone-icon">📎</span>
            <span class="file-drop-zone-text">
              拖拽文件或 <span @click.stop="triggerFileInput">浏览</span>
            </span>
            <div class="file-type-switcher">
              <button
                class="file-type-btn"
                :class="{ active: fileStore.currentFileType === 'data' }"
                data-type="data"
                @click.stop="switchFileType('data')"
              >
                数据文件
              </button>
              <button
                class="file-type-btn"
                :class="{ active: fileStore.currentFileType === 'template' }"
                data-type="template"
                @click.stop="switchFileType('template')"
              >
                模板文件
              </button>
            </div>
            <div class="file-count-badges">
              <span v-if="fileStore.hasDataFiles" class="file-badge data-badge">
                📄 {{ fileStore.dataCount }}
              </span>
              <span v-if="fileStore.hasTemplateFiles" class="file-badge template-badge">
                📋 {{ fileStore.templateCount }}
              </span>
            </div>
          </div>

          <div class="chat-input-wrapper">
            <div class="chat-input">
              <textarea
                ref="textareaRef"
                v-model="inputText"
                rows="1"
                placeholder="输入消息..."
                @keydown="handleKeyDown"
                @input="autoResize"
              ></textarea>
            </div>
            <button
              class="send-btn"
              :class="{ loading: sessionStore.isStreaming }"
              @click="sendMessage"
              :disabled="!inputText.trim() || sessionStore.isStreaming"
            >
              <span v-if="!sessionStore.isStreaming">➤</span>
              <span v-else class="send-spinner"></span>
            </button>
          </div>
        </div>

        <!-- Uploaded Files Panel -->
        <div class="uploaded-files-panel">
          <div class="panel-header" @click="fileStore.toggleFilesPanel">
            <span class="panel-title">
              已上传文件
              <span v-if="fileStore.dataCount + fileStore.templateCount > 0" class="file-count">
                ({{ fileStore.dataCount + fileStore.templateCount }})
              </span>
            </span>
            <span class="panel-toggle" :class="{ collapsed: fileStore.filesPanelCollapsed }">
              {{ fileStore.filesPanelCollapsed ? '▶' : '▼' }}
            </span>
          </div>
          <div class="panel-content" :class="{ collapsed: fileStore.filesPanelCollapsed }">
            <div v-if="fileStore.dataCount + fileStore.templateCount === 0" class="files-empty">
              <span class="empty-icon">📂</span>
              <span class="empty-text">暂无文件，上传文件后可选中发送给 AI</span>
            </div>
            <div v-else class="files-row">
              <!-- Data Files -->
              <div v-if="fileStore.hasDataFiles" class="files-group">
                <span class="files-label">📄 数据文件:</span>
                <div class="files-tags">
                  <div
                    v-for="file in fileStore.tempFiles.data"
                    :key="file.id"
                    class="file-tag"
                    :class="{ selected: file.is_selected }"
                  >
                    <input
                      type="checkbox"
                      :checked="file.is_selected"
                      @change="fileStore.toggleFileSelection(file.id, 'data', $event.target.checked)"
                      class="file-checkbox"
                    />
                    <span class="file-icon-small">{{ fileStore.getFileIcon(file.file_name) }}</span>
                    <span class="file-tag-name" :title="file.file_name">{{ file.file_name }}</span>
                    <span class="file-size-small">{{ formatFileSize(file.file_size) }}</span>
                    <button class="file-tag-remove" @click.stop="fileStore.removeFile(file.id, 'data')">×</button>
                  </div>
                </div>
              </div>

              <!-- Template Files -->
              <div v-if="fileStore.hasTemplateFiles" class="files-group">
                <span class="files-label">📋 模板文件:</span>
                <div class="files-tags">
                  <div
                    v-for="file in fileStore.tempFiles.template"
                    :key="file.id"
                    class="file-tag template"
                    :class="{ selected: file.is_selected }"
                  >
                    <input
                      type="checkbox"
                      :checked="file.is_selected"
                      @change="fileStore.toggleFileSelection(file.id, 'template', $event.target.checked)"
                      class="file-checkbox"
                    />
                    <span class="file-icon-small">{{ fileStore.getFileIcon(file.file_name) }}</span>
                    <span class="file-tag-name" :title="file.file_name">{{ file.file_name }}</span>
                    <span class="file-size-small">{{ formatFileSize(file.file_size) }}</span>
                    <button class="file-tag-remove" @click.stop="fileStore.removeFile(file.id, 'template')">×</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 进度条 */
.progress-card {
  background: #f9fafb;
  border-radius: 8px;
  padding: 12px 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.progress-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.progress-title {
  font-size: 14px;
  font-weight: 500;
  color: #374151;
}

.progress-msg {
  font-size: 12px;
  color: #9ca3af;
  flex: 1;
}

.progress-indicator {
  font-size: 12px;
  color: #9ca3af;
  animation: pulse 1s infinite;
}

.progress-done {
  font-size: 12px;
  color: #10b981;
  font-weight: 500;
}

.progress-bar-container {
  height: 8px;
  background: #e5e7eb;
  border-radius: 4px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #10b981, #34d399);
  border-radius: 4px;
  transition: width 0.3s ease;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* ============ 实体提取表格预览 ============ */
.entity-preview {
  margin-top: 12px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  overflow: hidden;
  background: white;
}

.entity-preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: white;
  border-bottom: 1px solid #e5e7eb;
}

.entity-preview-title {
  font-size: 13px;
  font-weight: 500;
  color: #111827;
}

.entity-preview-actions {
  display: flex;
  gap: 6px;
}

.entity-action-btn {
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 3px 10px;
  font-size: 12px;
  cursor: pointer;
}

.entity-action-btn:hover {
  background: #2563eb;
}

.entity-table-wrapper {
  overflow-x: auto;
  max-height: 400px;
  overflow-y: auto;
}

.entity-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  background: white;
}

.entity-table thead {
  position: sticky;
  top: 0;
  z-index: 1;
}

.entity-table th {
  background: white;
  color: #111827;
  font-weight: 600;
  padding: 6px 10px;
  text-align: left;
  white-space: nowrap;
  border-bottom: 1px solid #d1d5db;
  border-right: 1px solid #e5e7eb;
}

.entity-table td {
  padding: 5px 10px;
  border-bottom: 1px solid #f3f4f6;
  border-right: 1px solid #f9fafb;
  color: #111827;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  background: white;
}

.entity-table tbody tr:hover td {
  background: #f0f9ff;
}

.entity-preview-more {
  padding: 8px 12px;
  text-align: center;
  font-size: 12px;
  color: #6b7280;
  background: white;
  border-top: 1px solid #e5e7eb;
}

.table-fill-preview {
  border-color: #fcd34d;
  background: #fffbeb;
}

.table-fill-preview .entity-preview-header {
  background: #fffbeb;
  border-bottom: 1px solid #fde68a;
}

.table-fill-preview .entity-preview-title {
  color: #78350f;
}

.table-fill-preview .entity-table th {
  background: #fef3c7;
  color: #78350f;
  border-bottom: 1px solid #fcd34d;
  border-right: 1px solid #fde68a;
}

.table-fill-preview .entity-table td {
  border-bottom: 1px solid #fef3c7;
  border-right: 1px solid #fefce8;
  background: #ffffff;
}

.table-fill-preview .entity-table tbody tr:hover td {
  background: #fff7ed;
}

.table-fill-preview .entity-preview-more {
  background: #fffbeb;
  border-top: 1px solid #fde68a;
  color: #92400e;
}

.table-fill-stats {
  font-size: 12px;
  color: #92400e;
  white-space: nowrap;
}

.table-fill-stats-inline {
  margin-left: 8px;
  font-weight: 500;
}
</style>
