// hcm/frontend/e2e/establishment.spec.ts
import { expect, test } from '@playwright/test'
import { expectHeading, login, settled } from './helpers'

test.describe('Position / establishment management (C1)', () => {
  test('propose -> comp_manager approves -> accounting_officer approves -> recruiter sees it in the requisition picker', async ({ page }) => {
    await login(page, 'hradmin')
    await page.goto('/positions')
    await expectHeading(page, 'Positions')
    await settled(page)

    await page.getByRole('button', { name: '+ Propose position' }).click()
    await page.getByLabel('Title').fill('E2E Test Post')
    await page.getByLabel('Department').selectOption({ index: 1 })
    await page.getByLabel('Occupational level').selectOption({ index: 1 })
    await page.getByLabel('Location').selectOption({ index: 1 })
    await page.getByRole('button', { name: 'Propose position' }).click()
    await settled(page)

    const row = page.locator('tr', { hasText: 'E2E Test Post' })
    await expect(row).toBeVisible()
    await row.getByRole('button', { name: 'Submit' }).click()
    await settled(page)
    await expect(row).toContainText('In review')

    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)
    await login(page, 'compmanager')
    await page.goto('/positions')
    await settled(page)
    const compRow = page.locator('tr', { hasText: 'E2E Test Post' })
    await compRow.getByRole('button', { name: 'Approve' }).click()
    await settled(page)
    await expect(compRow).toContainText('In review')

    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)
    await login(page, 'accountingofficer')
    await page.goto('/positions')
    await settled(page)
    const aoRow = page.locator('tr', { hasText: 'E2E Test Post' })
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
    await expect(page.getByText('E2E Test Post', { exact: false })).toBeVisible()
  })

  test('a plain employee cannot reach the Positions page', async ({ page }) => {
    await login(page, 'employee')
    await page.goto('/positions')
    await page.waitForURL(/\/employees$/)
  })
})
