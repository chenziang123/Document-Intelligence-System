import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import authApi from '../api/auth'
import { getUserFromToken } from '../api/auth'

export const useAuthStore = defineStore('auth', () => {
  const currentUser = ref(null)
  const isInitializing = ref(true)
  const isAuthenticated = computed(() => !!currentUser.value)

  const userDisplayName = computed(() => {
    if (!currentUser.value) return ''
    return currentUser.value.display_name || currentUser.value.phone || '用户'
  })

  const userAvatar = computed(() => {
    if (!currentUser.value) return '?'
    const name = userDisplayName.value
    return name.charAt(0).toUpperCase()
  })

  function init() {
    isInitializing.value = true
    const user = getUserFromToken()
    if (user) {
      currentUser.value = user
    }
    isInitializing.value = false
  }

  async function login(phone, password) {
    const res = await authApi.login({ phone, password })
    const user = getUserFromToken()
    if (user) {
      currentUser.value = user
    }
    return res
  }

  async function register(phone, password, displayName = null) {
    const res = await authApi.register({
      phone,
      password,
      display_name: displayName,
    })
    const user = getUserFromToken()
    if (user) {
      currentUser.value = user
    }
    return res
  }

  async function logout() {
    try {
      await authApi.logout()
    } catch (e) {
      // 忽略登出错误
    }
    currentUser.value = null
    authApi.clearAccessToken()
  }

  async function fetchCurrentUser() {
    const res = await authApi.me()
    if (res) {
      currentUser.value = {
        id: res.id,
        phone: res.phone,
        display_name: res.display_name,
        status: res.status || 'active',
      }
    }
    return res
  }

  async function updateDisplayName(displayName) {
    const name = String(displayName || '').trim()
    const res = await authApi.updateProfile({ display_name: name })
    const user = getUserFromToken()
    if (user) {
      currentUser.value = user
    } else if (res?.user) {
      currentUser.value = {
        id: res.user.id,
        phone: res.user.phone,
        display_name: res.user.display_name,
        status: res.user.status || 'active',
      }
    }
    return res
  }

  return {
    currentUser,
    isInitializing,
    isAuthenticated,
    userDisplayName,
    userAvatar,
    init,
    login,
    register,
    logout,
    fetchCurrentUser,
    updateDisplayName,
  }
})
