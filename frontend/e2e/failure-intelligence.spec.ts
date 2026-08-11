import { test, expect } from '@playwright/test'

test('analyze a failure and see its classification plus run history', async ({ page }) => {
  const repoName = `e2e-failure-${Date.now()}`

  await page.goto('/repositories')
  await page.getByLabel('Name').fill(repoName)
  await page.getByLabel('URL').fill(`https://github.com/x/${repoName}`)
  await page.getByRole('button', { name: 'Register Repository' }).click()

  const repoRow = page.getByRole('row').filter({ hasText: repoName })
  await repoRow.getByRole('link', { name: 'Open' }).click()
  await page.getByRole('link', { name: 'Failure Intelligence' }).click()
  await expect(page.getByRole('heading', { name: 'Failure Intelligence' })).toBeVisible()

  await page
    .getByLabel('PyTest Output')
    .fill('FAILED tests/test_math.py::test_add - AssertionError: assert 5 == 4\n')
  await page.getByRole('button', { name: 'Analyze Failure' }).click()

  await expect(page.getByText('completed')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText('regression', { exact: true })).toBeVisible()
  await expect(page.getByText(/factual evidence/i)).toBeVisible()
  await expect(page.getByText(/ai-generated root cause hypotheses/i)).toBeVisible()

  // The run should also now appear in the run history with provider/model detail.
  await page.getByRole('link', { name: 'Run History' }).click()
  await expect(page.getByRole('heading', { name: 'Analysis Run History' })).toBeVisible()
  await expect(page.getByText('failure_intelligence')).toBeVisible()

  await page.getByRole('button', { name: 'Show invocations' }).first().click()
  await expect(page.getByRole('cell', { name: 'mock', exact: true })).toBeVisible()
  await expect(page.getByText(/ms$/)).toBeVisible()
})
