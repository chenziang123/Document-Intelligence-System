import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

client.interceptors.request.use((config) => {
  const token = window.localStorage.getItem('access_token')
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

client.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      // 无效/过期 token 会导致后端拒识；清除后后续请求按未登录处理，避免反复 401
      window.localStorage.removeItem('access_token')
    }
    const message =
      error.response?.data?.error?.message ||
      (typeof error.response?.data?.detail === 'string' ? error.response.data.detail : '') ||
      error.message
    return Promise.reject(new Error(message))
  }
)

export default client
