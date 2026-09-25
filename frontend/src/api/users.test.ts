import { afterEach, describe, expect, it } from 'vitest'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { client } from './client'
import {
  createUser,
  deleteUser,
  disableUser,
  enableUser,
  getUser,
  listUsers,
  resetPassword,
  updateUser,
} from './users'
import type { PagedUsers, UserDetail } from './types'

const originalAdapter = client.defaults.adapter

interface CapturedRequest {
  method?: string
  url?: string
  params?: Record<string, unknown>
  data?: unknown
}

/** 捕获请求并返回固定响应 */
function captureRequests(respond: (config: InternalAxiosRequestConfig) => unknown): CapturedRequest[] {
  const captured: CapturedRequest[] = []
  client.defaults.adapter = async (config: InternalAxiosRequestConfig): Promise<AxiosResponse> => {
    captured.push({
      method: config.method,
      url: config.url,
      params: config.params as Record<string, unknown> | undefined,
      data: config.data,
    })
    return {
      status: 200,
      statusText: 'test',
      data: respond(config),
      headers: {},
      config,
    }
  }
  return captured
}

afterEach(() => {
  client.defaults.adapter = originalAdapter
})

const paged: PagedUsers = { items: [], total: 0, page: 1, page_size: 20 }
const detail: UserDetail = {
  id: 7,
  username: 'alice',
  role: 'maintainer',
  status: 'enabled',
  must_change_password: false,
  created_at: '2026-09-25T00:00:00Z',
  updated_at: '2026-09-25T00:00:00Z',
  version: 3,
}

describe('listUsers（Contract §3.1：page/page_size/q/role/status/sort）', () => {
  it('传递全部查询参数，q 去首尾空格，空过滤项不发送', async () => {
    const captured = captureRequests(() => paged)
    await listUsers({ page: 2, page_size: 50, q: '  ali  ', role: 'admin', status: 'disabled', sort: '-created_at' })
    expect(captured).toHaveLength(1)
    expect(captured[0].method).toBe('get')
    expect(captured[0].url).toBe('/users')
    expect(captured[0].params).toEqual({
      page: '2',
      page_size: '50',
      q: 'ali',
      role: 'admin',
      status: 'disabled',
      sort: '-created_at',
    })
  })

  it('空字符串过滤项与空白 q 不作为参数发送', async () => {
    const captured = captureRequests(() => paged)
    await listUsers({ q: '   ', role: undefined, status: undefined })
    expect(captured[0].params).toEqual({})
  })
})

describe('用户管理端点路径与方法（Contract §3.2–3.8）', () => {
  it('createUser：POST /users，body 含 username/password/role', async () => {
    const captured = captureRequests(() => detail)
    await createUser({ username: 'alice', password: 'Passw0rd', role: 'maintainer' })
    expect(captured[0].method).toBe('post')
    expect(captured[0].url).toBe('/users')
    expect(JSON.parse(captured[0].data as string)).toEqual({
      username: 'alice',
      password: 'Passw0rd',
      role: 'maintainer',
    })
  })

  it('getUser：GET /users/{id}', async () => {
    const captured = captureRequests(() => detail)
    await getUser(7)
    expect(captured[0].method).toBe('get')
    expect(captured[0].url).toBe('/users/7')
  })

  it('updateUser：PATCH /users/{id}，body 为 {role, version}（用户名不可改）', async () => {
    const captured = captureRequests(() => detail)
    await updateUser(7, { role: 'admin', version: 3 })
    expect(captured[0].method).toBe('patch')
    expect(captured[0].url).toBe('/users/7')
    const body = JSON.parse(captured[0].data as string)
    expect(body).toEqual({ role: 'admin', version: 3 })
    expect('username' in body).toBe(false)
  })

  it('deleteUser：DELETE /users/{id}?version=', async () => {
    const captured = captureRequests(() => null)
    await deleteUser(7, 3)
    expect(captured[0].method).toBe('delete')
    expect(captured[0].url).toBe('/users/7')
    expect(captured[0].params).toEqual({ version: 3 })
  })

  it('disableUser / enableUser：POST /users/{id}/disable 与 /enable', async () => {
    const captured = captureRequests(() => null)
    await disableUser(7)
    await enableUser(7)
    expect(captured[0].method).toBe('post')
    expect(captured[0].url).toBe('/users/7/disable')
    expect(captured[1].method).toBe('post')
    expect(captured[1].url).toBe('/users/7/enable')
  })

  it('resetPassword：POST /users/{id}/reset-password，body 为 {new_password}', async () => {
    const captured = captureRequests(() => null)
    await resetPassword(7, { new_password: 'NewPass1' })
    expect(captured[0].method).toBe('post')
    expect(captured[0].url).toBe('/users/7/reset-password')
    expect(JSON.parse(captured[0].data as string)).toEqual({ new_password: 'NewPass1' })
  })
})
