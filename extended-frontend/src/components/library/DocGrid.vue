<script setup>
import { useLibraryStore } from '../../stores/libraryStore'

const libraryStore = useLibraryStore()

function handleDocClick(docId) {
  libraryStore.toggleDocSelect(docId)
}

function handleUpload() {
  const input = document.createElement('input')
  input.type = 'file'
  input.multiple = true
  input.accept = '.pdf,.doc,.docx,.xlsx,.xls'
  input.onchange = (e) => {
    const files = e.target.files
    if (files.length > 0) {
      // File upload handling would go here
      console.log('Selected files:', files)
    }
  }
  input.click()
}
</script>

<template>
  <div class="library-content">
    <!-- Content Header -->
    <div class="content-header">
      <div class="current-space">
        <span>{{ libraryStore.currentSpace?.icon }}</span>
        <span>{{ libraryStore.currentSpace?.name }}</span>
      </div>
      <div class="selected-info" v-if="libraryStore.selectedCount > 0">
        已选择 <strong>{{ libraryStore.selectedCount }}</strong> 个文档
        <button
          class="lib-btn"
          style="margin-left: 12px; padding: 6px 12px; font-size: 12px;"
          @click="libraryStore.clearSelection"
        >
          取消选择
        </button>
      </div>
    </div>

    <!-- Document Grid -->
    <div class="doc-grid">
      <div
        v-for="doc in libraryStore.allDocs"
        :key="doc.id"
        class="doc-card"
        :class="{ selected: libraryStore.isDocSelected(doc.id) }"
        @click="handleDocClick(doc.id)"
      >
        <div class="doc-checkbox">
          <span v-if="libraryStore.isDocSelected(doc.id)">✓</span>
        </div>
        <div class="doc-icon">📕</div>
        <div class="doc-name" :title="doc.name">{{ doc.name }}</div>
        <div class="doc-meta">
          <span>{{ doc.size }}</span>
          <span>{{ doc.time }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
