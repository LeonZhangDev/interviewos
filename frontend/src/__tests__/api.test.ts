import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, authToken, refreshAuthToken, setAuthToken, setAuthTokens } from '../api'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('token storage', () => {
  it('stores and removes both tokens', () => {
    setAuthTokens('access-1', 'refresh-1')
    expect(authToken()).toBe('access-1')
    expect(refreshAuthToken()).toBe('refresh-1')

    setAuthTokens('', '')
    expect(authToken()).toBe('')
    expect(refreshAuthToken()).toBe('')
  })

  it('setAuthToken keeps the stored refresh token', () => {
    setAuthTokens('old-access', 'keep-refresh')
    setAuthToken('new-access')
    expect(authToken()).toBe('new-access')
    expect(refreshAuthToken()).toBe('keep-refresh')
  })
})

describe('json() auth behaviour', () => {
  it('attaches the Authorization header when a token is stored', async () => {
    setAuthTokens('access-1', 'refresh-1')
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { username: 'alice' }))
    vi.stubGlobal('fetch', fetchMock)

    await api.me()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/auth/me')
    expect(init.headers.get('Authorization')).toBe('Bearer access-1')
  })

  it('refreshes once after a 401 and retries with the new token', async () => {
    setAuthTokens('expired', 'refresh-1')
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'token expired' }))
      .mockResolvedValueOnce(jsonResponse(200, { access_token: 'new-access', refresh_token: 'new-refresh' }))
      .mockResolvedValueOnce(jsonResponse(200, { id: 1, username: 'alice' }))
    vi.stubGlobal('fetch', fetchMock)

    // /api/auth/* endpoints never refresh, so exercise the flow via /api/dashboard
    const user = await api.dashboard()

    expect(user).toEqual({ id: 1, username: 'alice' })
    expect(authToken()).toBe('new-access')
    expect(refreshAuthToken()).toBe('new-refresh')
    expect(fetchMock).toHaveBeenCalledTimes(3)

    const [refreshUrl, refreshInit] = fetchMock.mock.calls[1]
    expect(refreshUrl).toBe('/api/auth/refresh')
    expect(refreshInit.method).toBe('POST')
    expect(JSON.parse(refreshInit.body)).toEqual({ refresh_token: 'refresh-1' })

    const retryInit = fetchMock.mock.calls[2][1]
    expect(retryInit.headers.get('Authorization')).toBe('Bearer new-access')
  })

  it('concurrent 401s share a single refresh call (single-flight)', async () => {
    setAuthTokens('expired', 'refresh-1')
    let dashboardCalls = 0
    const fetchMock = vi.fn(async (url: string) => {
      if (url === '/api/auth/refresh') {
        return jsonResponse(200, { access_token: 'new-access', refresh_token: 'new-refresh' })
      }
      dashboardCalls += 1
      return dashboardCalls <= 2
        ? jsonResponse(401, { detail: 'token expired' })
        : jsonResponse(200, { id: 1, username: 'alice' })
    })
    vi.stubGlobal('fetch', fetchMock)

    const [first, second] = await Promise.all([api.dashboard(), api.dashboard()])

    expect(first).toEqual({ id: 1, username: 'alice' })
    expect(second).toEqual({ id: 1, username: 'alice' })
    // 2 failed dashboard calls + 1 shared refresh + 2 retried dashboard calls
    expect(fetchMock).toHaveBeenCalledTimes(5)
    expect(fetchMock.mock.calls.filter(([url]) => url === '/api/auth/refresh')).toHaveLength(1)
  })

  it('fires interviewos:unauthorized and clears tokens when refresh fails', async () => {
    setAuthTokens('expired', 'refresh-1')
    const listener = vi.fn()
    window.addEventListener('interviewos:unauthorized', listener)
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'token expired' }))
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'refresh revoked' }))
    vi.stubGlobal('fetch', fetchMock)

    // the surfaced error is the original 401 body, not the refresh response
    await expect(api.dashboard()).rejects.toThrow('token expired')
    expect(listener).toHaveBeenCalledTimes(1)
    expect(authToken()).toBe('')
    expect(refreshAuthToken()).toBe('')
    window.removeEventListener('interviewos:unauthorized', listener)
  })

  it('skips the refresh call entirely when no refresh token is stored', async () => {
    setAuthTokens('expired', '')
    const listener = vi.fn()
    window.addEventListener('interviewos:unauthorized', listener)
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(401, { detail: 'token expired' }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.dashboard()).rejects.toThrow('token expired')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(listener).toHaveBeenCalledTimes(1)
    window.removeEventListener('interviewos:unauthorized', listener)
  })

  it('never refreshes on auth endpoints (bad login does not clear the session)', async () => {
    setAuthTokens('access-1', 'refresh-1')
    const listener = vi.fn()
    window.addEventListener('interviewos:unauthorized', listener)
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(401, { detail: '用户名或密码错误' }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.login({ identity: 'alice', password: 'wrong-password' })).rejects.toThrow('用户名或密码错误')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(listener).not.toHaveBeenCalled()
    expect(authToken()).toBe('access-1')
    window.removeEventListener('interviewos:unauthorized', listener)
  })

  it('propagates non-401 error bodies', async () => {
    setAuthTokens('access-1', 'refresh-1')
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(422, { detail: 'validation error' }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.questions()).rejects.toThrow('validation error')
  })
})
