import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import sessionApi from '../api/sessions'
import messageApi from '../api/messages'
import fileApi from '../api/files'
import agentApi from '../api/agents'
import authApi from '../api/auth'

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
  const sessions = ref([])
  const currentSessionId = ref(null)
  const messages = ref([])
  const dataFiles = ref([])
  const templateFiles = ref([])
  const modes = ref([...DEFAULT_MODES])
  const currentMode = ref('default_conversation')
  const isLoading = ref(false)
  const isStreaming = ref(false)
  const progressValue = ref(0)
  const progressMessage = ref('')
  const showProgressBar = ref(false)
  const ws = ref(null)

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

  const isAuthenticated = computed(() => !!currentUser.value)

  const selectedDataFiles = computed(() =>
    dataFiles.value.filter(f => f.is_selected)
  )

  const selectedTemplateFiles = computed(() =>
    templateFiles.value.filter(f => f.is_selected)
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
  }

  async function loadCurrentUser() {
    try {
      const user = await authApi.me()
      currentUser.value = user
      return user
    } catch (e) {
      currentUser.value = null
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
    } finally {
      currentUser.value = null
      clearConversationState()
      disconnectWebSocket()
    }
  }

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
      disconnectWebSocket()
      const res = await sessionApi.create({ title: '新会话', current_mode: currentMode.value })
      sessions.value.unshift(res)
      await selectSession(res.session_id)
    } catch (e) {
      console.error('创建会话失败:', e)
    }
  }

  async function selectSession(sessionId) {
    disconnectWebSocket()
    currentSessionId.value = sessionId
    await loadModes()
    await loadMessages(sessionId)
    await loadFiles(sessionId)
    const session = sessions.value.find(s => s.session_id === sessionId)
    if (session) {
      currentMode.value = session.current_mode || 'default_conversation'
    }
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
          clearConversationState()
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
      messages.value = (res || []).map((msg) => {
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
    } catch (e) {
      console.error('加载消息失败:', e)
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
    } catch (e) {
      console.error('加载文件失败:', e)
    }
  }

  async function uploadFile(file, fileType) {
    if (!currentSessionId.value) return
    try {
      await fileApi.upload(currentSessionId.value, file, fileType)
      // 以服务端列表为准，避免本地增量导致显示重复或错位。
      await loadFiles(currentSessionId.value)
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

  function connectWebSocket() {
    if (!currentSessionId.value) return
    disconnectWebSocket()

    ws.value = messageApi.connect(currentSessionId.value)

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
          loadMessages(currentSessionId.value).catch((e) => console.error('刷新消息失败:', e))
          loadFiles(currentSessionId.value).catch((e) => console.error('刷新文件失败:', e))
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
    syncFileSelectionToServer()
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
    const dataFiles = selectedDataFiles.value.map(f => ({
      file_id: f.id,
      file_name: f.file_name,
      storage_key: f.storage_key,
      file_size: f.file_size,
      is_selected: true,
    }))
    const templateFiles = selectedTemplateFiles.value.map(f => ({
      file_id: f.id,
      file_name: f.file_name,
      storage_key: f.storage_key,
      file_size: f.file_size,
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
    await loadCurrentUser()
    if (!currentUser.value) {
      clearConversationState()
      return
    }
    await loadSessions()
    await loadModes()
    if (sessions.value.length > 0) {
      await selectSession(sessions.value[0].session_id)
    }
  }

  return {
    currentUser,
    isAuthenticated,
    sessions,
    currentSessionId,
    messages,
    dataFiles,
    templateFiles,
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
  }
})