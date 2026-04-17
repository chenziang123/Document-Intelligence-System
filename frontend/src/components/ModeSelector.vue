<script setup>
import { computed } from 'vue'
import { NTag } from 'naive-ui'
import { useSessionStore } from '../stores/sessionStore'

const sessionStore = useSessionStore()

const modeLabels = {
  'default_conversation': { name: '默认对话', color: 'default' },
  'document_understanding': { name: '文档理解', color: 'info' },
  'document_editing': { name: '文档编辑', color: 'success' },
  'entity_extraction': { name: '实体提取', color: 'warning' },
  'table_filling': { name: '表格填表', color: 'error' },
  'mixed': { name: '混合模式', color: 'primary' },
}

const fixedModes = [
  { id: 'mixed', name: '混合模式' },
]

const allModes = computed(() => [...sessionStore.modes, ...fixedModes])
</script>

<template>
  <div class="flex items-center gap-2">
    <span class="text-sm text-gray-500">模式：</span>
    <div class="flex gap-2">
      <n-tag
        v-for="mode in allModes"
        :key="mode.id"
        :type="sessionStore.currentMode === mode.id ? 'success' : 'default'"
        :bordered="sessionStore.currentMode === mode.id"
        checkable
        :checked="sessionStore.currentMode === mode.id"
        @click="sessionStore.switchMode(mode.id)"
        class="cursor-pointer"
      >
        {{ mode.name }}
      </n-tag>
    </div>
  </div>
</template>
