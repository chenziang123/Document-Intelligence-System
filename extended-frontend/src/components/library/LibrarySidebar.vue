<script setup>
import { useLibraryStore } from '../../stores/libraryStore'

const libraryStore = useLibraryStore()

function handleSpaceClick(spaceId) {
  libraryStore.selectSpace(spaceId)
}

function handleDocClick(docId) {
  libraryStore.toggleDocSelect(docId)
}
</script>

<template>
  <div class="library-sidebar">
    <!-- Spaces Section -->
    <div class="space-section">
      <div class="space-header">
        <span class="space-title">文档空间</span>
        <button class="space-action" title="新建空间">+</button>
      </div>

      <div
        v-for="space in libraryStore.spaces"
        :key="space.id"
        class="space-item"
        :class="{ active: libraryStore.currentSpaceId === space.id }"
        @click="handleSpaceClick(space.id)"
      >
        <span class="space-icon">{{ space.icon }}</span>
        <span class="space-name">{{ space.name }}</span>
        <span class="space-count">{{ space.count }}</span>
      </div>
    </div>
  </div>
</template>
