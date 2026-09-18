import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { h } from 'vue'
import ElementPlus from 'element-plus'
import ErrorState from '../src/components/ErrorState.vue'
import { ApiError } from '../src/api/http'

/**
 * Error 态渲染测试：分支只由 error.code 驱动（api-conventions.md §5），
 * error.message 仅展示、不参与分支判断。
 */

function mountErrorState(error: ApiError) {
  return mount(ErrorState, {
    props: { error },
    global: { plugins: [ElementPlus] },
  })
}

describe('ErrorState 按 error.code 分支渲染', () => {
  it('INTERNAL_ERROR → 服务器内部错误（服务端未预期错误驱动的 Error 态）', () => {
    const wrapper = mountErrorState(
      new ApiError({ status: 500, code: 'INTERNAL_ERROR', message: '内部错误' }),
    )
    expect(wrapper.text()).toContain('服务器内部错误')
    expect(wrapper.attributes('data-error-code')).toBe('INTERNAL_ERROR')
    expect(wrapper.text()).toContain('HTTP 500')
  })

  it('message 文案变化不影响分支：code 是唯一分支依据', () => {
    const a = mountErrorState(
      new ApiError({ status: 500, code: 'INTERNAL_ERROR', message: '消息甲' }),
    )
    const b = mountErrorState(
      new ApiError({ status: 500, code: 'INTERNAL_ERROR', message: '完全不同的消息乙' }),
    )
    expect(a.text()).toContain('服务器内部错误')
    expect(b.text()).toContain('服务器内部错误')
  })

  it('NOT_FOUND → 渲染「未找到资源」，绝不渲染列表 Empty 文案「暂无数据」', () => {
    const wrapper = mountErrorState(
      new ApiError({ status: 404, code: 'NOT_FOUND', message: '资源不存在' }),
    )
    expect(wrapper.text()).toContain('未找到资源')
    expect(wrapper.text()).not.toContain('暂无数据')
  })

  it('FORBIDDEN 预留分支可渲染（F012 不触发，供 F013 使用）', () => {
    const wrapper = mountErrorState(
      new ApiError({ status: 403, code: 'FORBIDDEN', message: '' }),
    )
    expect(wrapper.text()).toContain('没有访问权限')
  })

  it('NETWORK_ERROR（前端本地码，后端未启动时出现）→ 无法连接服务器', () => {
    const wrapper = mountErrorState(
      new ApiError({ status: 0, code: 'NETWORK_ERROR', message: '无法连接服务器' }),
    )
    expect(wrapper.text()).toContain('无法连接服务器')
    expect(wrapper.text()).toContain('无 HTTP 响应')
  })

  it('VALIDATION_ERROR → 渲染 details 的字段与原因（AC-06）', () => {
    const wrapper = mountErrorState(
      new ApiError({
        status: 400,
        code: 'VALIDATION_ERROR',
        message: '请求校验失败',
        details: [{ field: 'name', message: 'name 不能为空' }],
      }),
    )
    expect(wrapper.text()).toContain('请求校验失败')
    expect(wrapper.text()).toContain('name')
    expect(wrapper.text()).toContain('name 不能为空')
  })

  it('未知 code → 兜底分支，并展示原始 code（不改写、不丢失）', () => {
    const wrapper = mountErrorState(
      new ApiError({ status: 418, code: 'SOME_FUTURE_CODE', message: '' }),
    )
    expect(wrapper.text()).toContain('请求失败')
    expect(wrapper.text()).toContain('SOME_FUTURE_CODE')
  })
})
