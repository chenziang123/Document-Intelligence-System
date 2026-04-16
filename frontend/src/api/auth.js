import client from './client'

const TOKEN_KEY = 'access_token'

function setAccessToken(token) {
  if (token) {
    window.localStorage.setItem(TOKEN_KEY, token)
  }
}

function clearAccessToken() {
  window.localStorage.removeItem(TOKEN_KEY)
}

export function getAccessToken() {
  return window.localStorage.getItem(TOKEN_KEY)
}

export default {
  register(data) {
    return client.post('/auth/register', data).then((res) => {
      if (res?.access_token) {
        setAccessToken(res.access_token)
      }
      return res
    })
  },

  login(data) {
    return client.post('/auth/login', data).then((res) => {
      if (res?.access_token) {
        setAccessToken(res.access_token)
      }
      return res
    })
  },

  me() {
    return client.get('/auth/me')
  },

  logout() {
    return client.post('/auth/logout').finally(() => {
      clearAccessToken()
    })
  },

  clearAccessToken,
  setAccessToken,
}