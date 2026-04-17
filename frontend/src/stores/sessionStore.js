import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import sessionApi from '../api/sessions'
import messageApi from '../api/messages'
import fileApi from '../api/files'
import agentApi from '../api/agents'
import authApi, { getAccessToken, getUserFromToken } from '../api/auth'

const SESSIONS_KEY = 'doc_sessions'
const MESSAGES_KEY = 'doc_messages_'
const STATE_KEY = 'doc_state'
const MAX_CACHED_MESSAGES = 5
const CACHE_TTL = 7 * 24 * 60 * 60 * 1000  // 7天过期

function readCache(key) {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    const data = JSON.parse(raw)
    if (data._ts && Date.now() - data._ts > CACHE_TTL) {
      localStorage.removeItem(key)
      return null
    }
    return data
  } catch {
    return null
  }
}

function writeCache(key, data) {
  try {
    localStorage.setItem(key, JSON.stringify({ _ts: Date.now(), ...data }))
  } catch {
    // localStorage满了，忽略
  }
}

function removeCache(key) {
  try {
    localStorage.removeItem(key)
  } catch {}
}

function cleanOldMessagesCache() {
  try {
    const keys = Object.keys(localStorage).filter(k => k.startsWith(MESSAGES_KEY))
    const metas = keys.map(k => {
      try { return { key: k, ts: JSON.parse(localStorage.getItem(k) || '{}')._ts || 0 } } catch { return null }
    }).filter(Boolean).sort((a, b) => b.ts - a.ts)
    metas.slice(MAX_CACHED_MESSAGES).forEach(m => removeCache(m.key))
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

function removeMessagesCache(sessionId) {
  removeCache(MESSAGES_KEY + sessionId)
}

const DEFAULT_MODES = [
  {
    id: 'default_conversation',
    name: '默认对话',
    description: '自由对话，通用问答',
    requires_data: false,
    requires_template: false,
  },
  {
    id: 'document_understanding',
    name: '文档理解',
    description: '上传文档后可交互式提问',
    requires_data: true,
    requires_template: false,
  },
  {
    id: 'document_editing',
    name: '文档编辑',
    description: '自然语言编辑Word/Excel/文本',
    requires_data: true,
    requires_template: false,
  },
  {
    id: 'entity_extraction',
    name: '实体提取',
    description: '从文档提取结构化数据',
    requires_data: true,
    requires_template: null,
  },
  {
    id: 'table_filling',
    name: '表格填表',
    description: '条件筛选并填入模板',
    requires_data: true,
    requires_template: true,
  },
]

function mergeModesWithDefaults(remoteModes = []) {
  const merged = [...DEFAULT_MODES]
  const existingIds = new Set(merged.map(m => m.id))
  for (const mode of remoteModes) {
    if (!mode || !mode.id) continue
    if (!existingIds.has(mode.id)) {
      merged.push(mode)
      existingIds.add(mode.id)
    }
  }
  return merged
}

export const useSessionStore = defineStore('session', () => {
  const currentUser = ref(null)
  const tokenVersion = ref(0)  // 用于触发 isAuthenticated 重新计算
  const sessions = ref([])
  const currentSessionId = ref(null)
  const messages = ref([])
  const dataFiles = ref([])
  const templateFiles = ref([])
  const tempDataFiles = ref([])  // 临时数据文件（不上传数据库）
  const tempTemplateFiles = ref([])  // 临时模板文件（不上传数据库）
  const modes = ref([...DEFAULT_MODES])
  const currentMode = ref('default_conversation')
  const isLoading = ref(false)
  const isInitializing = ref(true)  // 新增：初始化状态
  const isStreaming = ref(false)
  const progressValue = ref(0)
  const progressMessage = ref('')
  const showProgressBar = ref(false)
  const ws = ref(null)
  const wsConnecting = ref(false)
  let pendingWsResolve = null
  let lastWsCloseCode = null
  let lastWsCloseReason = null

  let pendingResolve = null
  let pendingResultData = null

  function needsMixedMode(files) {
    const hasDoc = files.some(f => /.(docx?|pdf|txt|md)$/i.test(f.file_name))
    const hasExcel = files.some(f => /.(xlsx?|csv)$/i.test(f.file_name))
    return hasDoc && hasExcel
  }

  function getFileCategory(fileName) {
    if (/.(docx?|pdf|txt|md)$/i.test(fileName)) return 'document'
    if (/.(xlsx?|csv)$/i.test(fileName)) return 'excel'
    return 'unknown'
  }

  const currentSession = computed(() =>
    sessions.value.find(s => s.session_id === currentSessionId.value)
  )

  const isAuthenticated = computed(() => {
    tokenVersion.value  // 依赖 tokenVersion 以便在登出时更新
    if (currentUser.value) return true
    if (getAccessToken()) return true
    return false
  })

  const selectedDataFiles = computed(() =>
    dataFiles.value.filter(f => f.is_selected)
  )

  const selectedTemplateFiles = computed(() =>
    templateFiles.value.filter(f => f.is_selected)
  )

  // 选中的临时数据文件
  const selectedTempDataFiles = computed(() =>
    tempDataFiles.value.filter(f => f.is_selected)
  )

  // 选中的临时模板文件
  const selectedTempTemplateFiles = computed(() =>
    tempTemplateFiles.value.filter(f => f.is_selected)
  )

  const modeConfig = {
    'default_conversation': { requiresData: false, requiresTemplate: false },
    'document_understanding': { requiresData: true, requiresTemplate: false },
    'document_editing': { requiresData: true, requiresTemplate: false },
    'entity_extraction': { requiresData: true, requiresTemplate: null },
    'table_filling': { requiresData: true, requiresTemplate: true },
    'mixed': { requiresData: true, requiresTemplate: null },
  }

  const currentModeConfig = computed(() => modeConfig[currentMode.value] || modeConfig['default_conversation'])

  function clearConversationState() {
    sessions.value = []
    currentSessionId.value = null
    messages.value = []
    dataFiles.value = []
    templateFiles.value = []
    tempDataFiles.value = []
    tempTemplateFiles.value = []
    // 登出时清空缓存
    try {
      Object.keys(localStorage).forEach(k => {
        if (k.startsWith('doc_')) localStorage.removeItem(k)
      })
    } catch {}
  }

  async function loadCurrentUser() {
    const token = getAccessToken()
    if (!token) {
      currentUser.value = null
      return null
    }
    try {
      const user = await authApi.me()
      currentUser.value = user
      tokenVersion.value++
      return user
    } catch (e) {
      console.warn('验证会话失败，保留本地token:', e.message)
      return null
    }
  }

  async function login(phone, password) {
    const res = await authApi.login({ phone, password })
    currentUser.value = res?.user || null
    await loadSessions()
    return res
  }

  async function register(phone, password, displayName = null) {
    const res = await authApi.register({ phone, password, display_name: displayName })
    currentUser.value = res?.user || null
    await loadSessions()
    return res
  }

  async function logout() {
    try {
      await authApi.logout()
    } catch (e) {
      console.warn('登出请求失败:', e.message)
    } finally {
      authApi.clearAccessToken()
      tokenVersion.value++
      currentUser.value = null
      clearConversationState()
      disconnectWebSocket()
    }
  }

  async function loadSessions() {
    try {
      const res = await sessionApi.list()
      sessions.value = res.items
      saveSessionsCache(sessions.value, currentSessionId.value)
    } catch (e) {
      console.error('加载会话列表失败:', e)
    }
  }

  async function createSession() {
    const newSession = {
      session_id: `temp_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      title: '新会话',
      current_mode: currentMode.value,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    sessions.value.unshift(newSession)
    currentSessionId.value = newSession.session_id
    messages.value = []
    dataFiles.value = []
    templateFiles.value = []
    tempDataFiles.value = []
    tempTemplateFiles.value = []
    connectWebSocket()

    try {
      const res = await sessionApi.create({ title: '新会话', current_mode: currentMode.value })
      const idx = sessions.value.findIndex(s => s.session_id === newSession.session_id)
      if (idx !== -1) {
        sessions.value[idx] = res
      }
      currentSessionId.value = res.session_id
      saveSessionsCache(sessions.value, res.session_id)
      loadModes().catch(console.error)
      loadFiles(res.session_id).catch(console.error)
      if (newSession.session_id !== res.session_id) {
        sessions.value = sessions.value.filter(s => s.session_id !== newSession.session_id)
      }
    } catch (e) {
      console.error('创建会话失败:', e)
      sessions.value = sessions.value.filter(s => s.session_id !== newSession.session_id)
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
    messages.value = []
    // 清空文件列表，上传区域只负责上传临时文件
    dataFiles.value = []
    templateFiles.value = []
    tempDataFiles.value = []
    tempTemplateFiles.value = []

    // 等待一小段时间确保旧连接完全关闭
    await new Promise(resolve => setTimeout(resolve, 100))
    connectWebSocket()

    const session = sessions.value.find(s => s.session_id === sessionId)
    if (session) {
      currentMode.value = session.current_mode || 'default_conversation'
    }

    const cachedMsgs = loadMessagesCache(sessionId)
    if (cachedMsgs && cachedMsgs.messages && cachedMsgs.messages.length > 0) {
      messages.value = cachedMsgs.messages
    } else {
      loadMessages(sessionId).catch(console.error)
    }

    loadModes().catch(e => console.warn('[selectSession] loadModes失败:', e.message))

    // 切换完成后保存缓存
    saveSessionsCache(sessions.value, sessionId)
  }

  async function deleteSession(sessionId) {
    const wasCurrentSession = currentSessionId.value === sessionId
    const remainingSessions = sessions.value.filter(s => s.session_id !== sessionId)
    sessions.value = remainingSessions

    const nextSession = remainingSessions[0]
    const nextSessionId = nextSession ? nextSession.session_id : null
    saveSessionsCache(remainingSessions, nextSessionId)
    removeMessagesCache(sessionId)

    if (wasCurrentSession) {
      if (nextSession) {
        currentSessionId.value = nextSession.session_id
        currentMode.value = nextSession.current_mode || 'default_conversation'
        messages.value = []
        dataFiles.value = []
        templateFiles.value = []
        tempDataFiles.value = []
        tempTemplateFiles.value = []
        const wsPrev = ws.value
        if (wsPrev) {
          wsPrev.onclose = null
          wsPrev.onerror = null
          wsPrev.close()
        }
        connectWebSocket()
        const cachedMsgs = loadMessagesCache(nextSession.session_id)
        if (cachedMsgs && cachedMsgs.messages && cachedMsgs.messages.length > 0) {
          messages.value = cachedMsgs.messages
        } else {
          loadMessages(nextSession.session_id).catch(console.error)
        }
      } else {
        currentSessionId.value = null
        clearConversationState()
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

  async function switchMode(mode) {
    if (currentMode.value === mode) return
    currentMode.value = mode
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
    const modeNames = {
      'default_conversation': '默认对话',
      'document_understanding': '文档理解',
      'document_editing': '文档编辑',
      'entity_extraction': '实体提取',
      'table_filling': '表格填表',
      'mixed': '混合模式',
    }
    messages.value.push({
      id: Date.now(),
      role: 'system',
      content: `已切换至「${modeNames[mode] || mode}」模式`,
      created_at: new Date().toISOString(),
    })
  }

  async function loadMessages(sessionId) {
    try {
      const res = await messageApi.list(sessionId)
      const msgs = (res || []).map((msg) => {
        const normalized = { ...msg }
        const metadata = normalized.metadata || {}
        if (!normalized.tableFillingData && metadata.tableFillingData) {
          normalized.tableFillingData = metadata.tableFillingData
        }
        if (!normalized.generatedFiles && Array.isArray(metadata.generated_files)) {
          normalized.generatedFiles = metadata.generated_files
        }
        return normalized
      })
      // 只有成功返回非空数据时才更新，避免后端超时时清空消息
      if (msgs.length > 0 || currentSessionId.value === sessionId) {
        messages.value = msgs
        saveMessagesCache(sessionId, msgs)
      }
    } catch (e) {
      console.warn('加载消息失败，保留本地消息:', e.message)
    }
  }

  async function loadModes() {
    try {
      const res = await agentApi.getCapabilities()
      const remoteModes = Array.isArray(res?.modes) ? res.modes : []
      modes.value = mergeModesWithDefaults(remoteModes)
    } catch (e) {
      console.error('加载模式失败:', e)
      // 网络抖动时保留内置模式，避免界面只显示混合模式。
      modes.value = mergeModesWithDefaults(modes.value)
    }
  }

  async function loadFiles(sessionId) {
    try {
      const res = await fileApi.list(sessionId)
      dataFiles.value = res.data_files || []
      templateFiles.value = res.template_files || []
      // 临时文件由前端单独管理，不从数据库加载
    } catch (e) {
      console.error('加载文件失败:', e)
    }
  }

  async function uploadFile(file, fileType) {
    if (!currentSessionId.value) return
    try {
      // 使用临时上传端点，不存入数据库
      const res = await fileApi.uploadTemp(currentSessionId.value, file, fileType)
      const fileInfo = {
        id: `temp_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        file_name: res.file_name,
        storage_key: res.storage_key,
        file_path: res.file_path,
        file_type: res.file_type,
        file_size: res.file_size,
        is_selected: false,
        created_at: res.created_at,
      }
      // 添加到临时文件列表
      if (fileType === 'data') {
        tempDataFiles.value.push(fileInfo)
      } else {
        tempTemplateFiles.value.push(fileInfo)
      }
    } catch (e) {
      console.error('上传文件失败:', e)
      throw e
    }
  }

  async function toggleFileSelection(fileId, fileType, isSelected) {
    // 区分数据库文件和临时文件
    if (String(fileId).startsWith('temp_')) {
      // 临时文件：只更新本地状态
      const tempList = fileType === 'data' ? tempDataFiles : tempTemplateFiles
      const idx = tempList.value.findIndex(f => f.id === fileId)
      if (idx !== -1) {
        tempList.value[idx].is_selected = isSelected
      }
    } else {
      // 数据库文件：同步到服务器
      try {
        await fileApi.updateSelection(currentSessionId.value, [{ file_id: fileId, is_selected: isSelected }])
        const files = fileType === 'data' ? dataFiles.value : templateFiles.value
        const idx = files.findIndex(f => f.id === fileId)
        if (idx !== -1) {
          files[idx].is_selected = isSelected
        }
      } catch (e) {
        console.error('更新文件选择失败:', e)
      }
    }
  }

  async function deleteFile(fileId, fileType) {
    // 区分数据库文件和临时文件
    if (String(fileId).startsWith('temp_')) {
      // 临时文件：只从本地删除
      const tempList = fileType === 'data' ? tempDataFiles : tempTemplateFiles
      const fileInfo = tempList.value.find(f => f.id === fileId)
      if (fileInfo) {
        try {
          await fileApi.deleteTempFile(currentSessionId.value, fileInfo.storage_key)
        } catch (e) {
          console.warn('删除临时文件失败:', e)
        }
        tempList.value = tempList.value.filter(f => f.id !== fileId)
      }
    } else {
      // 数据库文件：从数据库删除
      try {
        await fileApi.delete(currentSessionId.value, fileId)
        if (fileType === 'data') {
          dataFiles.value = dataFiles.value.filter(f => f.id !== fileId)
        } else {
          templateFiles.value = templateFiles.value.filter(f => f.id !== fileId)
        }
      } catch (e) {
        console.error('删除文件失败:', e)
      }
    }
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
      if (wsConnecting.value) {
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
        if (socket.readyState === WebSocket.CLOSED) {
          clearInterval(t)
          resolve(false)
          return
        }
        if (Date.now() - start > maxMs) {
          clearInterval(t)
          resolve(false)
        }
      }, 30)
    })
  }

  function connectWebSocket() {
    if (!currentSessionId.value) return
    const targetSessionId = currentSessionId.value

    // 如果正在连接，先等待之前的连接完成或超时
    if (wsConnecting.value) {
      return
    }

    // 关闭旧连接
    if (ws.value) {
      ws.value.onclose = null
      ws.value.onerror = null
      ws.value.close()
      ws.value = null
    }

    isStreaming.value = false
    wsConnecting.value = true

    ws.value = messageApi.connect(targetSessionId)

    ws.value.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'start') {
        isStreaming.value = true
        // 同时检查 result_type 和 mode 字段（后端可能发送不同的字段名）
        const isEntityMode = data.result_type === 'entity_extraction' || data.mode === 'entity_extraction'
        const isTableMode = data.result_type === 'table_filling' || data.mode === 'table_filling'
        if (isEntityMode || isTableMode) {
          showProgressBar.value = true
          progressValue.value = 0
          progressMessage.value = isTableMode ? '开始筛选数据...' : '开始提取...'
        }
      } else if (data.type === 'progress') {
        progressValue.value = data.progress
        progressMessage.value = data.message
      } else if (data.type === 'chunk') {
        if (data.result_type === 'entity_extraction') {
          try {
            const parsed = JSON.parse(data.content)
            const count = Array.isArray(parsed?.entities) ? parsed.entities.length : 0
            const summary = `实体提取完成，共提取 ${count} 条数据`
            const lastMsg = messages.value[messages.value.length - 1]
            if (lastMsg && lastMsg.role === 'assistant') {
              lastMsg.content = summary
            } else {
              messages.value.push({
                id: Date.now(),
                role: 'assistant',
                content: summary,
                created_at: new Date().toISOString(),
              })
            }
            // 保存实体提取数据到 pendingResultData
            pendingResultData = { extractionData: parsed }
          } catch (e) {
            console.error('解析实体提取结果失败:', e)
          }
        } else if (data.result_type === 'table_filling') {
          try {
            const parsed = JSON.parse(data.content)
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
            // 保存表格填表数据到 pendingResultData
            pendingResultData = { tableFillingData: parsed }
          } catch (e) {
            console.error('解析表格填表结果失败:', e)
          }
        } else {
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
        isStreaming.value = false
        showProgressBar.value = false
        progressValue.value = 100
        progressMessage.value = '处理完成'
        if (currentSessionId.value) {
          saveMessagesCache(currentSessionId.value, messages.value)
          // 清理已发送的临时文件（从本地列表移除）
          cleanupSentTempFiles()
        }
        if (pendingResolve) {
          pendingResolve({ success: true, resp: pendingResultData })
          pendingResolve = null
          pendingResultData = null
        }
      } else if (data.type === 'error') {
        const errorMsg = typeof data.message === 'string' ? data.message : JSON.stringify(data.message)
        console.error('流式错误:', errorMsg)
        isStreaming.value = false
        showProgressBar.value = false
        if (pendingResolve) {
          pendingResolve({ success: false, error: errorMsg })
          pendingResolve = null
          pendingResultData = null
        }
      }
    }

    ws.value.onclose = (event) => {
      lastWsCloseCode = event.code
      lastWsCloseReason = event.reason
      ws.value = null
      isStreaming.value = false
      wsConnecting.value = false
      if (pendingWsResolve) { pendingWsResolve(false); pendingWsResolve = null }
    }

    ws.value.onerror = (e) => {
      console.warn('[WebSocket] 连接失败:', e)
      const errorCode = lastWsCloseCode
      const errorReason = lastWsCloseReason
      ws.value = null
      isStreaming.value = false
      wsConnecting.value = false
      if (pendingWsResolve) { pendingWsResolve(false); pendingWsResolve = null }
    }

    ws.value.onopen = () => {
      wsConnecting.value = false
      if (pendingWsResolve) { pendingWsResolve(true); pendingWsResolve = null }
    }
  }

  function disconnectWebSocket() {
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }
    isStreaming.value = false
  }

  function downloadFile(path) {
    if (!path) return
    const url = `/api/files/download?path=${encodeURIComponent(path)}`
    window.open(url, '_blank')
  }

  function downloadSessionFile(fileId, fileName = 'download.bin') {
    if (!currentSessionId.value || !fileId) return
    const url = `/api/sessions/${encodeURIComponent(currentSessionId.value)}/files/${encodeURIComponent(fileId)}/download`
    const a = document.createElement('a')
    a.href = url
    a.download = fileName
    a.target = '_blank'
    a.rel = 'noopener noreferrer'
    document.body.appendChild(a)
    a.click()
    a.remove()
  }

  function clearAllSelectedFiles() {
    dataFiles.value.forEach(f => { f.is_selected = false })
    templateFiles.value.forEach(f => { f.is_selected = false })
    tempDataFiles.value.forEach(f => { f.is_selected = false })
    tempTemplateFiles.value.forEach(f => { f.is_selected = false })
    // 数据库文件需要同步到服务器
    syncFileSelectionToServer()
  }

  function clearTempSelection() {
    // 只清除临时文件的选中状态
    tempDataFiles.value.forEach(f => { f.is_selected = false })
    tempTemplateFiles.value.forEach(f => { f.is_selected = false })
  }

  function cleanupSentTempFiles() {
    // 清理已发送的临时文件（发送完成后从本地列表移除）
    const sentTempIds = new Set([
      ...selectedTempDataFiles.value.map(f => f.id),
      ...selectedTempTemplateFiles.value.map(f => f.id),
    ])
    tempDataFiles.value = tempDataFiles.value.filter(f => !sentTempIds.has(f.id))
    tempTemplateFiles.value = tempTemplateFiles.value.filter(f => !sentTempIds.has(f.id))
  }

  async function syncFileSelectionToServer() {
    try {
      const tasks = []
      dataFiles.value.forEach(f => {
        tasks.push(fileApi.updateSelection(currentSessionId.value, [{ file_id: f.id, is_selected: false }]))
      })
      templateFiles.value.forEach(f => {
        tasks.push(fileApi.updateSelection(currentSessionId.value, [{ file_id: f.id, is_selected: false }]))
      })
      if (tasks.length > 0) {
        await Promise.all(tasks)
      }
    } catch (e) {
      console.error('同步文件勾选状态失败:', e)
    }
  }

  function getSelectedFilesPayload() {
    // 现在只使用临时文件列表
    const dataFiles = selectedTempDataFiles.value.map(f => ({
      file_id: f.id,
      file_name: f.file_name,
      storage_key: f.storage_key,
      file_size: f.file_size,
      file_type: f.file_type || 'data',
      is_selected: true,
    }))
    const templateFiles = selectedTempTemplateFiles.value.map(f => ({
      file_id: f.id,
      file_name: f.file_name,
      storage_key: f.storage_key,
      file_size: f.file_size,
      file_type: f.file_type || 'template',
      is_selected: true,
    }))
    return { files: dataFiles, template_files: templateFiles }
  }

  async function mergeMixedEntities(results) {
    const allEntities = []

    for (const r of results) {
      if (r.type === 'entity_extraction') {
        const entities = r.extractionData?.entities || []
        for (const entity of entities) {
          allEntities.push(entity)
        }
      } else if (r.type === 'table_filling') {
        const outputJson = r.tableFillingData?.output_json
        const mapping = r.tableFillingData?.template_mapping || {}
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

  async function runTableFillingTasksLikeMixed(content, files, template_files) {
    const excelFiles = files.filter(f => getFileCategory(f.file_name) === 'excel')
    if (excelFiles.length === 0) return false

    const taskList = excelFiles.map(f => ({ file: f, mode: 'table_filling' }))
    const results = []
    const originalMode = currentMode.value

    for (let i = 0; i < taskList.length; i++) {
      const task = taskList[i]
      const taskTypeName = '表格处理任务'

      console.log(`[表格填表模式] 任务 ${i + 1}/${taskList.length} -> 表格填表 | 文件: ${task.file.file_name}`)

      showProgressBar.value = true
      progressValue.value = 0
      progressMessage.value = `处理文件 ${i + 1}/${taskList.length} - ${taskTypeName}: ${task.file.file_name}`

      messages.value.push({
        id: Date.now() + i,
        role: 'assistant',
        content: progressMessage.value,
        created_at: new Date().toISOString(),
        mixedSource: 'single',
        mixedTaskIndex: i,
        isProgressMessage: true,
      })

      const result = await new Promise((resolve) => {
        pendingResolve = resolve
        ws.value.send(JSON.stringify({
          content: content.trim(),
          mode: 'table_filling',
          files: [{ ...task.file, is_selected: true }],
          template_files: template_files,
        }))
      })

      results.push({ task, ...result })
    }

    clearAllSelectedFiles()
    currentMode.value = originalMode

    if (taskList.length === 1) {
      return true
    }

    const successfulResults = results.filter(r => r.success)
    const allEntities = await mergeMixedEntities(
      successfulResults.map(r => ({
        type: 'table_filling',
        ...r.resp,
      }))
    )

    messages.value.push({
      id: Date.now() + 999,
      role: 'assistant',
      content: `表格填表完成，共 ${allEntities.length} 条记录（来自 ${successfulResults.length} 个文件）`,
      created_at: new Date().toISOString(),
      mixedSource: 'merged',
    })
    return true
  }

  async function sendMessage(content) {
    if (!content.trim()) return

    if (!currentSessionId.value) {
      await createSession()
    }

    const sessionId = currentSessionId.value
    const { files, template_files } = getSelectedFilesPayload()
    const userMetadata = {}
    if (files.length > 0) userMetadata.files = files
    if (template_files.length > 0) userMetadata.template_files = template_files

    messages.value.push({
      id: Date.now(),
      role: 'user',
      content: content.trim(),
      created_at: new Date().toISOString(),
      metadata: Object.keys(userMetadata).length ? userMetadata : undefined,
    })

    if (currentMode.value === 'table_filling') {
      const handled = await runTableFillingTasksLikeMixed(content, files, template_files)
      if (handled) return
    }

    // 混合模式：始终使用混合模式逻辑，不管文件类型组合
    if (currentMode.value === 'mixed') {
      const docFiles = files.filter(f => getFileCategory(f.file_name) === 'document')
      const excelFiles = files.filter(f => getFileCategory(f.file_name) === 'excel')

      if (docFiles.length === 0 && excelFiles.length === 0) {
        isStreaming.value = true
        try {
          await messageApi.send(sessionId, {
            content: content.trim(),
            mode: 'mixed',
            files: files,
            template_files: template_files,
          })
          await loadMessages(sessionId)
        } catch (e) {
          console.error('发送消息失败:', e)
        } finally {
          isStreaming.value = false
        }
        return
      }

      const taskList = []
      docFiles.forEach(f => taskList.push({ file: f, mode: 'entity_extraction' }))
      excelFiles.forEach(f => taskList.push({ file: f, mode: 'table_filling' }))

      const results = []
      const originalMode = currentMode.value

      for (let i = 0; i < taskList.length; i++) {
        const task = taskList[i]
        const displayMode = task.mode
        const taskTypeName = task.mode === 'entity_extraction' ? '实体提取任务' : '表格处理任务'

        console.log(`[混合模式] 任务 ${i + 1}/${taskList.length} -> ${task.mode === 'entity_extraction' ? '实体提取' : '表格填表'} | 文件: ${task.file.file_name}`)

        // 更新进度条显示当前任务
        showProgressBar.value = true
        progressValue.value = 0
        const currentProgressMsg = `处理文件 ${i + 1}/${taskList.length} - ${taskTypeName}: ${task.file.file_name}`
        progressMessage.value = currentProgressMsg

        messages.value.push({
          id: Date.now() + i,
          role: 'assistant',
          content: currentProgressMsg,
          created_at: new Date().toISOString(),
          mixedSource: 'single',
          mixedTaskIndex: i,
          isProgressMessage: true,
        })

        // 等待 WebSocket 连接成功后再发送
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

        const result = await new Promise((resolve) => {
          pendingResolve = resolve
          ws.value.send(JSON.stringify({
            content: content.trim(),
            mode: task.mode,
            files: [{ ...task.file, is_selected: true }],
            template_files: template_files,
          }))
        })

        results.push({ task, ...result })
      }

      // 所有任务完成后，清除选中状态
      clearAllSelectedFiles()

      currentMode.value = originalMode

      // 如果只有一个文件，不需要合并，直接用已有消息的结果
      if (taskList.length === 1) {
        console.log('[混合模式] 单文件处理完成，直接使用已有结果')
        return
      }

      // 多文件才需要合并结果
      const successfulResults = results.filter(r => r.success)
      const allEntities = await mergeMixedEntities(
        successfulResults.map(r => ({
          type: r.task.mode === 'entity_extraction' ? 'entity_extraction' : 'table_filling',
          ...r.resp,
        }))
      )

      // mixed统一填表：把 docx+xlsx 合并实体写入同一个模板（xlsx/docx）。
      if (template_files.length > 0 && allEntities.length > 0) {
        const tpl = template_files[0]
        try {
          const mixedFillResp = await agentApi.mixedFill({
            session_id: sessionId,
            entities: allEntities,
            template_file: tpl.storage_key,
            output_json: '',
            output_template: '',
          })

          const payload = {
            success: !!mixedFillResp?.success,
            message: mixedFillResp?.message || '统一填表完成',
            ...(mixedFillResp?.data || {}),
          }
          if (Array.isArray(mixedFillResp?.data?.file_ids) && mixedFillResp.data.file_ids.length > 0) {
            payload.generatedFiles = mixedFillResp.data.file_ids
          }

          messages.value.push({
            id: Date.now() + 998,
            role: 'assistant',
            content: payload.message || '',
            created_at: new Date().toISOString(),
            tableFillingData: payload,
          })
        } catch (e) {
          messages.value.push({
            id: Date.now() + 998,
            role: 'assistant',
            content: `统一填表失败: ${e.message}`,
            created_at: new Date().toISOString(),
          })
        }
      }

      messages.value.push({
        id: Date.now() + 999,
        role: 'assistant',
        content: `混合模式完成，共 ${allEntities.length} 条记录（来自 ${successfulResults.length} 个文件）`,
        created_at: new Date().toISOString(),
        mixedSource: 'merged',
      })
      return
    }

    // 非混合模式：根据文件类型自动判断是否走混合逻辑
    if (!needsMixedMode(files)) {
      const canStream = await waitForWebSocketOpen()
      if (ws.value && ws.value.readyState === WebSocket.OPEN && canStream) {
        ws.value.send(JSON.stringify({
          content: content.trim(),
          mode: currentMode.value,
          files: files,
          template_files: template_files,
        }))
        clearAllSelectedFiles()
      } else {
        isStreaming.value = true
        try {
          await messageApi.send(sessionId, {
            content: content.trim(),
            mode: currentMode.value,
            files: files,
            template_files: template_files,
          })
          await loadMessages(sessionId)
        } catch (e) {
          console.error('发送消息失败:', e)
        } finally {
          isStreaming.value = false
        }
      }
      return
    }
  }

  async function init() {
    const token = getAccessToken()

    if (!token) {
      clearConversationState()
      isInitializing.value = false
      return
    }

    const localUser = getUserFromToken()
    if (localUser) {
      currentUser.value = localUser
    }

    const cached = loadSessionsCache()
    if (cached && cached.sessions && cached.sessions.length > 0) {
      sessions.value = cached.sessions
      if (cached.currentSessionId) {
        currentSessionId.value = cached.currentSessionId
        const sess = sessions.value.find(s => s.session_id === cached.currentSessionId)
        if (sess) {
          currentMode.value = sess.current_mode || 'default_conversation'
        }
        const cachedMsgs = loadMessagesCache(cached.currentSessionId)
        if (cachedMsgs && cachedMsgs.messages) {
          messages.value = cachedMsgs.messages
        }
      }
    }

    isInitializing.value = false

    try {
      await loadSessions()
    } catch (e) {
      console.warn('[init] loadSessions失败:', e)
    }

    if (currentSessionId.value) {
      connectWebSocket()
      const cachedMsgs = loadMessagesCache(currentSessionId.value)
      if (!cachedMsgs || !cachedMsgs.messages || cachedMsgs.messages.length === 0) {
        loadMessages(currentSessionId.value).catch(console.error)
      }
      // 不再从数据库加载文件列表
    }

    loadModes().catch(e => console.warn('[init] loadModes失败:', e.message))
  }

  return {
    currentUser,
    isAuthenticated,
    isInitializing,
    sessions,
    currentSessionId,
    messages,
    dataFiles,
    templateFiles,
    tempDataFiles,
    tempTemplateFiles,
    modes,
    currentMode,
    isLoading,
    isStreaming,
    progressValue,
    progressMessage,
    showProgressBar,
    currentSession,
    selectedDataFiles,
    selectedTemplateFiles,
    selectedTempDataFiles,
    selectedTempTemplateFiles,
    currentModeConfig,
    loadCurrentUser,
    login,
    register,
    logout,
    init,
    loadSessions,
    createSession,
    selectSession,
    deleteSession,
    updateSessionTitle,
    switchMode,
    loadMessages,
    loadModes,
    loadFiles,
    uploadFile,
    toggleFileSelection,
    deleteFile,
    sendMessage,
    clearAllSelectedFiles,
    syncFileSelectionToServer,
    getSelectedFilesPayload,
    connectWebSocket,
    disconnectWebSocket,
    downloadFile,
    downloadSessionFile,
    cleanupSentTempFiles,
  }
})