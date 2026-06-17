<script setup>
import { ref } from 'vue'
import { Bell, Settings, FolderClosed, MessagesSquare, Workflow } from 'lucide-vue-next'
import { useTabStore } from '../stores/tabStore'
import { useAuthStore } from '../stores/authStore'
import BrandLogo from './BrandLogo.vue'
import UserProfilePanel from './UserProfilePanel.vue'

const tabStore = useTabStore()
const authStore = useAuthStore()
const showUserProfile = ref(false)

const navItems = [
  { id: 'library', label: '文档库', icon: FolderClosed },
  { id: 'chat', label: '智能对话', icon: MessagesSquare },
  { id: 'workflow', label: '工作流编排', icon: Workflow },
]

function handleTabClick(tabId) {
  tabStore.switchTab(tabId)
}

function openUserProfile() {
  showUserProfile.value = true
}

function closeUserProfile() {
  showUserProfile.value = false
}
</script>

<template>
  <aside class="app-nav-rail" aria-label="全局导航">
    <button type="button" class="nav-rail-logo" @click="handleTabClick('library')" title="识墨文坊">
      <BrandLogo :show-text="false" />
    </button>

    <nav class="nav-rail-menu">
      <button
        v-for="item in navItems"
        :key="item.id"
        type="button"
        class="nav-rail-item"
        :class="{ active: tabStore.currentTab === item.id }"
        :title="item.label"
        @click="handleTabClick(item.id)"
      >
        <component :is="item.icon" :size="22" :stroke-width="1.9" aria-hidden="true" />
        <span>{{ item.label }}</span>
      </button>
    </nav>

    <div class="nav-rail-footer">
      <button type="button" class="nav-rail-tool" title="通知" aria-label="通知">
        <Bell :size="20" :stroke-width="1.9" />
      </button>
      <button type="button" class="nav-rail-tool" title="设置" aria-label="设置">
        <Settings :size="20" :stroke-width="1.9" />
      </button>
      <button
        type="button"
        class="nav-rail-avatar"
        :title="`${authStore.userDisplayName} · 点击查看用户信息`"
        @click="openUserProfile"
      >
        {{ authStore.userAvatar }}
      </button>
    </div>
  </aside>

  <UserProfilePanel :visible="showUserProfile" @close="closeUserProfile" />
</template>
