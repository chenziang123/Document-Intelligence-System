<script setup>
import LibrarySidebar from './LibrarySidebar.vue'
import DocGrid from './DocGrid.vue'
import { useLibraryStore } from '../../stores/libraryStore'

const libraryStore = useLibraryStore()
</script>

<template>
  <div class="library-view">
    <!-- Toolbar -->
    <div class="library-toolbar">
      <div class="library-title">
        <span>📚</span>
        <span>文档库管理</span>
      </div>
      <div class="library-actions">
        <button class="lib-btn">
          <span>🔍</span>
          <span>搜索</span>
        </button>
        <button class="lib-btn">
          <span>📤</span>
          <span>导入</span>
        </button>
        <button class="lib-btn primary">
          <span>+</span>
          <span>新建文档</span>
        </button>
      </div>
    </div>

    <!-- Body: Sidebar + Content -->
    <div class="library-body">
      <LibrarySidebar />
      <DocGrid />
    </div>
  </div>
</template>
