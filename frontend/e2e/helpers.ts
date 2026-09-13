import type { Page } from '@playwright/test'
import { expect } from '@playwright/test'

export const PASSWORD = 'e2e-password-12345'

export function randomUsername(prefix: string): string {
  const suffix = Math.random().toString(36).slice(2, 10)
  return `${prefix}_${suffix}`
}

/** Registers a fresh random user through the real auth UI and waits for the workbench. */
export async function registerThroughUi(page: Page, username: string): Promise<void> {
  await page.goto('/')
  await page.locator('.auth-tabs button', { hasText: '创建账号' }).click()
  await page.getByPlaceholder('leon', { exact: true }).fill(username)
  await page.getByPlaceholder('you@example.com').fill(`${username}@e2e.test`)
  await page.getByPlaceholder('Leon Zhang').fill(username)
  await page.getByPlaceholder('至少 8 位').fill(PASSWORD)
  await page.locator('button.auth-submit').click()

  await expect(page.locator('.top-user small', { hasText: `@${username}` })).toBeVisible()
}

/** Logs in through the real auth UI. */
export async function loginThroughUi(page: Page, username: string): Promise<void> {
  await page.goto('/')
  await page.getByPlaceholder('leon', { exact: true }).fill(username)
  await page.getByPlaceholder('至少 8 位').fill(PASSWORD)
  await page.locator('button.auth-submit').click()

  await expect(page.locator('.top-user small', { hasText: `@${username}` })).toBeVisible()
}

export async function logoutThroughUi(page: Page): Promise<void> {
  await page.getByRole('button', { name: '退出登录' }).click()
  await expect(page.locator('.auth-shell')).toBeVisible()
}
