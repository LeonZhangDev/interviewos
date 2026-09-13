import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import { AuthPage } from '../pages/AuthPage'
import type { AuthUser } from '../types'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      login: vi.fn(),
      register: vi.fn(),
    },
  }
})

// The tab buttons and the submit button share the same label ("登录" /
// "创建账号"), so the submit button is always addressed through its class.
const loginSubmit = () => screen.getByText('登录', { selector: 'button.auth-submit' })
const registerTab = () => screen.getByText('创建账号', { selector: '.auth-tabs button' })
const registerSubmit = () => screen.getByText('创建账号', { selector: 'button.auth-submit' })

const user: AuthUser = {
  id: 1,
  username: 'alice',
  email: 'alice@example.com',
  display_name: 'Alice Zhang',
  created_at: '2026-09-10T00:00:00Z',
}

beforeEach(() => {
  vi.mocked(api.login).mockReset()
  vi.mocked(api.register).mockReset()
})

describe('AuthPage', () => {
  it('disables the login submit until identity and password are long enough', async () => {
    render(<AuthPage onAuthenticated={vi.fn()} />)
    expect(loginSubmit()).toBeDisabled()

    await userEvent.type(screen.getByPlaceholderText('leon'), 'alice')
    expect(loginSubmit()).toBeDisabled()

    await userEvent.type(screen.getByPlaceholderText('至少 8 位'), 'password-123')
    expect(loginSubmit()).toBeEnabled()
  })

  it('switches to register mode with its own validation rules', async () => {
    render(<AuthPage onAuthenticated={vi.fn()} />)
    await userEvent.click(registerTab())

    expect(screen.getByPlaceholderText('you@example.com')).toBeInTheDocument()
    expect(registerSubmit()).toBeDisabled()

    await userEvent.type(screen.getByPlaceholderText('leon'), 'alice')
    await userEvent.type(screen.getByPlaceholderText('you@example.com'), 'a@b.io')
    await userEvent.type(screen.getByPlaceholderText('Leon Zhang'), 'Alice Zhang')
    expect(registerSubmit()).toBeDisabled()

    await userEvent.type(screen.getByPlaceholderText('至少 8 位'), 'password-123')
    expect(registerSubmit()).toBeEnabled()
  })

  it('logs in, stores tokens and hands the user to the app', async () => {
    vi.mocked(api.login).mockResolvedValue({
      access_token: 'access-1',
      refresh_token: 'refresh-1',
      user,
    })
    const onAuthenticated = vi.fn()
    render(<AuthPage onAuthenticated={onAuthenticated} />)

    await userEvent.type(screen.getByPlaceholderText('leon'), 'alice')
    await userEvent.type(screen.getByPlaceholderText('至少 8 位'), 'password-123')
    await userEvent.click(loginSubmit())

    await waitFor(() => expect(onAuthenticated).toHaveBeenCalledWith(user))
    expect(api.login).toHaveBeenCalledWith({ identity: 'alice', password: 'password-123' })
    expect(localStorage.getItem('interviewos_token')).toBe('access-1')
    expect(localStorage.getItem('interviewos_refresh')).toBe('refresh-1')
  })

  it('submits login from the password field Enter key', async () => {
    vi.mocked(api.login).mockResolvedValue({ access_token: 'a', refresh_token: 'r', user })
    render(<AuthPage onAuthenticated={vi.fn()} />)

    await userEvent.type(screen.getByPlaceholderText('leon'), 'alice')
    await userEvent.type(screen.getByPlaceholderText('至少 8 位'), 'password-123{Enter}')

    await waitFor(() => expect(api.login).toHaveBeenCalledTimes(1))
  })

  it('shows the backend error message on a failed login', async () => {
    vi.mocked(api.login).mockRejectedValue(new Error('用户名或密码错误'))
    render(<AuthPage onAuthenticated={vi.fn()} />)

    await userEvent.type(screen.getByPlaceholderText('leon'), 'alice')
    await userEvent.type(screen.getByPlaceholderText('至少 8 位'), 'password-123')
    await userEvent.click(loginSubmit())

    expect(await screen.findByText('用户名或密码错误')).toBeInTheDocument()
    expect(localStorage.getItem('interviewos_token')).toBeNull()
  })

  it('registers with the full payload', async () => {
    vi.mocked(api.register).mockResolvedValue({ access_token: 'a', refresh_token: 'r', user })
    const onAuthenticated = vi.fn()
    render(<AuthPage onAuthenticated={onAuthenticated} />)

    await userEvent.click(registerTab())
    await userEvent.type(screen.getByPlaceholderText('leon'), 'alice')
    await userEvent.type(screen.getByPlaceholderText('you@example.com'), 'alice@example.com')
    await userEvent.type(screen.getByPlaceholderText('Leon Zhang'), 'Alice Zhang')
    await userEvent.type(screen.getByPlaceholderText('至少 8 位'), 'password-123')
    await userEvent.click(registerSubmit())

    await waitFor(() => expect(onAuthenticated).toHaveBeenCalledWith(user))
    expect(api.register).toHaveBeenCalledWith({
      username: 'alice',
      email: 'alice@example.com',
      password: 'password-123',
      display_name: 'Alice Zhang',
    })
  })
})
