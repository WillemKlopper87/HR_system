import { expect, test } from '@playwright/test'
import { expectHeading, login, settled } from './helpers'

test.describe('employee self-service (Sprint 15)', () => {
  test('employee: edit own contact details, see benefits and learning', async ({ page }) => {
    await login(page, 'employee')
    await page.goto('/my-profile')
    await expectHeading(page, 'My Profile')
    await settled(page)
    await expect(page.getByRole('heading', { name: 'Employment details' })).toBeVisible()
    const phone = `082${Date.now().toString().slice(-7)}`
    await page.getByLabel('Phone').fill(phone)
    await page.getByRole('button', { name: 'Save contact details' }).click()
    await expect(page.getByText('Saved.')).toBeVisible()
    await page.reload()
    await settled(page)
    await expect(page.getByLabel('Phone')).toHaveValue(phone)

    await page.goto('/my-benefits')
    await expectHeading(page, 'My Benefits')
    await settled(page)
    await expect(page.locator('table thead')).toContainText('My status')

    await page.goto('/my-learning')
    await expectHeading(page, 'My Learning')
    await settled(page)
    await expect(page.locator('table thead')).toContainText('Provider')
  })
})

test.describe('policy library (ADR-008)', () => {
  test('employee acknowledges a policy; hr_admin sees library + compliance %', async ({ page }) => {
    await login(page, 'employee')
    await page.goto('/my-policies')
    await expectHeading(page, 'My Policies')
    await settled(page)
    const pending = page.locator('table tbody tr', { hasText: 'Not yet' })
    const pendingBefore = await pending.count()
    expect(pendingBefore).toBeGreaterThan(0)
    await pending.first().getByRole('button', { name: 'Acknowledge' }).click()
    await expect(page.locator('table tbody tr', { hasText: 'Not yet' })).toHaveCount(pendingBefore - 1)
    // library + dashboard are hr_admin-only
    await page.goto('/policies')
    await page.waitForURL(/\/employees$/)
    await page.getByRole('button', { name: 'Sign out' }).click()
    await page.waitForURL(/\/login$/)

    await login(page, 'hradmin')
    await page.goto('/policies')
    await expectHeading(page, 'Policy Library')
    await settled(page)
    await expect(page.locator('table thead')).toContainText('Passages')
    await expect(page.locator('table tbody tr').first()).toBeVisible()
    await page.goto('/dashboards/policy-acknowledgment')
    await expectHeading(page, 'Policy Acknowledgment Compliance')
    await settled(page)
    await expect(page.locator('table thead')).toContainText('Completion')
  })
})
