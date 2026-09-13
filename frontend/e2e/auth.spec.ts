import { expect, test } from '@playwright/test'
import { loginThroughUi, logoutThroughUi, randomUsername, registerThroughUi } from './helpers'

test('registering shows the authenticated workbench', async ({ page }) => {
  const username = randomUsername('e2e_auth')

  await registerThroughUi(page, username)

  await expect(page.getByRole('heading', { name: '把学习、代码、项目和面试连成一条线。' })).toBeVisible()
  await expect(page.locator('.sidebar')).toBeVisible()
})

test('logout blocks the workbench until the user logs in again', async ({ page }) => {
  const username = randomUsername('e2e_guard')

  await registerThroughUi(page, username)
  await expect(page.locator('.top-user small', { hasText: `@${username}` })).toBeVisible()

  await logoutThroughUi(page)
  await expect(page.locator('.auth-shell')).toBeVisible()

  // a fresh load without a token must not reach the workbench
  await page.goto('/')
  await expect(page.locator('.auth-shell')).toBeVisible()
  await expect(page.locator('.sidebar')).toHaveCount(0)

  // logging back in restores the workbench
  await loginThroughUi(page, username)
  await expect(page.locator('.top-user small', { hasText: `@${username}` })).toBeVisible()
  await expect(page.getByRole('heading', { name: '把学习、代码、项目和面试连成一条线。' })).toBeVisible()
})
