import { expect, test, type Browser } from '@playwright/test'
import { randomUsername, registerThroughUi } from './helpers'

test('public portfolio switches from legacy to CMS after publishing', async ({ page, browser }) => {
  const username = randomUsername('e2e_pf')
  const displayName = `E2E CMS ${username}`
  const headline = 'E2E Headline Engineer'

  await registerThroughUi(page, username)

  const anon = await (browser as Browser).newContext()
  const anonPage = await anon.newPage()
  try {
    // unpublished → anonymous visitors see the legacy static shape
    await anonPage.goto(`/portfolio/${username}`)
    await expect(anonPage.getByText('AI 工程师作品集')).toBeVisible()
    await expect(anonPage.getByRole('heading', { name: 'AI / Agent Engineer' })).toBeVisible()
    await expect(anonPage.getByText('作品集', { exact: true })).toHaveCount(0)

    // edit and publish through the CMS UI
    await page.locator('.nav-item', { hasText: '作品集管理' }).click()
    await expect(page.getByRole('heading', { name: '作品集编辑器' })).toBeVisible()

    await page.getByLabel('显示名称').fill(displayName)
    await page.getByLabel('头衔 / Headline').fill(headline)
    await page.getByLabel('技能标签（逗号分隔，最多 30 个）').fill('Playwright, E2E')
    await page.getByRole('button', { name: '保存资料' }).click()
    await expect(page.getByText('已保存 — 公开页仍为默认内容，点击右上角“发布”生效。')).toBeVisible()

    await page.getByRole('button', { name: '未发布 · 点击发布' }).click()
    await expect(page.getByRole('button', { name: '已发布 · 点击下线' })).toBeVisible()

    // published → anonymous visitors see the CMS content
    await anonPage.goto(`/portfolio/${username}`)
    await expect(anonPage.getByText('作品集', { exact: true })).toBeVisible()
    await expect(anonPage.getByRole('heading', { name: displayName, level: 1 })).toBeVisible()
    await expect(anonPage.getByRole('heading', { name: headline, level: 2 })).toBeVisible()
    await expect(anonPage.getByText('Playwright', { exact: true })).toBeVisible()
  } finally {
    await anon.close()
  }
})
