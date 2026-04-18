import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import sessionApi from '../api/sessions'
import messageApi from '../api/messages'
import fileApi from '../api/files'
import agentApi from '../api/agents'
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

function getFileCategory(fileName) {
  if (/.(docx?|pdf|txt|md)$/i.test(fileName)) return 'document'
  if (/.(xlsx?|csv)$/i.test(fileName)) return 'excel'
  return 'unknown'
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

  // 进度条相关（混合模式/实体提取/表格填表）
  const progressValue = ref(0)
  const progressMessage = ref('')
  const showProgressBar = ref(false)

  // WebSocket 回调（用于混合模式多任务处理）
  let pendingResolve = null
  let pendingResultData = null

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
        // 更新 tempFiles（缓冲区内条目替换为已上传后的元数据）
        const index = fileStore.tempFiles.data.findIndex(f => f.id === file.id)
        if (index > -1) {
          const prev = fileStore.tempFiles.data[index]
          const u = prev?.file_url
          if (u && String(u).startsWith('blob:')) {
            try { URL.revokeObjectURL(u) } catch (_) {}
          }
          fileStore.tempFiles.data[index] = updatedFileInfo
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
          const prev = fileStore.tempFiles.template[index]
          const u = prev?.file_url
          if (u && String(u).startsWith('blob:')) {
            try { URL.revokeObjectURL(u) } catch (_) {}
          }
          fileStore.tempFiles.template[index] = updatedTemplateInfo
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

  // 清除所有选中的文件（仅本地缓冲区，不请求后端）
  function clearAllSelectedFiles() {
    const fileStore = useFileStore()
    fileStore.tempFiles.data.forEach(f => { f.is_selected = false })
    fileStore.tempFiles.template.forEach(f => { f.is_selected = false })
  }

  /** 上传区不展示/同步会话服务端文件列表，保留空实现以兼容创建/切换会话时的调用 */
  async function loadFiles(_sessionId) {}

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
      'mixed': '混合模式',
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
      console.log('[WebSocket onmessage] 收到消息:', event.data)
      const data = JSON.parse(event.data)
      console.log('[WebSocket onmessage] 解析后:', data)
      if (data.type === 'start') {
        console.log('[WebSocket onmessage] type=start, 收到开始信号')
        isStreaming.value = true
        // 实体提取/表格填表/混合模式显示进度条
        const isEntityOrTable = data.result_type === 'entity_extraction' ||
                               data.result_type === 'table_filling' ||
                               data.mode === 'entity_extraction' ||
                               data.mode === 'table_filling'
        console.log('[WebSocket onmessage] isEntityOrTable:', isEntityOrTable, 'result_type:', data.result_type, 'mode:', data.mode)
        if (isEntityOrTable) {
          showProgressBar.value = true
          progressValue.value = 0
          progressMessage.value = data.result_type === 'table_filling' || data.mode === 'table_filling'
            ? '开始筛选数据...'
            : '开始提取...'
        }
      } else if (data.type === 'progress') {
        console.log('[WebSocket onmessage] type=progress:', data.progress, data.message)
        progressValue.value = data.progress
        progressMessage.value = data.message
      } else if (data.type === 'chunk') {
        console.log('[WebSocket onmessage] type=chunk, result_type:', data.result_type, 'content长度:', data.content?.length)
        isStreaming.value = false
        // 实体提取结果处理
        if (data.result_type === 'entity_extraction') {
          try {
            const parsed = JSON.parse(data.content)
            const entities = Array.isArray(parsed?.entities) ? parsed.entities : []
            const count = entities.length
            const summary = `实体提取完成，共提取 ${count} 条数据`
            const lastMsg = messages.value[messages.value.length - 1]
            if (lastMsg && lastMsg.role === 'assistant') {
              lastMsg.content = summary
              lastMsg.entitiesData = entities
            } else {
              messages.value.push({
                id: Date.now(),
                role: 'assistant',
                content: summary,
                created_at: new Date().toISOString(),
                entitiesData: entities,
              })
            }
            pendingResultData = { extractionData: parsed, entities }
            console.log('[WebSocket onmessage] 实体提取结果解析成功, count:', count, 'keys:', Object.keys(parsed))
          } catch (e) {
            console.error('[WebSocket onmessage] 解析实体提取结果失败:', e)
          }
        } else if (data.result_type === 'table_filling') {
          try {
            const parsed = JSON.parse(data.content)
            console.log('[WebSocket onmessage] table_filling parsed, keys:', Object.keys(parsed), 'generated_files:', parsed.generated_files)
            const lastMsg = messages.value[messages.value.length - 1]
            if (lastMsg && lastMsg.role === 'assistant') {
              lastMsg.tableFillingData = parsed
            } else {
              messages.value.push({
                id: Date.now(),
                role: 'assistant',
                content: parsed.message || '',
                created_at: new Date().toISOString(),
                tableFillingData: parsed,
              })
            }
            pendingResultData = { tableFillingData: parsed }
            console.log('[WebSocket onmessage] table_filling stored, msg count:', messages.value.length, 'lastMsg.tableFillingData:', !!messages.value[messages.value.length - 1]?.tableFillingData)
          } catch (e) {
            console.error('[WebSocket onmessage] 解析表格填表结果失败:', e)
          }
        } else {
          // 普通流式文本
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
        }
      } else if (data.type === 'done') {
        console.log('[WebSocket onmessage] type=done, pendingResolve:', !!pendingResolve, 'generated_files:', data.generated_files)
        isStreaming.value = false
        showProgressBar.value = false
        progressValue.value = 100
        progressMessage.value = '处理完成'
        // 把 generated_files 存入最后一条助手消息
        if (data.generated_files) {
          const lastMsg = messages.value[messages.value.length - 1]
          if (lastMsg && lastMsg.role === 'assistant') {
            lastMsg.generated_files = data.generated_files
            // 表格填表 chunk 与 done 分开发字段时，合并进 tableFillingData 便于前端统一展示/下载
            if (lastMsg.tableFillingData && typeof lastMsg.tableFillingData === 'object') {
              lastMsg.tableFillingData.generated_files = data.generated_files
            }
          }
        }
        if (currentSessionId.value) {
          saveMessagesCache(currentSessionId.value, messages.value)
        }
        if (pendingResolve) {
          const resolveData = { success: true, resp: pendingResultData }
          if (data.generated_files) resolveData.generated_files = data.generated_files
          console.log('[WebSocket onmessage] 调用 pendingResolve', resolveData)
          pendingResolve(resolveData)
          pendingResolve = null
          pendingResultData = null
        }
      } else if (data.type === 'error') {
        const errorMsg = typeof data.message === 'string' ? data.message : JSON.stringify(data.message)
        console.error('[WebSocket onmessage] type=error:', errorMsg, 'pendingResolve:', !!pendingResolve)
        isStreaming.value = false
        showProgressBar.value = false
        if (pendingResolve) {
          pendingResolve({ success: false, error: errorMsg })
          pendingResolve = null
          pendingResultData = null
        }
      } else {
        console.log('[WebSocket onmessage] 未知类型:', data.type)
      }
    }

    ws.value.onclose = () => {
      console.log('[WebSocket onclose] 连接已关闭, pendingResolve:', !!pendingResolve)
      ws.value = null
      isStreaming.value = false
      wsConnecting.value = false
    }

    ws.value.onerror = (err) => {
      console.warn('[WebSocket onerror] 连接失败:', err, 'pendingResolve:', !!pendingResolve)
      ws.value = null
      isStreaming.value = false
      wsConnecting.value = false
      if (pendingResolve) {
        console.log('[WebSocket onerror] 通过 pendingResolve 报告失败')
        pendingResolve({ success: false, error: 'WebSocket连接错误' })
        pendingResolve = null
        pendingResultData = null
      }
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
        console.log('[waitForWebSocketOpen] 无 WebSocket 实例')
        resolve(false)
        return
      }
      console.log('[waitForWebSocketOpen] readyState:', socket.readyState, '(0=CONNECTING, 1=OPEN, 2=CLOSING, 3=CLOSED)')
      if (socket.readyState === WebSocket.OPEN) {
        console.log('[waitForWebSocketOpen] 已 OPEN')
        resolve(true)
        return
      }
      if (socket.readyState === WebSocket.CONNECTING) {
        console.log('[waitForWebSocketOpen] 等待 CONNECTING...')
        setTimeout(() => resolve(waitForWebSocketOpen(maxMs)), 50)
        return
      }
      const start = Date.now()
      const t = setInterval(() => {
        if (!ws.value || ws.value !== socket) {
          console.log('[waitForWebSocketOpen] WebSocket 实例已变化')
          clearInterval(t)
          resolve(false)
          return
        }
        console.log('[waitForWebSocketOpen] polling readyState:', socket.readyState)
        if (socket.readyState === WebSocket.OPEN) {
          clearInterval(t)
          console.log('[waitForWebSocketOpen] OPEN!')
          resolve(true)
          return
        }
        if (socket.readyState === WebSocket.CLOSED || socket.readyState === WebSocket.CLOSING) {
          clearInterval(t)
          console.log('[waitForWebSocketOpen] 已 CLOSED/CLOSING')
          resolve(false)
          return
        }
        if (Date.now() - start > maxMs) {
          clearInterval(t)
          console.log('[waitForWebSocketOpen] 超时')
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
    // 混合模式：自动分发任务
    if (mode === 'mixed') {
      await runMixedMode(content, files, template_files)
      return
    }

    console.log('[sendToBackend] 发送请求:', { sessionId, content, mode, files, template_files })
    
    const canStream = await waitForWebSocketOpen()
    if (ws.value && ws.value.readyState === WebSocket.OPEN && canStream) {
      console.log('[sendToBackend] 通过 WebSocket 发送')
      clearAllSelectedFiles()
      ws.value.send(JSON.stringify({
        content,
        mode,
        files,
        template_files,
      }))
    } else {
      console.log('[sendToBackend] 通过 API 发送')
      clearAllSelectedFiles()
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

  // 合并混合模式多个任务的实体数据
  async function mergeMixedEntities(results) {
    const allEntities = []
    for (const r of results) {
      if (r.type === 'entity_extraction') {
        const entities = r.resp?.extractionData?.entities || []
        for (const entity of entities) {
          allEntities.push(entity)
        }
      } else if (r.type === 'table_filling') {
        const outputJson = r.resp?.tableFillingData?.output_json
        const mapping = r.resp?.tableFillingData?.template_mapping || {}
        if (outputJson) {
          try {
            const url = `/api/files/download?path=${encodeURIComponent(outputJson)}`
            const resp = await fetch(url)
            const rows = await resp.json()
            for (const row of rows) {
              const entity = {}
              for (const [tplCol, srcCol] of Object.entries(mapping)) {
                const val = row[srcCol]
                entity[tplCol] = Array.isArray(val) ? val : [val, '']
              }
              allEntities.push(entity)
            }
          } catch (e) {
            console.error('加载 output_json 失败:', e)
          }
        }
      }
    }
    return allEntities
  }

  // 混合模式主逻辑：按文件类型分发任务
  async function runMixedMode(content, files, template_files) {
    const docFiles = files.filter(f => getFileCategory(f.file_name) === 'document')
    const excelFiles = files.filter(f => getFileCategory(f.file_name) === 'excel')

    // 无文件或纯文本：直接发送
    if (docFiles.length === 0 && excelFiles.length === 0) {
      isStreaming.value = true
      try {
        await messageApi.send(currentSessionId.value, {
          content: content.trim(),
          mode: 'mixed',
          files: files,
          template_files: template_files,
        })
        await loadMessages(currentSessionId.value)
      } catch (e) {
        console.error('发送消息失败:', e)
      } finally {
        isStreaming.value = false
      }
      return
    }

    // 构建任务列表
    const taskList = []
    docFiles.forEach(f => taskList.push({ file: f, mode: 'entity_extraction' }))
    excelFiles.forEach(f => taskList.push({ file: f, mode: 'table_filling' }))

    const results = []
    const originalMode = currentMode.value

    for (let i = 0; i < taskList.length; i++) {
      const task = taskList[i]
      const taskTypeName = task.mode === 'entity_extraction' ? '实体提取任务' : '表格处理任务'

      console.log(`[混合模式] 任务 ${i + 1}/${taskList.length} -> ${taskTypeName} | 文件: ${task.file.file_name}`)

      // 显示进度条
      showProgressBar.value = true
      progressValue.value = 0
      const currentProgressMsg = `处理文件 ${i + 1}/${taskList.length} - ${taskTypeName}: ${task.file.file_name}`
      progressMessage.value = currentProgressMsg

      // 添加任务进度消息
      messages.value.push({
        id: Date.now() + i,
        role: 'assistant',
        content: currentProgressMsg,
        created_at: new Date().toISOString(),
        mixedSource: 'single',
        mixedTaskIndex: i,
        isProgressMessage: true,
      })

      // 等待 WebSocket 连接
      const canStream = await waitForWebSocketOpen()
      if (!canStream || !ws.value || ws.value.readyState !== WebSocket.OPEN) {
        messages.value.push({
          id: Date.now() + i + 1000,
          role: 'assistant',
          content: 'WebSocket 连接失败，请重试',
          created_at: new Date().toISOString(),
        })
        results.push({ task, success: false })
        continue
      }

      // 发送任务并等待结果
      console.log(`[混合模式] 任务 ${i + 1}/${taskList.length} - 发送前 ws.readyState:`, ws.value?.readyState)
      const result = await new Promise((resolve) => {
        pendingResolve = resolve
        try {
          const msg = JSON.stringify({
            content: content.trim(),
            mode: task.mode,
            files: [{ ...task.file, is_selected: true }],
            template_files: template_files,
          })
          console.log(`[混合模式] 任务 ${i + 1}/${taskList.length} - 发送消息:`, JSON.parse(msg))
          ws.value.send(msg)
          console.log(`[混合模式] 任务 ${i + 1}/${taskList.length} - 发送完成，等待结果...`)
        } catch (e) {
          console.error(`[混合模式] 任务 ${i + 1}/${taskList.length} - 发送失败:`, e)
          pendingResolve = null
          resolve({ success: false, error: e.message })
        }
      })
      console.log(`[混合模式] 任务 ${i + 1}/${taskList.length} - 收到结果:`, result)

      results.push({ task, ...result })
    }

    // 清空选中状态（注意：混合模式在每个任务完成后才清空，不是发送前清空）
    clearAllSelectedFiles()
    currentMode.value = originalMode

    // 单文件直接返回
    if (taskList.length === 1) {
      console.log('[混合模式] 单文件处理完成')
      return
    }

    // 多文件合并结果
    const successfulResults = results.filter(r => r.success)
    const allEntities = await mergeMixedEntities(successfulResults)

    messages.value.push({
      id: Date.now() + 999,
      role: 'assistant',
      content: `混合模式完成，共 ${allEntities.length} 条记录（来自 ${successfulResults.length} 个文件）`,
      created_at: new Date().toISOString(),
      mixedSource: 'merged',
    })
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
    progressValue,
    progressMessage,
    showProgressBar,
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
