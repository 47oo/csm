<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormItemRule } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import { isApiError } from '../api/client'
import { validatePassword } from '../utils/validation'

// 改密页：首登强制（must_change_password）与用户菜单自助进入共用。
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const forced = computed(() => auth.mustChangePassword)

const formRef = ref<FormInstance>()
const submitting = ref(false)
const serverErrors = reactive<{ current_password: string; new_password: string }>({
  current_password: '',
  new_password: '',
})
const form = reactive({
  currentPassword: '',
  newPassword: '',
  confirmPassword: '',
})

function clearServerError(field: 'current_password' | 'new_password'): void {
  serverErrors[field] = ''
}

const currentPasswordRule: FormItemRule[] = [
  { required: true, message: '请输入当前口令', trigger: 'blur' },
]
const newPasswordRule: FormItemRule[] = [
  {
    required: true,
    validator: (_rule, value: string, callback) => {
      callback(validatePassword(value ?? '') ?? undefined)
    },
    trigger: 'blur',
  },
]
const confirmPasswordRule: FormItemRule[] = [
  {
    required: true,
    validator: (_rule, value: string, callback) => {
      if ((value ?? '') === '') {
        callback(new Error('请再次输入新口令'))
      } else if (value !== form.newPassword) {
        callback(new Error('两次输入的新口令不一致'))
      } else {
        callback()
      }
    },
    trigger: 'blur',
  },
]

async function handleSubmit(): Promise<void> {
  serverErrors.current_password = ''
  serverErrors.new_password = ''
  const valid = await formRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    await auth.changePassword(form.currentPassword, form.newPassword)
    ElMessage.success('口令修改成功')
    if (forced.value) {
      // 强制改密完成：进入原目标页或首页
      const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : ''
      void router.replace(redirect.startsWith('/') ? redirect : { name: 'home' })
    } else {
      void router.replace({ name: 'home' })
    }
  } catch (error) {
    if (isApiError(error)) {
      // 400 INVALID_CURRENT_PASSWORD → 当前口令字段；422 PASSWORD_POLICY → 新口令字段
      const currentError = error.fieldError('current_password')
      const newError = error.fieldError('new_password')
      if (currentError) serverErrors.current_password = currentError
      if (newError) serverErrors.new_password = newError
      if (!currentError && !newError) {
        ElMessage.error(error.message)
      }
    } else {
      ElMessage.error('修改失败，请稍后重试')
    }
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="change-password-page">
    <el-card class="change-password-card">
      <h2 class="change-password-title">修改口令</h2>
      <el-alert
        v-if="forced"
        type="warning"
        :closable="false"
        show-icon
        title="首次登录须先修改初始口令，完成后才能访问其它页面"
        class="change-password-alert"
      />
      <el-form
        ref="formRef"
        :model="form"
        label-position="top"
        @submit.prevent="handleSubmit"
      >
        <el-form-item
          label="当前口令"
          prop="currentPassword"
          :rules="currentPasswordRule"
          :error="serverErrors.current_password || undefined"
        >
          <el-input
            v-model="form.currentPassword"
            type="password"
            autocomplete="current-password"
            show-password
            @input="clearServerError('current_password')"
          />
        </el-form-item>
        <el-form-item
          label="新口令"
          prop="newPassword"
          :rules="newPasswordRule"
          :error="serverErrors.new_password || undefined"
        >
          <el-input
            v-model="form.newPassword"
            type="password"
            autocomplete="new-password"
            show-password
            placeholder="至少 8 位且同时包含字母与数字"
            @input="clearServerError('new_password')"
          />
        </el-form-item>
        <el-form-item label="确认新口令" prop="confirmPassword" :rules="confirmPasswordRule">
          <el-input
            v-model="form.confirmPassword"
            type="password"
            autocomplete="new-password"
            show-password
            @keyup.enter="handleSubmit"
          />
        </el-form-item>
        <el-button
          type="primary"
          class="change-password-submit"
          :loading="submitting"
          native-type="submit"
        >
          确认修改
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.change-password-page {
  min-height: calc(100vh - 56px);
  display: flex;
  align-items: center;
  justify-content: center;
}
.change-password-card {
  width: 420px;
  padding: 8px 12px 4px;
}
.change-password-title {
  text-align: center;
  margin: 8px 0 20px;
  font-size: 18px;
}
.change-password-alert {
  margin-bottom: 16px;
}
.change-password-submit {
  width: 100%;
}
</style>
