<script setup>
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
          :key="msg.id || index"
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
            </div>
            <div class="message-actions" v-if="msg.role === 'assistant'">
              <button class="message-action" @click="copyMessage(msg.content)">复制</button>
            </div>
            <div class="message-time">{{ formatTime(msg.created_at) }}</div>
          </div>
        </div>

        <div v-if="sessionStore.isStreaming && sessionStore.messages.length > 0" class="message assistant">
          <div class="message-avatar">🤖</div>
          <div class="message-content">
            <div class="message-bubble streaming">
              <span class="streaming-dot"></span>
              <span class="streaming-dot"></span>
              <span class="streaming-dot"></span>
            </div>
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
