import { test, expect } from '@playwright/test'

test('trigger a test suggestion and accept it from Human Review', async ({ page }) => {
  const repoName = `e2e-suggest-${Date.now()}`

  await page.goto('/repositories')
  await page.getByLabel('Name').fill(repoName)
  await page.getByLabel('URL').fill(`https://github.com/x/${repoName}`)
  await page.getByRole('button', { name: 'Register Repository' }).click()

  const repoRow = page.getByRole('row').filter({ hasText: repoName })
  await repoRow.getByRole('link', { name: 'Open' }).click()
  await page.getByRole('link', { name: 'Test Suggestions' }).click()
  await expect(page.getByRole('heading', { name: 'Test Suggestions' })).toBeVisible()

  await page.getByLabel('Source Code').fill('def add(a, b):\n    return a + b\n')
  await page.getByRole('button', { name: 'Run Test Intelligence' }).click()

  await expect(page.getByText('completed')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByRole('button', { name: 'Accept' })).toBeVisible()

  // The same pending suggestion must show up in the cross-repo review queue.
  await page.getByRole('link', { name: 'Human Review' }).click()
  await expect(page.getByRole('heading', { name: 'Human Review' })).toBeVisible()
  const reviewRow = page.getByText(repoName)
  await expect(reviewRow).toBeVisible({ timeout: 10_000 })

  await page
    .locator('li')
    .filter({ hasText: repoName })
    .getByRole('button', { name: 'Accept' })
    .click()

  // Once accepted, it should drop out of the pending review queue.
  await expect(page.getByText(repoName)).toHaveCount(0, { timeout: 10_000 })
})
