import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import fileApi from '../api/files'
import { useSessionStore } from './sessionStore'

export const useFileStore = defineStore('file', () => {
  const currentFileType = ref('data')
  const filesPanelCollapsed = ref(true)
  const searchQuery = ref('')
  const isUploading = ref(false)

  const uploadedFiles = ref({
    data: [],
    template: []
  })

  const tempFiles = ref({
    data: [],
    template: []
  })

  const currentFiles = computed(() => tempFiles.value[currentFileType.value])

  const hasDataFiles = computed(() => tempFiles.value.data.length > 0)
  const hasTemplateFiles = computed(() => tempFiles.value.template.length > 0)
  const hasFiles = computed(() => hasDataFiles.value || hasTemplateFiles.value)

  const dataCount = computed(() => tempFiles.value.data.length)
  const templateCount = computed(() => tempFiles.value.template.length)

  function switchFileType(type) {
    currentFileType.value = type
  }

  function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  }

  async function addFile(type, file) {
    // 生成唯一ID
    const tempId = 'temp_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9)
    
    // 创建文件对象URL（用于预览）
    const fileUrl = URL.createObjectURL(file)
    
    // 只保存到临时状态，不上传到服务器
    const fileInfo = {
      id: tempId,
      file_name: file.name,
      file_size: file.size,
      file_type: type,
      file_url: fileUrl,
      original_file: file, // 原始文件对象
      is_selected: true,
      created_at: new Date().toISOString(),
    }
    
    tempFiles.value[type].push(fileInfo)
    uploadedFiles.value[type].push({ ...fileInfo })
  }

  async function removeFile(id, type) {
    const sessionStore = useSessionStore()
    const index = tempFiles.value[type].findIndex(f => f.id === id)
    if (index > -1) {
      const fileInfo = tempFiles.value[type][index]
      // 如果是数据库文件，调用 API 删除
      if (!String(id).startsWith('temp_')) {
        try {
          await fileApi.delete(sessionStore.currentSessionId, id)
        } catch (e) {
          console.warn('删除文件失败:', e)
        }
      }
      // 从 tempFiles 中移除
      tempFiles.value[type].splice(index, 1)
      // 同时从 uploadedFiles 中移除
      const uploadedIndex = uploadedFiles.value[type].findIndex(f => f.id === id)
      if (uploadedIndex > -1) {
        uploadedFiles.value[type].splice(uploadedIndex, 1)
      }
    }
  }

  function toggleFileSelection(id, type, isSelected) {
    // 更新 tempFiles
    const tempIndex = tempFiles.value[type].findIndex(f => f.id === id)
    if (tempIndex > -1) {
      tempFiles.value[type][tempIndex].is_selected = isSelected
    }
    // 同时更新 uploadedFiles
    const uploadedIndex = uploadedFiles.value[type].findIndex(f => f.id === id)
    if (uploadedIndex > -1) {
      uploadedFiles.value[type][uploadedIndex].is_selected = isSelected
    }
  }

  function getFileIcon(filename) {
    const ext = filename.split('.').pop().toLowerCase()
    if (['pdf'].includes(ext)) return '📄'
    if (['doc', 'docx'].includes(ext)) return '📝'
    if (['xls', 'xlsx', 'csv'].includes(ext)) return '📊'
    if (['png', 'jpg', 'jpeg'].includes(ext)) return '🖼️'
    return '📎'
  }

  function getFileTypeLabel(filename) {
    const ext = filename.split('.').pop().toLowerCase()
    const map = {
      pdf: 'PDF',
      doc: 'DOC',
      docx: 'DOCX',
      xls: 'XLS',
      xlsx: 'XLSX',
      txt: 'TXT',
      md: 'MD',
      csv: 'CSV',
      png: 'PNG',
      jpg: 'JPG',
      jpeg: 'JPEG',
    }
    return map[ext] || ext.toUpperCase()
  }

  function toggleFilesPanel() {
    filesPanelCollapsed.value = !filesPanelCollapsed.value
  }

  return {
    currentFileType,
    filesPanelCollapsed,
    searchQuery,
    uploadedFiles,
    tempFiles,
    currentFiles,
    hasDataFiles,
    hasTemplateFiles,
    hasFiles,
    dataCount,
    templateCount,
    isUploading,
    switchFileType,
    addFile,
    removeFile,
    toggleFileSelection,
    toggleFilesPanel,
    getFileIcon,
    getFileTypeLabel,
    setSearchQuery: (q) => { searchQuery.value = q }
  }
})
