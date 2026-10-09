import { ref } from 'vue'

/** 亮/暗主题:localStorage 记忆,首次无偏好时跟随系统;index.html 内联脚本防首屏闪烁。 */
export type Theme = 'light' | 'dark'
const STORAGE_KEY = 'gmod_mm_theme'

function initial(): Theme {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch { /* 隐私模式等场景忽略 */ }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function apply(t: Theme) {
  document.documentElement.classList.toggle('dark', t === 'dark')
  document.documentElement.style.colorScheme = t
}

const theme = ref<Theme>(initial())
apply(theme.value)

function setTheme(t: Theme) {
  theme.value = t
  try { localStorage.setItem(STORAGE_KEY, t) } catch { /* 忽略 */ }
  apply(t)
}

function toggleTheme() {
  setTheme(theme.value === 'dark' ? 'light' : 'dark')
}

export function useTheme() {
  return { theme, setTheme, toggleTheme }
}
