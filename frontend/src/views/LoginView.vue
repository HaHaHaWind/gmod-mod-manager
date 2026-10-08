<script setup lang="ts">
/** 登录页:中文表单,错误直接展示后端 message(含限速提示)。 */
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useSystemStore } from '@/stores/system'
import { ApiRequestError } from '@/api/client'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const system = useSystemStore()

const formRef = ref<FormInstance>()
const loading = ref(false)
const errorMsg = ref('')
const form = ref({ username: '', password: '' })

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function submit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  errorMsg.value = ''
  try {
    await auth.login(form.value.username.trim(), form.value.password)
    await system.refresh()
    ElMessage.success(`欢迎,${auth.username}`)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    router.push(redirect)
  } catch (e) {
    if (e instanceof ApiRequestError) {
      errorMsg.value = e.code === 'invalid_credentials'
        ? '用户名或密码错误' : e.message
    } else {
      errorMsg.value = '登录失败,请稍后重试'
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <el-card class="login-card">
      <div class="login-head">
        <h2>GMod Workshop Mod 管理面板</h2>
        <p>面向 Garry's Mod 专用服务器的 Workshop 内容管理</p>
      </div>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top"
               @keyup.enter="submit">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" :prefix-icon="User" placeholder="管理员用户名"
                    autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password
                    :prefix-icon="Lock" placeholder="密码" autocomplete="current-password" />
        </el-form-item>
        <el-alert v-if="errorMsg" :title="errorMsg" type="error" show-icon :closable="false" />
        <el-button type="primary" class="login-btn" :loading="loading" native-type="submit"
                   @click.prevent="submit">
          登 录
        </el-button>
      </el-form>
      <p class="login-tip">首次部署请用命令行创建管理员账号(见 README)。</p>
    </el-card>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex; align-items: center; justify-content: center;
  background: linear-gradient(160deg, #1f2d3d 0%, #2b3a4d 60%, #33526e 100%);
}
.login-card { width: 400px; }
.login-head { text-align: center; margin-bottom: 18px; }
.login-head h2 { margin: 0 0 6px; font-size: 20px; }
.login-head p { margin: 0; color: #909399; font-size: 13px; }
.login-btn { width: 100%; margin-top: 8px; }
.login-tip { margin: 14px 0 0; font-size: 12px; color: #909399; text-align: center; }
</style>
