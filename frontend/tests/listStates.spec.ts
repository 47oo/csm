import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { h } from 'vue'
import ElementPlus from 'element-plus'
import ListStates from '../src/components/ListStates.vue'
import { ApiError } from '../src/api/http'

/**
 * 列表三态基座测试：Loading / Error / Empty / 内容互斥渲染，
 * 且 Empty（200 + items 为空）与 Not Found（404）是不同状态。
 */

function mountListStates(props: {
  loading: boolean
  error: ApiError | null
  empty: boolean
  emptyDescription?: string
}) {
  return mount(ListStates, {
    props,
    slots: { default: () => h('div', { class: 'slot-content' }, '列表内容') },
    global: { plugins: [ElementPlus] },
  })
}

describe('ListStates 三态互斥', () => {
  it('loading=true → 骨架屏；不渲染 Empty、Error、内容', () => {
    const wrapper = mountListStates({ loading: true, error: null, empty: false })

    expect(wrapper.attributes('data-state')).toBe('loading')
    expect(wrapper.find('.el-skeleton').exists()).toBe(true)
    expect(wrapper.find('.el-empty').exists()).toBe(false)
    expect(wrapper.find('.slot-content').exists()).toBe(false)
  })

  it('error 非 null → Error 态（按 error.code 渲染）', () => {
    const wrapper = mountListStates({
      loading: false,
      error: new ApiError({ status: 500, code: 'INTERNAL_ERROR', message: '内部错误' }),
      empty: false,
    })

    expect(wrapper.attributes('data-state')).toBe('error')
    expect(wrapper.text()).toContain('服务器内部错误')
    expect(wrapper.find('.slot-content').exists()).toBe(false)
  })

  it('Empty：请求成功且列表为空 → el-empty +「暂无数据」', () => {
    const wrapper = mountListStates({ loading: false, error: null, empty: true })

    expect(wrapper.attributes('data-state')).toBe('empty')
    expect(wrapper.find('.el-empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('暂无数据')
  })

  it('Empty 支持自定义文案', () => {
    const wrapper = mountListStates({
      loading: false,
      error: null,
      empty: true,
      emptyDescription: '暂无数据（Empty 态：接口返回 200，items 为空数组）',
    })
    expect(wrapper.text()).toContain('接口返回 200')
  })

  it('Not Found 与 Empty 是不同状态：error 优先，渲染「未找到资源」而非「暂无数据」', () => {
    const wrapper = mountListStates({
      loading: false,
      error: new ApiError({ status: 404, code: 'NOT_FOUND', message: '资源不存在' }),
      // 即使调用方误传 empty=true，Error 优先，不得回落到 Empty 态。
      empty: true,
    })

    expect(wrapper.attributes('data-state')).toBe('error')
    expect(wrapper.text()).toContain('未找到资源')
    expect(wrapper.text()).not.toContain('暂无数据')
    expect(wrapper.find('.el-empty').exists()).toBe(false)
  })

  it('非上述情况 → 渲染默认插槽内容', () => {
    const wrapper = mountListStates({ loading: false, error: null, empty: false })

    expect(wrapper.attributes('data-state')).toBe('content')
    expect(wrapper.find('.slot-content').exists()).toBe(true)
    expect(wrapper.text()).toContain('列表内容')
  })
})
