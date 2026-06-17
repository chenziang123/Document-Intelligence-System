import { defineStore } from 'pinia'
import { ref } from 'vue'

const TAB_STORAGE_KEY = 'dis_active_tab'
const VALID_TABS = ['library', 'chat', 'workflow']

function readStoredTab() {
  try {
    const stored = sessionStorage.getItem(TAB_STORAGE_KEY)
    return VALID_TABS.includes(stored) ? stored : 'library'
  } catch {
    return 'library'
  }
}

export const useTabStore = defineStore('tab', () => {
  const currentTab = ref(readStoredTab())

  const tabs = [
    { id: 'library', label: '文档库' },
    { id: 'chat', label: '智能对话' },
    { id: 'workflow', label: '工作流编排' }
  ]

  function switchTab(tabId) {
    if (!VALID_TABS.includes(tabId)) return
    currentTab.value = tabId
    try {
      sessionStorage.setItem(TAB_STORAGE_KEY, tabId)
    } catch {
      /* ignore quota / private mode */
    }
  }

  return {
    currentTab,
    tabs,
    switchTab
  }
})
