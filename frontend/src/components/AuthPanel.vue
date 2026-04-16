<script setup>
import { computed, ref } from 'vue'
import { NAlert, NButton, NCard, NInput, NTabPane, NTabs } from 'naive-ui'
import { useSessionStore } from '../stores/sessionStore'

const sessionStore = useSessionStore()

const tab = ref('login')
const loading = ref(false)
const errorText = ref('')

const loginPhone = ref('')
const loginPassword = ref('')

const registerPhone = ref('')
const registerPassword = ref('')
const registerDisplayName = ref('')

const canLogin = computed(() => loginPhone.value.trim() && loginPassword.value)
const canRegister = computed(() => registerPhone.value.trim() && registerPassword.value.length >= 6)

async function submitLogin() {
  if (!canLogin.value) return
  loading.value = true
  errorText.value = ''
  try {
    await sessionStore.login(loginPhone.value.trim(), loginPassword.value)
    await sessionStore.init()
  } catch (e) {
    errorText.value = e?.message || '登录失败'
  } finally {
    loading.value = false
  }
}

async function submitRegister() {
  if (!canRegister.value) return
  loading.value = true
  errorText.value = ''
  try {
    await sessionStore.register(
      registerPhone.value.trim(),
      registerPassword.value,
      registerDisplayName.value.trim() || null,
    )
    await sessionStore.init()
  } catch (e) {
    errorText.value = e?.message || '注册失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-shell">
    <div class="auth-bg-shape auth-bg-shape-a" aria-hidden="true"></div>
    <div class="auth-bg-shape auth-bg-shape-b" aria-hidden="true"></div>

    <n-card class="auth-card" :bordered="false">
      <div class="auth-title-wrap">
        <h1 class="auth-title">文档智能系统</h1>
        <p class="auth-subtitle">登录后可使用会话历史与文件持久化能力</p>
      </div>

      <n-alert v-if="errorText" type="error" :show-icon="false" class="auth-error">
        {{ errorText }}
      </n-alert>

      <n-tabs v-model:value="tab" animated>
        <n-tab-pane name="login" tab="登录">
          <div class="auth-form">
            <label class="auth-label">手机号</label>
            <n-input v-model:value="loginPhone" placeholder="请输入手机号" clearable />

            <label class="auth-label">密码</label>
            <n-input
              v-model:value="loginPassword"
              type="password"
              show-password-on="click"
              placeholder="请输入密码"
            />

            <n-button type="primary" block :loading="loading" :disabled="!canLogin" @click="submitLogin">
              登录
            </n-button>
          </div>
        </n-tab-pane>

        <n-tab-pane name="register" tab="注册">
          <div class="auth-form">
            <label class="auth-label">手机号</label>
            <n-input v-model:value="registerPhone" placeholder="请输入手机号" clearable />

            <label class="auth-label">昵称（可选）</label>
            <n-input v-model:value="registerDisplayName" placeholder="例如：项目经理A" clearable />

            <label class="auth-label">密码</label>
            <n-input
              v-model:value="registerPassword"
              type="password"
              show-password-on="click"
              placeholder="至少 6 位"
            />

            <n-button type="primary" block :loading="loading" :disabled="!canRegister" @click="submitRegister">
              注册并登录
            </n-button>
          </div>
        </n-tab-pane>
      </n-tabs>
    </n-card>
  </div>
</template>

<style scoped>
.auth-shell {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle at 15% 20%, #d4f5e6 0%, #f5fbf8 42%, #eef4ff 100%);
  overflow: hidden;
  padding: 24px;
}

.auth-bg-shape {
  position: absolute;
  border-radius: 999px;
  filter: blur(2px);
}

.auth-bg-shape-a {
  width: 380px;
  height: 380px;
  background: linear-gradient(135deg, rgba(24, 160, 88, 0.2), rgba(31, 94, 255, 0.16));
  top: -120px;
  right: -80px;
}

.auth-bg-shape-b {
  width: 300px;
  height: 300px;
  background: linear-gradient(135deg, rgba(255, 202, 40, 0.15), rgba(24, 160, 88, 0.12));
  bottom: -80px;
  left: -70px;
}

.auth-card {
  width: 100%;
  max-width: 430px;
  border-radius: 18px;
  box-shadow: 0 20px 60px rgba(36, 63, 95, 0.14);
  z-index: 1;
}

.auth-title-wrap {
  margin-bottom: 14px;
}

.auth-title {
  margin: 0;
  font-size: 28px;
  line-height: 1.2;
  letter-spacing: 0.5px;
  color: #14324d;
  font-family: Georgia, 'Times New Roman', serif;
}

.auth-subtitle {
  margin: 6px 0 0;
  color: #59708a;
  font-size: 14px;
}

.auth-error {
  margin-bottom: 12px;
}

.auth-form {
  display: grid;
  gap: 10px;
  margin-top: 4px;
}

.auth-label {
  font-size: 13px;
  color: #4c6074;
  font-weight: 600;
}

@media (max-width: 640px) {
  .auth-shell {
    padding: 16px;
  }

  .auth-title {
    font-size: 24px;
  }
}
</style>
