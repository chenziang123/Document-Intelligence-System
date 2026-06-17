<script setup>
import { ref, watch, computed } from 'vue'
import { LogOut, UserRound } from 'lucide-vue-next'
import { useAuthStore } from '../stores/authStore'
import { useSessionStore } from '../stores/sessionStore'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['close'])

const authStore = useAuthStore()
const sessionStore = useSessionStore()

const displayName = ref('')
const saving = ref(false)
const errorText = ref('')
const successText = ref('')

const phoneMasked = computed(() => {
  const phone = authStore.currentUser?.phone || ''
  if (phone.length === 11) {
    return `${phone.slice(0, 3)}****${phone.slice(7)}`
  }
  return phone || '—'
})

const canSave = computed(() => {
  const next = displayName.value.trim()
  return next.length > 0 && next !== authStore.userDisplayName && !saving.value
})

watch(
  () => props.visible,
  async (open) => {
    if (!open) return
    errorText.value = ''
    successText.value = ''
    displayName.value = authStore.userDisplayName
    try {
      await authStore.fetchCurrentUser()
      displayName.value = authStore.userDisplayName
    } catch {
      /* 使用本地缓存 */
    }
  }
)

function closePanel() {
  emit('close')
}

async function handleSave() {
  errorText.value = ''
  successText.value = ''
  const next = displayName.value.trim()
  if (!next) {
    errorText.value = '用户名不能为空'
    return
  }
  if (next.length > 32) {
    errorText.value = '用户名不能超过 32 个字符'
    return
  }
  saving.value = true
  try {
    await authStore.updateDisplayName(next)
    displayName.value = authStore.userDisplayName
    successText.value = '用户名已更新'
  } catch (e) {
    errorText.value = e?.message || '保存失败，请稍后重试'
  } finally {
    saving.value = false
  }
}

async function handleLogout() {
  await sessionStore.disconnectWebSocket()
  await authStore.logout()
  closePanel()
}
</script>

<template>
  <div class="modal-overlay" :class="{ active: visible }" @click.self="closePanel">
    <div class="modal user-profile-modal" role="dialog" aria-labelledby="user-profile-title">
      <div class="modal-header">
        <h2 id="user-profile-title" class="modal-title">用户信息</h2>
        <button class="modal-close" type="button" title="关闭" @click="closePanel">×</button>
      </div>

      <div class="modal-body user-profile-body">
        <div class="user-profile-hero">
          <div class="user-profile-avatar" aria-hidden="true">
            {{ authStore.userAvatar }}
          </div>
          <div class="user-profile-hero-text">
            <div class="user-profile-hero-name">{{ authStore.userDisplayName }}</div>
            <div class="user-profile-hero-phone">{{ phoneMasked }}</div>
          </div>
        </div>

        <div v-if="errorText" class="user-profile-alert user-profile-alert--error">{{ errorText }}</div>
        <div v-if="successText" class="user-profile-alert user-profile-alert--success">{{ successText }}</div>

        <div class="user-profile-field">
          <label class="user-profile-label" for="profile-display-name">
            <UserRound :size="14" :stroke-width="2" aria-hidden="true" />
            用户名
          </label>
          <input
            id="profile-display-name"
            v-model="displayName"
            type="text"
            class="user-profile-input"
            maxlength="32"
            placeholder="请输入用户名"
            @keyup.enter="handleSave"
          />
          <p class="user-profile-hint">用于头像展示与对话区显示，最多 32 个字符</p>
        </div>

        <div class="user-profile-field">
          <label class="user-profile-label">手机号</label>
          <div class="user-profile-readonly">{{ authStore.currentUser?.phone || '—' }}</div>
        </div>
      </div>

      <div class="user-profile-footer">
        <button type="button" class="user-profile-btn user-profile-btn--ghost" @click="handleLogout">
          <LogOut :size="16" :stroke-width="2" aria-hidden="true" />
          退出登录
        </button>
        <div class="user-profile-footer-actions">
          <button type="button" class="user-profile-btn user-profile-btn--secondary" @click="closePanel">
            取消
          </button>
          <button
            type="button"
            class="user-profile-btn user-profile-btn--primary"
            :disabled="!canSave"
            @click="handleSave"
          >
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.user-profile-modal {
  width: 440px;
}

.user-profile-body {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.user-profile-hero {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  background: var(--bg-secondary);
}

.user-profile-avatar {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: oklch(0.52 0.16 255 / 0.12);
  border: 1px solid rgba(37, 99, 235, 0.25);
  color: var(--primary);
  font-size: 22px;
  font-weight: 700;
  flex-shrink: 0;
}

.user-profile-hero-name {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}

.user-profile-hero-phone {
  margin-top: 4px;
  font-size: 13px;
  color: var(--text-muted);
}

.user-profile-alert {
  padding: 10px 12px;
  border-radius: var(--radius-md);
  font-size: 13px;
  line-height: 1.45;
}

.user-profile-alert--error {
  color: #dc2626;
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.22);
}

.user-profile-alert--success {
  color: #059669;
  background: rgba(5, 150, 105, 0.08);
  border: 1px solid rgba(5, 150, 105, 0.22);
}

.user-profile-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.user-profile-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.user-profile-input,
.user-profile-readonly {
  width: 100%;
  box-sizing: border-box;
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  font-size: 14px;
  color: var(--text-primary);
  background: var(--bg-tertiary);
}

.user-profile-input:focus {
  outline: none;
  border-color: var(--primary);
}

.user-profile-readonly {
  color: var(--text-muted);
  background: var(--bg-secondary);
}

.user-profile-hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}

.user-profile-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 24px 20px;
  border-top: 1px solid var(--border-color);
}

.user-profile-footer-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.user-profile-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: var(--radius-md);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s, color 0.2s;
}

.user-profile-btn--ghost {
  border: 1px solid var(--border-color);
  background: transparent;
  color: var(--text-secondary);
}

.user-profile-btn--ghost:hover {
  background: rgba(239, 68, 68, 0.08);
  border-color: rgba(239, 68, 68, 0.28);
  color: #dc2626;
}

.user-profile-btn--secondary {
  border: 1px solid var(--border-color);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.user-profile-btn--secondary:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.user-profile-btn--primary {
  border: 1px solid rgba(37, 99, 235, 0.45);
  background: var(--primary);
  color: #fff;
}

.user-profile-btn--primary:hover:not(:disabled) {
  filter: brightness(1.05);
}

.user-profile-btn--primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
