<script setup>
import { ref, computed } from 'vue'
import { Pencil, Trash2, Plus } from 'lucide-vue-next'
import { useSessionStore } from '../../stores/sessionStore'

const sessionStore = useSessionStore()

const editingSessionId = ref(null)
const editingTitle = ref('')
const savingTitle = ref(false)
const searchQuery = ref('')

const sortedSessions = computed(() => {
  const sorted = [...sessionStore.sessions].sort((a, b) => {
    const dateA = new Date(a.updated_at || a.created_at)
    const dateB = new Date(b.updated_at || b.created_at)
    const timeA = isNaN(dateA.getTime()) ? 0 : dateA.getTime()
    const timeB = isNaN(dateB.getTime()) ? 0 : dateB.getTime()
    return timeB - timeA
  })
  if (!searchQuery.value) return sorted
  const query = searchQuery.value.toLowerCase()
  return sorted.filter(s => (s.title || '').toLowerCase().includes(query))
})

const groupedSessions = computed(() => {
  const groups = {
    '今天': [],
    '昨天': [],
    '本周': [],
    '较早': []
  }
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today - 86400000)
  const weekAgo = new Date(today - 7 * 86400000)

  sortedSessions.value.forEach(session => {
    const date = new Date(session.updated_at || session.created_at)
    if (date >= today) {
      groups['今天'].push(session)
    } else if (date >= yesterday) {
      groups['昨天'].push(session)
    } else if (date >= weekAgo) {
      groups['本周'].push(session)
    } else {
      groups['较早'].push(session)
    }
  })
  return groups
})

function handleSearch(e) {
  searchQuery.value = e.target.value
}

function startRename(session) {
  editingSessionId.value = session.session_id
  editingTitle.value = session.title || ''
}

function cancelRename() {
  editingSessionId.value = null
  editingTitle.value = ''
}

async function saveRename(session) {
  if (savingTitle.value) return
  const title = (editingTitle.value || '').trim()
  if (!title) {
    cancelRename()
    return
  }
  if (title === (session.title || '')) {
    cancelRename()
    return
  }
  savingTitle.value = true
  try {
    await sessionStore.updateSessionTitle(session.session_id, title)
  } finally {
    savingTitle.value = false
    cancelRename()
  }
}
</script>

<template>
  <aside class="chat-sidebar">
    <div class="chat-sidebar-header">
      <button class="new-session-btn" @click="sessionStore.createSession">
        <Plus :size="18" :stroke-width="2" aria-hidden="true" />
        <span>新建会话</span>
      </button>
    </div>

    <div class="chat-search">
      <input
        type="text"
        placeholder="搜索会话..."
        :value="searchQuery"
        @input="handleSearch"
      />
    </div>

    <div class="session-list">
      <div
        v-if="sessionStore.isInitializing && sessionStore.sessions.length === 0"
        class="session-empty"
      >
        加载会话...
      </div>

      <template v-for="(sessions, group) in groupedSessions" :key="group">
        <div v-if="sessions.length > 0" class="session-group">
          <div class="session-group-title">{{ group }}</div>
          <div
            v-for="session in sessions"
            :key="session.session_id"
            class="session-item"
            :class="{ active: sessionStore.currentSessionId === session.session_id }"
            @click="sessionStore.selectSession(session.session_id)"
          >
            <div class="session-info">
              <div v-if="editingSessionId === session.session_id" class="session-edit" @click.stop>
                <input
                  v-model="editingTitle"
                  type="text"
                  class="session-edit-input"
                  :disabled="savingTitle"
                  @keydown.enter.prevent="saveRename(session)"
                  @keydown.esc.prevent="cancelRename"
                  @blur="saveRename(session)"
                  autofocus
                />
              </div>
              <template v-else>
                <span class="session-name">{{ session.title }}</span>
                <span class="session-time">{{ sessionStore.formatTime(session.updated_at) }}</span>
              </template>
            </div>
            <div class="session-actions" @click.stop>
              <button
                class="session-action-btn"
                type="button"
                title="重命名"
                @click="startRename(session)"
              >
                <Pencil :size="14" :stroke-width="2" aria-hidden="true" />
              </button>
              <button
                class="session-action-btn delete"
                type="button"
                title="删除会话"
                @click="sessionStore.deleteSession(session.session_id)"
              >
                <Trash2 :size="14" :stroke-width="2" aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>
      </template>

      <div v-if="sortedSessions.length === 0" class="session-empty">
        暂无会话，点击上方按钮创建
      </div>
    </div>
  </aside>
</template>
