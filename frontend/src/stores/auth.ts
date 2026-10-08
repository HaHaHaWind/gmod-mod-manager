/** 会话状态:登录态 + CSRF,启动时探测 /api/auth/me。 */
import { defineStore } from 'pinia'
import { apiLogin, apiLogout, apiMe } from '@/api'
import { setCsrfToken } from '@/api/client'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    username: '',
    isAdmin: false,
    checked: false,          // 是否已做过会话探测
  }),
  getters: {
    loggedIn: (s) => s.username !== '',
  },
  actions: {
    async probe() {
      try {
        const me = await apiMe()
        this.username = me.username
        this.isAdmin = me.is_admin
        setCsrfToken(me.csrf_token)
      } catch {
        this.username = ''
        this.isAdmin = false
      } finally {
        this.checked = true
      }
    },
    async login(username: string, password: string) {
      const resp = await apiLogin(username, password)
      this.username = resp.username
      this.isAdmin = resp.is_admin
      setCsrfToken(resp.csrf_token)
    },
    async logout() {
      try { await apiLogout() } catch { /* 会话可能已失效,忽略 */ }
      this.username = ''
      this.isAdmin = false
      setCsrfToken('')
    },
  },
})
