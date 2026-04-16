<script setup>
import { computed, ref } from 'vue'
import { NButton, NInput, NScrollbar } from 'naive-ui'
import { useSessionStore } from '../stores/sessionStore'

const sessionStore = useSessionStore()
const editingSessionId = ref(null)
const editingTitle = ref('')
const savingTitle = ref(false)

const sortedSessions = computed(() => {
  return [...sessionStore.sessions].sort((a, b) =>
    new Date(b.updated_at) - new Date(a.updated_at)
  )
})

function formatTime(isoString) {
  if (!isoString) return ''
  const date = new Date(isoString)
  const now = new Date()
  const diff = now - date
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  return date.toLocaleDateString('zh-CN')
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
  <div class="flex flex-col h-full">
    <!-- 新建会话按钮 -->
    <div class="p-3">
      <n-button block type="primary" @click="sessionStore.createSession">
        + 新建会话
      </n-button>
    </div>

    <!-- 会话列表 -->
    <n-scrollbar class="flex-1">
      <div class="px-2 pb-2">
        <div
          v-for="session in sortedSessions"
          :key="session.session_id"
          :class="[
            'p-3 rounded-lg cursor-pointer mb-1 transition-colors',
            session.session_id === sessionStore.currentSessionId
              ? 'bg-green-50 border border-green-200'
              : 'hover:bg-gray-100'
          ]"
          @click="sessionStore.selectSession(session.session_id)"
        >
          <div class="flex justify-between items-start">
            <div class="flex-1 min-w-0">
              <n-input
                v-if="editingSessionId === session.session_id"
                v-model:value="editingTitle"
                size="small"
                maxlength="64"
                :disabled="savingTitle"
                @click.stop
                @keydown.enter.prevent="saveRename(session)"
                @keydown.esc.prevent="cancelRename"
                @blur="saveRename(session)"
              />
              <div v-else class="font-medium text-gray-800 truncate">
                {{ session.title }}
              </div>
              <div class="text-xs text-gray-500 mt-1">
                {{ formatTime(session.updated_at) }}
              </div>
            </div>
            <div class="flex items-center gap-1 ml-2">
              <n-button
                size="tiny"
                quaternary
                title="重命名"
                @click.stop="startRename(session)"
              >
                <template #icon>
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 4h2m-7 14h12M7 16l8.586-8.586a2 2 0 112.828 2.828L9.828 18.828A2 2 0 018.414 19.414L5 20l.586-3.414A2 2 0 016.172 15.172z" />
                  </svg>
                </template>
              </n-button>
              <n-button
                size="tiny"
                quaternary
                title="删除会话"
                @click.stop="sessionStore.deleteSession(session.session_id)"
              >
                <template #icon>
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </template>
              </n-button>
            </div>
          </div>
        </div>

        <!-- 空状态 -->
        <div v-if="sortedSessions.length === 0" class="text-center text-gray-400 py-8">
          暂无会话，点击上方按钮创建
        </div>
      </div>
    </n-scrollbar>
  </div>
</template>
