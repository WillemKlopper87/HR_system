// hcm/frontend/e2e/establishment.spec.ts
import { expect, test } from '@playwright/test'
import { expectHeading, login, settled } from './helpers'

test.describe('Position / establishment management (C1)', () => {
  test('propose -> comp_manager approves -> accounting_officer approves -> recruiter sees it in the requisition picker', async ({ page }) => {
    // Timestamp-suffixed (not a static literal): the Django backend persists
    // across every test and retry within one `npx playwright test`
    // invocation (retries: CI ? 1 : 0), so a static title risks a duplicate
    // row surviving a retry after a genuine prior failure -- which then
    // makes the hasText/getByText locators below match 2 elements (a
    // strict-mode violation that masks the real failure). Same fix as
    // talent.spec.ts's positionTitle.
    const positionTitle = `E2E Test Post ${Date.now().toString().slice(-5)}`
    await login(page, 'hradmin')
    await page.goto('/positions')
    await expectHeading(page, 'Positions')
    await settled(page)

    await page.getByRole('button', { name: '+ Propose position' }).click()
    await page.getByLabel('Title').fill(positionTitle)
    await page.getByLabel('Department').selectOption({ index: 1 })
    await page.getByLabel('Occupational level').selectOption({ index: 1 })
    await page.getByLabel('Location').selectOption({ index: 1 })
    await page.getByRole('button', { name: 'Propose position' }).click()
    await settled(page)

    const row = page.locator('tr', { hasText: positionTitle })
    await expect(row).toBeVisible()
    await row.getByRole('button', { name: 'Submit' }).click()
    await settled(page)
    await expect(row).toContainText('In review')

    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)
    await login(page, 'compmanager')
    await page.goto('/positions')
    await settled(page)
    const compRow = page.locator('tr', { hasText: positionTitle })
    await compRow.getByRole('button', { name: 'Approve' }).click()
    await settled(page)
    await expect(compRow).toContainText('In review')

    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)
    await login(page, 'accountingofficer')
    await page.goto('/positions')
    await settled(page)
    const aoRow = page.locator('tr', { hasText: positionTitle })
    await aoRow.getByRole('button', { name: 'Approve' }).click()
    await settled(page)
    await expect(aoRow).toContainText('Approved')
    await expect(aoRow).toContainText('Vacant')

    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)
    await login(page, 'recruiter')
    await page.goto('/requisitions')
    await expectHeading(page, 'Requisitions')
    await settled(page)
    await page.getByRole('button', { name: '+ New requisition' }).click()
    // the picker is filtered to the form's currently-selected department/
    // level (empty until chosen) -- select the SAME ones used to propose
    // the position above (also index 1) before its post_number can appear.
    await page.getByLabel('Department').selectOption({ index: 1 })
    await page.getByLabel('Occupational level').selectOption({ index: 1 })
    await expect(page.getByText(positionTitle, { exact: false })).toBeVisible()
  })

  test('a plain employee cannot reach the Positions page', async ({ page }) => {
    await login(page, 'employee')
    await page.goto('/positions')
    await page.waitForURL(/\/employees$/)
  })
})
