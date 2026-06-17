<script setup>
import { ref, onMounted, watch } from 'vue'
import { useTabStore } from './stores/tabStore'
import { useAuthStore } from './stores/authStore'
import { useSessionStore } from './stores/sessionStore'
import AppHeader from './components/AppHeader.vue'
import AuthPanel from './components/AuthPanel.vue'
import LibraryView from './components/library/LibraryView.vue'
import ChatView from './components/chat/ChatView.vue'
import WorkflowView from './components/workflow/WorkflowView.vue'
import BatchModal from './components/BatchModal.vue'

const tabStore = useTabStore()
const authStore = useAuthStore()
const sessionStore = useSessionStore()
const showBatchModal = ref(false)

// 挂载时初始化认证状态
onMounted(() => {
  authStore.init()
})

// 当用户登录成功后，初始化会话
watch(() => authStore.isAuthenticated, (isAuth) => {
  if (isAuth) {
    sessionStore.init()
  }
}, { immediate: true })

function openBatchModal() {
  showBatchModal.value = true
}

function closeBatchModal() {
  showBatchModal.value = false
}
</script>

<template>
  <div class="app">
    <!-- 未登录显示登录界面 -->
    <AuthPanel v-if="!authStore.isAuthenticated && !authStore.isInitializing" />

    <!-- 已登录显示主界面：左侧导航 + 主内容区 -->
    <div v-else-if="authStore.isAuthenticated" class="app-shell">
      <AppHeader />

      <div class="app-main">
        <main class="main-content">
          <LibraryView v-if="tabStore.currentTab === 'library'" />
          <!-- keep-alive：避免每次从文档库切回时整页销毁/重建 ChatView（WebSocket 重连 + 全量 Markdown 重算导致卡顿） -->
          <keep-alive>
            <ChatView v-if="tabStore.currentTab === 'chat'" />
          </keep-alive>
          <!-- keep-alive：切换模块时保留工作流画布与节点配置，避免侧栏重复加载覆盖编辑态 -->
          <keep-alive>
            <WorkflowView
              v-if="tabStore.currentTab === 'workflow'"
              @open-batch-modal="openBatchModal"
            />
          </keep-alive>
        </main>

        <BatchModal
          :visible="showBatchModal"
          @close="closeBatchModal"
        />
      </div>
    </div>

    <!-- 初始化中显示加载状态 -->
    <div v-else class="loading-screen">
      <div class="loading-spinner"></div>
      <p>加载中...</p>
    </div>
  </div>
</template>
