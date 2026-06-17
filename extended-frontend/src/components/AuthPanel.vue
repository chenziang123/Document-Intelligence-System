<script setup>
import { ref, computed } from 'vue'
import { Shield, Smartphone, Lock, Eye, EyeOff, AlertCircle } from 'lucide-vue-next'
import { useAuthStore } from '../stores/authStore'
import BrandLogo from './BrandLogo.vue'

const authStore = useAuthStore()

const activeTab = ref('login')
const loading = ref(false)
const errorText = ref('')
const showPassword = ref(false)

const loginPhone = ref('')
const loginPassword = ref('')
const registerPhone = ref('')
const registerPassword = ref('')
const registerDisplayName = ref('')

const highlights = [
  '文档理解 · 问答与信息提取',
  '文档编辑 · 替换、统一样式、生成目录',
  '提取填表 · Word 字段自动填入 Excel',
  '工作流编排 · 拖拽 Agent 节点批量处理',
]

const canLogin = computed(() => loginPhone.value.trim() && loginPassword.value)
const canRegister = computed(() => registerPhone.value.trim() && registerPassword.value.length >= 6)

function switchTab(tab) {
  activeTab.value = tab
  errorText.value = ''
}

async function handleLogin() {
  if (!canLogin.value) return
  loading.value = true
  errorText.value = ''
  try {
    await authStore.login(loginPhone.value.trim(), loginPassword.value)
  } catch (e) {
    errorText.value = e?.message || '登录失败'
  } finally {
    loading.value = false
  }
}

async function handleRegister() {
  if (!canRegister.value) return
  loading.value = true
  errorText.value = ''
  try {
    await authStore.register(
      registerPhone.value.trim(),
      registerPassword.value,
      registerDisplayName.value.trim() || null
    )
  } catch (e) {
    errorText.value = e?.message || '注册失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-shell">
    <aside class="auth-brand">
      <div class="auth-brand-top">
        <div class="auth-brand-icon" aria-hidden="true">
          <Shield :size="20" :stroke-width="1.9" />
        </div>
        <span class="auth-brand-name">识墨文坊</span>
      </div>

      <div class="auth-brand-body">
        <h1 class="auth-brand-title">识墨文坊</h1>
        <p class="auth-brand-desc">
          理解、编辑、编排一体。上传 Word / Excel / PDF，用自然语言完成文档全流程处理。
        </p>
        <ul class="auth-highlights">
          <li v-for="item in highlights" :key="item">
            <span>✓</span>
            <span>{{ item }}</span>
          </li>
        </ul>
      </div>

      <p class="auth-brand-footer">© 2026 识墨文坊 · 文档智能工坊</p>
    </aside>

    <div class="auth-form-panel">
      <div class="auth-form-inner">
        <div class="auth-form-head">
          <BrandLogo class="auth-mobile-logo" />
          <h2>{{ activeTab === 'login' ? '欢迎回来' : '创建账户' }}</h2>
          <p>识墨文坊 · 理解、编辑、编排一体</p>
        </div>

        <div v-if="errorText" class="auth-error">
          <AlertCircle :size="18" :stroke-width="2" />
          <span>{{ errorText }}</span>
        </div>

        <div class="auth-tabs">
          <button
            type="button"
            class="auth-tab"
            :class="{ active: activeTab === 'login' }"
            @click="switchTab('login')"
          >
            登录
          </button>
          <button
            type="button"
            class="auth-tab"
            :class="{ active: activeTab === 'register' }"
            @click="switchTab('register')"
          >
            注册
          </button>
        </div>

        <form v-if="activeTab === 'login'" class="auth-form" @submit.prevent="handleLogin">
          <div class="auth-field">
            <label class="auth-label" for="login-phone">手机号</label>
            <div class="auth-input-wrap">
              <Smartphone class="auth-input-icon" :size="16" :stroke-width="2" />
              <input
                id="login-phone"
                v-model="loginPhone"
                type="tel"
                class="auth-input"
                placeholder="请输入手机号"
                autocomplete="tel"
              />
            </div>
          </div>

          <div class="auth-field">
            <label class="auth-label" for="login-password">密码</label>
            <div class="auth-input-wrap">
              <Lock class="auth-input-icon" :size="16" :stroke-width="2" />
              <input
                id="login-password"
                v-model="loginPassword"
                :type="showPassword ? 'text' : 'password'"
                class="auth-input"
                placeholder="请输入密码"
                autocomplete="current-password"
              />
              <button type="button" class="auth-pwd-toggle" @click="showPassword = !showPassword">
                <EyeOff v-if="showPassword" :size="16" />
                <Eye v-else :size="16" />
              </button>
            </div>
          </div>

          <button type="submit" class="auth-submit" :disabled="!canLogin || loading">
            <span v-if="!loading">登录</span>
            <span v-else class="auth-spinner" />
          </button>
        </form>

        <form v-else class="auth-form" @submit.prevent="handleRegister">
          <div class="auth-field">
            <label class="auth-label" for="register-phone">手机号</label>
            <div class="auth-input-wrap">
              <Smartphone class="auth-input-icon" :size="16" :stroke-width="2" />
              <input
                id="register-phone"
                v-model="registerPhone"
                type="tel"
                class="auth-input"
                placeholder="请输入手机号"
                autocomplete="tel"
              />
            </div>
          </div>

          <div class="auth-field">
            <label class="auth-label" for="register-name">昵称</label>
            <div class="auth-input-wrap">
              <input
                id="register-name"
                v-model="registerDisplayName"
                type="text"
                class="auth-input auth-input--plain"
                placeholder="昵称（可选）"
                autocomplete="name"
              />
            </div>
          </div>

          <div class="auth-field">
            <label class="auth-label" for="register-password">密码</label>
            <div class="auth-input-wrap">
              <Lock class="auth-input-icon" :size="16" :stroke-width="2" />
              <input
                id="register-password"
                v-model="registerPassword"
                :type="showPassword ? 'text' : 'password'"
                class="auth-input"
                placeholder="设置 6 位以上密码"
                autocomplete="new-password"
              />
              <button type="button" class="auth-pwd-toggle" @click="showPassword = !showPassword">
                <EyeOff v-if="showPassword" :size="16" />
                <Eye v-else :size="16" />
              </button>
            </div>
          </div>

          <button type="submit" class="auth-submit" :disabled="!canRegister || loading">
            <span v-if="!loading">注册并登录</span>
            <span v-else class="auth-spinner" />
          </button>
        </form>

        <p class="auth-switch">
          {{ activeTab === 'login' ? '还没有账户？' : '已有账户？' }}
          <button type="button" @click="switchTab(activeTab === 'login' ? 'register' : 'login')">
            {{ activeTab === 'login' ? '立即注册' : '去登录' }}
          </button>
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth-mobile-logo {
  display: flex;
  justify-content: center;
  margin-bottom: 24px;
}

@media (min-width: 1024px) {
  .auth-mobile-logo {
    display: none;
  }
}
</style>
