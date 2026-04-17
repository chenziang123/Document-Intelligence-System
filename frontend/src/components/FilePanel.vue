<script setup>
import { computed, ref } from 'vue'
import { NUpload, NButton, NTag, NAlert, NScrollbar, useMessage } from 'naive-ui'
import { useSessionStore } from '../stores/sessionStore'

const message = useMessage()
const sessionStore = useSessionStore()
const uploadingCount = ref(0)
const isUploading = computed(() => uploadingCount.value > 0)

// 上传区域只显示临时文件
const tempDataFiles = computed(() => sessionStore.tempDataFiles)
const tempTemplateFiles = computed(() => sessionStore.tempTemplateFiles)

// 根据当前模式判断是否需要显示数据文件
const showDataTab = computed(() => {
  return sessionStore.currentModeConfig.requiresData !== false
})

// 根据当前模式判断是否需要显示模板
const showTemplateTab = computed(() => {
  const config = sessionStore.currentModeConfig
  return config.requiresTemplate !== false
})

// 判断是否有未上传必需模板
const templateRequired = computed(() => {
  return sessionStore.currentModeConfig.requiresTemplate === true
})

// 整个上传区域是否显示
const showUploadPanel = computed(() => {
  return showDataTab.value || showTemplateTab.value
})

const hasTemplateWarning = computed(() => {
  // table_filling 模式下不显示警告
  if (sessionStore.currentMode === 'table_filling') {
    return null
  }
  if (templateRequired.value && sessionStore.selectedTempTemplateFiles.length === 0) {
    return 'warning'
  }
  return null
})

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function getFileTypeTag(type) {
  const ext = type.split('.').pop().toLowerCase()
  const map = {
    pdf:  { tag: 'error',   label: 'PDF' },
    doc:  { tag: 'info',   label: 'DOC' },
    docx: { tag: 'info',   label: 'DOCX' },
    xls:  { tag: 'success', label: 'XLS' },
    xlsx: { tag: 'success', label: 'XLSX' },
    txt:  { tag: 'default', label: 'TXT' },
    md:   { tag: 'default', label: 'MD' },
    csv:  { tag: 'warning', label: 'CSV' },
    png:  { tag: 'info',   label: 'PNG' },
    jpg:  { tag: 'info',   label: 'JPG' },
    jpeg: { tag: 'info',   label: 'JPEG' },
  }
  const item = map[ext]
  return item ? { tag: item.tag, label: item.label } : { tag: 'default', label: ext.toUpperCase() }
}

async function handleUploadRequest(options, fileType) {
  const uploadInfo = options?.file
  const rawFile = uploadInfo?.file || uploadInfo
  if (!rawFile) {
    options?.onError?.()
    message.error('上传失败: 无法读取文件对象')
    return
  }

  // 无会话时自动创建（沿用当前选中的模式）
  if (!sessionStore.currentSessionId) {
    await sessionStore.createSession()
  }
  uploadingCount.value += 1
  try {
    await sessionStore.uploadFile(rawFile, fileType)
    options?.onFinish?.()
    message.success('上传成功')
  } catch (e) {
    options?.onError?.()
    message.error('上传失败: ' + e.message)
  } finally {
    uploadingCount.value = Math.max(0, uploadingCount.value - 1)
  }
}
</script>

<template>
  <div v-if="showUploadPanel">
    <!-- 警告提示 -->
    <n-alert
      v-if="hasTemplateWarning"
      type="warning"
      :title="templateRequired ? '请上传模板文件' : '提示'"
      class="mb-3"
      :bordered="false"
    >
      {{ templateRequired ? '当前模式需要模板文件才能正常工作' : '如需指定输出格式，请上传模板文件' }}
    </n-alert>

    <!-- 数据文件 -->
    <div v-if="showDataTab" class="mb-3">
      <div class="flex items-center justify-between mb-2">
        <span class="text-sm font-medium text-gray-700">
          数据文件
          <span class="text-gray-400 text-xs">({{ tempDataFiles.length }})</span>
        </span>
        <n-upload
          :custom-request="(options) => handleUploadRequest(options, 'data')"
          :show-file-list="false"
          :disabled="isUploading"
          accept=".pdf,.doc,.docx,.xls,.xlsx,.txt,.md"
          multiple
        >
          <n-button size="small" :loading="isUploading">+ 上传数据</n-button>
        </n-upload>
      </div>

      <n-scrollbar x-scrollable v-if="tempDataFiles.length > 0">
        <div class="flex gap-2 pb-1">
          <div
            v-for="file in tempDataFiles"
            :key="file.id"
            :class="[
              'flex items-center gap-2 px-3 py-1.5 rounded border text-sm',
              file.is_selected ? 'bg-green-50 border-green-300' : 'bg-white border-gray-200'
            ]"
          >
            <input
              type="checkbox"
              :checked="file.is_selected"
              @change="sessionStore.toggleFileSelection(file.id, 'data', $event.target.checked)"
              class="w-4 h-4 text-green-600 rounded focus:ring-green-500"
            />
            <span class="truncate max-w-32">{{ file.file_name }}</span>
            <n-tag :type="getFileTypeTag(file.file_name).tag" size="tiny">{{ getFileTypeTag(file.file_name).label }}</n-tag>
            <span class="text-xs text-gray-400">{{ formatSize(file.file_size) }}</span>
            <button
              @click="sessionStore.deleteFile(file.id, 'data')"
              class="text-gray-400 hover:text-red-500"
            >
              ×
            </button>
          </div>
        </div>
      </n-scrollbar>
      <div v-else class="text-gray-400 text-sm">暂无数据文件</div>
    </div>

    <!-- 模板文件（条件显示） -->
    <div v-if="showTemplateTab">
      <div class="border-t pt-3">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-medium text-gray-700">
            模板文件
            <span class="text-gray-400 text-xs">({{ tempTemplateFiles.length }})</span>
          </span>
          <n-upload
            :custom-request="(options) => handleUploadRequest(options, 'template')"
            :show-file-list="false"
            :disabled="isUploading"
            accept=".pdf,.doc,.docx,.xls,.xlsx,.txt,.md"
            multiple
          >
            <n-button size="small" :loading="isUploading">+ 上传模板</n-button>
          </n-upload>
        </div>

        <n-scrollbar x-scrollable v-if="tempTemplateFiles.length > 0">
          <div class="flex gap-2 pb-1">
            <div
              v-for="file in tempTemplateFiles"
              :key="file.id"
              :class="[
                'flex items-center gap-2 px-3 py-1.5 rounded border text-sm',
                file.is_selected ? 'bg-green-50 border-green-300' : 'bg-white border-gray-200'
              ]"
            >
              <input
                type="checkbox"
                :checked="file.is_selected"
                @change="sessionStore.toggleFileSelection(file.id, 'template', $event.target.checked)"
                class="w-4 h-4 text-green-600 rounded focus:ring-green-500"
              />
              <span class="truncate max-w-32">{{ file.file_name }}</span>
              <n-tag :type="getFileTypeTag(file.file_name).tag" size="tiny">{{ getFileTypeTag(file.file_name).label }}</n-tag>
              <span class="text-xs text-gray-400">{{ formatSize(file.file_size) }}</span>
              <button
                @click="sessionStore.deleteFile(file.id, 'template')"
                class="text-gray-400 hover:text-red-500"
              >
                ×
              </button>
            </div>
          </div>
        </n-scrollbar>
        <div v-else class="text-gray-400 text-sm">暂无模板文件</div>
      </div>
    </div>
  </div>
</template>
