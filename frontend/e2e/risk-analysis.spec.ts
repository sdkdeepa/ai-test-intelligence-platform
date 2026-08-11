import { test, expect } from '@playwright/test'

const SAMPLE_DIFF = `diff --git a/app/auth/login.py b/app/auth/login.py
index 1111111..2222222 100644
--- a/app/auth/login.py
+++ b/app/auth/login.py
@@ -10,8 +10,8 @@ def handle_login(username, password):
     user = find_user(username)
     if user is None:
         raise ValueError("unknown user")
-    if not check_password(user, password):
+    if not authenticate(user, password):
         raise ValueError("invalid credentials")
`

test('register a repository, trigger risk analysis, and see the finding', async ({ page }) => {
  const repoName = `e2e-risk-${Date.now()}`

  await page.goto('/repositories')
  await expect(page.getByRole('heading', { name: 'Repository Overview' })).toBeVisible()

  await page.getByLabel('Name').fill(repoName)
  await page.getByLabel('URL').fill(`https://github.com/x/${repoName}`)
  await page.getByRole('button', { name: 'Register Repository' }).click()

  const repoRow = page.getByRole('row').filter({ hasText: repoName })
  await expect(repoRow).toBeVisible()
  await repoRow.getByRole('link', { name: 'Open' }).click()

  await expect(page).toHaveURL(/\/repositories\/.+\/risk/)
  await expect(page.getByRole('heading', { name: 'Risk Analysis', exact: true })).toBeVisible()

  await page.getByLabel(/diff/i).fill(SAMPLE_DIFF)
  await page.getByRole('button', { name: 'Run Risk Analysis' }).click()

  // Poll surfaces the run's state inline; wait for the terminal state.
  await expect(page.getByText('completed')).toBeVisible({ timeout: 15_000 })

  // The finding itself should now be listed with its release recommendation.
  await expect(page.getByText('app/auth/login.py', { exact: true })).toBeVisible()
  await expect(page.getByText(/^Risk score: /i)).toBeVisible()
})
