import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import sessionApi from '../api/sessions'
import messageApi from '../api/messages'
import fileApi from '../api/files'
import { getAccessToken } from '../api/auth'
import { useFileStore } from './fileStore'

const SESSIONS_KEY = 'doc_sessions'
const MESSAGES_KEY = 'doc_messages_'

function readCache(key) {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function writeCache(key, data) {
  try {
    localStorage.setItem(key, JSON.stringify({ _ts: Date.now(), ...data }))
  } catch {}
}

function removeCache(key) {
  try {
    localStorage.removeItem(key)
  } catch {}
}

function saveSessionsCache(sessions, currentSessionId) {
  writeCache(SESSIONS_KEY, { sessions, currentSessionId })
}

function loadSessionsCache() {
  return readCache(SESSIONS_KEY)
}

function saveMessagesCache(sessionId, messages) {
  writeCache(MESSAGES_KEY + sessionId, { messages })
}

function loadMessagesCache(sessionId) {
  return readCache(MESSAGES_KEY + sessionId)
}

export const useSessionStore = defineStore('session', () => {
  const sessions = ref([])
  const currentSessionId = ref(null)
  const messages = ref([])
  const isLoading = ref(false)
  const isInitializing = ref(true)
  const isStreaming = ref(false)
  const isUploadingFiles = ref(false)
  const uploadProgress = ref('')
  const sidebarCollapsed = ref(false)
  const ws = ref(null)
  const wsConnecting = ref(false)

  // 模式相关
  const currentMode = ref('default_conversation')
  const modeConfig = {
    'default_conversation': { requiresData: false, requiresTemplate: false },
    'document_understanding': { requiresData: true, requiresTemplate: false },
    'document_editing': { requiresData: true, requiresTemplate: false },
  }
  const currentModeConfig = computed(() => modeConfig[currentMode.value] || modeConfig['default_conversation'])

  // 获取选中的文件（区分已上传和临时文件）
  function getSelectedFilesPayload() {
    const fileStore = useFileStore()
    // 临时文件（有 original_file 需上传）
    const tempDataFiles = fileStore.tempFiles.data.filter(f => f.is_selected && f.original_file)
    const tempTemplateFiles = fileStore.tempFiles.template.filter(f => f.is_selected && f.original_file)
    // 已上传文件（有 file_path 不用再上传）
    const uploadedDataFiles = fileStore.tempFiles.data.filter(f => f.is_selected && !f.original_file)
    const uploadedTemplateFiles = fileStore.tempFiles.template.filter(f => f.is_selected && !f.original_file)

    console.log('[getSelectedFilesPayload] tempDataFiles:', tempDataFiles)
    console.log('[getSelectedFilesPayload] tempTemplateFiles:', tempTemplateFiles)
    console.log('[getSelectedFilesPayload] uploadedDataFiles:', uploadedDataFiles)
    console.log('[getSelectedFilesPayload] uploadedTemplateFiles:', uploadedTemplateFiles)

    return {
      // 需要上传的临时文件（包含原始文件对象）
      tempFiles: tempDataFiles.map(f => ({ ...f })),
      tempTemplateFiles: tempTemplateFiles.map(f => ({ ...f })),
      // 已上传的文件（确保包含 storage_key 供后端使用）
      files: uploadedDataFiles.map(f => ({
        id: f.id,
        file_name: f.file_name,
        file_path: f.file_path,
        storage_key: f.storage_key || f.file_path,
        file_size: f.file_size,
        file_type: f.file_type || 'data',
      })),
      template_files: uploadedTemplateFiles.map(f => ({
        id: f.id,
        file_name: f.file_name,
        file_path: f.file_path,
        storage_key: f.storage_key || f.file_path,
        file_size: f.file_size,
        file_type: f.file_type || 'template',
      })),
    }
  }
  
  // 上传临时文件到服务器
  async function uploadTempFiles(tempDataFiles, tempTemplateFiles, onProgress) {
    const fileStore = useFileStore()
    const uploadedFiles = []
    const uploadedTemplateFiles = []
    const allFiles = [...tempDataFiles, ...tempTemplateFiles]
    let uploadedCount = 0
    console.log('[uploadTempFiles] 开始上传临时文件:', { tempDataFiles, tempTemplateFiles })
    
    // 上传数据文件
    for (const file of tempDataFiles) {
      try {
        console.log('[uploadTempFiles] 上传数据文件:', file.file_name, file.original_file)
        const res = await fileApi.upload(currentSessionId.value, file.original_file, 'data')
        console.log('[uploadTempFiles] 数据文件上传响应:', res)
        uploadedCount++
        onProgress?.(uploadedCount, allFiles.length)
        // 更新本地状态，替换 temp 记录为正式记录
        const filePath = res.file_path || res.path || res.storage_key || ''
        const updatedFileInfo = {
          id: res.id,
          file_name: res.file_name || file.file_name,
          file_path: filePath,
          storage_key: filePath,  // 确保有 storage_key 字段
          file_size: res.file_size || file.file_size,
          file_type: 'data',
          is_selected: true,
          created_at: res.created_at || new Date().toISOString(),
        }
        // 更新 tempFiles
        const index = fileStore.tempFiles.data.findIndex(f => f.id === file.id)
        if (index > -1) {
          fileStore.tempFiles.data[index] = updatedFileInfo
        }
        // 同时更新 uploadedFiles（移除旧记录，添加新记录）
        const uploadedIndex = fileStore.uploadedFiles.data.findIndex(f => f.id === file.id || f.id === res.id)
        if (uploadedIndex > -1) {
          fileStore.uploadedFiles.data[uploadedIndex] = updatedFileInfo
        } else {
          fileStore.uploadedFiles.data.push(updatedFileInfo)
        }
        console.log('[uploadTempFiles] 文件路径:', filePath)
        uploadedFiles.push(updatedFileInfo)
      } catch (e) {
        console.error('[uploadTempFiles] 上传数据文件失败:', e)
      }
    }
    
    // 上传模板文件
    for (const file of tempTemplateFiles) {
      try {
        console.log('[uploadTempFiles] 上传模板文件:', file.file_name, file.original_file)
        const res = await fileApi.upload(currentSessionId.value, file.original_file, 'template')
        console.log('[uploadTempFiles] 模板文件上传响应:', res)
        uploadedCount++
        onProgress?.(uploadedCount, allFiles.length)
        const index = fileStore.tempFiles.template.findIndex(f => f.id === file.id)
        const filePath = res.file_path || res.path || res.storage_key || ''
        const updatedTemplateInfo = {
          id: res.id,
          file_name: res.file_name || file.file_name,
          file_path: filePath,
          storage_key: filePath,  // 确保有 storage_key 字段
          file_size: res.file_size || file.file_size,
          file_type: 'template',
          is_selected: true,
          created_at: res.created_at || new Date().toISOString(),
        }
        if (index > -1) {
          fileStore.tempFiles.template[index] = updatedTemplateInfo
        }
        // 同时更新 uploadedFiles
        const uploadedIndex = fileStore.uploadedFiles.template.findIndex(f => f.id === file.id || f.id === res.id)
        if (uploadedIndex > -1) {
          fileStore.uploadedFiles.template[uploadedIndex] = updatedTemplateInfo
        } else {
          fileStore.uploadedFiles.template.push(updatedTemplateInfo)
        }
        console.log('[uploadTempFiles] 模板文件路径:', filePath)
        uploadedTemplateFiles.push(updatedTemplateInfo)
      } catch (e) {
        console.error('[uploadTempFiles] 上传模板文件失败:', e)
      }
    }
    
    console.log('[uploadTempFiles] 上传完成:', { uploadedFiles, uploadedTemplateFiles })
    return { uploadedFiles, uploadedTemplateFiles }
  }

  // 清除所有选中的文件
  function clearAllSelectedFiles() {
    const fileStore = useFileStore()
    fileStore.tempFiles.data.forEach(f => { f.is_selected = false })
    fileStore.tempFiles.template.forEach(f => { f.is_selected = false })
    fileStore.uploadedFiles.data.forEach(f => { f.is_selected = false })
    fileStore.uploadedFiles.template.forEach(f => { f.is_selected = false })
    // 同步到服务器
    syncFileSelectionToServer()
  }

  // 同步文件勾选状态到服务器
  async function syncFileSelectionToServer() {
    if (!currentSessionId.value) return
    try {
      const fileStore = useFileStore()
      const tasks = []
      const selections = []
      
      console.log('[syncFileSelectionToServer] 开始同步文件勾选状态')
      console.log('[syncFileSelectionToServer] uploadedFiles.data:', fileStore.uploadedFiles.data)
      console.log('[syncFileSelectionToServer] uploadedFiles.template:', fileStore.uploadedFiles.template)
      
      fileStore.uploadedFiles.data.forEach(f => {
        selections.push({ file_id: f.id, is_selected: f.is_selected })
      })
      fileStore.uploadedFiles.template.forEach(f => {
        selections.push({ file_id: f.id, is_selected: f.is_selected })
      })
      
      console.log('[syncFileSelectionToServer] 准备同步的 selections:', selections)
      
      if (selections.length > 0) {
        try {
          await fileApi.updateSelection(currentSessionId.value, selections)
          console.log('[syncFileSelectionToServer] 同步成功')
        } catch (e) {
          console.error('[syncFileSelectionToServer] 同步失败:', e)
        }
      }
    } catch (e) {
      console.error('[syncFileSelectionToServer] 同步文件勾选状态失败:', e)
    }
  }

  // 从数据库加载文件列表
  async function loadFiles(sessionId) {
    try {
      const res = await fileApi.list(sessionId)
      const fileStore = useFileStore()
      fileStore.uploadedFiles.data = res.data_files || []
      fileStore.uploadedFiles.template = res.template_files || []
      // 同步到 tempFiles
      fileStore.tempFiles.data = [...fileStore.uploadedFiles.data]
      fileStore.tempFiles.template = [...fileStore.uploadedFiles.template]
    } catch (e) {
      console.error('加载文件失败:', e)
    }
  }

  const currentSession = computed(() =>
    sessions.value.find(s => s.session_id === currentSessionId.value)
  )

  function formatTime(isoString) {
    // 防御：如果没有有效时间，使用空字符串
    const date = isoString ? new Date(isoString) : null
    if (!date || isNaN(date.getTime())) return ''
    const now = new Date()
    const diff = now - date
    const diffDays = Math.floor(diff / 86400000)

    if (diff < 60000) return '刚刚'
    if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
    if (diff < 86400000) {
      // 今天：显示 HH:mm
      return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
    }
    if (diffDays < 3) {
      return `${diffDays}天前`
    }
    // 3天及以上：显示日期
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    return `${year}/${month}/${day}`
  }

  async function switchMode(mode) {
    if (currentMode.value === mode) return
    currentMode.value = mode

    const modeNames = {
      'default_conversation': '默认对话',
      'document_understanding': '文档理解',
      'document_editing': '文档编辑',
    }

    messages.value.push({
      id: Date.now(),
      role: 'system',
      content: `已切换至「${modeNames[mode] || mode}」模式`,
      created_at: new Date().toISOString(),
    })

    // 同步模式到服务器
    if (currentSessionId.value) {
      const idx = sessions.value.findIndex(s => s.session_id === currentSessionId.value)
      if (idx !== -1) {
        sessions.value[idx] = { ...sessions.value[idx], current_mode: mode }
        saveSessionsCache(sessions.value, currentSessionId.value)
      }
      sessionApi.update(currentSessionId.value, { current_mode: mode }).catch(e =>
        console.warn('[switchMode] 更新模式失败:', e.message)
      )
    }
  }

  async function loadSessions() {
    try {
      const res = await sessionApi.list()
      sessions.value = (res.items || []).map(s => ({
        ...s,
        updated_at: s.updated_at || s.created_at || new Date().toISOString(),
      }))
      saveSessionsCache(sessions.value, currentSessionId.value)

      // 如果有当前会话，同步 current_mode
      if (currentSessionId.value) {
        const sess = sessions.value.find(s => s.session_id === currentSessionId.value)
        console.log('[loadSessions] 查找当前会话:', currentSessionId.value, '结果:', sess)
        if (sess?.current_mode) {
          currentMode.value = sess.current_mode
          console.log('[loadSessions] 从服务器同步 currentMode:', currentMode.value)
        } else {
          console.log('[loadSessions] 服务器会话无current_mode, 保持 currentMode:', currentMode.value)
        }
      }
    } catch (e) {
      console.error('[loadSessions] 加载会话列表失败:', e)
    }
  }

  async function createSession() {
    const tempId = `temp_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    const newSession = {
      session_id: tempId,
      title: '新会话',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    sessions.value.unshift(newSession)
    currentSessionId.value = tempId
    messages.value = []
    connectWebSocket()

    try {
      const res = await sessionApi.create({ title: '新会话', current_mode: 'default_conversation' })
      const idx = sessions.value.findIndex(s => s.session_id === tempId)
      if (idx !== -1) {
        sessions.value[idx] = res
      }
      currentSessionId.value = res.session_id
      // 新会话创建后重置模式为默认
      currentMode.value = 'default_conversation'
      // 加载新会话的文件列表（为空）
      loadFiles(res.session_id).catch(console.error)
      saveSessionsCache(sessions.value, res.session_id)
    } catch (e) {
      console.error('创建会话失败:', e)
      sessions.value = sessions.value.filter(s => s.session_id !== tempId)
      currentSessionId.value = sessions.value[0]?.session_id || null
    }
  }

  async function selectSession(sessionId) {
    if (currentSessionId.value === sessionId) return

    const prevWs = ws.value
    if (prevWs) {
      prevWs.onclose = null
      prevWs.onerror = null
      prevWs.close()
    }

    currentSessionId.value = sessionId

    // 切换到该会话保存的模式（如果没有则使用默认模式）
    const sess = sessions.value.find(s => s.session_id === sessionId)
    currentMode.value = sess?.current_mode || 'default_conversation'

    messages.value = []
    await new Promise(resolve => setTimeout(resolve, 100))
    connectWebSocket()

    const cachedMsgs = loadMessagesCache(sessionId)
    if (cachedMsgs && cachedMsgs.messages?.length > 0) {
      messages.value = cachedMsgs.messages
    } else {
      loadMessages(sessionId).catch(console.error)
    }

    // 从数据库加载文件列表
    loadFiles(sessionId).catch(console.error)

    saveSessionsCache(sessions.value, sessionId)
  }

  async function deleteSession(sessionId) {
    const wasCurrentSession = currentSessionId.value === sessionId
    const remainingSessions = sessions.value.filter(s => s.session_id !== sessionId)
    sessions.value = remainingSessions

    const nextSession = remainingSessions[0]
    const nextSessionId = nextSession?.session_id || null
    saveSessionsCache(remainingSessions, nextSessionId)
    removeCache(MESSAGES_KEY + sessionId)

    if (wasCurrentSession) {
      if (nextSession) {
        currentSessionId.value = nextSession.session_id
        messages.value = []
        const wsPrev = ws.value
        if (wsPrev) {
          wsPrev.onclose = null
          wsPrev.onerror = null
          wsPrev.close()
        }
        connectWebSocket()
        const cachedMsgs = loadMessagesCache(nextSession.session_id)
        if (cachedMsgs?.messages?.length > 0) {
          messages.value = cachedMsgs.messages
        } else {
          loadMessages(nextSession.session_id).catch(console.error)
        }
      } else {
        currentSessionId.value = null
        messages.value = []
        disconnectWebSocket()
      }
    }

    try {
      await sessionApi.delete(sessionId)
    } catch (e) {
      console.error('删除会话失败:', e)
    }
  }

  async function updateSessionTitle(sessionId, title) {
    try {
      const res = await sessionApi.update(sessionId, { title })
      const idx = sessions.value.findIndex(s => s.session_id === sessionId)
      if (idx !== -1) {
        sessions.value[idx] = { ...sessions.value[idx], ...res }
        saveSessionsCache(sessions.value, currentSessionId.value)
      }
    } catch (e) {
      console.error('更新会话失败:', e)
    }
  }

  async function loadMessages(sessionId) {
    try {
      const res = await messageApi.list(sessionId)
      const msgs = Array.isArray(res) ? res : []
      if (msgs.length > 0 || currentSessionId.value === sessionId) {
        messages.value = msgs
        saveMessagesCache(sessionId, msgs)
      }
    } catch (e) {
      console.warn('加载消息失败:', e.message)
    }
  }

  function connectWebSocket() {
    if (!currentSessionId.value) return

    if (wsConnecting.value) return

    if (ws.value) {
      ws.value.onclose = null
      ws.value.onerror = null
      ws.value.close()
      ws.value = null
    }

    isStreaming.value = false
    wsConnecting.value = true

    ws.value = messageApi.connect(currentSessionId.value)

    ws.value.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'start') {
        // 开始接收响应
      } else if (data.type === 'chunk') {
        // 收到第一个 chunk 时立即停止 loading 动画
        isStreaming.value = false
        const lastMsg = messages.value[messages.value.length - 1]
        if (lastMsg && lastMsg.role === 'assistant') {
          lastMsg.content += data.content
        } else {
          messages.value.push({
            id: Date.now(),
            role: 'assistant',
            content: data.content,
            created_at: new Date().toISOString(),
          })
        }
      } else if (data.type === 'done') {
        isStreaming.value = false
        if (currentSessionId.value) {
          saveMessagesCache(currentSessionId.value, messages.value)
        }
      } else if (data.type === 'error') {
        const errorMsg = typeof data.message === 'string' ? data.message : JSON.stringify(data.message)
        console.error('流式错误:', errorMsg)
        isStreaming.value = false
        messages.value.push({
          id: Date.now(),
          role: 'assistant',
          content: `错误: ${errorMsg}`,
          created_at: new Date().toISOString(),
        })
      }
    }

    ws.value.onclose = () => {
      ws.value = null
      isStreaming.value = false
      wsConnecting.value = false
    }

    ws.value.onerror = () => {
      console.warn('[WebSocket] 连接失败')
      ws.value = null
      isStreaming.value = false
      wsConnecting.value = false
    }

    ws.value.onopen = () => {
      console.log('[WebSocket] onopen - 连接已建立')
      wsConnecting.value = false
    }

    ws.value.send = new Proxy(ws.value.send, {
      apply(target, thisArg, args) {
        console.log('[WebSocket] 发送消息:', args[0] ? JSON.parse(args[0]) : args[0])
        return target.apply(thisArg, args)
      }
    })
  }

  function disconnectWebSocket() {
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }
    isStreaming.value = false
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function waitForWebSocketOpen(maxMs = 8000) {
    return new Promise((resolve) => {
      const socket = ws.value
      if (!socket) {
        resolve(false)
        return
      }
      if (socket.readyState === WebSocket.OPEN) {
        resolve(true)
        return
      }
      if (socket.readyState === WebSocket.CONNECTING) {
        setTimeout(() => resolve(waitForWebSocketOpen(maxMs)), 50)
        return
      }
      const start = Date.now()
      const t = setInterval(() => {
        if (!ws.value || ws.value !== socket) {
          clearInterval(t)
          resolve(false)
          return
        }
        if (socket.readyState === WebSocket.OPEN) {
          clearInterval(t)
          resolve(true)
          return
        }
        if (Date.now() - start > maxMs) {
          clearInterval(t)
          resolve(false)
          return
        }
      }, 50)
    })
  }

  async function sendMessage(content, mode = 'default_conversation') {
    if (!content.trim()) return

    if (!currentSessionId.value) {
      await createSession()
    }

    const sessionId = currentSessionId.value
    const { tempFiles, tempTemplateFiles, files: uploadedFiles, template_files: uploadedTemplateFiles } = getSelectedFilesPayload()
    const effectiveMode = mode || currentMode.value || 'default_conversation'
    const hasPendingFiles = tempFiles.length > 0 || tempTemplateFiles.length > 0

    console.log('[sendMessage] 发送消息:', { content, effectiveMode, hasPendingFiles, uploadedFiles, uploadedTemplateFiles, tempFiles: tempFiles.length, tempTemplateFiles: tempTemplateFiles.length })

    // 立即显示用户消息（带待上传状态的文件）
    const tempMsgId = Date.now()
    const pendingFiles = [
      ...uploadedFiles.map(f => ({ ...f, pending: false })),
      ...uploadedTemplateFiles.map(f => ({ ...f, pending: false })),
      ...tempFiles.map(f => ({ file_name: f.file_name, file_size: f.file_size, pending: true })),
      ...tempTemplateFiles.map(f => ({ file_name: f.file_name, file_size: f.file_size, pending: true })),
    ]
    console.log('[sendMessage] pendingFiles:', pendingFiles)
    messages.value.push({
      id: tempMsgId,
      role: 'user',
      content: content.trim(),
      created_at: new Date().toISOString(),
      metadata: { files: pendingFiles },
    })

    // 立即设置 loading 状态
    isStreaming.value = true

    // 需要上传的文件列表
    let allFiles = [...uploadedFiles]
    let allTemplateFiles = [...uploadedTemplateFiles]

    // 后台上传临时文件（不等完成）
    if (hasPendingFiles) {
      const totalFiles = tempFiles.length + tempTemplateFiles.length
      isUploadingFiles.value = true
      uploadProgress.value = `正在上传文件 (0/${totalFiles})...`
      
      uploadTempFiles(tempFiles, tempTemplateFiles, (count, total) => {
        uploadProgress.value = `正在上传文件 (${count}/${total})...`
      }).then(({ uploadedFiles: newFiles, uploadedTemplateFiles: newTemplateFiles }) => {
        console.log('[sendMessage] 上传完成，准备发送:', { newFiles, newTemplateFiles })
        allFiles = [...allFiles, ...newFiles]
        allTemplateFiles = [...allTemplateFiles, ...newTemplateFiles]
        isUploadingFiles.value = false
        
        // 更新消息中的文件为已上传状态
        const msgIndex = messages.value.findIndex(m => m.id === tempMsgId)
        if (msgIndex > -1) {
          messages.value[msgIndex].metadata = {
            files: [...allFiles.map(f => ({ ...f, pending: false })), ...allTemplateFiles.map(f => ({ ...f, pending: false }))]
          }
          console.log('[sendMessage] 更新消息文件状态:', messages.value[msgIndex].metadata)
        }
        
        // 上传完成后发送消息
        sendToBackend(sessionId, content.trim(), effectiveMode, allFiles, allTemplateFiles)
      }).catch(err => {
        console.error('[sendMessage] 上传文件失败:', err)
        isUploadingFiles.value = false
        // 上传失败也要发送消息（不带文件）
        sendToBackend(sessionId, content.trim(), effectiveMode, [], [])
      })
    } else {
      // 没有待上传文件，直接发送
      sendToBackend(sessionId, content.trim(), effectiveMode, allFiles, allTemplateFiles)
    }
  }

  async function sendToBackend(sessionId, content, mode, files, template_files) {
    console.log('[sendToBackend] 发送请求:', { sessionId, content, mode, files, template_files })
    clearAllSelectedFiles()
    
    const canStream = await waitForWebSocketOpen()
    if (ws.value && ws.value.readyState === WebSocket.OPEN && canStream) {
      console.log('[sendToBackend] 通过 WebSocket 发送')
      ws.value.send(JSON.stringify({
        content,
        mode,
        files,
        template_files,
      }))
    } else {
      console.log('[sendToBackend] 通过 API 发送')
      try {
        await messageApi.send(sessionId, {
          content,
          mode,
          files,
          template_files,
        })
        await loadMessages(sessionId)
      } catch (e) {
        console.error('[sendToBackend] 发送消息失败:', e)
        messages.value.push({
          id: Date.now(),
          role: 'assistant',
          content: `发送失败: ${e.message}`,
          created_at: new Date().toISOString(),
        })
      } finally {
        isStreaming.value = false
      }
    }
  }

  async function init() {
    console.log('[init] 开始初始化')
    isInitializing.value = true

    const cached = loadSessionsCache()
    console.log('[init] 缓存数据:', cached)
    if (cached?.sessions?.length > 0) {
      sessions.value = cached.sessions
      console.log('[init] 从缓存加载会话列表, 数量:', cached.sessions.length)
      if (cached.currentSessionId) {
        currentSessionId.value = cached.currentSessionId
        console.log('[init] 当前会话ID:', cached.currentSessionId)
        const sess = sessions.value.find(s => s.session_id === cached.currentSessionId)
        console.log('[init] 缓存会话对象:', sess)
        // 确保 currentMode 始终有值
        currentMode.value = sess?.current_mode || 'default_conversation'
        console.log('[init] 初始 currentMode:', currentMode.value)
        const cachedMsgs = loadMessagesCache(cached.currentSessionId)
        if (cachedMsgs?.messages) {
          messages.value = cachedMsgs.messages
        }
      } else {
        currentMode.value = 'default_conversation'
        console.log('[init] 无当前会话ID, currentMode设为默认值')
      }
    } else {
      currentMode.value = 'default_conversation'
      console.log('[init] 无缓存会话, currentMode设为默认值')
    }

    try {
      await loadSessions()
    } catch (e) {
      console.warn('[init] loadSessions失败:', e)
    }

    console.log('[init] 初始化完成, currentMode:', currentMode.value, 'isInitializing设为false')
    isInitializing.value = false

    if (currentSessionId.value) {
      connectWebSocket()
      const cachedMsgs = loadMessagesCache(currentSessionId.value)
      if (!cachedMsgs?.messages?.length) {
        loadMessages(currentSessionId.value).catch(console.error)
      }
    }
  }

  return {
    sessions,
    currentSessionId,
    messages,
    isLoading,
    isInitializing,
    isStreaming,
    isUploadingFiles,
    uploadProgress,
    currentSession,
    currentMode,
    currentModeConfig,
    init,
    loadSessions,
    createSession,
    selectSession,
    deleteSession,
    updateSessionTitle,
    loadMessages,
    sendMessage,
    switchMode,
    connectWebSocket,
    disconnectWebSocket,
    toggleSidebar,
    sidebarCollapsed,
    formatTime,
    loadFiles,
  }
})
