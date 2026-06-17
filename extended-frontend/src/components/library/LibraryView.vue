<script setup>
import LibrarySidebar from './LibrarySidebar.vue'
import DocGrid from './DocGrid.vue'
import { Search } from 'lucide-vue-next'
import { useLibraryStore } from '../../stores/libraryStore'

const libraryStore = useLibraryStore()

function onSearch(event) {
  libraryStore.setSearchQuery(event.target.value)
}

function clearSearch() {
  libraryStore.setSearchQuery('')
}
</script>

<template>
  <div class="library-view">
    <!-- Toolbar -->
    <div class="library-toolbar">
      <div class="library-title">
        <span>文档库管理</span>
        <span class="library-title-sub">个人空间 · 文档检索与管理</span>
      </div>
      <div class="library-actions">
        <!-- 搜索框 -->
        <div class="search-box">
          <span class="search-icon-svg" aria-hidden="true">
            <Search :size="16" :stroke-width="2" />
          </span>
          <input
            :value="libraryStore.searchQuery"
            class="search-input"
            placeholder="搜索文档..."
            @input="onSearch"
          />
          <button
            v-if="libraryStore.searchQuery"
            class="search-clear"
            type="button"
            @click="clearSearch"
          >
            ×
          </button>
        </div>

      </div>
    </div>

    <!-- Body: Sidebar + Content -->
    <div class="library-body">
      <LibrarySidebar />
      <DocGrid />
    </div>
  </div>
</template>

<style scoped>
.library-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--background);
}

.library-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 28px;
  background: var(--card);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.library-title {
  font-family: var(--font-heading);
  font-size: 20px;
  font-weight: 700;
  color: var(--foreground);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.library-title-sub {
  font-size: 13px;
  font-weight: 400;
  color: var(--muted-foreground);
}

.library-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.search-box {
  position: relative;
  display: flex;
  align-items: center;
}

.search-icon-svg {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  color: var(--muted-foreground);
  pointer-events: none;
}

.search-input {
  padding: 8px 36px;
  background: var(--card);
  border: 1px solid var(--input);
  border-radius: var(--radius-md);
  font-size: 13px;
  color: var(--foreground);
  outline: none;
  width: 256px;
  height: 36px;
  transition: border-color 0.2s, box-shadow 0.2s;
  font-family: inherit;
}

.search-input::placeholder {
  color: var(--muted-foreground);
}

.search-input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px oklch(0.52 0.16 255 / 0.12);
}

.search-clear {
  position: absolute;
  right: 10px;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--muted-foreground);
  font-size: 16px;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
}

.search-clear:hover {
  background: var(--secondary);
  color: var(--foreground);
}

.library-body {
  flex: 1;
  display: flex;
  overflow: hidden;
}
</style>
