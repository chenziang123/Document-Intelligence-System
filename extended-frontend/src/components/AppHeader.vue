<script setup>
import { Bell, Settings, FileText } from 'lucide-vue-next'
import { useTabStore } from '../stores/tabStore'
import { useAuthStore } from '../stores/authStore'
import { useSessionStore } from '../stores/sessionStore'

const tabStore = useTabStore()
const authStore = useAuthStore()
const sessionStore = useSessionStore()

function handleTabClick(tabId) {
  tabStore.switchTab(tabId)
}

async function handleLogout() {
  await sessionStore.disconnectWebSocket()
  await authStore.logout()
}
</script>

<template>
  <header class="header">
    <div class="header-left">
      <div class="logo">
        <div class="logo-icon" aria-hidden="true">
          <FileText :size="20" :stroke-width="2" />
        </div>
        <span>文档智能系统</span>
      </div>

      <nav class="main-nav">
        <button
          v-for="tab in tabStore.tabs"
          :key="tab.id"
          class="nav-tab"
          :class="{ active: tabStore.currentTab === tab.id }"
          :data-tab="tab.id"
          @click="handleTabClick(tab.id)"
        >
          <span>{{ tab.label }}</span>
        </button>
      </nav>
    </div>

    <div class="header-right">
      <button class="header-btn" type="button" title="通知" aria-label="通知">
        <Bell :size="18" :stroke-width="2" aria-hidden="true" />
      </button>
      <button class="header-btn" type="button" title="设置" aria-label="设置">
        <Settings :size="18" :stroke-width="2" aria-hidden="true" />
      </button>

      <div class="header-user">
        <div class="user-info">
          <span class="user-name">{{ authStore.userDisplayName }}</span>
          <button type="button" class="logout-btn" @click="handleLogout" title="退出登录">
            退出
          </button>
        </div>
        <div class="user-avatar" :title="authStore.userDisplayName">
          {{ authStore.userAvatar }}
        </div>
      </div>
    </div>
  </header>
</template>
