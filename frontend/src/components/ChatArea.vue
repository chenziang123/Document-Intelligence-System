<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { NInput, NButton, NScrollbar, NTag, NProgress } from 'naive-ui'
import { useSessionStore } from '../stores/sessionStore'
import { assistantMarkdownToHtml } from '../utils/markdown'
import * as XLSX from 'xlsx'

const sessionStore = useSessionStore()
const showProgress = computed(() => sessionStore.showProgressBar)
const progressVal = computed(() => sessionStore.progressValue)
const progressMsg = computed(() => sessionStore.progressMessage)
const inputValue = ref('')
const messagesContainer = ref(null)

// 实体提取表格最大显示行数
const MAX_TABLE_ROWS = 10

// 滚动到底部
function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTo({ top: messagesContainer.value.scrollHeight, behavior: 'smooth' })
    }
  })
}

watch(() => sessionStore.messages.length, scrollToBottom)
watch(() => sessionStore.isStreaming, (streaming) => {
  if (streaming) scrollToBottom()
})

async function handleSend() {
  if (!inputValue.value.trim()) return
  const content = inputValue.value
  inputValue.value = ''
  await sessionStore.sendMessage(content)
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

function formatTime(isoString) {
  if (!isoString) return ''
  return new Date(isoString).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function formatFileSize(bytes) {
  if (bytes == null || Number.isNaN(Number(bytes))) return ''
  const n = Number(bytes)
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(2)} KB`
  return `${(n / (1024 * 1024)).toFixed(2)} MB`
}

function fileExtLabel(fileName) {
  if (!fileName || typeof fileName !== 'string') return 'FILE'
  const ext = fileName.split('.').pop()
  return ext ? ext.toUpperCase() : 'FILE'
}

// 文件后缀 → { bg, text, icon }
function getFileStyle(fileName) {
  const ext = (fileName || '').split('.').pop().toLowerCase()
  const map = {
    pdf:  { bg: 'bg-red-50',      text: 'text-red-600',      icon: 'pdf' },
    doc:  { bg: 'bg-blue-50',     text: 'text-blue-600',     icon: 'doc' },
    docx: { bg: 'bg-blue-50',     text: 'text-blue-600',     icon: 'doc' },
    xls:  { bg: 'bg-green-50',    text: 'text-green-600',    icon: 'xls' },
    xlsx: { bg: 'bg-green-50',    text: 'text-green-600',    icon: 'xls' },
    txt:  { bg: 'bg-gray-100',    text: 'text-gray-600',     icon: 'txt' },
    md:   { bg: 'bg-gray-100',    text: 'text-gray-600',     icon: 'txt' },
    png:  { bg: 'bg-purple-50',   text: 'text-purple-600',  icon: 'img' },
    jpg:  { bg: 'bg-purple-50',   text: 'text-purple-600',  icon: 'img' },
    jpeg: { bg: 'bg-purple-50',   text: 'text-purple-600',  icon: 'img' },
    gif:  { bg: 'bg-purple-50',   text: 'text-purple-600',  icon: 'img' },
    csv:  { bg: 'bg-teal-50',     text: 'text-teal-600',    icon: 'csv' },
  }
  return map[ext] || { bg: 'bg-gray-50', text: 'text-gray-500', icon: 'file' }
}

/** 用户消息中与文字一并发送的附件（metadata 与后端一致） */
function userMessageAttachments(msg) {
  const m = msg.metadata || {}
  const data = (m.files || []).map((f) => ({ ...f, _kind: 'data' }))
  const tpl = (m.template_files || []).map((f) => ({ ...f, _kind: 'template' }))
  return [...data, ...tpl]
}

function renderAssistant(msg) {
  return assistantMarkdownToHtml(msg.content)
}

// 获取表格显示的行数（最多10行）
function getTableRows(entities) {
  if (!entities || !Array.isArray(entities)) return []
  return entities.slice(0, MAX_TABLE_ROWS)
}

// 获取表格列名
function getTableColumns(schema) {
  if (!schema || !schema.fields) return []
  return schema.fields
}

// 获取实体数据总条数
function getTotalCount(extractionData) {
  if (!extractionData || !extractionData.entities) return 0
  return extractionData.entities.length
}

const showStreamingPlaceholder = computed(() => {
  if (!sessionStore.isStreaming) return false
  const list = sessionStore.messages
  const last = list[list.length - 1]
  return !last || last.role !== 'assistant'
})

// 判断消息是否需要渲染为实体提取结果表格
function isEntityExtractionMessage(msg) {
  return msg.role === 'assistant' && msg.extractionData && msg.extractionData.entities
}

// 渲染单元格值（处理数组格式 [值, 位置]）
function renderCellValue(rawValue) {
  if (Array.isArray(rawValue)) {
    return rawValue[0] || ''
  }
  return rawValue || ''
}

// 下载 JSON
function downloadJson(msg) {
  const data = {
    message: msg.extractionData.message,
    schema: msg.extractionData.schema,
    entities: msg.extractionData.entities,
  }
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `entity_extraction_${new Date().toISOString().replace(/[:.]/g, '-')}.json`
  a.click()
  URL.revokeObjectURL(url)
}

// 下载 XLSX
function downloadXlsx(msg) {
  const { schema, entities } = msg.extractionData
  const cols = schema?.fields || []

  // 准备表头和数据
  const header = ['序号', ...cols]
  const rows = entities.map((row, idx) => [
    idx + 1,
    ...cols.map(col => {
      const val = row[col]
      if (Array.isArray(val)) return val[0] || ''
      return val ?? ''
    }),
  ])

  const wsData = [header, ...rows]
  const ws = XLSX.utils.aoa_to_sheet(wsData)

  // 自动列宽
  const colWidths = header.map((h, ci) => {
    const maxLen = wsData.reduce((acc, row) => {
      const cell = String(row[ci] ?? '')
      return Math.max(acc, cell.length)
    }, h.length)
    return { wch: Math.min(maxLen + 2, 50) }
  })
  ws['!cols'] = colWidths

  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, '实体提取结果')
  XLSX.writeFile(wb, `entity_extraction_${new Date().toISOString().replace(/[:.]/g, '-')}.xlsx`)
}

onMounted(() => {
  sessionStore.connectWebSocket()
})

onUnmounted(() => {
  sessionStore.disconnectWebSocket()
})
</script>

<template>
  <div class="h-full flex flex-col">
      <!-- 消息列表 -->
    <n-scrollbar ref="messagesContainer" class="flex-1 p-4">
      <!-- 空状态 -->
      <div v-if="sessionStore.messages.length === 0" class="h-full flex items-center justify-center text-gray-400">
        <div class="text-center">
          <div class="text-4xl mb-4">💬</div>
          <div>开始对话吧！</div>
          <div class="text-sm mt-2">选择模式、上传文件后发送消息</div>
        </div>
      </div>

      <!-- 消息列表 -->
      <div v-else class="space-y-4">
        <div
          v-for="msg in sessionStore.messages"
          :key="msg.id"
          :class="[
            'flex',
            msg.role === 'user' ? 'justify-end' :
            msg.role === 'system' ? 'justify-center' :
            'justify-start'
          ]"
        >
          <!-- 用户：带附件时「文件卡片 + 文案」作为一条消息（与参考图一致） -->
          <div
            v-if="msg.role === 'user' && userMessageAttachments(msg).length > 0"
            class="max-w-md flex flex-col items-end gap-2"
          >
            <div
              v-for="(att, idx) in userMessageAttachments(msg)"
              :key="`${att.file_id ?? idx}-${att.file_name}`"
              class="w-full max-w-sm rounded-lg border border-gray-200 bg-white px-3 py-2.5 shadow-sm"
            >
              <div class="flex items-start gap-3">
                <div
                  :class="['flex h-10 w-10 shrink-0 items-center justify-center rounded-md text-xs font-bold', getFileStyle(att.file_name).bg, getFileStyle(att.file_name).text]"
                  aria-hidden="true"
                >
                  <!-- PDF 图标 -->
                  <svg v-if="getFileStyle(att.file_name).icon === 'pdf'" xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
                  <!-- DOC 图标 -->
                  <svg v-else-if="getFileStyle(att.file_name).icon === 'doc'" xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
                  <!-- XLS 图标 -->
                  <svg v-else-if="getFileStyle(att.file_name).icon === 'xls'" xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><rect x="8" y="12" width="8" height="7" rx="1"/><line x1="9" y1="15" x2="15" y2="15"/></svg>
                  <!-- 图片图标 -->
                  <svg v-else-if="getFileStyle(att.file_name).icon === 'img'" xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                  <!-- 通用文件图标 -->
                  <svg v-else xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                </div>
                <div class="min-w-0 flex-1">
                  <div class="truncate text-sm font-medium text-gray-900" :title="att.file_name">
                    {{ att.file_name }}
                  </div>
                  <div class="mt-0.5 text-xs text-gray-400">
                    {{ fileExtLabel(att.file_name) }}
                    <span v-if="formatFileSize(att.file_size)"> | {{ formatFileSize(att.file_size) }}</span>
                    <span v-if="att._kind === 'template'" class="ml-1 text-amber-600">· 模板</span>
                  </div>
                </div>
              </div>
            </div>
            <div
              class="rounded-xl bg-amber-50/90 px-4 py-2.5 text-left text-[15px] leading-relaxed text-amber-950 shadow-sm ring-1 ring-amber-100/80"
            >
              <div class="whitespace-pre-wrap break-words">{{ msg.content }}</div>
            </div>
            <div class="text-xs text-gray-400">
              {{ formatTime(msg.created_at) }}
            </div>
          </div>

          <!-- 用户：纯文字（无附件）保持原有绿色气泡 -->
          <div
            v-else-if="msg.role === 'user'"
            class="max-w-2xl rounded-lg bg-green-600 px-4 py-2 text-white"
          >
            <div class="whitespace-pre-wrap break-words">{{ msg.content }}</div>
            <div class="mt-1 text-xs text-green-100">
              {{ formatTime(msg.created_at) }}
            </div>
          </div>

          <!-- 系统消息 -->
          <div
            v-else-if="msg.role === 'system'"
            class="max-w-xl mx-auto w-full text-center"
          >
            <div class="inline-flex items-center gap-1.5 rounded-full bg-blue-50 border border-blue-100 px-4 py-1.5 text-xs text-blue-600 shadow-sm">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
              <span>{{ msg.content }}</span>
            </div>
          </div>

          <!-- 助手 -->
          <div
            v-else
            class="max-w-2xl rounded-lg bg-gray-100 px-4 py-2 text-gray-800"
          >
            <!-- 实体提取结果表格 -->
            <template v-if="isEntityExtractionMessage(msg)">
              <!-- 摘要信息 -->
              <div class="mb-3 flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <n-tag type="success" size="small">实体提取</n-tag>
                  <span class="text-sm text-gray-600">{{ msg.extractionData.message }}</span>
                </div>
                <div class="flex items-center gap-1">
                  <n-button size="tiny" @click="downloadJson(msg)">
                    <template #icon>
                      <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                    </template>
                    JSON
                  </n-button>
                  <n-button size="tiny" type="primary" @click="downloadXlsx(msg)">
                    <template #icon>
                      <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                    </template>
                    XLSX
                  </n-button>
                </div>
              </div>
              <!-- 数据表格 -->
              <div class="overflow-x-auto">
                <table class="min-w-full text-sm border-collapse border border-gray-300">
                  <thead>
                    <tr class="bg-gray-200">
                      <th class="border border-gray-300 px-2 py-1 text-left font-medium">#</th>
                      <th
                        v-for="col in getTableColumns(msg.extractionData.schema)"
                        :key="col"
                        class="border border-gray-300 px-2 py-1 text-left font-medium"
                      >
                        {{ col }}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(row, idx) in getTableRows(msg.extractionData.entities)"
                      :key="idx"
                      class="hover:bg-gray-50"
                    >
                      <td class="border border-gray-300 px-2 py-1 text-gray-400">{{ idx + 1 }}</td>
                      <td
                        v-for="col in getTableColumns(msg.extractionData.schema)"
                        :key="col"
                        class="border border-gray-300 px-2 py-1"
                      >
                        {{ renderCellValue(row[col]) }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <!-- 超过10行的提示 -->
              <div
                v-if="getTotalCount(msg.extractionData) > MAX_TABLE_ROWS"
                class="mt-2 text-xs text-gray-500"
              >
                共 {{ getTotalCount(msg.extractionData) }} 条记录，仅显示前 {{ MAX_TABLE_ROWS }} 条。完整数据已保存。
              </div>
            </template>
            <!-- 普通 Markdown 渲染 -->
            <template v-else>
              <div
                class="assistant-md break-words text-left"
                v-html="renderAssistant(msg)"
              />
            </template>
            <div class="mt-1 text-xs text-gray-400">
              {{ formatTime(msg.created_at) }}
            </div>
          </div>
        </div>

        <!-- 正在输入指示器 -->
        <div v-if="showStreamingPlaceholder" class="flex justify-start">
          <div class="bg-gray-100 rounded-lg px-4 py-2 text-gray-500">
            <span class="animate-pulse">正在输入...</span>
          </div>
        </div>

        <!-- 进度条消息（仅实体提取模式） -->
        <div v-if="showProgress && sessionStore.currentMode === 'entity_extraction'" class="flex justify-start">
          <div class="w-1/2 bg-gray-50 rounded-lg px-4 py-3 text-gray-800 shadow-sm">
            <div class="flex items-center justify-between mb-2">
              <div class="flex items-center gap-2">
                <span class="text-sm font-medium text-gray-700">实体提取中</span>
                <span class="text-xs text-gray-400">{{ progressMsg }}</span>
              </div>
              <span v-if="progressVal < 100" class="text-xs text-gray-400 animate-pulse">
                ●
              </span>
              <span v-else class="text-xs text-green-500 font-medium">完成</span>
            </div>
            <n-progress
              type="line"
              :percentage="progressVal"
              :show-indicator="false"
              :height="10"
              :border-radius="5"
              color="#10b981"
              rail-color="#e5e7eb"
            />
          </div>
        </div>
      </div>
    </n-scrollbar>

    <!-- 输入区域 -->
    <div class="border-t bg-white p-4">
      <div class="flex gap-2">
        <n-input
          v-model:value="inputValue"
          type="textarea"
          :rows="2"
          placeholder="输入消息... (Enter 发送，Shift+Enter 换行)"
          @keydown="handleKeydown"
        />
        <n-button
          type="primary"
          :disabled="!inputValue.trim()"
          :loading="sessionStore.isStreaming"
          @click="handleSend"
        >
          发送
        </n-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.assistant-md :deep(p) {
  margin: 0.35em 0;
}
.assistant-md :deep(p:first-child) {
  margin-top: 0;
}
.assistant-md :deep(p:last-child) {
  margin-bottom: 0;
}
.assistant-md :deep(ul),
.assistant-md :deep(ol) {
  margin: 0.35em 0;
  padding-left: 1.25rem;
}
.assistant-md :deep(ul) {
  list-style-type: disc;
}
.assistant-md :deep(ol) {
  list-style-type: decimal;
}
.assistant-md :deep(pre) {
  margin: 0.5em 0;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.06);
  overflow-x: auto;
  font-size: 0.875em;
}
.assistant-md :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.9em;
}
.assistant-md :deep(p code),
.assistant-md :deep(li code) {
  padding: 0.1em 0.35em;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.08);
}
.assistant-md :deep(a) {
  color: #15803d;
  text-decoration: underline;
}
.assistant-md :deep(strong) {
  font-weight: 600;
}
</style>
