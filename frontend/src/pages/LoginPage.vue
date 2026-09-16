<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { login } from '../api/auth'
import type { AuthenticatedUser } from '../api/auth'
import { ApiError } from '../api/http'

/**
 * 登录页（F013 产品页）。
 *
 * - 调用 POST /api/auth/login（契约 §5.1，唯一豁免端点）；成功 → emit success
 *   携带 AuthenticatedUser，由 App 切入系统视图；
 * - username / password 仅做必填校验；不做长度 / 复杂度校验（R-AUTH-004 不属
 *   登录路径，契约 §8），也不 trim（契约 §5.1：原样精确匹配）；
 * - 三态互不相同（AC-06）：默认 / 提交 Loading（禁止重复提交）/ 失败提示
 *   （401 → 停留登录页 + 固定失败提示，按 error.code 分支，不解析 message）；
 * - 无 Empty 态（登录不是集合查询）；
 * - 会话 Cookie（csm_session，HttpOnly）由浏览器管理，本页不读不写任何令牌。
 */

const emit = defineEmits<{ success: [user: AuthenticatedUser] }>()

interface LoginForm {
  username: string
  password: string
}

const formRef = ref<FormInstance>()
const form = reactive<LoginForm>({ username: '', password: '' })
const submitting = ref(false)
const failure = ref<ApiError | null>(null)

/** 仅必填校验（契约 §5.1 / §8：长度与复杂度校验不在登录路径）。 */
const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入口令', trigger: 'blur' }],
}

/** 页面状态：三态互不相同（Loading 优先于失败提示）。 */
const state = computed<'default' | 'loading' | 'error'>(() => {
  if (submitting.value) return 'loading'
  if (failure.value !== null) return 'error'
  return 'default'
})

/**
 * 失败提示文案：按 error.code 分支（api-conventions.md §5），不解析 message。
 *
 * UNAUTHENTICATED → 固定失败提示：用户名不存在 / 口令错误 / 账号停用在服务端
 * 返回完全相同的 401（R-AUTH-006），前端不尝试区分，也不提示账号是否存在。
 */
const failureMessage = computed<string | null>(() => {
  switch (failure.value?.code) {
    case 'UNAUTHENTICATED':
      return '用户名或口令不正确，请重试。'
    case 'NETWORK_ERROR':
      return '无法连接服务器，请检查网络或服务状态后重试。'
    case undefined:
      return null
    default:
      return '登录失败，请稍后重试。'
  }
})

async function handleSubmit(): Promise<void> {
  // 提交中禁止重复提交（含校验进行中的窗口期，防止连点 / 连按回车发出多个请求）。
  if (submitting.value) return
  submitting.value = true
  failure.value = null
  try {
    const formInstance = formRef.value
    const valid =
      formInstance === undefined
        ? false
        : await formInstance.validate().then(
            () => true,
            () => false,
          )
    if (!valid) return

    const user = await login({ username: form.username, password: form.password })
    emit('success', user)
  } catch (err) {
    failure.value =
      err instanceof ApiError
        ? err
        : new ApiError({ status: 0, code: 'UNKNOWN_ERROR', message: '发生未知错误。' })
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="login-page" :data-state="state">
    <section class="login-page__card">
      <h1 class="login-page__title">CSM 登录</h1>

      <div
        v-if="failure !== null"
        class="login-page__failure"
        role="alert"
        :data-error-code="failure.code"
      >
        <el-alert type="error" :closable="false" show-icon :title="failureMessage ?? ''" />
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @submit.prevent="handleSubmit"
      >
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" autocomplete="username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="口令" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            autocomplete="current-password"
            placeholder="请输入口令"
          />
        </el-form-item>
        <el-button
          class="login-page__submit"
          type="primary"
          native-type="submit"
          :loading="submitting"
        >
          登录
        </el-button>
      </el-form>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 16px;
}

.login-page__card {
  width: 100%;
  max-width: 380px;
  padding: 32px 28px 36px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.login-page__title {
  margin: 0 0 20px;
  font-size: 20px;
  text-align: center;
}

.login-page__failure {
  margin-bottom: 16px;
}

.login-page__submit {
  width: 100%;
}
</style>
