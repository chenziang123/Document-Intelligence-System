<script setup>
import { NConfigProvider, NMessageProvider, NDialogProvider } from 'naive-ui'
import { ref } from 'vue'
import Sidebar from './components/Sidebar.vue'
import ChatArea from './components/ChatArea.vue'
import ModeSelector from './components/ModeSelector.vue'
import FilePanel from './components/FilePanel.vue'
import { useSessionStore } from './stores/sessionStore'

const sessionStore = useSessionStore()
sessionStore.init()

const themeOverrides = {
  common: {
    primaryColor: '#18a058',
    primaryColorHover: '#36ad6a',
  }
}

const sidebarCollapsed = ref(false)

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}
</script>

<template>
  <n-config-provider :theme-overrides="themeOverrides">
    <n-message-provider>
      <n-dialog-provider>
        <div class="h-screen flex">
          <!-- 侧边栏（展开） -->
          <transition name="sidebar-expand">
            <aside
              v-if="!sidebarCollapsed"
              class="w-64 border-r bg-gray-50 flex flex-col shrink-0"
            >
              <div class="p-4 border-b flex items-center justify-between">
                <h1 class="text-lg font-bold text-gray-700 truncate">文档智能系统</h1>
                <button
                  @click="toggleSidebar"
                  title="收起侧边栏"
                  class="shrink-0 w-7 h-7 flex items-center justify-center rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-200 transition-colors"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="15 18 9 12 15 6"/>
                  </svg>
                </button>
              </div>
              <Sidebar />
            </aside>
          </transition>

          <!-- 侧边栏已收缩时，显示窄条触发器 -->
          <transition name="sidebar-expand">
            <div
              v-if="sidebarCollapsed"
              class="w-12 border-r bg-gray-50 flex flex-col items-center py-3 gap-2 shrink-0"
            >
              <button
                @click="sessionStore.createSession(); sidebarCollapsed = false"
                title="新建会话"
                class="w-9 h-9 flex items-center justify-center rounded-lg bg-green-600 text-white hover:bg-green-700 transition-colors"
              >
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
                </svg>
              </button>
              <button
                @click="toggleSidebar"
                title="展开侧边栏"
                class="w-9 h-9 flex items-center justify-center rounded-lg bg-green-50 text-green-700 hover:bg-green-100 transition-colors"
              >
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="9 18 15 12 9 6"/>
                </svg>
              </button>
            </div>
          </transition>

          <!-- 主内容区 -->
          <main class="flex-1 flex flex-col min-w-0">
            <!-- 模式选择器 -->
            <div class="border-b bg-white px-4 py-3">
              <ModeSelector />
            </div>

            <!-- 文件面板 -->
            <div class="border-b bg-gray-50 px-4 py-3 max-h-48 overflow-y-auto">
              <FilePanel />
            </div>

            <!-- 聊天区域 -->
            <div class="flex-1 overflow-hidden">
              <ChatArea />
            </div>
          </main>
        </div>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<style scoped>
.sidebar-expand-enter-active,
.sidebar-expand-leave-active {
  transition: width 0.2s ease, opacity 0.2s ease;
  overflow: hidden;
}
.sidebar-expand-enter-from,
.sidebar-expand-leave-to {
  width: 0 !important;
  opacity: 0;
}
</style>
