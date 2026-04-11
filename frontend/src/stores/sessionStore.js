import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import sessionApi from '../api/sessions'
import messageApi from '../api/messages'
import fileApi from '../api/files'
import agentApi from '../api/agents'

export const useSessionStore = defineStore('session', () => {
  // 状态
  const sessions = ref([])
  const currentSessionId = ref(null)
  const messages = ref([])
  const dataFiles = ref([])
  const templateFiles = ref([])
  const modes = ref([])
  const currentMode = ref('default_conversation')
  const isLoading = ref(false)
  const isStreaming = ref(false)
  // 进度相关状态
  const progressValue = ref(0)
  const progressMessage = ref('')
  const showProgressBar = ref(false)
  const ws = ref(null)

  // 计算属性
  const currentSession = computed(() =>
    sessions.value.find(s => s.session_id === currentSessionId.value)
  )

  const selectedDataFiles = computed(() =>
    dataFiles.value.filter(f => f.is_selected)
  )

  const selectedTemplateFiles = computed(() =>
    templateFiles.value.filter(f => f.is_selected)
  )

  // 模式配置
  const modeConfig = {
    'default_conversation': { requiresData: false, requiresTemplate: false },
    'document_understanding': { requiresData: true, requiresTemplate: false },
    'document_editing': { requiresData: true, requiresTemplate: false },
    'entity_extraction': { requiresData: true, requiresTemplate: null },
    'table_filling': { requiresData: true, requiresTemplate: true },
  }

  const currentModeConfig = computed(() => modeConfig[currentMode.value] || modeConfig['default_conversation'])

  // Actions
  async function loadSessions() {
    try {
      const res = await sessionApi.list()
      sessions.value = res.items
    } catch (e) {
      console.error('加载会话列表失败:', e)
    }
  }

  async function createSession() {
    try {
      // 断开旧连接
      disconnectWebSocket()
      const res = await sessionApi.create({ title: '新会话', current_mode: currentMode.value })
      sessions.value.unshift(res)
      await selectSession(res.session_id)
    } catch (e) {
      console.error('创建会话失败:', e)
    }
  }

  async function selectSession(sessionId) {
    // 断开旧连接
    disconnectWebSocket()
    currentSessionId.value = sessionId
    await loadMessages(sessionId)
    await loadFiles(sessionId)
    // 更新当前模式
    const session = sessions.value.find(s => s.session_id === sessionId)
    if (session) {
      currentMode.value = session.current_mode || 'default_conversation'
    }
    // 连接 WebSocket
    connectWebSocket()
  }

  async function deleteSession(sessionId) {
    try {
      await sessionApi.delete(sessionId)
      sessions.value = sessions.value.filter(s => s.session_id !== sessionId)
      if (currentSessionId.value === sessionId) {
        currentSessionId.value = sessions.value[0]?.session_id || null
        if (currentSessionId.value) {
          await selectSession(currentSessionId.value)
        } else {
          messages.value = []
          dataFiles.value = []
          templateFiles.value = []
        }
      }
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
      }
    } catch (e) {
      console.error('更新会话失败:', e)
    }
  }

  async function switchMode(mode) {
    if (currentMode.value === mode) return
    currentMode.value = mode
    if (currentSessionId.value) {
      await sessionApi.update(currentSessionId.value, { current_mode: mode })
    }
    // 追加系统消息，出现在上一次消息下方
    const modeNames = {
      'default_conversation': '默认对话',
      'document_understanding': '文档理解',
      'document_editing': '文档编辑',
      'entity_extraction': '实体提取',
      'table_filling': '表格填表',
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
      messages.value = res
    } catch (e) {
      console.error('加载消息失败:', e)
    }
  }

  async function loadModes() {
    try {
      const res = await agentApi.getCapabilities()
      modes.value = res.modes
    } catch (e) {
      console.error('加载模式失败:', e)
    }
  }

  async function loadFiles(sessionId) {
    try {
      const res = await fileApi.list(sessionId)
      dataFiles.value = res.data_files || []
      templateFiles.value = res.template_files || []
    } catch (e) {
      console.error('加载文件失败:', e)
    }
  }

  async function uploadFile(file, fileType) {
    if (!currentSessionId.value) return
    try {
      const res = await fileApi.upload(currentSessionId.value, file, fileType)
      if (fileType === 'data') {
        dataFiles.value.unshift(res)
      } else {
        templateFiles.value.unshift(res)
      }
    } catch (e) {
      console.error('上传文件失败:', e)
      throw e
    }
  }

  async function toggleFileSelection(fileId, fileType, isSelected) {
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

  async function deleteFile(fileId, fileType) {
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

  // WebSocket 流式聊天
  function connectWebSocket() {
    if (!currentSessionId.value) return
    disconnectWebSocket()

    ws.value = messageApi.connect(currentSessionId.value)

    ws.value.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'start') {
        isStreaming.value = true
        // 只有实体提取模式才显示进度条
        if (currentMode.value === 'entity_extraction') {
          showProgressBar.value = true
          progressValue.value = 0
          progressMessage.value = '开始提取...'
        }
      } else if (data.type === 'progress') {
        progressValue.value = data.progress
        progressMessage.value = data.message
      } else if (data.type === 'chunk') {
        // 实体提取模式：content 是 JSON 字符串，解析后存入 extractionData
        if (data.result_type === 'entity_extraction') {
          try {
            const parsed = JSON.parse(data.content)
            const lastMsg = messages.value[messages.value.length - 1]
            if (lastMsg && lastMsg.role === 'assistant') {
              lastMsg.extractionData = parsed
            } else {
              messages.value.push({
                id: Date.now(),
                role: 'assistant',
                content: '',
                created_at: new Date().toISOString(),
                extractionData: parsed,
              })
            }
          } catch (e) {
            console.error('解析实体提取结果失败:', e)
          }
        } else {
          // 普通文本追加到最后一条助手消息
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
      } else if (data.type === 'error') {
        const errorMsg = typeof data.message === 'string' ? data.message : JSON.stringify(data.message)
        console.error('流式错误:', errorMsg)
        isStreaming.value = false
        showProgressBar.value = false
      }
    }

    ws.value.onclose = () => {
      ws.value = null
      isStreaming.value = false
    }

    ws.value.onerror = (e) => {
      console.error('WebSocket 错误:', e)
      ws.value = null
      isStreaming.value = false
    }

    ws.value.onopen = () => {
    }
  }

  function disconnectWebSocket() {
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }
    isStreaming.value = false
  }

  // 清除所有已勾选的文件（发送消息后调用）
  // 分两阶段：先立即更新本地 UI，后台同步数据库
  function clearAllSelectedFiles() {
    // 第一阶段：立即清除本地勾选状态（同步执行，UI 无延迟）
    dataFiles.value.forEach(f => { f.is_selected = false })
    templateFiles.value.forEach(f => { f.is_selected = false })

    // 第二阶段：后台静默同步到数据库（异步，不阻塞）
    syncFileSelectionToServer()
  }

  // 同步文件勾选状态到后端数据库
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

  // 获取当前勾选的文件列表（用于发送给后端）
  function getSelectedFilesPayload() {
    const dataFiles = selectedDataFiles.value.map(f => ({
      file_id: f.id,
      file_name: f.file_name,
      file_path: f.file_path,
      file_size: f.file_size,
      is_selected: true,
    }))
    const templateFiles = selectedTemplateFiles.value.map(f => ({
      file_id: f.id,
      file_name: f.file_name,
      file_path: f.file_path,
      file_size: f.file_size,
      is_selected: true,
    }))
    return { files: dataFiles, template_files: templateFiles }
  }

  async function sendMessage(content) {
    if (!content.trim()) return

    // 没有会话时自动创建
    if (!currentSessionId.value) {
      await createSession()
    }

    const sessionId = currentSessionId.value

    // 获取当前勾选的文件（和消息一起发送；需在 push 前快照，供 UI 展示附件卡片）
    const { files, template_files } = getSelectedFilesPayload()
    const userMetadata = {}
    if (files.length > 0) userMetadata.files = files
    if (template_files.length > 0) userMetadata.template_files = template_files

    // 添加用户消息（metadata 与后端持久化结构一致，用于「文件 + 文字」同条展示）
    messages.value.push({
      id: Date.now(),
      role: 'user',
      content: content.trim(),
      created_at: new Date().toISOString(),
      metadata: Object.keys(userMetadata).length ? userMetadata : undefined,
    })

    // 若有 WebSocket，等待连接就绪后走流式
    const canStream = await waitForWebSocketOpen()
    if (ws.value && ws.value.readyState === WebSocket.OPEN && canStream) {
      ws.value.send(JSON.stringify({
        content: content.trim(),
        mode: currentMode.value,
        files: files,
        template_files: template_files,
      }))
      // 发送消息后立即清除勾选 UI（不等 AI 响应）
      clearAllSelectedFiles()
    } else {
      // 非流式
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
  }

  // 初始化
  async function init() {
    await loadSessions()
    await loadModes()
    if (sessions.value.length > 0) {
      await selectSession(sessions.value[0].session_id)
    }
  }

  return {
    // 状态
    sessions,
    currentSessionId,
    messages,
    dataFiles,
    templateFiles,
    modes,
    currentMode,
    isLoading,
    isStreaming,
    // 进度相关状态
    progressValue,
    progressMessage,
    showProgressBar,
    // 计算属性
    currentSession,
    selectedDataFiles,
    selectedTemplateFiles,
    currentModeConfig,
    // Actions
    init,
    loadSessions,
    createSession,
    selectSession,
    deleteSession,
    updateSessionTitle,
    switchMode,
    uploadFile,
    toggleFileSelection,
    deleteFile,
    sendMessage,
    clearAllSelectedFiles,
    syncFileSelectionToServer,
    getSelectedFilesPayload,
    connectWebSocket,
    disconnectWebSocket,
  }
})
