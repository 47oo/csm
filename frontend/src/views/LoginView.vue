<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import { isApiError } from '../api/client'
import { validateUsername } from '../utils/validation'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const formRef = ref<FormInstance>()
const submitting = ref(false)
const formError = ref('')
const form = reactive({
  username: '',
  password: '',
})

const rules: FormRules = {
  username: [{ required: true, validator: (_rule, value: string, callback) => {
    const error = validateUsername(value ?? '')
    callback(error ?? undefined)
  }, trigger: 'blur' }],
  password: [{ required: true, message: '请输入口令', trigger: 'blur' }],
}

async function handleSubmit(): Promise<void> {
  formError.value = ''
  const valid = await formRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    await auth.login(form.username, form.password)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : ''
    void router.replace(redirect.startsWith('/') ? redirect : { name: 'home' })
  } catch (error) {
    if (isApiError(error)) {
      // 401 INVALID_CREDENTIALS：统一文案（防账号枚举）；403 ACCOUNT_DISABLED：账号已禁用
      formError.value = error.message
    } else {
      formError.value = '登录失败，请稍后重试'
    }
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <el-card class="login-card">
      <h2 class="login-title">CSM 资源管理平台</h2>
      <el-alert
        v-if="auth.initError"
        type="warning"
        :closable="false"
        show-icon
        :title="`无法确认登录状态：${auth.initError}`"
        class="login-init-error"
      />
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @submit.prevent="handleSubmit"
      >
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            name="username"
            autocomplete="username"
            placeholder="仅字母与数字"
          />
        </el-form-item>
        <el-form-item label="口令" prop="password">
          <el-input
            v-model="form.password"
            name="password"
            type="password"
            autocomplete="current-password"
            show-password
            @keyup.enter="handleSubmit"
          />
        </el-form-item>
        <el-alert
          v-if="formError"
          type="error"
          :closable="false"
          show-icon
          :title="formError"
          class="login-error"
        />
        <el-button
          type="primary"
          class="login-submit"
          :loading="submitting"
          native-type="submit"
        >
          登录
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(180deg, #1f2d3d 0%, #2b3d4f 100%);
}
.login-card {
  width: 380px;
  padding: 8px 12px 4px;
}
.login-title {
  text-align: center;
  margin: 8px 0 20px;
  font-size: 18px;
}
.login-error,
.login-init-error {
  margin-bottom: 16px;
}
.login-submit {
  width: 100%;
}
</style>
